import type { ReactElement, ReactNode } from "react";
import type { Emphasis, Id } from "./item.ts";
import type { Point, Seconds, Size } from "./values.ts";

/** Visual state an item starts from on enter, or ends at on exit, beyond its position. */
export type Pose = { readonly opacity?: number; readonly scale?: number };

/** What every element in a scene may carry besides its block's own props. */
export type Placement = {
  /** The item's identity for its whole life, whatever its parent (plan 458 C2). */
  readonly id: string;
  /** Centre, in world units at the scene root, or container-local inside a `Group`. */
  readonly at?: Point | undefined;
  readonly emphasis?: Emphasis | undefined;
  /** Replaces the automatic stagger with a deliberate delay after the arrival time. */
  readonly delay?: Seconds | undefined;
  /** Paint order; higher is in front. Defaults to scene order. */
  readonly layer?: number | undefined;
};

/** Props of a block element in a scene: the block's props, its placement, and any children. */
export type BlockProps<P> = P & Placement & { readonly children?: ReactNode };

/** One child of a container, measured, as its layout sees it. */
export type ChildBox = {
  readonly id: Id;
  readonly size: Size;
  readonly at: Point | undefined;
};

/** Where a container puts its children. Positions are child centres relative to its centre. */
export type Arrangement = {
  readonly size: Size;
  readonly positions: ReadonlyMap<Id, Point>;
  /**
   * The container-local point its own `at` names. Defaults to its centre; a free `Group`
   * anchors at its local origin, so `at` places that origin.
   */
  readonly anchor?: Point;
};

/** Places a container's children from their sizes. Pure. */
export type Layout<P> = (props: P, children: ReadonlyArray<ChildBox>) => Arrangement;

/*
 * Methods (not function-valued properties) on purpose: method parameters are bivariant, so a
 * `Block<"pill", PillProps>` can sit in a step's item map beside blocks of other kinds.
 */
/** How one kind of item is sized, laid out, rendered and, optionally, enters and exits. */
export type BlockSpec<K extends string, P extends object> = {
  readonly kind: K;
  /**
   * Intrinsic size in world units; the engine centres the item on its placement.
   * `content` is the size its layout needs when the block holds children.
   */
  size(this: void, props: P, content: Size | undefined): Size;
  /** The block's own visual (a frame, a label); its children are separate items. */
  render(this: void, props: P): ReactNode;
  /** Present when the block holds children. */
  layout?(this: void, props: P, children: ReadonlyArray<ChildBox>): Arrangement;
  /** Defaults to `{ opacity: 0, scale: 0.97 }`; never start from scale 0. */
  readonly enter?: Pose;
  /** Defaults to `{ opacity: 0, scale: 0.97 }`. */
  readonly exit?: Pose;
  /** Frameless containers lay out children but are not items themselves. */
  readonly frameless?: true;
};

/** A block, usable directly as a JSX element type in scenes: `<Pill id="gmail" … />`. */
export type Block<K extends string, P extends object> = BlockSpec<K, P> &
  ((props: BlockProps<P>) => never);

const blocks = new WeakSet<object>();

/** True when a JSX element type is a block (rather than a scene component). */
export function isBlock(
  type: ReactElement["type"],
): type is BlockSpec<string, object> & (() => never) {
  return type instanceof Function && blocks.has(type);
}

/** Creates a `Block`. The engine never knows a block's name; decks import the blocks they use. */
export function defineBlock<K extends string, P extends object>(
  spec: BlockSpec<K, P>,
): Block<K, P> {
  const element = (): never => {
    throw new Error(
      `Block "${spec.kind}" was rendered by React. Blocks belong in scenes, which the deck evaluates.`,
    );
  };
  const block = Object.assign(element, spec);
  blocks.add(block);
  return block;
}
