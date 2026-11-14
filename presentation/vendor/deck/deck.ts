import { evaluateScene, type SceneError } from "./scene.ts";
import { slideId, type Position, type Slide, type SlideDefinition } from "./slide.ts";
import { stepId, type Camera, type Step } from "./step.ts";
import { err, ok, type Result } from "./values.ts";

/** What an author writes in `deck.tsx`. */
export type DeckDefinition = {
  readonly title: string;
  /** Emails allowed to open the deployed deck. */
  readonly viewers: ReadonlyArray<string>;
  /** The camera a step uses when its shot names none. */
  readonly home: Camera;
  readonly slides: ReadonlyArray<SlideDefinition>;
};

/** A parsed, ordered, valid deck. */
export type Deck = {
  readonly title: string;
  readonly viewers: ReadonlyArray<string>;
  readonly slides: readonly [Slide, ...Array<Slide>];
};

type At = { readonly slide: string; readonly step: string };
export type DuplicateSlideId = { readonly _tag: "DuplicateSlideId"; readonly slide: string };
export type EmptySlide = { readonly _tag: "EmptySlide"; readonly slide: string };
/** Integer-like step ids would be reordered by JavaScript object key order. */
export type NumericStepId = { readonly _tag: "NumericStepId"; readonly at: At };
export type InvalidScene = {
  readonly _tag: "InvalidScene";
  readonly at: At;
  readonly error: SceneError;
};
export type EmptyDeck = { readonly _tag: "EmptyDeck" };
export type DeckError = DuplicateSlideId | EmptySlide | NumericStepId | InvalidScene | EmptyDeck;

/** Declares a deck: metadata, then its slides in order. */
export function deck(
  meta: Omit<DeckDefinition, "slides">,
  slides: ReadonlyArray<SlideDefinition>,
): DeckDefinition {
  return { ...meta, slides };
}

const integerLike = /^(0|[1-9]\d*)$/;

/** Evaluates every step's scene in order; the first problem is returned as a value. */
export function parseDeck(definition: DeckDefinition): Result<Deck, DeckError> {
  const slides: Array<Slide> = [];
  const slideIds = new Set<string>();

  for (const slide of definition.slides) {
    if (slideIds.has(slide.id)) return err({ _tag: "DuplicateSlideId", slide: slide.id });
    slideIds.add(slide.id);
    const steps: Array<Step> = [];

    for (const step of slide.steps) {
      const at = { slide: slide.id, step: step.id };
      if (integerLike.test(step.id)) return err({ _tag: "NumericStepId", at });
      const world = evaluateScene(step.shot.scene);
      if (world._tag === "Err") return err({ _tag: "InvalidScene", at, error: world.error });
      steps.push({
        id: stepId(step.id),
        camera: step.shot.camera ?? definition.home,
        items: world.value.items,
        wires: world.value.wires,
        change: step.shot.change ?? "move",
        notes: step.notes,
      });
    }

    const [first, ...rest] = steps;
    if (first === undefined) return err({ _tag: "EmptySlide", slide: slide.id });
    slides.push({ id: slideId(slide.id), title: slide.title, steps: [first, ...rest] });
  }

  const [first, ...rest] = slides;
  if (first === undefined) return err({ _tag: "EmptyDeck" });
  return ok({ title: definition.title, viewers: definition.viewers, slides: [first, ...rest] });
}

/** A readable one-line description of a deck error, for the error screen and the CLI. */
export function describeDeckError(error: DeckError): string {
  switch (error._tag) {
    case "DuplicateSlideId":
      return `Two slides share the id "${error.slide}".`;
    case "EmptySlide":
      return `Slide "${error.slide}" has no steps.`;
    case "NumericStepId":
      return `Step id "${error.at.step}" in "${error.at.slide}" looks like a number; use a word.`;
    case "EmptyDeck":
      return "The deck has no slides.";
    case "InvalidScene": {
      const where = `#/${error.at.slide}/${error.at.step}`;
      const e = error.error;
      switch (e._tag) {
        case "DuplicateId":
          return `${where}: two items share the id "${e.id}".`;
        case "MissingId":
          return `${where}: a "${e.kind}" element has no id.`;
        case "NotABlock":
          return `${where}: "${e.type}" is not a block; visuals belong in a block's render.`;
        case "NotAContainer":
          return `${where}: "${e.id}" (${e.kind}) was given children but has no layout.`;
        case "UnknownEndpoint":
          return `${where}: wire "${e.wire}" points at "${e.id}", which isn't in the scene.`;
        case "ComponentFailed":
          return `${where}: component ${e.component} failed (${e.message}). Scene components must be pure: no hooks.`;
      }
    }
  }
}

/** One entry per click, in order, with where it sits. */
export type Place = {
  readonly position: Position;
  readonly step: Step;
  readonly slide: Slide;
  /** 1-based, for "Slide 3 · step 2 of 4". */
  readonly slideNumber: number;
  readonly stepNumber: number;
};

export function places(deck: Deck): ReadonlyArray<Place> {
  return deck.slides.flatMap((slide, s) =>
    slide.steps.map((step, i) => ({
      position: { slide: slide.id, step: step.id },
      step,
      slide,
      slideNumber: s + 1,
      stepNumber: i + 1,
    })),
  );
}

/** "Slide 3 · The Pond · step 2 of 6", as the owner talks about a deck. */
export function placeLabel(place: Place): string {
  return `Slide ${place.slideNumber} · ${place.slide.title} · step ${place.stepNumber} of ${place.slide.steps.length}`;
}

export function formatPosition(position: Position): string {
  return `#/${position.slide}/${position.step}`;
}

/** Index of `#/<slide>/<step>` among `places`; unknown or empty → 0 (the first step). */
export function placeIndex(all: ReadonlyArray<Place>, hash: string): number {
  const [slide, step] = hash.replace(/^#\/?/, "").split("/");
  const index = all.findIndex((p) => p.position.slide === slide && p.position.step === step);
  return index < 0 ? 0 : index;
}
