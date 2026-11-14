/*
 * Scenes: ordinary JSX made of block elements, evaluated (not rendered) into world items.
 * Function components are called, fragments and arrays flattened, `false`/`null` skipped.
 * Then containers are measured bottom-up and placed top-down (plan 458 §5.1).
 */
import { Children, Fragment, isValidElement, type ReactElement, type ReactNode } from "react";
import { isBlock, type Arrangement, type BlockSpec, type Placement } from "./block.ts";
import { asId, type Item, type Id } from "./item.ts";
import { err, ok, stage, type Point, type Result, type Size } from "./values.ts";
import { Wire, type WireProps, type PlacedWire } from "./wire.ts";

/** A scene: JSX made of block elements, wires, components, fragments, arrays, false/null. */
export type Scene = ReactNode;

/** Why a scene could not become a world. */
export type SceneError =
  | { readonly _tag: "DuplicateId"; readonly id: string }
  | { readonly _tag: "MissingId"; readonly kind: string }
  | { readonly _tag: "NotABlock"; readonly type: string }
  | { readonly _tag: "NotAContainer"; readonly id: string; readonly kind: string }
  | { readonly _tag: "UnknownEndpoint"; readonly wire: string; readonly id: string }
  | { readonly _tag: "ComponentFailed"; readonly component: string; readonly message: string };

/** The evaluated scene: items in scene order, and the wires between them. */
export type EvaluatedScene = {
  readonly items: ReadonlyMap<Id, Item>;
  readonly wires: ReadonlyMap<Id, PlacedWire>;
};

type Node = {
  readonly id: Id;
  readonly block: BlockSpec<string, object>;
  readonly props: object;
  readonly at: Placement["at"];
  readonly emphasis: Placement["emphasis"];
  readonly delay: Placement["delay"];
  readonly layer: Placement["layer"];
  readonly children: ReadonlyArray<Node> | undefined;
};
type Walked = { readonly nodes: Array<Node>; readonly wires: Array<WireProps> };

// SAFETY: React types element props as `unknown`-ish `any`; a block element's props are the
// block's own props plus `Placement` and `children`, which `defineBlock`'s element type enforces
// at every authoring call site.
const propsOf = (element: ReactElement) => element.props as Placement & { children?: ReactNode };

function nameOf(type: ReactElement["type"]): string {
  return type instanceof Function ? type.name || "anonymous" : String(type);
}

function walk(scene: Scene, into: Walked): SceneError | undefined {
  // `toArray` flattens arrays and drops null, undefined and booleans.
  for (const child of Children.toArray(scene)) {
    const failure = visit(child, into);
    if (failure !== undefined) return failure;
  }
  return undefined;
}

function visit(
  scene: ReturnType<typeof Children.toArray>[number],
  into: Walked,
): SceneError | undefined {
  if (!isValidElement(scene)) return { _tag: "NotABlock", type: `text "${String(scene)}"` };
  const element: ReactElement = scene;
  const props = propsOf(element);
  if (element.type === Fragment) return walk(props.children, into);
  if (element.type === Wire) {
    // SAFETY: the element's type is `Wire`, whose props type is `WireProps`.
    into.wires.push(element.props as WireProps);
    return undefined;
  }
  if (isBlock(element.type)) {
    const block = element.type;
    const { id, at, emphasis, delay, layer, children, ...own } = props;
    if (id === undefined || id === "") return { _tag: "MissingId", kind: block.kind };
    let nested: Array<Node> | undefined;
    if (children !== undefined && children !== null && children !== false) {
      if (block.layout === undefined) return { _tag: "NotAContainer", id, kind: block.kind };
      const inner: Walked = { nodes: [], wires: into.wires };
      const failure = walk(children, inner);
      if (failure !== undefined) return failure;
      nested = inner.nodes;
    }
    into.nodes.push({
      id: asId(id),
      block,
      props: own,
      at,
      emphasis,
      delay,
      layer,
      children: nested,
    });
    return undefined;
  }
  if (element.type instanceof Function) {
    // SAFETY: a scene component is a function of its props; class components, which scenes do
    // not support, fail the call and are reported as `ComponentFailed`.
    const component = element.type as (props: ReactElement["props"]) => ReactNode;
    let output: ReactNode;
    try {
      output = component(element.props);
    } catch (cause) {
      return {
        _tag: "ComponentFailed",
        component: nameOf(element.type),
        message: cause instanceof Error ? cause.message : String(cause),
      };
    }
    return walk(output, into);
  }
  return { _tag: "NotABlock", type: nameOf(element.type) };
}

