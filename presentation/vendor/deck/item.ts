import type { BlockSpec } from "./block.ts";
import type { Brand, Point, Seconds, Size } from "./values.ts";

/**
 * An authored id: an item's (or wire's) identity across steps, whatever its parent. Items and
 * wires in one scene share one id space.
 */
export type Id = Brand<string, "Id">;

/** Whether the item recedes. */
export type Emphasis = "full" | "dimmed";

/** One keyed thing placed in the world for a step; `props` is typed by the block that made it. */
export type Item = {
  readonly kind: string;
  readonly props: object;
  readonly block: BlockSpec<string, object>;
  /** World centre, after layout. */
  readonly center: Point;
  /** World size, after layout. */
  readonly size: Size;
  readonly emphasis: Emphasis;
  /** Replaces the automatic stagger when set. */
  readonly delay: Seconds | undefined;
  /** Paint order; higher is in front. Undefined keeps scene order. */
  readonly layer: number | undefined;
  /** The nearest enclosing container (item or frameless group), if any. */
  readonly parent: Id | undefined;
  /** Enclosing items (not frameless groups), nearest first; they may overlap this one. */
  readonly within: ReadonlyArray<Id>;
};

/** Brands an authored id. Uniqueness within a step is checked by `evaluateScene`. */
export function asId(raw: string): Id {
  // SAFETY: an Id is any authored string; `evaluateScene` owns its uniqueness invariant.
  return raw as Id;
}

export function sizeOf(item: Item): Size {
  return item.size;
}
