/*
 * Functional core: when each item enters, moves or exits, and how the camera moves.
 * No React, no Motion, no clock. Ported from temple-pitch World.tsx `buildPlan` (L61–L79),
 * without its slide-specific rules.
 */
import { gatherPath, type Path } from "./gather.ts";
import type { Id } from "./item.ts";
import { sameCamera, type Step } from "./step.ts";
import type { Ease, Timing } from "./timing.ts";
import type { Seconds } from "./values.ts";

export type Cue =
  | { readonly _tag: "Enter"; readonly delay: Seconds; readonly duration: Seconds }
  | {
      readonly _tag: "Move";
      readonly delay: Seconds;
      readonly duration: Seconds;
      readonly ease: Ease;
      readonly path?: Path;
    }
  | { readonly _tag: "Exit"; readonly delay: Seconds; readonly duration: Seconds };

export type Choreography = {
  readonly camera: { readonly delay: Seconds; readonly duration: Seconds; readonly ease: Ease };
  readonly cues: ReadonlyMap<Id, Cue>;
  /** When the last animation ends; `deck capture` uses it for mid-change frames. */
  readonly total: Seconds;
};

const end = (cue: { readonly delay: Seconds; readonly duration: Seconds }) =>
  cue.delay + cue.duration;

export function choreograph(from: Step | undefined, to: Step, timing: Timing): Choreography {
  const cues = new Map<Id, Cue>();
  if (from === undefined) {
    for (const key of to.items.keys()) cues.set(key, { _tag: "Enter", delay: 0, duration: 0 });
    return { camera: { delay: 0, duration: 0, ease: timing.ease.move }, cues, total: 0 };
  }

  const moved = !sameCamera(from.camera, to.camera);
  const leaving = [...from.items.keys()].filter((key) => !to.items.has(key));
  const entering = [...to.items].filter(([key]) => !from.items.has(key));
  const settle = 0.05 * timing.slowdown;

  let camera: Choreography["camera"];
  let arrive: Seconds;
  const exit = { delay: 0, duration: timing.exit };

  switch (to.change) {
    case "move":
      camera = { delay: 0, duration: moved ? timing.camera : 0, ease: timing.ease.move };
      arrive = moved ? timing.camera * timing.arrival : settle;
      break;
    case "clear": {
      const cleared = leaving.length > 0 ? timing.exit : 0;
      camera = { delay: cleared, duration: moved ? timing.camera : 0, ease: timing.ease.move };
      arrive = cleared + (moved ? timing.camera * timing.arrival : settle);
      break;
    }
    case "gather":
      exit.duration = timing.gather.strip;
      camera = {
        delay: timing.gather.strip,
        duration: timing.gather.duration,
        ease: timing.ease.soft,
      };
      arrive = timing.gather.strip + timing.gather.duration * timing.arrival;
      break;
  }

  for (const key of leaving) cues.set(key, { _tag: "Exit", ...exit });

  for (const [key, item] of to.items) {
    const before = from.items.get(key);
    if (before === undefined) continue;
    if (to.change === "gather") {
      cues.set(key, {
        _tag: "Move",
        delay: camera.delay,
        duration: camera.duration,
        ease: timing.ease.soft,
        path: gatherPath(before.center, item.center, from.camera, to.camera, timing.ease.soft),
      });
    } else {
      cues.set(key, {
        _tag: "Move",
        delay: camera.delay,
        duration: moved ? timing.camera : timing.move,
        ease: timing.ease.move,
      });
    }
  }

  // New items bloom outward from the centre of the new frame, a capped beat apart.
  const distance = ([, item]: (typeof entering)[number]) =>
    Math.hypot(item.center.x - to.camera.center.x, item.center.y - to.camera.center.y);
  [...entering]
    .sort((a, b) => distance(a) - distance(b))
    .forEach(([key, item], i) => {
      const offset =
        item.delay === undefined
          ? Math.min(i * timing.stagger, timing.staggerMax)
          : item.delay * timing.slowdown;
      cues.set(key, { _tag: "Enter", delay: arrive + offset, duration: timing.enter });
    });

  const total = Math.max(end(camera), ...[...cues.values()].map(end));
  return { camera, cues, total };
}
