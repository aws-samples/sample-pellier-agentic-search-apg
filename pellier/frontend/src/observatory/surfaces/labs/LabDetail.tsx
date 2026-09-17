import { useEffect, useRef } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { LAB_EXERCISES, findLabExercise } from '../../labs/labCatalog';
import guides from '../../labs/generated/workshopGuides.json';
import GuideContent, { type GuideNode } from './GuideContent';
import './Labs.css';
import './LabGuide.css';

interface Guide {
  title: string;
  sourcePage: string;
  sourceSha256: string;
  sections: { id: string; text: string }[];
  nodes: GuideNode[];
}

const pages = guides.pages as Record<string, Guide>;

/** Studio owns the instructions; the bundled copy works within the event app. */
export default function LabDetail() {
  const { exerciseId, guideId } = useParams<{ exerciseId: string; guideId: string }>();
  const id = exerciseId ?? guideId ?? '';
  const exercise = findLabExercise(exerciseId);
  const guide = pages[id];
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (guide) {
      document.title = guide.title + ' · Pellier Observatory';
      heading.current?.focus({ preventScroll: true });
    }
  }, [guide]);

  if (!guide) return <div className="lab-not-found">
    <h1>Guide not found</h1><p>Choose one of the four governed labs.</p>
    <Link to="/observatory">Return to Lab Collection</Link>
  </div>;

  return <article className="lab-guide" data-testid="lab-detail">
    <header className="lab-guide-header">
      <Link to="/observatory"><ArrowLeft size={16} aria-hidden="true" /> Lab Collection</Link>
      <p className="lab-guide-eyebrow">100-minute governed workshop · Participant guide</p>
      <h1 ref={heading} tabIndex={-1} className="observatory-page-title font-display">{guide.title}</h1>
      <p>Build in Code Editor, inspect the result in Pellier, and keep the evidence for your run.</p>
      {exercise && <Link className="lab-action-primary" to={'/observatory/workbench?lab=' + exercise.id}>
        Open Lab {Number(exercise.number)} in Workbench <ArrowRight size={16} aria-hidden="true" />
      </Link>}
    </header>
    <div className="lab-guide-layout">
      <nav className="lab-guide-navigation" aria-label="Workshop guides">
        <a href="#guide-steps">Jump to the guide</a>
        <Link to="/observatory/guide/introduction" aria-current={id === 'introduction' ? 'page' : undefined}>Introduction</Link>
        {LAB_EXERCISES.map(lab => <Link key={lab.id} to={'/observatory/labs/' + lab.id} aria-current={id === lab.id ? 'page' : undefined}>
          <span>Lab {Number(lab.number)} · {lab.anchorName}</span>{lab.shortTitle}
        </Link>)}
        <Link to="/observatory/guide/summary" aria-current={id === 'summary' ? 'page' : undefined}>Summary and cleanup</Link>
        <details className="lab-guide-on-page">
          <summary>On this page</summary>
          {guide.sections.map(section => <a key={section.id} href={'#' + section.id}>{section.text}</a>)}
        </details>
        <Link to="/observatory/guide/background">Architecture background</Link>
        <Link to="/observatory/guide/reference">Technical reference</Link>
      </nav>
      <div className="lab-guide-content" id="guide-steps" tabIndex={-1}>
        <GuideContent nodes={guide.nodes} />
        <footer className="lab-guide-source">
          <strong>Guide provenance</strong>
          <p>Bundled from the Workshop Studio participant guide. Instructions and reference images do not certify a completed run.</p>
          <details><summary>Source reference</summary><code>{guide.sourcePage}</code><code>SHA-256 {guide.sourceSha256}</code></details>
        </footer>
      </div>
    </div>
  </article>;
}
