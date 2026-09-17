/**
 * Which governed Labs surfaces run requests and which inspect recorded evidence.
 *
 * The collection is the visual entry to one participant-facing workbench.
 * Deeper system pages remain reference views.
 */

export type LabsInteraction = 'interactive' | 'reference';

export const INTERACTIVE_PATHS: readonly string[] = [
  '/observatory',
  '/observatory/labs',
  '/observatory/workbench',
];

export interface ObservatoryModeCopy {
  label: string;
  detail: string;
}

const INTERACTIVE_COPY: Record<string, ObservatoryModeCopy> = {
  '/observatory': {
    label: 'Labs & Workbench',
    detail:
      'Follow the four labs in order, then use Workbench to inspect the evidence for each change.',
  },
  '/observatory/labs': {
    label: 'Participant guide',
    detail:
      'Follow the steps, check your results, and use the recovery beside each exercise. Open Workbench to inspect live behavior.',
  },
  '/observatory/workbench': {
    label: 'Labs & Workbench',
    detail:
      'Run a live Storefront Dispatcher request and inspect routing, memory, guardrails, agent activity, tool calls, SQL, and the grounded answer.',
  },
};

/**
 * Every non-Workbench surface gets this.
 *
 * Observatory is part of the core participant experience. This banner names
 * the interaction boundary: reading recorded evidence does not start a live
 * request. The lab guide determines which deeper exercises are optional.
 */
const REFERENCE_COPY: ObservatoryModeCopy = {
  label: 'Reference view',
  detail:
    'Inspect system evidence and implementation detail without starting a new shopper turn.',
};

function normalize(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
}

export function isInteractivePath(pathname: string): boolean {
  const path = normalize(pathname);
  return INTERACTIVE_PATHS.some(
    (interactivePath) =>
      path === interactivePath ||
      (interactivePath !== '/observatory' &&
        path.startsWith(`${interactivePath}/`)),
  );
}

export function interactionForPath(pathname: string): LabsInteraction {
  return isInteractivePath(pathname) ? 'interactive' : 'reference';
}

export function modeCopyForPath(pathname: string): ObservatoryModeCopy {
  if (normalize(pathname).startsWith('/observatory/guide/')) return INTERACTIVE_COPY['/observatory/labs'];
  if (!isInteractivePath(pathname)) return REFERENCE_COPY;

  const path = normalize(pathname);
  const exact = INTERACTIVE_COPY[path];
  if (exact) return exact;

  const parent = [...INTERACTIVE_PATHS]
    .sort((left, right) => right.length - left.length)
    .find(
    (interactivePath) =>
      path.startsWith(`${interactivePath}/`),
    );
  return (
    (parent && INTERACTIVE_COPY[parent]) || INTERACTIVE_COPY['/observatory']
  );
}
