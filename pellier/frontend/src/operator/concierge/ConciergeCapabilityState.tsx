/**
 * The pane's operating state, from live backend capability truth.
 *
 * A deliberately closed governance rail is a legitimate operating state, not a
 * fault. So this is an eyebrow and a sentence, never a red banner: "Disconnected",
 * "Offline" or "Error" would misdescribe a system that is working exactly as
 * configured and would alarm an operator who can still do most of their job.
 *
 * Three causes stay visually distinct, because they need different responses:
 *
 *   read only              governance closed the write rail on purpose
 *   capability unverified  the control plane could not be read
 *   conversation problem   session data failed to load
 */

import React, { useState } from 'react'

import {
  CAPABILITY_LABELS,
  governedUnavailableCopy,
} from '../../services/operatorCapabilities'
import type { CapabilitySnapshot, CapabilityState } from '../../services/operator'
import type { ConciergeConfig } from '../../services/operatorConcierge'

/** Governed writes, in the order an operator thinks about them. */
const GOVERNED_ORDER = ['initiate_return', 'escalate_to_human', 'issue_credit'] as const

const GOVERNED_LABELS: Record<string, string> = {
  initiate_return: 'Initiate return',
  escalate_to_human: 'Escalate to human',
  issue_credit: 'Store credit',
}

interface Props {
  status: string
  capabilities: CapabilitySnapshot | null
  config: ConciergeConfig | null
}

const ConciergeCapabilityState: React.FC<Props> = ({ status, capabilities, config }) => {
  const [open, setOpen] = useState(false)

  if (status === 'loading') {
    return (
      <div className="operator-concierge-state" data-state="loading"
           data-testid="operator-concierge-state">
        <span className="operator-concierge-state-eyebrow">Reading capability</span>
        {/* Not "unavailable". Governed state has not been read yet, and this surface's
            whole argument is that unverified and closed are different facts. */}
        <p className="operator-concierge-state-copy">
          Confirming which governed actions are currently available.
        </p>
      </div>
    )
  }

  if (status === 'capability_unverified' || !capabilities) {
    return (
      <div className="operator-concierge-state" data-state="unverified"
           data-testid="operator-concierge-state">
        <span className="operator-concierge-state-eyebrow">Capability unverified</span>
        <p className="operator-concierge-state-copy">
          Governed action state could not be confirmed, so no action is offered.
          Client investigation remains available.
        </p>
      </div>
    )
  }

  if (status === 'conversation_unavailable') {
    return (
      <div className="operator-concierge-state" data-state="conversation"
           data-testid="operator-concierge-state">
        <span className="operator-concierge-state-eyebrow">Conversation unavailable</span>
        <p className="operator-concierge-state-copy">
          This client&rsquo;s Concierge history could not be loaded.
        </p>
      </div>
    )
  }

  if (status === 'config_unavailable') {
    // Capabilities can load successfully even when config fails (they're
    // fetched in parallel in useOperatorConcierge), so without this branch
    // execution fell through to the "ready"/"read-only" render below using
    // whatever capabilities did arrive -- contradicting the recovery banner
    // OperatorConcierge renders lower on the same pane for this exact
    // status ("The investigation service configuration could not be
    // read."). Matching that wording here keeps the pane from disagreeing
    // with itself.
    return (
      <div className="operator-concierge-state" data-state="conversation"
           data-testid="operator-concierge-state">
        <span className="operator-concierge-state-eyebrow">Configuration unavailable</span>
        <p className="operator-concierge-state-copy">
          The investigation service configuration could not be read.
        </p>
      </div>
    )
  }

  const closed = !capabilities.governedActionsAvailable
  const unavailableCopy = governedUnavailableCopy(capabilities)

  return (
    <div
      className="operator-concierge-state"
      data-state={closed ? 'read-only' : 'ready'}
      data-testid="operator-concierge-state"
    >
      <span className="operator-concierge-state-eyebrow">
        {closed ? 'Read only' : 'Ready'}
      </span>
      <p className="operator-concierge-state-copy">
        {closed ? (
          <>
            {unavailableCopy.title}. {unavailableCopy.detail}
          </>
        ) : (
          <>Client context available.</>
        )}
      </p>
      {config && !config.composerEnabled ? (
        <p className="operator-concierge-state-copy">{config.note}</p>
      ) : null}

      {/* Secondary by design. The pane must not read as an IAM console. */}
      <button
        type="button"
        className="operator-concierge-state-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        data-testid="operator-concierge-capability-toggle"
      >
        {open ? 'Hide action detail' : 'Action detail'}
      </button>

      {open ? (
        <dl className="operator-concierge-capabilities"
            data-testid="operator-concierge-capabilities">
          {GOVERNED_ORDER.map((tool) => {
            const entry = capabilities.capabilities[tool]
            if (!entry) return null
            return (
              <div className="operator-concierge-capability" key={tool}>
                <dt>{GOVERNED_LABELS[tool] ?? tool}</dt>
                <dd data-capability-state={entry.state}>
                  {CAPABILITY_LABELS[entry.state as CapabilityState] ?? entry.state}
                </dd>
              </div>
            )
          })}
        </dl>
      ) : null}
    </div>
  )
}

export default ConciergeCapabilityState
