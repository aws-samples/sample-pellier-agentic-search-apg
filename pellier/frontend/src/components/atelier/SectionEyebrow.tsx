/**
 * SectionEyebrow — the small burgundy pill with leading dot used above
 * every section on every architecture page. Standalone version (use
 * this when the section isn't wrapped in a ``SectionFrame``).
 */
import type { ReactNode } from 'react'

export default function SectionEyebrow({ children }: { children: ReactNode }) {
  return <div className="at-section-eyebrow">{children}</div>
}
