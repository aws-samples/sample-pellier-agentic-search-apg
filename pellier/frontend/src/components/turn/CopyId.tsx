/**
 * An id as a code chip with a copy control, so an engineer can paste it into
 * SQL or a CloudWatch query. The chip never breaks inside the id: a row of
 * chips wraps between them. When the clipboard refuses (no permission, or no
 * secure context) the id is selected instead, so the keyboard shortcut copies it.
 */
import { useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'

const COPIED_MS = 1600

/** Copy state and the copy action for one value, with the select-it fallback. */
export function useCopy(value: string) {
  const [copied, setCopied] = useState(false)
  const target = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!copied) return undefined
    const timer = window.setTimeout(() => setCopied(false), COPIED_MS)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      const node = target.current
      const selection = window.getSelection()
      if (!node || !selection) return
      const range = document.createRange()
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }
  return { copied, copy, target }
}

export interface CopyIdProps {
  value: string
  /** What the id names, for the control's accessible name: "audit row id". */
  noun: string
}

export default function CopyId({ value, noun }: CopyIdProps) {
  const { copied, copy, target } = useCopy(value)
  const label = copied ? `Copied ${noun}` : `Copy ${noun}`
  return (
    <span className="tn-chip tn-chip-id" data-testid="copy-id">
      <code ref={target} className="tn-chip-code">{value}</code>
      <button type="button" className="tn-copy" onClick={copy} aria-label={label} title={label}>
        {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      </button>
    </span>
  )
}
