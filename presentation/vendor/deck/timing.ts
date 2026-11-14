/*
 * Motion tokens, after Emil Kowalski's guidance (web-animation-design skill):
 *  - on-screen movement and morphs use a strong ease-in-out;
 *  - entering and exiting use a strong ease-out, never ease-in;
 *  - explanatory motion may run longer than the 300 ms UI rule;
 *  - stagger is 30–80 ms and capped so a group never drags.
 */
import { createContext, useContext } from "react";
import type { Seconds } from "./values.ts";

export type Ease = readonly [number, number, number, number];

/** Every duration and easing the engine uses, in one value. */
export type Timing = {
  readonly ease: { readonly move: Ease; readonly out: Ease; readonly soft: Ease };
  /** Persisting items moving or changing state without a camera move. */
  readonly move: Seconds;
  readonly enter: Seconds;
  /** Shorter than `enter`. */
  readonly exit: Seconds;
  readonly camera: Seconds;
  /** Fraction of the camera move after which new items begin to arrive. */
  readonly arrival: number;
  readonly stagger: Seconds;
  readonly staggerMax: Seconds;
  /** Opacity of an item whose emphasis is `dimmed`. */
  readonly dimmed: number;
  /** The `gather` change: strip, then contract and settle in one screen-space move. */
  readonly gather: { readonly strip: Seconds; readonly duration: Seconds };
  /** The factor already applied; blocks multiply their own inner durations by it. */
  readonly slowdown: number;
};

export const defaultTiming: Timing = {
  ease: { move: [0.77, 0, 0.175, 1], out: [0.23, 1, 0.32, 1], soft: [0.45, 0, 0.2, 1] },
  move: 0.9,
  enter: 0.75,
  exit: 0.6,
  camera: 1.1,
  arrival: 0.7,
  stagger: 0.04,
  staggerMax: 0.32,
  dimmed: 0.28,
  gather: { strip: 0.5, duration: 2.25 },
  slowdown: 1,
};

/** Multiplies every duration by `slowdown` (from `?slow=`); larger is slower. */
export function slowdown(timing: Timing, factor: number): Timing {
  const s = (seconds: Seconds) => seconds * factor;
  return {
    ...timing,
    move: s(timing.move),
    enter: s(timing.enter),
    exit: s(timing.exit),
    camera: s(timing.camera),
    stagger: s(timing.stagger),
    staggerMax: s(timing.staggerMax),
    gather: { strip: s(timing.gather.strip), duration: s(timing.gather.duration) },
    slowdown: timing.slowdown * factor,
  };
}

/** A Motion-ready copy of an `Ease`. */
export function bezier(ease: Ease): [number, number, number, number] {
  return [ease[0], ease[1], ease[2], ease[3]];
}

const TimingContext = createContext<Timing>(defaultTiming);
export const TimingProvider = TimingContext.Provider;

/** The player's timing, already slowed down; blocks use it for their own inner motion. */
export function useTiming(): Timing {
  return useContext(TimingContext);
}
