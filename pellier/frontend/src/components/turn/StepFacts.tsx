/**
 * A step's Builder evidence as labelled rows, with the backend's raw line one
 * disclosure away. Tool names, the model and ids are chips that wrap between
 * one another and never inside a token; an id carries a copy control.
 */
import { ChevronRight } from 'lucide-react'

import CopyId from './CopyId'
import { evidenceFacts, evidenceLine } from './evidence'
import type { FactPart } from './evidence'
import type { TurnStep } from './turnTypes'

export const SHOW_RAW_STEP = 'Show the raw step'

/** An id this long needs the row's full width, so its label stacks above it. */
const LONG_ID = 16
/**
 * Nor does a code chip this long, such as a model id, fit beside its label in a narrow
 * column like the Operator's; stacked, it stays whole instead of breaking inside the token.
 */
const LONG_CODE = 24

const needsFullWidth = (parts: FactPart[]) => parts.some(part =>
  (part.kind === 'id' && part.text.length > LONG_ID) || (part.kind === 'code' && part.text.length > LONG_CODE))

function Part({ part }: { part: FactPart }) {
  if (part.kind === 'id') return <CopyId value={part.text} noun={part.noun} />
  if (part.kind === 'code') return <code className="tn-chip tn-chip-code">{part.text}</code>
  return <span className="tn-fact-text">{part.text}</span>
}

export default function StepFacts({ step }: { step: TurnStep }) {
  const facts = evidenceFacts(step)
  if (facts.length === 0) return null
  return (
    <>
      <dl className="tn-facts" data-testid="turn-evidence">
        {facts.map(fact => (
          <div key={fact.label} className="tn-fact" data-stacked={needsFullWidth(fact.parts) ? 'true' : undefined}>
            <dt>{fact.label}</dt>
            <dd>
              {fact.parts.map((part, index) => <Part key={`${part.kind}-${index}`} part={part} />)}
            </dd>
          </div>
        ))}
      </dl>
      <details className="tn-raw" data-testid="turn-evidence-raw">
        <summary>
          <ChevronRight size={12} strokeWidth={2} className="tn-chev" aria-hidden="true" />
          {SHOW_RAW_STEP}
        </summary>
        <span className="tn-raw-text">{evidenceLine(step)}</span>
      </details>
    </>
  )
}
