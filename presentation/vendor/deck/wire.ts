import type { Id } from "./item.ts";

/**
 * How a wire reads: `data` thin grey; `permission` orange dashed (permissions must look
 * different from data); `danger` red dashed; `pipe` thick teal.
 */
export type WireTone = "data" | "permission" | "danger" | "pipe";

/** Props of `<Wire>` in a scene. */
export type WireProps = {
  /** Defaults to `from/to`; set it when two wires join the same pair. */
  readonly id?: string;
  /** Item ids; a wire draws between their live boxes, so it never drifts from them. */
  readonly from: string;
  readonly to: string;
  readonly tone?: WireTone;
  /** Sideways bow as a fraction of the wire's length; 0 is straight. */
  readonly bend?: number;
};

/** A wire after evaluation: ids resolved, defaults applied. */
export type PlacedWire = {
  readonly from: Id;
  readonly to: Id;
  readonly tone: WireTone;
  readonly bend: number;
};

/** A drawn connection between two items: `<Wire from="a" to="b" tone="data" />`. */
export function Wire(props: WireProps): never {
  throw new Error(
    `Wire "${props.from}/${props.to}" was rendered by React. Wires belong in scenes.`,
  );
}
