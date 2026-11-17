/*
 * Fits, navigates and presents a deck.
 * - Fit: the 1440 × 810 stage is only scaled, never relaid out (sized from `visualViewport`).
 * - Input: arrows, space, page keys; tap the left quarter to go back, elsewhere forward; swipe.
 * - URL: `#/<slide>/<step>`; unknown positions fall back to the first step.
 * - `?slow=N` slows every duration; `?view=presenter` shows the presenter view.
 * - Windows of the same deck follow each other through a BroadcastChannel.
 */
import { useMountEffect } from "./use-mount-effect.ts";
import { MotionConfig } from "motion/react";
import { useRef, useState, useSyncExternalStore, type MouseEvent, type PointerEvent } from "react";
import { choreograph } from "./choreography.ts";
import {
  formatPosition,
  describeDeckError,
  parseDeck,
  placeIndex,
  placeLabel,
  places,
  type DeckDefinition,
  type DeckError,
  type Place,
} from "./deck.ts";
import { PresenterView } from "./presenter-view.tsx";
import { defaultTiming, slowdown, TimingProvider } from "./timing.ts";
import { stage } from "./values.ts";
import { World } from "./world.tsx";

const subscribeHash = (onChange: () => void) => {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
};
const readHash = () => window.location.hash;

const subscribeViewport = (onChange: () => void) => {
  const viewport = window.visualViewport;
  viewport?.addEventListener("resize", onChange);
  window.addEventListener("resize", onChange);
  return () => {
    viewport?.removeEventListener("resize", onChange);
    window.removeEventListener("resize", onChange);
  };
};
const readFit = () => {
  const width = window.visualViewport?.width ?? window.innerWidth;
  const height = window.visualViewport?.height ?? window.innerHeight;
  return Math.min(width / stage.width, height / stage.height);
};

const search = () => new URLSearchParams(window.location.search);

/** Plays `definition`; an invalid deck shows its first authoring error instead. */
export function Player({ deck: definition }: { readonly deck: DeckDefinition }) {
  const [parsed] = useState(() => parseDeck(definition));
  if (parsed._tag === "Err") return <DeckErrorScreen error={parsed.error} />;
  return <Playing all={places(parsed.value)} title={parsed.value.title} />;
}

function Playing({ all, title }: { readonly all: ReadonlyArray<Place>; readonly title: string }) {
  const [timing] = useState(() => slowdown(defaultTiming, Number(search().get("slow") ?? 1) || 1));
  const [presenter] = useState(() => search().get("view") === "presenter");
  const index = placeIndex(all, useSyncExternalStore(subscribeHash, readHash));
  const fit = useSyncExternalStore(subscribeViewport, readFit);

  // Remember the step shown before this one: choreography is a function of the pair.
  const [shown, setShown] = useState<{ index: number; previous: number | undefined }>({
    index,
    previous: undefined,
  });
  if (shown.index !== index) setShown({ index, previous: shown.index });

  const go = (delta: number) => {
    const from = placeIndex(all, window.location.hash);
    const target = all[Math.max(0, Math.min(all.length - 1, from + delta))];
    if (target !== undefined) window.location.replace(formatPosition(target.position));
  };

  useMountEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isForeignInput(event.target)) return;
      // Controls own activation keys; arrow navigation remains available after a click.
      if (event.target instanceof Element && event.target.closest("button, a") && [" ", "Enter"].includes(event.key)) return;
      if (["ArrowRight", " ", "PageDown", "Enter"].includes(event.key)) go(1);
      else if (["ArrowLeft", "PageUp", "Backspace"].includes(event.key)) go(-1);
      else if (event.key === "Home") go(-all.length);
      else return;
      event.preventDefault();
    };
    const channel = new BroadcastChannel(`deck:${title}`);
    const announce = () => channel.postMessage(window.location.hash);
    channel.onmessage = (message: MessageEvent<string>) => {
      if (message.data !== window.location.hash) window.location.replace(message.data);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("hashchange", announce);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("hashchange", announce);
      channel.close();
    };
  });

  const place = all[index];
  if (place === undefined) return null;
  const choreography = choreograph(
    shown.previous === undefined ? undefined : all[shown.previous]?.step,
    place.step,
    timing,
  );

  if (presenter) {
    return (
      <TimingProvider value={timing}>
        <PresenterView all={all} index={index} />
      </TimingProvider>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <TimingProvider value={timing}>
        <div
          style={{
            position: "fixed",
            inset: 0,
            display: "grid",
            placeItems: "center",
            background: "#fff",
            touchAction: "none",
          }}
        >
          <Gestures onStep={go}>
            <div
              data-deck-position={formatPosition(place.position)}
              data-deck-total={choreography.total}
              data-deck-label={placeLabel(place)}
              data-deck-notes={place.step.notes}
              data-deck-camera={`${place.step.camera.center.x},${place.step.camera.center.y},${place.step.camera.scale}`}
              style={{
                position: "relative",
                width: stage.width * fit,
                height: stage.height * fit,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  width: stage.width,
                  height: stage.height,
                  transformOrigin: "0 0",
                  transform: `scale(${fit})`,
                }}
              >
                <World step={place.step} choreography={choreography} />
              </div>
            </div>
          </Gestures>
        </div>
      </TimingProvider>
    </MotionConfig>
  );
}

/**
 * Tap the left quarter to go back, elsewhere to go forward; a horizontal swipe also steps.
 * Taps use `click` so tools that claim a click first (Agentation calls `preventDefault` in the
 * capture phase while annotating) are respected.
 */
function Gestures({
  onStep,
  children,
}: {
  readonly onStep: (delta: number) => void;
  readonly children: React.ReactNode;
}) {
  const start = useRef<{ x: number; y: number } | undefined>(undefined);
  const swiped = useRef(false);
  const down = (event: PointerEvent) => {
    start.current = { x: event.clientX, y: event.clientY };
    swiped.current = false;
  };
  const up = (event: PointerEvent) => {
    const from = start.current;
    start.current = undefined;
    if (from === undefined) return;
    const dx = event.clientX - from.x;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(event.clientY - from.y)) {
      swiped.current = true;
      onStep(dx < 0 ? 1 : -1);
    }
  };
  const click = (event: MouseEvent<HTMLDivElement>) => {
    if (swiped.current || event.defaultPrevented || isForeignInput(event.target)) return;
    const box = event.currentTarget.getBoundingClientRect();
    onStep(event.clientX - box.left < box.width * 0.25 ? -1 : 1);
  };
  return (
    <div onPointerDown={down} onPointerUp={up} onClick={click}>
      {children}
    </div>
  );
}

/** Typing into a field, or using an overlay tool such as Agentation, must never change the step. */
function isForeignInput(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return (
    target.closest(
      "dialog, input, textarea, select, [contenteditable], [data-agentation-root], [data-feedback-toolbar]",
    ) !== null
  );
}

function DeckErrorScreen({ error }: { readonly error: DeckError }) {
  return (
    <pre
      style={{
        padding: 32,
        font: "14px ui-monospace, monospace",
        color: "var(--orange-dark)",
      }}
    >
      {describeDeckError(error)}
    </pre>
  );
}
