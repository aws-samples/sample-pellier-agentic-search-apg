/**
 * The Builder view's turn id: the key that joins an answer to its evidence.
 *
 * The backend mints it on `turn_start`. The same id is `turn_id` on the
 * turn's `pellier.tool_audit` rows, the `pellier.turn_id` attribute on its
 * spans in CloudWatch, and the source turn of any Operator review the turn
 * asked for. The line only names the key; the rows and spans are the proof.
 */
import { useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import LayerTag from './LayerTag'

const COPIED_MS = 1600

export default function TurnIdLine({ turnId }: { turnId: string }) {
  const [copied, setCopied] = useState(false)
  const idRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!copied) return undefined
    const timer = window.setTimeout(() => setCopied(false), COPIED_MS)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(turnId)
      setCopied(true)
    } catch {
      // The clipboard refused (no permission, or no secure context): select
      // the id instead, so the keyboard shortcut copies it.
      const node = idRef.current
      const selection = window.getSelection()
      if (!node || !selection) return
      const range = document.createRange()
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }

  const label = copied ? 'Turn id copied' : 'Copy turn id'
  return (
    <p className="tn-turn" data-testid="turn-id">
      <LayerTag>Turn</LayerTag>
      <code
        ref={idRef}
        className="tn-turn-id"
        title="This turn's tool_audit rows and CloudWatch spans carry this id"
      >
        {turnId}
      </code>
      <button type="button" className="tn-turn-copy" onClick={copy} aria-label={label} title={label}>
        {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      </button>
      <span className="gov-visually-hidden" role="status">{copied ? 'Turn id copied' : ''}</span>
    </p>
  )
}
