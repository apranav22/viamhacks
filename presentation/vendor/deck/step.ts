import type { Item, Id } from "./item.ts";
import type { PlacedWire } from "./wire.ts";
import type { Brand, Point } from "./values.ts";

/** A step's stable identity; kebab-case, unique within its slide, the second URL segment. */
export type StepId = Brand<string, "StepId">;

/** Parses an authored step id. Uniqueness within a slide is checked by `parseDeck`. */
export function stepId(raw: string): StepId {
  // SAFETY: a StepId is any authored string; `parseDeck` owns its uniqueness invariant.
  return raw as StepId;
}

/** Which world point sits at the centre of the screen, and the zoom. */
export type Camera = { readonly center: Point; readonly scale: number };

/**
 * How the audience gets from the previous step to this one.
 * - `move`: persisting items move with the camera; new items arrive as it settles.
 * - `gather`: the one deliberate rearrangement; leavers strip away, then everything travels a
 *   straight line on screen while the camera reframes underneath.
 * - `clear`: everything leaving finishes before anything arrives.
 */
export type StepChange = "move" | "gather" | "clear";

/** What the audience sees after one click within a slide. */
export type Step = {
  readonly id: StepId;
  readonly camera: Camera;
  readonly items: ReadonlyMap<Id, Item>;
  readonly wires: ReadonlyMap<Id, PlacedWire>;
  readonly change: StepChange;
  readonly notes: string;
};

export function sameCamera(a: Camera, b: Camera): boolean {
  return a.center.x === b.center.x && a.center.y === b.center.y && a.scale === b.scale;
}
