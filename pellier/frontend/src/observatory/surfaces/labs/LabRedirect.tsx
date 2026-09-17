import { Navigate, useParams } from 'react-router-dom';
import { findLabExercise } from '../../labs/labCatalog';

/** Old guide bookmarks retain their lab context; Studio owns the instructions. */
export default function LabRedirect() {
  const { exerciseId } = useParams<{ exerciseId: string }>();
  const exercise = findLabExercise(exerciseId);
  return <Navigate replace to={exercise ? `/observatory/workbench?lab=${exercise.id}` : '/observatory'} />;
}
