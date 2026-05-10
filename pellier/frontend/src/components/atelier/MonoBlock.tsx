/**
 * MonoBlock — cream-2 monospace block for code snippets (Memory
 * sequence) and handoff blocks (Runtime → in / → out rows).
 *
 * Semantic sub-components for inline coloring:
 *
 *   <MonoBlock.Comment>  ink-4 italic       ``# a comment``
 *   <MonoBlock.Key>      burgundy           ``agentcore``
 *   <MonoBlock.Str>      green              ``"sess_4f"``
 *   <MonoBlock.Arrow>    burgundy bold      ``→``
 *
 * Usage:
 *
 *   <MonoBlock label="Handoff · orchestrator → specialist">
 *     <MonoBlock.Arrow>→</MonoBlock.Arrow> in: <MonoBlock.Str>"what's in stock"</MonoBlock.Str>
 *     <br/>
 *     <MonoBlock.Arrow>→</MonoBlock.Arrow> out: <MonoBlock.Key>agent</MonoBlock.Key>=recommendation
 *   </MonoBlock>
 */
import type { ReactNode } from 'react'

export interface MonoBlockProps {
  /** Optional dashed-rule label above the block. */
  label?: string
  children: ReactNode
}

function MonoBlock({ label, children }: MonoBlockProps) {
  return (
    <div className="at-mono">
      {label && <div className="at-mono-label">{label}</div>}
      {children}
    </div>
  )
}

MonoBlock.Comment = function Comment({ children }: { children: ReactNode }) {
  return <span className="at-mono-comment">{children}</span>
}

MonoBlock.Key = function Key({ children }: { children: ReactNode }) {
  return <span className="at-mono-key">{children}</span>
}

MonoBlock.Str = function Str({ children }: { children: ReactNode }) {
  return <span className="at-mono-str">{children}</span>
}

MonoBlock.Arrow = function Arrow({ children }: { children: ReactNode }) {
  return <span className="at-mono-arrow">{children}</span>
}

export default MonoBlock
