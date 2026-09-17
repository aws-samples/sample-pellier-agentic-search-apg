import { Link } from 'react-router-dom';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';

/** Evaluation protocol, not an invented scorecard. Results live in evidence views. */
export default function EvaluationsDetail() {
  return <DetailPageShell numeral="VI" conceptName="Evaluations" category="quality"
    title="Evaluations, measured."
    prose="A result needs a defined question, a controlled comparison, and retained evidence. Workshop acceptance checks establish bounded behavior; they do not estimate production quality or latency."
    cheatSheet={[
      { numeral: 'i.', text: 'Keep the model, corpus, query set, caller, and execution path fixed when attributing a result to a code change.' },
      { numeral: 'ii.', text: 'Report sample count and failures with latency. One successful turn cannot establish P95 or an accuracy rate.' },
      { numeral: 'iii.', text: 'Judge the final answer against source rows as well as the trace. A tool call proves execution, not answer correctness.' },
    ]}>
    <div style={{ display: 'grid', gap: '20px', lineHeight: 1.65 }}>
      <ExpCard><h2>Retrieval: explain the candidate budget</h2>
        <p>Lab 2 records how candidate generation changes the retrieved rows. Use its budget sweep to explain recall, ranking, and query cost. A broader relevance claim needs held-out queries with explicit labels and a fixed corpus.</p>
        <Link to="/observatory/workbench?lab=retrieval-acceptance">Return to Lab 2 in Workbench</Link>
      </ExpCard>
      <ExpCard><h2>Actions: distinguish four outcomes</h2>
        <p>Lab 4 tests policy denial, database refusal, commit, and replay. Compare the receipt with database effects. An HTTP success or a fluent response does not establish that the authorized effect committed exactly once.</p>
        <Link to="/observatory/workbench?lab=fail-closed-policy">Return to Lab 4 in Workbench</Link>
      </ExpCard>
      <ExpCard><h2>Read results with their provenance</h2>
        <p>No accuracy, latency, or citation score is assigned by this reference page. The evidence views identify available records and report unavailable sources explicitly.</p>
        <p><Link to="/observatory/evaluations">Evaluation configuration and recorded evidence</Link></p>
        <p><Link to="/observatory/performance">Measured performance evidence</Link></p>
        <p><Link to="/observatory/proof-board">Proof Board</Link></p>
      </ExpCard>
    </div>
  </DetailPageShell>;
}
