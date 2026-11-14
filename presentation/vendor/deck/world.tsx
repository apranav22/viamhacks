/*
 * One world under one camera (temple-pitch graph/05-ethos-world.md).
 *
 * Items are keyed for life: persisting keys move, new keys enter, missing keys exit. Exiting
 * items stop receiving props, so their timing comes from `AnimatePresence`'s `custom`, which
 * Motion resolves for exit variants (motion@c624ce8e resolve-dynamic-variants.ts L40–L41).
 * That replaces temple-pitch's module-level `plan`.
 */
import {
  AnimatePresence,
  animate,
  motion,
  motionValue,
  useMotionValue,
  useTransform,
  type MotionValue,
  type Variants,
} from "motion/react";
import { useLayoutEffect, useState } from "react";
import type { Pose } from "./block.ts";
import type { Choreography, Cue } from "./choreography.ts";
import { sizeOf, type Item, type Id } from "./item.ts";
import type { Step } from "./step.ts";
import { bezier, useTiming, type Timing } from "./timing.ts";
import { stage } from "./values.ts";
import type { PlacedWire, WireTone } from "./wire.ts";

/** An item's live box, shared by the item and every wire attached to it. */
type Box = {
  readonly x: MotionValue<number>;
  readonly y: MotionValue<number>;
  readonly width: MotionValue<number>;
  readonly height: MotionValue<number>;
  readonly opacity: MotionValue<number>;
};
type Boxes = (key: Id) => Box;

function useBoxes(): Boxes {
  const [boxes] = useState(() => new Map<Id, Box>());
  return (key) => {
    let box = boxes.get(key);
    if (box === undefined) {
      box = {
        x: motionValue(0),
        y: motionValue(0),
        width: motionValue(0),
        height: motionValue(0),
        opacity: motionValue(0),
      };
      boxes.set(key, box);
    }
    return box;
  };
}

const defaultPose = { opacity: 0, scale: 0.97 } as const satisfies Pose;

export type WorldProps = { readonly step: Step; readonly choreography: Choreography };

/** Renders one step's items under the camera, animating from whatever was shown before. */
export function World({ step, choreography }: WorldProps) {
  const timing = useTiming();
  const boxes = useBoxes();
  const cx = useMotionValue(step.camera.center.x);
  const cy = useMotionValue(step.camera.center.y);
  const scale = useMotionValue(step.camera.scale);

  // The camera is a Motion adapter: three motion values animated when the step changes.
  // A layout effect (not `useEffect`) starts it before paint, so no frame shows the old camera.
  useLayoutEffect(() => {
    const transition = { ...choreography.camera, ease: bezier(choreography.camera.ease) };
    const runs = [
      animate(cx, step.camera.center.x, transition),
      animate(cy, step.camera.center.y, transition),
      animate(scale, step.camera.scale, transition),
    ];
    return () => runs.forEach((run) => run.stop());
  }, [step, choreography, cx, cy, scale]);

  const transform = useTransform(
    () =>
      `translate(${stage.width / 2}px, ${stage.height / 2}px) scale(${scale.get()}) translate(${-cx.get()}px, ${-cy.get()}px)`,
  );

  return (
    <div
      style={{ position: "absolute", inset: 0, background: "#fff", overflow: "hidden" }}
      data-deck-stage=""
    >
      <motion.div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: 0,
          height: 0,
          transformOrigin: "0 0",
          transform,
        }}
      >
        <AnimatePresence initial={false} custom={choreography}>
          {[...step.items].map(([key, item], order) => (
            <ItemView
              key={key}
              asId={key}
              item={item}
              order={order}
              cue={choreography.cues.get(key)}
              timing={timing}
              box={boxes(key)}
            />
          ))}
        </AnimatePresence>
        <svg
          width={1}
          height={1}
          style={{ position: "absolute", left: 0, top: 0, overflow: "visible", zIndex: 0 }}
        >
          <AnimatePresence initial={false}>
            {[...step.wires].map(([key, wire]) => (
              <WireView
                key={key}
                wire={wire}
                from={boxes(wire.from)}
                to={boxes(wire.to)}
                arrive={arrival(wire, choreography)}
                timing={timing}
              />
            ))}
          </AnimatePresence>
        </svg>
      </motion.div>
    </div>
  );
}

