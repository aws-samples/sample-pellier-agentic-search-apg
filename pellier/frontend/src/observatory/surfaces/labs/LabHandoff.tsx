import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { LAB_EXERCISES, type LabExercise } from '../../labs/labCatalog';
import './LabHandoff.css';

/** A reading checkpoint, never an inferred lab-completion badge. */
export default function LabHandoff({ exercise }: { exercise: LabExercise }) {
  const next = LAB_EXERCISES[LAB_EXERCISES.findIndex(lab => lab.id === exercise.id) + 1];

  return <section className="lab-handoff" aria-labelledby="lab-handoff-title">
    <div>
      <p className="lab-handoff-eyebrow">Before you continue</p>
      <h2 id="lab-handoff-title" className="font-display">Defend the result</h2>
      <p>{exercise.decisionPrompt}</p>
      <details>
        <summary>Evidence to keep for Lab {Number(exercise.number)}</summary>
        <p>{exercise.evidenceAssertion}</p>
        <Link to={`/observatory/proof-board#${exercise.proofCardIds[0]}`}>Inspect Lab {Number(exercise.number)} evidence</Link>
      </details>
    </div>
    <div className="lab-handoff-next">
      <p>{exercise.nextBoundary}</p>
      <p className="lab-handoff-condition">Complete the checks in Workshop Studio before moving on. A finished conversation alone does not complete the lab.</p>
      <Link to={next ? `/observatory/workbench?lab=${next.id}` : '/observatory/proof-board'}>
        {next ? `Open Lab ${Number(next.number)} · ${next.anchorName}` : 'Review the workshop evidence'}
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </div>
  </section>;
}
