import { useSyncExternalStore } from 'react';

/** One workspace: panel navigation is needed only when the columns cannot fit. */
export const WORKBENCH_COMPACT_QUERY = '(max-width: 1100px)';

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(WORKBENCH_COMPACT_QUERY);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

export function useCompactWorkbench(): boolean {
  return useSyncExternalStore(subscribe,
    () => window.matchMedia(WORKBENCH_COMPACT_QUERY).matches,
    () => false);
}

export type FocusPanelId = 'run' | 'inspect' | 'reconcile';

export interface FocusPanel {
  id: FocusPanelId;
  label: string;
  /** The `data-motion-panel` value of the grid panel this step reveals. */
  panel: 'requests' | 'trace' | 'results';
}

export const FOCUS_PANELS: readonly FocusPanel[] = [
  { id: 'run', label: 'Run', panel: 'requests' },
  { id: 'inspect', label: 'Inspect evidence', panel: 'trace' },
  { id: 'reconcile', label: 'Reconcile answer', panel: 'results' },
];

/**
 * Index of the Inspect evidence step.
 *
 * A completed run advances here: the evidence panel is worth reading once
 * there is evidence in it, and not while the turn is still streaming.
 */
export const FOCUS_INSPECT_STEP = 1;

/** Index of the focus panel with this id; `run` when the id is unknown. */
export function focusStepIndex(id: string | null | undefined): number {
  const index = FOCUS_PANELS.findIndex((panel) => panel.id === id);
  return index === -1 ? 0 : index;
}
