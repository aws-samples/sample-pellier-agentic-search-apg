/**
 * A copy control for an identifier a person pastes into SQL, such as a write
 * key. Mirrors the Builder view's turn id: the value stays selectable text,
 * and when the clipboard refuses, the value is selected so the keyboard
 * shortcut copies it.
 */
import { Check, Copy } from 'lucide-react'
import React, { useEffect, useRef, useState } from 'react'

const COPIED_MS = 1600

interface Props {
  value: string
  /** Names the value for assistive technology: "Copy write key". */
  noun: string
}

const CopyValue: React.FC<Props> = ({ value, noun }) => {
  const [copied, setCopied] = useState(false)
  const valueRef = useRef<HTMLElement>(null)

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
      const node = valueRef.current
      const selection = window.getSelection()
      if (!node || !selection) return
      const range = document.createRange()
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }

  const label = copied ? `${noun} copied` : `Copy ${noun}`
  return (
    <span className="op-copy" data-testid="operator-copy-value">
      <code ref={valueRef} className="op-copy-value">{value}</code>
      <button type="button" className="op-copy-button" onClick={() => void copy()} aria-label={label} title={label}>
        {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      </button>
      <span className="gov-visually-hidden" role="status">{copied ? `${noun} copied` : ''}</span>
    </span>
  )
}

export default CopyValue
