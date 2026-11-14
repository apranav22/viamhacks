import { type EffectCallback, useEffect } from "react";

/**
 * Synchronizes one mounted component instance with an external system.
 *
 * The setup observes mount-time snapshots only. It may run more than once across development
 * Strict Mode checks and real remounts. Setup must therefore be reversible or idempotent, and any
 * cleanup must mirror setup.
 *
 * Prefer render-time derivation, event handlers, Query or Mutation, `useSyncExternalStore`, callback
 * refs, keyed remounting, or XState when one of those owners describes the behavior more precisely.
 *
 * @param setup - Mount-scoped external setup and optional symmetric cleanup.
 */
export function useMountEffect(setup: EffectCallback): void {
  useEffect(setup, []);
}