type Measured = { readonly size: Size; readonly arrangement: Arrangement | undefined };

function measure(node: Node, sizes: Map<Node, Measured>): Measured {
  const children = node.children ?? [];
  let arrangement: Arrangement | undefined;
  if (node.block.layout !== undefined && node.children !== undefined) {
    arrangement = node.block.layout(
      node.props,
      children.map((child) => {
        const inner = measure(child, sizes);
        const at = child.at;
        const anchor = inner.arrangement?.anchor ?? { x: 0, y: 0 };
        // A child's `at` names its anchor; layouts work with centres.
        return {
          id: child.id,
          size: inner.size,
          at: at === undefined ? undefined : { x: at.x - anchor.x, y: at.y - anchor.y },
        };
      }),
    );
  }
  const measured = { size: node.block.size(node.props, arrangement?.size), arrangement };
  sizes.set(node, measured);
  return measured;
}

function place(
  node: Node,
  center: Point,
  parent: Id | undefined,
  within: ReadonlyArray<Id>,
  sizes: Map<Node, Measured>,
  items: Map<Id, Item>,
) {
  const measured = sizes.get(node) ?? measure(node, sizes);
  const framed = node.block.frameless !== true;
  if (framed) {
    items.set(node.id, {
      kind: node.block.kind,
      props: node.props,
      block: node.block,
      center,
      size: measured.size,
      emphasis: node.emphasis ?? "full",
      delay: node.delay,
      layer: node.layer,
      parent,
      within,
    });
  }
  const inside = framed ? [node.id, ...within] : within;
  for (const child of node.children ?? []) {
    const offset = measured.arrangement?.positions.get(child.id) ?? { x: 0, y: 0 };
    place(child, { x: center.x + offset.x, y: center.y + offset.y }, node.id, inside, sizes, items);
  }
}

function ids(nodes: ReadonlyArray<Node>, seen: Set<string>): string | undefined {
  for (const node of nodes) {
    if (seen.has(node.id)) return node.id;
    seen.add(node.id);
    const duplicate = ids(node.children ?? [], seen);
    if (duplicate !== undefined) return duplicate;
  }
  return undefined;
}

/**
 * Evaluates a scene into world items and wires. Root elements sit at their `at` in world units
 * (default: the stage centre). Pure: the same scene always yields the same world.
 */
export function evaluateScene(scene: Scene): Result<EvaluatedScene, SceneError> {
  const walked: Walked = { nodes: [], wires: [] };
  const failure = walk(scene, walked);
  if (failure !== undefined) return err(failure);

  const seen = new Set<string>();
  const duplicate = ids(walked.nodes, seen);
  if (duplicate !== undefined) return err({ _tag: "DuplicateId", id: duplicate });

  const sizes = new Map<Node, Measured>();
  const items = new Map<Id, Item>();
  for (const node of walked.nodes) {
    const { arrangement } = measure(node, sizes);
    const at = node.at ?? { x: stage.width / 2, y: stage.height / 2 };
    const anchor = arrangement?.anchor ?? { x: 0, y: 0 };
    place(node, { x: at.x - anchor.x, y: at.y - anchor.y }, undefined, [], sizes, items);
  }

  const wires = new Map<Id, PlacedWire>();
  for (const wire of walked.wires) {
    const id = wire.id ?? `${wire.from}/${wire.to}`;
    if (seen.has(id)) return err({ _tag: "DuplicateId", id });
    seen.add(id);
    for (const end of [wire.from, wire.to])
      if (!items.has(asId(end))) return err({ _tag: "UnknownEndpoint", wire: id, id: end });
    wires.set(asId(id), {
      from: asId(wire.from),
      to: asId(wire.to),
      tone: wire.tone ?? "data",
      bend: wire.bend ?? 0,
    });
  }
  return ok({ items, wires });
}
