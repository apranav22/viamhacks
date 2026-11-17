import type { Scene } from "./scene.ts";
import type { Camera, Step, StepChange, StepId } from "./step.ts";
import type { Brand } from "./values.ts";

/** A slide's stable identity; kebab-case, unique within a deck, the first URL segment. */
export type SlideId = Brand<string, "SlideId">;

/** Parses an authored slide id. Uniqueness within a deck is checked by `parseDeck`. */
export function slideId(raw: string): SlideId {
  // SAFETY: a SlideId is any authored string; `parseDeck` owns its uniqueness invariant.
  return raw as SlideId;
}

/** A named chapter: consecutive steps telling one part of the story. Never empty. */
export type Slide = {
  readonly id: SlideId;
  readonly title: string;
  readonly steps: readonly [Step, ...Array<Step>];
};

/** Where the audience is: the URL `#/<slide>/<step>`. */
export type Position = { readonly slide: SlideId; readonly step: StepId };

/** Where we are within a slide. Steps are ordered, so "reached" is meaningful. */
export type StepCursor<Id extends string> = {
  readonly id: Id;
  /** True at `step` and every later step of the slide. */
  reached(step: Id): boolean;
};

/** One step's snapshot. Notes live with the step ids in `slide({ steps })`. */
export type Shot = {
  readonly scene: Scene;
  /** Default: the deck's `home`. */
  readonly camera?: Camera;
  /** Default: `"move"`. */
  readonly change?: StepChange;
};

/** One authored step, before its scene is evaluated. */
export type StepDefinition = {
  readonly id: string;
  readonly notes: string;
  readonly shot: Shot;
};

/** One authored slide, as `slide()` returns it. */
export type SlideDefinition = {
  readonly id: string;
  readonly title: string;
  readonly steps: ReadonlyArray<StepDefinition>;
};

/**
 * Declares a slide: its steps with their presenter notes, in click order, and how each looks.
 *
 * @param meta - `steps` maps step id → notes; key order is click order.
 * @param shot - The snapshot for one step; pure.
 */
export function slide<const Steps extends Readonly<Record<string, string>>>(
  meta: { readonly id: string; readonly title: string; readonly steps: Steps },
  shot: (step: StepCursor<keyof Steps & string>) => Shot,
): SlideDefinition {
  // SAFETY: `Object.keys` of a `Steps` literal returns exactly its string keys.
  const order = Object.keys(meta.steps) as Array<keyof Steps & string>;
  return {
    id: meta.id,
    title: meta.title,
    steps: order.map((id, index) => ({
      id,
      notes: meta.steps[id] ?? "",
      shot: shot({ id, reached: (other) => index >= order.indexOf(other) }),
    })),
  };
}
