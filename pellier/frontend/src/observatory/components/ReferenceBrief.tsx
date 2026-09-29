import { Link } from 'react-router-dom';
import { readLabProgress, resumeHref } from '../../shared/labProgress';
import { LAB_EXERCISES } from '../labs/labCatalog';
import { GOVERNED_SOURCE, REFERENCES, labGroupFor, type ReferenceId } from './referenceCatalog';
import { REFERENCE_DIAGNOSTICS } from './referenceDiagnostics';
import './ReferenceBrief.css';

/**
 * One card per reference: the question it answers and its evidence boundary
 * stay open; how to inspect, failure cases and the implementation open on
 * demand. A reference inside a lab returns from its page title instead.
 */
export default function ReferenceBrief({ id }: { id: ReferenceId }) {
  const reference = REFERENCES[id];
  const saved = readLabProgress();
  const lab = LAB_EXERCISES.find(item => item.id === (saved?.lab ?? reference.lab))!;
  return <section className="reference-brief" aria-label="How this reference supports the labs">
    <p className="reference-brief-role">{reference.role}</p>
    <h2>{reference.question}</h2>
    <p className="reference-brief-limit"><strong>Evidence boundary</strong>{reference.limit}</p>
    <div className="reference-brief-more">
      <details className="reference-brief-chip">
        <summary>How to inspect</summary>
        <p className="reference-brief-inspect">{reference.inspect}</p>
      </details>
      <details className="reference-brief-chip reference-diagnostics">
        <summary>Failure cases</summary>
        <p className="reference-diagnostics-intro">Use these questions to interpret your lab records. They describe possible cases, not results observed in this deployment.</p>
        <ol className="reference-diagnostics-list">
          {REFERENCE_DIAGNOSTICS[id].map(item => <li key={item.observation}>
            <h3>{item.observation}</h3>
            <dl>
              <div><dt>Mechanism</dt><dd>{item.mechanism}</dd></div>
              <div><dt>Evidence to inspect</dt><dd>{item.evidence}</dd></div>
            </dl>
          </li>)}
        </ol>
      </details>
      <details className="reference-brief-chip">
        <summary>Implementation</summary>
        <ul>
          {reference.sources.map(path => <li key={path}><a href={`${GOVERNED_SOURCE}/${path}`} target="_blank" rel="noopener noreferrer"><code>{path}</code></a></li>)}
        </ul>
      </details>
      {labGroupFor(id) ? null : (
        <Link className="reference-brief-return" to={saved ? resumeHref(saved) : `/observatory/workbench?lab=${lab.id}`}>
          Return to Lab {Number(lab.number)} in Workbench
        </Link>
      )}
    </div>
  </section>;
}
