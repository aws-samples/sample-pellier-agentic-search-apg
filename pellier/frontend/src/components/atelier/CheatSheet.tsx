/**
 * CheatSheet — the three-column rule grid at the bottom of Template A
 * (Skills, Evaluations) and Template B (Memory, Runtime) pages.
 *
 * Per the Atelier system rules, this appears only on Template A/B
 * pages — not on C (Network) or D (Schema), where the diagram /
 * schema is itself the cheat sheet.
 */
import type { ReactNode } from 'react'
import SectionEyebrow from './SectionEyebrow'

export interface CheatSheetCell {
  /** Mono small-caps key, shown above the name. */
  key: string
  /** Italic serif cell name (the distinguishing word — "Agents", "Shape", "Truth"). */
  name: string
  /** Italic serif question in quotes below the name. */
  question?: ReactNode
  /** Bullet-point list items — supports ReactNode for inline ``<em>``. */
  list: ReactNode[]
}

export interface CheatSheetProps {
  eyebrow?: string
  title: ReactNode
  cells: CheatSheetCell[]
}

export default function CheatSheet({ eyebrow, title, cells }: CheatSheetProps) {
  return (
    <section className="at-cheat">
      {eyebrow && <SectionEyebrow>{eyebrow}</SectionEyebrow>}
      <h2 className="at-cheat-title">{title}</h2>
      <div className="at-cheat-grid">
        {cells.map((cell) => (
          <div className="at-cheat-cell" key={cell.key}>
            <div className="at-cheat-key">{cell.key}</div>
            <div className="at-cheat-name">{cell.name}</div>
            {cell.question && <div className="at-cheat-q">{cell.question}</div>}
            <ul className="at-cheat-list">
              {cell.list.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
