import { useState } from 'react';
import { Link } from 'react-router-dom';

import { readLabProgress, resumeHref } from '../../../shared/labProgress';
import { imageSrc } from '../../../utils/assetPath';
import WorkbenchResources from '../../components/WorkbenchResources';
import { LAB_EXERCISES } from '../../labs/labCatalog';
import { statusForExercise } from '../../labs/evidence';
import { useLabEvidence } from '../../labs/useLabEvidence';
import { EvidenceLoadNotice, LabStatusMark } from './LabShared';
import './Labs.css';

export default function LabsCatalog() {
  const { data, error, loading, reload } = useLabEvidence();
  const [resumePoint] = useState(readLabProgress);
  const resumeLab = LAB_EXERCISES.find((exercise) => exercise.id === resumePoint?.lab);

  return (
    <div className="labs-catalog" data-testid="labs-catalog">
      <header className="labs-catalog-hero">
        <div className="labs-catalog-hero-copy">
          <div>
            <p className="labs-catalog-eyebrow">One shop. Four engineering questions.</p>
            <h1 className="font-display">Governed Lab Collection</h1>
          </div>
          <div className="labs-catalog-orientation">
            <p>
              Can you trust the answer, find eligible products, carry context
              across conversations, and control who may act? Build those
              boundaries in order, using four customers at the same shop.
            </p>
            <div className="labs-catalog-start">
              <Link className="labs-catalog-primary" to={resumePoint ? resumeHref(resumePoint) : '/observatory/workbench?lab=grounded-inventory'}>
                {resumeLab ? `Resume Lab ${Number(resumeLab.number)}` : 'Start Lab 1'}
              </Link>
            </div>
          </div>
        </div>
      </header>

      <section className="labs-catalog-body" aria-labelledby="labs-catalog-heading">
        <div className="labs-catalog-intro">
          <div>
            <h2 id="labs-catalog-heading" className="font-display">Four technical labs</h2>
            <p>Follow the instructions in Workshop Studio and build in Code Editor. Open each lab here to run its scenario and inspect the evidence. Environment status describes available evidence; the Studio checks establish completion.</p>
          </div>
        </div>
        {error ? <EvidenceLoadNotice error={error} onRetry={reload} /> : null}
        <div className="labs-catalog-contact-sheet">
          {LAB_EXERCISES.map((exercise, index) => {
            const to = `/observatory/workbench?lab=${exercise.id}`;
            return (
              <article className="labs-catalog-card" data-lab={exercise.number} key={exercise.id} aria-labelledby={`collection-${exercise.id}`}>
                <Link to={to} tabIndex={-1} aria-hidden="true" className="labs-catalog-portrait-link">
                  <figure>
                    <img src={imageSrc(exercise.image)} width={exercise.imageWidth} height={exercise.imageHeight} alt="" loading={index < 2 ? 'eager' : 'lazy'} decoding="async" />
                    <figcaption><span>{exercise.anchorName}</span><span>Lab {Number(exercise.number)}</span></figcaption>
                  </figure>
                </Link>
                <div className="labs-catalog-card-copy">
                  <h3 id={`collection-${exercise.id}`}><Link to={to}>{exercise.title}</Link></h3>
                  <p className="labs-catalog-customer-need">{exercise.customerNeed}</p>
                  <p>{exercise.summary}</p>
                  <LabStatusMark status={statusForExercise(exercise, data)} loading={loading} discloseDetails />
                  <Link className="labs-catalog-card-open" to={to} aria-label={`Open Lab ${Number(exercise.number)} in Workbench`}>
                    Open Lab {Number(exercise.number)} in Workbench
                  </Link>
                  <Link className="labs-catalog-workbench-link" to={exercise.evidenceHref ?? `/observatory/proof-board#${exercise.proofCardIds[0]}`}>Inspect lab evidence</Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      <section className="labs-catalog-close" aria-labelledby="labs-close-heading">
        <div>
          <h2 id="labs-close-heading" className="font-display">Finish with a defensible architecture</h2>
          <p>Bring together the warehouse result, retrieval receipt, managed run, and five-outcome proof. Explain which layer owns each fact, which control acted, and what remains unknown. Return to Workshop Studio for the summary and cleanup instructions.</p>
        </div>
        <Link to="/observatory/proof-board">Review the workshop evidence</Link>
      </section>
      <WorkbenchResources collapsible defaultExpanded={false} />
    </div>
  );
}
