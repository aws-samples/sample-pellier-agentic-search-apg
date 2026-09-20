import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import './BoundaryOutcomes.css';

const LESSONS = [
  ['authentication_failed', 'Authentication fails', 'No validated caller. Cedar is not evaluated.'],
  ['cedar_denied', 'Cedar denies', 'The authenticated caller is refused before tool execution.'],
  ['transaction_rejected', 'The transaction rejects', 'Cedar permits the call. The tool runs, but the business rule prevents a write.'],
  ['committed', 'The operation commits', 'A finalized operation joins to the matching business record.'],
  ['output_suppressed', 'The output is suppressed', 'The managed output check withholds a response. The committed credit remains.'],
] as const;

type Outcome = typeof LESSONS[number][0] | 'inconclusive';
export interface BoundaryAttempt {
  id: number; case: string; operationKey: string; invocationId: string;
  tool: string; principal: string | null; observedAt: string;
  outcome: Outcome; control: string; toolExecuted: boolean | null; dataChanged: boolean | null;
  authentication: string; authorization: string; output: string;
  database: { executionRows?: number; writeRows?: number; committedRows?: number; domainRows?: number; ledgerRows?: number; pendingClaimRows?: number };
  contradiction: string | null;
}
export interface BoundaryRun {
  runId: string; observedAt: string; attempts: BoundaryAttempt[];
  outcomes: Record<string, boolean>; complete: boolean;
}
export interface BoundaryPayload { runs: BoundaryRun[]; source: string }
const fact = (value: boolean | null) => value === null ? 'Unknown' : value ? 'Yes' : 'No';

export default function BoundaryOutcomes() {
  const { data, loading, error, errorStatus, refetch } = useObservatoryData<BoundaryPayload>({ key: 'governance/outcomes' });
  const [selectedId, setSelectedId] = useState('');
  const runs = data?.runs ?? [];
  const run = runs.find(item => item.runId === selectedId) ?? runs[0];
  return <section className="boundary-outcomes" aria-labelledby="boundary-heading">
    <div className="boundary-heading">
      <div><span className="govern-eyebrow">Lab 4 · Five observed outcomes</span>
        <h2 id="boundary-heading">Which control acted?</h2></div>
      <button className="pellier-action-quiet" type="button" onClick={refetch} disabled={loading}>Refresh evidence</button>
    </div>
    <p>Read authorization, execution, and data changes separately. These records contain CLI observations and exact-key Aurora snapshots. They are not provider policy decision logs.</p>
    <ol className="boundary-lessons">{LESSONS.map(([id, title, description]) => <li key={id}>
      <div><strong>{title}</strong><span className="boundary-state">{run?.outcomes[id] ? 'Observed in this run' : 'Not yet proved'}</span></div>
      <p>{description}</p>
    </li>)}</ol>
    {loading && <p role="status">Reading boundary evidence…</p>}
    {error && <div role="alert">
      <p>{errorStatus === 401 || errorStatus === 403
        ? 'Sign in with an Operator account to inspect cross-principal evidence.'
        : 'Boundary evidence is unavailable. No outcome can be established from this read.'}</p>
      {(errorStatus === 401 || errorStatus === 403) && <Link className="govern-evidence-link" to="/signin?returnTo=%2Fobservatory%2Fgovern%2Fverification">Sign in to inspect the five outcomes</Link>}
    </div>}
    {!loading && !error && !run && <p role="status">No five-outcome run is recorded. Complete the Workshop Studio Lab 4 proof to populate this view. Deployment configuration alone does not prove enforcement.</p>}
    {run && <>
      <label className="boundary-run-select">Evidence run
        <select aria-label="Evidence run" value={run.runId} onChange={event => setSelectedId(event.target.value)}>
          {runs.map(item => <option value={item.runId} key={item.runId}>{new Date(item.observedAt).toLocaleString()} · {item.runId}</option>)}
        </select>
      </label>
      <p role="status"><strong>{run.complete ? 'All five outcomes and controls held.' : 'This proof is incomplete.'}</strong> Each snapshot was measured after its invocation. No missing evidence is treated as zero.</p>
      <div className="boundary-table-scroll" role="region" aria-label="Recorded boundary outcomes" tabIndex={0}>
        <table className="boundary-table">
          <thead><tr><th scope="col">Attempt</th><th scope="col">Control / outcome</th><th scope="col">Tool executed</th><th scope="col">Data changed</th><th scope="col">Response</th></tr></thead>
          <tbody>{[...run.attempts].reverse().map(attempt => <tr key={attempt.id}>
            <th scope="row">{attempt.case}<small>{attempt.principal ?? 'No verified principal'}</small></th>
            <td>{attempt.control}{attempt.contradiction && <p role="alert">Contradiction: {attempt.contradiction}</p>}</td>
            <td>{fact(attempt.toolExecuted)}</td><td>{fact(attempt.dataChanged)}</td>
            <td>{attempt.output === 'SUPPRESSED' ? 'Suppressed' : attempt.output === 'RETURNED' ? 'Returned' : 'Not established'}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="boundary-caution">Suppression is not rollback. Reconcile the existing operation key before retrying. Replay may add an audit attempt while retaining one business effect.</p>
      <p className="boundary-caution">Data changed refers to business rows. A refused request can retain an unfinished idempotency claim; its measured count appears below.</p>
      <details><summary>Inspect correlation keys and database counts</summary>
        {run.attempts.map(attempt => <article className="boundary-record" key={attempt.id}>
          <h3>{attempt.case}</h3>
          <dl><dt>Invocation</dt><dd><code>{attempt.invocationId}</code></dd>
            <dt>Operation key</dt><dd><code>{attempt.operationKey}</code></dd>
            <dt>Tool</dt><dd><code>{attempt.tool}</code></dd>
            <dt>Authentication / authorization</dt><dd>{attempt.authentication} / {attempt.authorization}</dd>
            <dt>Execution / claimed / committed / domain / inventory rows</dt>
            <dd><code>{[attempt.database.executionRows, attempt.database.writeRows, attempt.database.committedRows, attempt.database.domainRows, attempt.database.ledgerRows].map(v => v ?? '?').join(' / ')}</code></dd>
            <dt>Matching unfinished claim rows</dt><dd>{attempt.database.pendingClaimRows ?? 'Not measured'}</dd>
          </dl>
        </article>)}
      </details>
    </>}
  </section>;
}
