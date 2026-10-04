import React from 'react'
import { redirectToSignIn } from '../../utils/auth'

interface Props {
  /** What signing in gives the staff member, phrased as the outcome. */
  unlocks?: string
}

/**
 * The recovery action on a staff-only surface.
 *
 * Nadia signs in through the normal Cognito sign-in page, typing her
 * password. There is no one-click staff chip on purpose: approving a store
 * credit is the action Lab 4 says only staff can take, and a chip would hand
 * it to anyone who can open the app. `redirectToSignIn` returns to the exact
 * record she asked for.
 */
const OperatorSignInAction: React.FC<Props> = ({ unlocks }) => (
  <button
    type="button"
    className="op-button"
    onClick={() => redirectToSignIn('email')}
    data-testid="operator-state-sign-in"
  >
    {unlocks ? `Sign in to ${unlocks}` : 'Sign in'}
  </button>
)

export default OperatorSignInAction
