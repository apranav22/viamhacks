/*
 * `?view=presenter`: notes, where you are, what comes next, and elapsed time. Open it in a second
 * window; both windows follow each other (see Player).
 */
import { useMountEffect } from "./use-mount-effect.ts";
import { useState } from "react";
import { choreograph } from "./choreography.ts";
import { placeLabel as label, type Place } from "./deck.ts";
import { useTiming } from "./timing.ts";
import { stage } from "./values.ts";
import { World } from "./world.tsx";

export function PresenterView({
  all,
  index,
}: {
  readonly all: ReadonlyArray<Place>;
  readonly index: number;
}) {
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(startedAt);
  useMountEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  });

  const place = all[index];
  const next = all[index + 1];
  if (place === undefined) return null;
  const seconds = Math.floor((now - startedAt) / 1000);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "grid",
        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
        overflow: "auto",
        paddingBottom: 80,
        gridTemplateRows: "auto 1fr",
        gap: 24,
        padding: 32,
        boxSizing: "border-box",
        background: "var(--ui-neutral-50)",
        fontFamily: "var(--font-sans)",
        color: "var(--ui-neutral-900)",
      }}
    >
      <header
        style={{
          gridColumn: "1 / -1",
          display: "flex",
          justifyContent: "space-between",
          fontSize: 15,
          fontWeight: 600,
        }}
      >
        <span>{label(place)}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
      </header>
      <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <Preview place={place} />
        <p style={{ margin: 0, fontSize: 20, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
          {place.step.notes}
        </p>
      </section>
      <section style={{ display: "flex", flexDirection: "column", gap: 16, opacity: 0.8 }}>
        {next === undefined ? (
          <p style={{ margin: 0 }}>End of deck</p>
        ) : (
          <>
            <Preview place={next} />
            <span style={{ fontSize: 14 }}>Next: {label(next)}</span>
          </>
        )}
      </section>
    </div>
  );
}

const previewWidth = 560;

function Preview({ place }: { readonly place: Place }) {
  const timing = useTiming();
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        maxWidth: previewWidth,
        aspectRatio: `${stage.width} / ${stage.height}`,
        containerType: "inline-size",
        overflow: "hidden",
        borderRadius: 8,
        boxShadow: "0 0 0 1px var(--ui-neutral-200)",
      }}
    >
      <div
        style={{
          position: "absolute",
          width: stage.width,
          height: stage.height,
          transformOrigin: "0 0",
          transform: "scale(calc(100cqw / 1440px))",
        }}
      >
        <World
          key={`${place.position.slide}/${place.position.step}`}
          step={place.step}
          choreography={choreograph(undefined, place.step, timing)}
        />
      </div>
    </div>
  );
}
