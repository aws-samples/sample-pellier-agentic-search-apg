import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { WORKSHOP_JOURNEYS, type WorkshopAnchorId } from '../../data/workshopJourneys'
import { findLabExercise } from '../../observatory/labs/labCatalog'
import examples from '../../data/pellierTraceScenarios.json'
import './trace-evidence.css'

type Example = (typeof examples)[number]

/** Public projections of recorded evidence, with source excerpts labelled separately. */
export default function TraceScenarioDetails({ example }: { example: Example }) {
  const { inspection, learning } = example
  const lab = findLabExercise(learning.labId)
  const journey = WORKSHOP_JOURNEYS[learning.anchorId as WorkshopAnchorId]
  if (!lab || !journey) return null
  return (
    <section id={`trace-details-${example.id}`} tabIndex={-1} className="trace-evidence" aria-label={`${learning.label} technical details`}>
      <header className="trace-evidence-heading">
        <span className="trace-evidence-eyebrow">Inside this request</span>
        <span className="trace-evidence-state" data-state={example.outcomeStatus}>{inspection.status}</span>
      </header>
      <h2>{learning.label}</h2>
      <div className="trace-evidence-operation">
        <code>{inspection.operation}</code>
        <span>{inspection.measurement}</span>
      </div>
      <dl className="trace-evidence-facts">
        <div><dt>Source</dt><dd>{inspection.source}</dd></div>
        <div><dt>Domain records</dt><dd>{inspection.domainRecords.join(' · ')}</dd></div>
        <div><dt>Recorded result</dt><dd>{inspection.result}</dd></div>
        <div><dt>LLM activity</dt><dd>{inspection.llmActivity}</dd></div>
      </dl>
      <div className="trace-evidence-code">
        <div className="trace-evidence-code-heading">
          <span>{inspection.codeLabel}</span><span>{inspection.language}</span>
        </div>
        <pre tabIndex={0} aria-label={inspection.codeLabel}><code>{inspection.code}</code></pre>
      </div>
      <p className="trace-evidence-caption">{inspection.codeNote}</p>
      <details className="trace-evidence-provenance">
        <summary>Recording and measurement details</summary>
        <p>{inspection.provenance}</p>
        <code>{inspection.recordRef}</code>
      </details>
      <div className="trace-evidence-exercise">
        <span className="trace-evidence-eyebrow">Lab {Number(lab.number)} · {lab.shortTitle}</span>
        <p>{learning.relationship}</p>
        <Link to={`/observatory/workbench?lab=${learning.labId}`}>
          Open {journey.anchorName}’s exercise <ArrowUpRight size={14} aria-hidden />
        </Link>
        {journey.surface === 'operator' && (
          <Link to={`/operator/clients/${journey.customerId}?guided=service-recovery#operator-concierge-title`}>
            Open the guided Operator turns <ArrowUpRight size={14} aria-hidden />
          </Link>
        )}
      </div>
    </section>
  )
}
