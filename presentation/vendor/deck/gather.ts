/*
 * The `gather` change, ported from temple-pitch World.tsx L124–L153 as pure keyframes.
 *
 * Mixing world-space motion with a zooming camera makes items fling out and back. Instead each
 * persisting item travels a straight, eased line on screen while the camera reframes underneath;
 * we sample that line and convert every sample back into world units under the camera at that
 * moment. Motion then plays the samples linearly, so no effect or per-frame callback is needed.
 */
import type { Camera } from "./step.ts";
import type { Ease } from "./timing.ts";
import { stage, type Point } from "./values.ts";

export type Path = {
  readonly x: ReadonlyArray<number>;
  readonly y: ReadonlyArray<number>;
  readonly times: ReadonlyArray<number>;
};

const samples = 24;

/** CSS cubic-bezier easing as a function of progress. */
export function cubicBezier([x1, y1, x2, y2]: Ease): (t: number) => number {
  const at = (a: number, b: number, s: number) =>
    3 * a * s * (1 - s) ** 2 + 3 * b * s ** 2 * (1 - s) + s ** 3;
  return (t) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 30; i++) {
      const mid = (lo + hi) / 2;
      if (at(x1, x2, mid) < t) lo = mid;
      else hi = mid;
    }
    return at(y1, y2, (lo + hi) / 2);
  };
}

const toScreen = (p: Point, c: Camera): Point => ({
  x: stage.width / 2 + (p.x - c.center.x) * c.scale,
  y: stage.height / 2 + (p.y - c.center.y) * c.scale,
});
const toWorld = (p: Point, c: Camera): Point => ({
  x: c.center.x + (p.x - stage.width / 2) / c.scale,
  y: c.center.y + (p.y - stage.height / 2) / c.scale,
});
const mix = (a: number, b: number, e: number) => a + (b - a) * e;

/** World keyframes that move `from` → `to` along a straight on-screen line while the camera eases. */
export function gatherPath(
  from: Point,
  to: Point,
  before: Camera,
  after: Camera,
  ease: Ease,
): Path {
  const e = cubicBezier(ease);
  const a = toScreen(from, before);
  const b = toScreen(to, after);
  const x: Array<number> = [];
  const y: Array<number> = [];
  const times: Array<number> = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const k = e(t);
    const camera = {
      center: {
        x: mix(before.center.x, after.center.x, k),
        y: mix(before.center.y, after.center.y, k),
      },
      scale: mix(before.scale, after.scale, k),
    };
    const w = toWorld({ x: mix(a.x, b.x, k), y: mix(a.y, b.y, k) }, camera);
    x.push(w.x);
    y.push(w.y);
    times.push(t);
  }
  return { x, y, times };
}
