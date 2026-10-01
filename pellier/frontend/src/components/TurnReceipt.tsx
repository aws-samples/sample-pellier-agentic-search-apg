/**
 * TurnReceipt: the copyable turn reference plus two badges that mean
 * different things.
 *
 *   Response complete   the stream finished (a transport fact)
 *   Evidence recorded   the durable ledger for this turn_id reports every
 *                       required sufficiency check satisfied (a data fact)
 *
 * The second badge is fetched from the principal-scoped ledger endpoint and
 * never inferred from the first. While the fetch is in flight, or when the
 * caller has no verified session to read a ledger with, the receipt says
 * nothing about evidence.
 */
import { useEffect, useState } from 'react'
import { Check, Copy, FileCheck2, FileWarning } from 'lucide-react'
import { useOptionalAuth } from '../contexts/AuthContext'
import { CHAT_TRUST } from '../copy'
import {
  fetchTurnEvidenceLedger,
  requiredEvidenceSatisfied,
} from '../services/evidenceLedger'
import '../styles/turn-receipt.css'

interface TurnReceiptProps {
  /** A correlation reference for older messages without a stable turn id. */
  reference: string
  /** Stable per-turn id used to read the evidence ledger. */
  turnId?: string | null
  /** True once the stream has finished for this turn. */
  complete?: boolean
  surface?: 'pellier' | 'observatory'
}

function shortReference(reference: string): string {
  if (reference.length <= 20) return reference
  return `${reference.slice(0, 10)}...${reference.slice(-6)}`
}

/**
 * Whether the evidence ledger for `turnId` is fully recorded.
 *
 * Resolves to `null` while unknown: before the fetch settles, when there is
 * no turn id, and when the caller cannot read a principal-scoped ledger.
 */
function useEvidenceRecorded(
  turnId: string | null | undefined,
  enabled: boolean,
): boolean | null {
  const isAuthenticated = useOptionalAuth()?.isAuthenticated ?? false
  const [recorded, setRecorded] = useState<boolean | null>(null)

  useEffect(() => {
    setRecorded(null)
    if (!enabled || !turnId || !isAuthenticated) return
    const controller = new AbortController()
    fetchTurnEvidenceLedger(turnId, controller.signal)
      .then((ledger) => {
        if (controller.signal.aborted) return
        setRecorded(
          ledger ? requiredEvidenceSatisfied(ledger.evidenceSufficiency) : null,
        )
      })
      .catch(() => {
        if (!controller.signal.aborted) setRecorded(null)
      })
    return () => controller.abort()
  }, [enabled, turnId, isAuthenticated])

  return recorded
}

export default function TurnReceipt({
  reference,
  turnId,
  complete = true,
  surface = 'pellier',
}: TurnReceiptProps) {
  const [copied, setCopied] = useState(false)
  const evidenceRecorded = useEvidenceRecorded(turnId, complete)
  const effectiveReference = turnId || reference
  const isTurnReference = Boolean(turnId) || reference.startsWith('turn-')
  const copyLabel = isTurnReference ? CHAT_TRUST.COPY_REFERENCE : CHAT_TRUST.COPY_TRACE_REFERENCE

  useEffect(() => {
    if (!copied) return
    const timeout = window.setTimeout(() => setCopied(false), 1800)
    return () => window.clearTimeout(timeout)
  }, [copied])

  const copyReference = async () => {
    try {
      await navigator.clipboard.writeText(effectiveReference)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = effectiveReference
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    setCopied(true)
  }

  return (
    <div
      className={`turn-receipt turn-receipt--${surface}`}
      data-testid="turn-receipt"
      data-complete={complete ? 'true' : 'false'}
      /* Three states, not two. `false` means the ledger was read and a
         required check is not satisfied; `null` means nothing was read.
         Collapsing them made a refuted turn look like an unexamined one. */
      data-evidence={
        evidenceRecorded === true
          ? 'recorded'
          : evidenceRecorded === false
            ? 'incomplete'
            : 'unknown'
      }
    >
      <span className="turn-receipt__badges">
        {complete ? (
          <span className="turn-receipt__status" data-testid="turn-response-complete">
            <Check size={13} aria-hidden="true" />
            {CHAT_TRUST.RESPONSE_COMPLETE}
          </span>
        ) : null}
        {evidenceRecorded === true ? (
          <span
            className="turn-receipt__status turn-receipt__status--evidence"
            data-testid="turn-evidence-recorded"
          >
            <FileCheck2 size={13} aria-hidden="true" />
            {CHAT_TRUST.EVIDENCE_RECORDED}
          </span>
        ) : null}
        {/* Stated on the inspection surface only. An operator reading the
            Observatory needs to know the ledger was checked and came back
            short; the storefront's shopper is owed the answer, not a
            governance verdict, and the absent badge is already honest there. */}
        {evidenceRecorded === false && surface === 'observatory' ? (
          <span
            className="turn-receipt__status turn-receipt__status--incomplete"
            data-testid="turn-evidence-incomplete"
          >
            <FileWarning size={13} aria-hidden="true" />
            {CHAT_TRUST.EVIDENCE_INCOMPLETE}
          </span>
        ) : null}
      </span>
      <code title={effectiveReference}>{shortReference(effectiveReference)}</code>
      <button
        type="button"
        className="turn-receipt__copy"
        onClick={() => void copyReference()}
        aria-label={
          copied ? CHAT_TRUST.COPIED_REFERENCE : copyLabel
        }
        title={
          copied ? CHAT_TRUST.COPIED_REFERENCE : copyLabel
        }
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  )
}
