import type { ConciergeInvestigationStep } from '../../services/operatorConcierge'
import { traceStatus, type ResolutionStep } from '../../shared/trace/ResolutionTrace'

/** A completion updates its original row, even if another step has since begun. */
export function upsertInvestigationStep(
  steps: ConciergeInvestigationStep[], update: ConciergeInvestigationStep,
): ConciergeInvestigationStep[] {
  const index = steps.findIndex(step => step.kind === update.kind)
  if (index < 0) return [...steps, update]
  return steps.map((step, position) => position === index ? update : step)
}

export function operatorTraceSteps(steps: ConciergeInvestigationStep[]): ResolutionStep[] {
  return steps.map(step => ({
    id: step.kind,
    title: step.label,
    status: traceStatus(step.status),
    summary: step.result,
    source: step.source,
    durationMs: step.durationMs,
    detail: traceStatus(step.status) === 'unknown' ? `Reported status: ${step.status}` : undefined,
  }))
}
