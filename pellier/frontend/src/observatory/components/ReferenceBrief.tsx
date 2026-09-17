import { Link } from 'react-router-dom';
import { readLabProgress, resumeHref } from '../../shared/labProgress';
import { LAB_EXERCISES } from '../labs/labCatalog';
import { GOVERNED_SOURCE, REFERENCES, type ReferenceId } from './referenceCatalog';
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
