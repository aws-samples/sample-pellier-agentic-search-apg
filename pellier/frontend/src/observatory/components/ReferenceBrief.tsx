import { Link } from 'react-router-dom';
import { readLabProgress, resumeHref } from '../../shared/labProgress';
import { LAB_EXERCISES } from '../labs/labCatalog';
import { GOVERNED_SOURCE, REFERENCES, type ReferenceId } from './referenceCatalog';
import { REFERENCE_DIAGNOSTICS } from './referenceDiagnostics';
import './ReferenceBrief.css';

/** Navigation state remembers a place, never a lab result or an identity. */
export function referenceReturnHref(): string {
  const saved = readLabProgress();
  return saved ? `${resumeHref(saved)}#resources` : '/observatory#resources';
}

export default function ReferenceBrief({ id }: { id: ReferenceId }) {
  const reference = REFERENCES[id];
  const saved = readLabProgress();
  const lab = LAB_EXERCISES.find(item => item.id === (saved?.lab ?? reference.lab))!;
  return <section className="reference-brief" aria-label="How this reference supports the labs">
    <p className="reference-brief-role">{reference.role}</p>
    <h2>{reference.question}</h2>
    <div className="reference-brief-reading">
      <p><strong>Inspect</strong>{reference.inspect}</p>
      <p><strong>Evidence boundary</strong>{reference.limit}</p>
    </div>
    <details className="reference-diagnostics">
      <summary>Reason through failure cases</summary>
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
    <footer>
      <Link to={saved ? resumeHref(saved) : `/observatory/workbench?lab=${lab.id}`}>
        Return to Lab {Number(lab.number)} in Workbench
      </Link>
      <details><summary>Read the implementation</summary><ul>
        {reference.sources.map(path => <li key={path}><a href={`${GOVERNED_SOURCE}/${path}`} target="_blank" rel="noopener noreferrer"><code>{path}</code></a></li>)}
      </ul></details>
    </footer>
  </section>;
}