type ItemViewProps = {
  readonly asId: Id;
  readonly item: Item;
  readonly order: number;
  readonly cue: Cue | undefined;
  readonly timing: Timing;
  readonly box: Box;
};

function ItemView({ asId, item, order, cue, timing, box }: ItemViewProps) {
  const size = sizeOf(item);
  const x = item.center.x - size.width / 2;
  const y = item.center.y - size.height / 2;
  const opacity = item.emphasis === "dimmed" ? timing.dimmed : 1;
  const enter = { ...defaultPose, ...item.block.enter };
  const exit = { ...defaultPose, ...item.block.exit };
  const out = bezier(timing.ease.out);

  const variants: Variants = {
    hidden: {
      x,
      y,
      width: size.width,
      height: size.height,
      opacity: enter.opacity,
      scale: enter.scale,
    },
    shown: shownFor(cue, { x, y, width: size.width, height: size.height, opacity }, size, timing),
    gone: (choreography: Choreography) => {
      const leaving = choreography.cues.get(asId);
      const delay = leaving?._tag === "Exit" ? leaving.delay : 0;
      const duration = leaving?._tag === "Exit" ? leaving.duration : timing.exit;
      return {
        opacity: exit.opacity,
        scale: exit.scale,
        zIndex: 0,
        transition: { delay, duration, ease: out, zIndex: { duration: 0 } },
      };
    },
  };
  const Render = item.block.render;

  return (
    <motion.div
      data-deck-item={asId}
      data-deck-kind={item.kind}
      data-deck-layered={item.layer === undefined ? undefined : ""}
      variants={variants}
      initial="hidden"
      animate="shown"
      exit="gone"
      data-deck-within={item.within.length === 0 ? undefined : item.within.join(" ")}
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        opacity: box.opacity,
        zIndex: item.layer ?? order + 1,
      }}
    >
      {/* Same id, new kind (a setup becoming a tile): the box morphs while the new content
          fades in on top and the old one holds, then goes, so the stack never dips. */}
      <AnimatePresence initial={false}>
        <motion.div
          key={item.kind}
          initial={{ opacity: 0 }}
          animate={{
            opacity: 1,
            transition: {
              delay: cue?._tag === "Move" ? cue.delay : 0,
              duration: timing.move * 0.6,
              ease: out,
            },
          }}
          exit={{
            opacity: 0,
            transition: {
              delay: (cue?._tag === "Move" ? cue.delay : 0) + timing.move * 0.5,
              duration: timing.move * 0.4,
              ease: out,
            },
          }}
          style={{ position: "absolute", inset: 0 }}
        >
          <Render {...item.props} />
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}

function shownFor(
  cue: Cue | undefined,
  target: {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
    readonly opacity: number;
  },
  size: { readonly width: number; readonly height: number },
  timing: Timing,
) {
  const out = bezier(timing.ease.out);
  if (cue === undefined) return { ...target, scale: 1, transition: { duration: 0 } };
  switch (cue._tag) {
    case "Enter":
      return {
        ...target,
        scale: 1,
        transition: {
          delay: cue.delay,
          duration: cue.duration,
          ease: out,
          x: { duration: 0 },
          y: { duration: 0 },
        },
      };
    case "Exit":
      return { ...target, scale: 1 };
    case "Move": {
      const ease = bezier(cue.ease);
      const opacity = { duration: timing.move * 0.7, ease: out };
      if (cue.path === undefined) {
        return {
          ...target,
          scale: 1,
          transition: { delay: cue.delay, duration: cue.duration, ease, opacity },
        };
      }
      const along = {
        delay: cue.delay,
        duration: cue.duration,
        times: [...cue.path.times],
        ease: "linear" as const,
      };
      return {
        x: cue.path.x.map((value) => value - size.width / 2),
        y: cue.path.y.map((value) => value - size.height / 2),
        width: target.width,
        height: target.height,
        opacity: target.opacity,
        scale: 1,
        transition: {
          x: along,
          y: along,
          width: { delay: cue.delay, duration: cue.duration, ease },
          height: { delay: cue.delay, duration: cue.duration, ease },
          opacity,
          scale: { duration: 0 },
        },
      };
    }
  }
}

