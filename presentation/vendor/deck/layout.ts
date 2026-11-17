/*
 * Frameless containers and the layouts behind them. Pure geometry: children's sizes in,
 * positions (relative to the container's centre) out. Containers never draw anything.
 */
import { defineBlock, type Arrangement, type ChildBox } from "./block.ts";
import type { Id } from "./item.ts";
import type { Point, Size } from "./values.ts";

/** Cross-axis alignment of children in a `Row` or `Column`. */
export type Align = "start" | "center" | "end";

/** Space between children in world units. */
export type Gap = number;

const cross = (align: Align, room: number, size: number) =>
  align === "start" ? -room / 2 + size / 2 : align === "end" ? room / 2 - size / 2 : 0;

/** Lays children out along one axis, in order, `gap` apart. */
function line(
  axis: "x" | "y",
  { gap = 0, align = "center" }: { readonly gap?: Gap; readonly align?: Align },
  children: ReadonlyArray<ChildBox>,
): Arrangement {
  const along = (s: Size) => (axis === "x" ? s.width : s.height);
  const across = (s: Size) => (axis === "x" ? s.height : s.width);
  const length =
    children.reduce((sum, c) => sum + along(c.size), 0) + gap * Math.max(0, children.length - 1);
  const thickness = Math.max(0, ...children.map((c) => across(c.size)));
  const positions = new Map<Id, Point>();
  let cursor = -length / 2;
  for (const child of children) {
    const main = cursor + along(child.size) / 2;
    const side = cross(align, thickness, across(child.size));
    positions.set(child.id, axis === "x" ? { x: main, y: side } : { x: side, y: main });
    cursor += along(child.size) + gap;
  }
  const size =
    axis === "x" ? { width: length, height: thickness } : { width: thickness, height: length };
  return { size, positions };
}

/** Children in a grid of equal cells (the largest child's size), filled row by row. */
function grid(
  { columns, gap = { x: 0, y: 0 } }: { readonly columns: number; readonly gap?: Point },
  children: ReadonlyArray<ChildBox>,
): Arrangement {
  const cell = {
    width: Math.max(0, ...children.map((c) => c.size.width)),
    height: Math.max(0, ...children.map((c) => c.size.height)),
  };
  const cols = Math.max(1, Math.min(columns, children.length));
  const rows = Math.ceil(children.length / cols);
  const size = {
    width: cols * cell.width + (cols - 1) * gap.x,
    height: rows * cell.height + Math.max(0, rows - 1) * gap.y,
  };
  const positions = new Map<Id, Point>();
  children.forEach((child, i) => {
    positions.set(child.id, {
      x: -size.width / 2 + (i % cols) * (cell.width + gap.x) + cell.width / 2,
      y: -size.height / 2 + Math.floor(i / cols) * (cell.height + gap.y) + cell.height / 2,
    });
  });
  return { size, positions };
}

/** Children at their own `at` (local; default the origin). Anchored at the local origin. */
function free(children: ReadonlyArray<ChildBox>): Arrangement {
  if (children.length === 0) return { size: { width: 0, height: 0 }, positions: new Map() };
  const at = (c: ChildBox) => c.at ?? { x: 0, y: 0 };
  const left = Math.min(...children.map((c) => at(c).x - c.size.width / 2));
  const right = Math.max(...children.map((c) => at(c).x + c.size.width / 2));
  const top = Math.min(...children.map((c) => at(c).y - c.size.height / 2));
  const bottom = Math.max(...children.map((c) => at(c).y + c.size.height / 2));
  const middle = { x: (left + right) / 2, y: (top + bottom) / 2 };
  return {
    size: { width: right - left, height: bottom - top },
    positions: new Map(
      children.map((c) => [c.id, { x: at(c).x - middle.x, y: at(c).y - middle.y }]),
    ),
    anchor: { x: -middle.x, y: -middle.y },
  };
}

/** Edge padding around an arrangement; asymmetric padding shifts the children. */
export type Padding = {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
};

/** Adds padding around `inner`, for container blocks with a frame (a wall, a card). */
function pad(padding: Padding, inner: Arrangement): Arrangement {
  const shift = { x: (padding.left - padding.right) / 2, y: (padding.top - padding.bottom) / 2 };
  return {
    size: {
      width: inner.size.width + padding.left + padding.right,
      height: inner.size.height + padding.top + padding.bottom,
    },
    positions: new Map(
      [...inner.positions].map(([id, p]) => [id, { x: p.x + shift.x, y: p.y + shift.y }]),
    ),
  };
}

/** Layouts for block authors: each places children and returns an `Arrangement`. */
export const arrange = { line, grid, free, pad };

/** Props of a container that takes none of its own. */
export type NoProps = Readonly<Record<never, never>>;

const nothing = () => null;
const content = <P>(_: P, size: Size | undefined): Size => size ?? { width: 0, height: 0 };

/** Children at their own `at`, relative to the group's `at`. Frameless. */
export const Group = defineBlock<"group", NoProps>({
  kind: "group",
  frameless: true,
  size: content,
  render: nothing,
  layout: (_, children) => free(children),
});

/** Props of a `Row` or `Column`. */
export type LineProps = { readonly gap?: Gap; readonly align?: Align };
/** Props of a `Grid`. */
export type GridProps = { readonly columns: number; readonly gap?: Point };

/** Children left to right. Frameless. */
export const Row = defineBlock<"row", LineProps>({
  kind: "row",
  frameless: true,
  size: content,
  render: nothing,
  layout: (props, children) => line("x", props, children),
});

/** Children top to bottom. Frameless. */
export const Column = defineBlock<"column", LineProps>({
  kind: "column",
  frameless: true,
  size: content,
  render: nothing,
  layout: (props, children) => line("y", props, children),
});

/** Children in equal cells, row by row. Frameless. */
export const Grid = defineBlock<"grid", GridProps>({
  kind: "grid",
  frameless: true,
  size: content,
  render: nothing,
  layout: (props, children) => grid(props, children),
});
