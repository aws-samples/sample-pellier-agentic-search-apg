import type { LabExercise } from '../../labs/labCatalog';
import './LabBuildConnection.css';

/** Source orientation only. Workshop Studio owns the tasks and proof commands. */
export default function LabBuildConnection({ exercise }: { exercise: LabExercise }) {
  const { buildConnection } = exercise;
  return <details className="lab-build-connection" key={exercise.id}>
    <summary>Connect your edit to the app</summary>
    <div>
      <p className="lab-build-path">{buildConnection.requestPath}</p>
      <p>{buildConnection.observableChange}</p>
      <ul aria-label="Files you edit">
        {buildConnection.files.map(file => <li key={file}><code>{file}</code></li>)}
      </ul>
      <p><strong>Challenge the result.</strong> {buildConnection.counterexample}</p>
    </div>
  </details>;
}
