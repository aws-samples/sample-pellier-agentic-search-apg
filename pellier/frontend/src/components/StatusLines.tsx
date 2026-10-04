/**
 * StatusLines: three facts under the chat header, each from its own source.
 *
 *   Scenario           the persona context (a workshop scenario, not a login)
 *   Verified identity  the Cognito session from the auth context
 *   Execution path     the rail reported by the last completed turn
 *
 * The rows are independent on purpose. A shopper can pick Marco without any
 * Cognito session, an operator can be signed in with no scenario chosen, and
 * neither says which rail will serve the next turn. Rendering the three side
 * by side is what stops one from being read as a proxy for another.
 */
import { useOptionalAuth } from '../contexts/AuthContext'
import { usePersona } from '../contexts/PersonaContext'
import { SCENARIO, STATUS_LINES } from '../copy'
import type { AgentChatMessage } from '../hooks/useAgentChat'

interface StatusLinesProps {
  /** The active thread; only the last completed turn's rail is read. */
  messages: ReadonlyArray<AgentChatMessage>
}

/** The rail of the newest assistant turn that reported one. */
function lastReportedRail(
  messages: ReadonlyArray<AgentChatMessage>,
): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'assistant') continue
    const rail = message.railDecision?.rail
    if (rail) return rail
  }
  return null
}

export default function StatusLines({ messages }: StatusLinesProps) {
  const { persona } = usePersona()
  const auth = useOptionalAuth()
  const identity =
    auth?.isAuthenticated && auth.user
      ? auth.user.username || auth.user.givenName || auth.user.email || auth.user.sub
      : null
  // The method is a fact the server reported, never inferred from the name.
  const workshop = Boolean(auth?.isAuthenticated && auth.user?.signInMethod === 'workshop')
  const rail = lastReportedRail(messages)

  const rows: Array<{ label: string; value: string; known: boolean }> = [
    {
      label: STATUS_LINES.SCENARIO,
      value: persona?.display_name ?? SCENARIO.NONE_SELECTED,
      known: Boolean(persona),
    },
    {
      label: STATUS_LINES.VERIFIED_IDENTITY,
      value: identity
        ? workshop ? `${identity}, ${STATUS_LINES.WORKSHOP_SESSION}` : identity
        : STATUS_LINES.NOT_SIGNED_IN,
      known: Boolean(identity),
    },
    {
      label: STATUS_LINES.EXECUTION_PATH,
      value: rail ?? STATUS_LINES.EXECUTION_UNKNOWN,
      known: Boolean(rail),
    },
  ]

  return (
    <dl className="cd-status-lines" data-testid="status-lines">
      {rows.map((row) => (
        <div key={row.label} data-status-row data-known={row.known ? 'true' : 'false'}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}
