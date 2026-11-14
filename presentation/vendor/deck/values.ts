/** A nominal refinement of `T`; values are created only by the parser that owns `Name`. */
export type Brand<T, Name extends string> = T & { readonly __brand: Name };

/** A point in world units. The authored stage is 1440 × 810. */
export type Point = { readonly x: number; readonly y: number };

/** An image a block shows: always with alt text. */
export type ImageRef = { readonly src: string; readonly alt: string };

/** A size in world units. */
export type Size = { readonly width: number; readonly height: number };

/** An axis-aligned rectangle in world units; `x`, `y` is its top-left corner. */
export type Rect = Point & Size;

export const centerOf = (rect: Rect): Point => ({
  x: rect.x + rect.width / 2,
  y: rect.y + rect.height / 2,
});

/** A duration or delay in seconds, before `slowdown` is applied. */
export type Seconds = number;

/** The authored stage. The deck is only ever scaled, never relaid out. */
export const stage: Size = { width: 1440, height: 810 };

export type Ok<A> = { readonly _tag: "Ok"; readonly value: A };
export type Err<E> = { readonly _tag: "Err"; readonly error: E };
/** Expected failure as a value. */
export type Result<A, E> = Ok<A> | Err<E>;

export const ok = <A>(value: A): Ok<A> => ({ _tag: "Ok", value });
export const err = <E>(error: E): Err<E> => ({ _tag: "Err", error });