/** When a wire may appear: once both ends have arrived. */
function arrival(wire: PlacedWire, choreography: Choreography): number {
  const done = (key: Id) => {
    const cue = choreography.cues.get(key);
    return cue?._tag === "Enter" ? cue.delay + cue.duration : 0;
  };
  return Math.max(done(wire.from), done(wire.to));
}

const tones: Record<
  WireTone,
  { readonly stroke: string; readonly width: number; readonly dash?: string }
> = {
  data: { stroke: "var(--ui-neutral-300)", width: 2 },
  permission: { stroke: "var(--orange)", width: 2, dash: "6 6" },
  danger: { stroke: "var(--ui-red-500, #e5484d)", width: 2, dash: "6 6" },
  pipe: { stroke: "var(--teal)", width: 6 },
};

type WireViewProps = {
  readonly wire: PlacedWire;
  readonly from: Box;
  readonly to: Box;
  readonly arrive: number;
  readonly timing: Timing;
};

/** A wire between two live boxes; it can never drift from what it connects. */
function WireView({ wire, from, to, arrive, timing }: WireViewProps) {
  const d = useTransform(() => {
    const centre = (b: Box) => ({
      x: b.x.get() + b.width.get() / 2,
      y: b.y.get() + b.height.get() / 2,
    });
    const a = centre(from);
    const b = centre(to);
    // Clip the centre-to-centre line at each box's edge.
    const clip = (box: Box, p: { x: number; y: number }, dx: number, dy: number) => {
      const t = Math.min(
        dx === 0 ? Infinity : box.width.get() / 2 / Math.abs(dx),
        dy === 0 ? Infinity : box.height.get() / 2 / Math.abs(dy),
        1,
      );
      return { x: p.x + dx * t, y: p.y + dy * t };
    };
    const start = clip(from, a, b.x - a.x, b.y - a.y);
    const end = clip(to, b, a.x - b.x, a.y - b.y);
    if (wire.bend === 0) return `M${start.x} ${start.y} L${end.x} ${end.y}`;
    const length = Math.hypot(end.x - start.x, end.y - start.y) || 1;
    const mx = (start.x + end.x) / 2 - ((end.y - start.y) / length) * wire.bend * length;
    const my = (start.y + end.y) / 2 + ((end.x - start.x) / length) * wire.bend * length;
    return `M${start.x} ${start.y} Q${mx} ${my} ${end.x} ${end.y}`;
  });
  // A receding end takes its wires with it.
  const ends = useTransform(() => Math.min(from.opacity.get(), to.opacity.get()));
  const tone = tones[wire.tone];
  const out = bezier(timing.ease.out);
  return (
    <motion.g
      initial={{ opacity: 0 }}
      animate={{
        opacity: 1,
        transition: { delay: arrive, duration: timing.enter * 0.6, ease: out },
      }}
      exit={{ opacity: 0, transition: { duration: timing.exit * 0.6, ease: out } }}
    >
      <motion.path
        d={d}
        fill="none"
        stroke={tone.stroke}
        strokeWidth={tone.width}
        strokeDasharray={tone.dash}
        strokeLinecap="round"
        style={{ opacity: ends }}
      />
    </motion.g>
  );
}
