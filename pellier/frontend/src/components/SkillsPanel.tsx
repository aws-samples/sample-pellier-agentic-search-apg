/**
 * SkillsPanel — Atelier Architecture tab Skills view.
 *
 * Consumes the shared ``atelier/`` primitives (DetailPageShell,
 * SectionFrame, CheatSheet, LiveStrip, StatusBadge). The Skills
 * page is the visual contract — every other architecture page
 * mirrors the same shell + primitives.
 *
 * Page structure:
 *   1. DetailPageShell — crumb, title, subtitle, meta strip
 *   2. TriangleSection — agents / tools / skills mental model
 *   3. Library + live log two-column layout
 *      - Library: SkillLibraryCard[] (Active / Considered / Dormant)
 *      - Live log: the router's routing decision for this turn
 *   4. ImpactSection — before/after static teaching example (v1)
 *   5. CheatSheet — three-layer cheat sheet (agents/tools/skills)
 *   6. SkillModal (conditional) — renders the skill body markdown
 */
import { useEffect, useMemo, useState } from 'react'
import MarkdownMessage from './MarkdownMessage'
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  StatusBadge,
} from './atelier'
import type { SkillRouting } from '../hooks/useAgentChat'
import '../styles/skills-panel.css'

interface SkillMeta {
  name: string
  display_name: string
  description: string
  version: string
  token_estimate: number
  body: string
  path: string
}

interface SkillsPanelProps {
  /** The most recent turn's routing decision; drives the library state. */
  routing: SkillRouting | null
  /** The user query that triggered the current routing, for the log. */
  userMessage: string | null
}

type SkillState = 'active' | 'considered' | 'dormant'

function resolveState(
  name: string,
  routing: SkillRouting | null,
): SkillState {
  if (!routing) return 'dormant'
  if (routing.loaded_skills.includes(name)) return 'active'
  if (routing.considered.some((c) => c.name === name)) return 'considered'
  return 'dormant'
}

export default function SkillsPanel({
  routing,
  userMessage,
}: SkillsPanelProps) {
  const [skills, setSkills] = useState<SkillMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSkill, setSelectedSkill] = useState<SkillMeta | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/atelier/skills')
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setSkills(data.skills || [])
      } catch {
        // Non-fatal — library card renders empty state.
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const activeCount = routing?.loaded_skills.length ?? 0
  const turnElapsedMs = routing?.elapsed_ms ?? 0
  const tokensAdded = useMemo(() => {
    if (!routing) return 0
    return routing.loaded_skills
      .map((name) => skills.find((s) => s.name === name)?.token_estimate ?? 0)
      .reduce((a, b) => a + b, 0)
  }, [routing, skills])

  return (
    <>
      <DetailPageShell
        crumb={['Atelier', 'Architecture', 'Skills']}
        title={
          <>
            Skills, <em>at the boutique.</em>
          </>
        }
        subtitle="Domain expertise, loaded only when the conversation needs it. Skills don't pick products and they don't fetch data — they shape how the agent thinks and writes about a topic."
        meta={[
          { label: 'Active', value: `${activeCount} of ${skills.length || '—'}` },
          { label: 'This turn', value: turnElapsedMs ? `${turnElapsedMs} ms` : '—' },
          { label: 'Tokens added', value: tokensAdded || '—' },
          { label: 'Library version', value: 'v1.0' },
        ]}
      >
        {/* ---- Triangle ---- */}
        <TriangleSection />

        {/* ---- Library + Live log ---- */}
        <section className="sk-layout">
          <div className="sk-col">
            <div>
              <div className="sk-col-head">
                <div className="sk-col-eyebrow">The library</div>
                <div className="sk-col-meta">
                  /skills · {skills.length} available
                </div>
              </div>
              <h2 className="sk-col-title">
                What's <em>on the shelf.</em>
              </h2>
              <p className="sk-col-sub">
                Each skill is a folder under{' '}
                <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>
                  /skills/
                </span>{' '}
                — a{' '}
                <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>
                  SKILL.md
                </span>{' '}
                with optional helper files. New ones drop in without code changes.
              </p>
            </div>

            {loading ? (
              <div className="sk-empty-log">Loading the library…</div>
            ) : skills.length === 0 ? (
              <div className="sk-empty-log">
                No skills registered yet. Drop a SKILL.md into /skills/
                and restart the server.
              </div>
            ) : (
              skills.map((s) => (
                <SkillLibraryCard
                  key={s.name}
                  skill={s}
                  state={resolveState(s.name, routing)}
                  onOpen={() => setSelectedSkill(s)}
                />
              ))
            )}
          </div>

          <div className="sk-col">
            <div>
              <div className="sk-col-head">
                <div className="sk-col-eyebrow">Live · this turn</div>
                <div className="sk-col-meta">
                  {routing
                    ? `${routing.loaded_skills.length} loaded · ${routing.elapsed_ms}ms`
                    : 'awaiting first turn'}
                </div>
              </div>
              <h2 className="sk-col-title">
                What loaded, <em>and why.</em>
              </h2>
              <p className="sk-col-sub">
                For every turn, the skill router decides which skills the
                conversation needs. Routing is one short LLM call against
                the skill library's{' '}
                <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>
                  description
                </span>{' '}
                field.
              </p>
            </div>

            <LiveActivationLog
              routing={routing}
              userMessage={userMessage}
              tokensAdded={tokensAdded}
            />
          </div>
        </section>

        {/* ---- Before / After impact (static v1) ---- */}
        <ImpactSection />

        {/* ---- Three-layer cheat sheet (shared component) ---- */}
        <CheatSheet
          eyebrow="When in doubt"
          title={
            <>
              Three layers, <em>three questions.</em>
            </>
          }
          cells={[
            {
              key: 'AGENTS',
              name: 'Who handles it?',
              question: <em>"Which specialist owns this turn?"</em>,
              list: [
                'Has its own system prompt',
                'Decides what to do next',
                'Can hand off to other agents',
                <>
                  <em>Add when</em> a new role is needed
                </>,
              ],
            },
            {
              key: 'TOOLS',
              name: 'What action runs?',
              question: <em>"Which function returns the data?"</em>,
              list: [
                'Typed inputs and outputs',
                'Deterministic, no opinions',
                'Cost: one function call',
                <>
                  <em>Add when</em> new data or action is needed
                </>,
              ],
            },
            {
              key: 'SKILLS',
              name: 'How do we think about it?',
              question: <em>"Which expert lens loads here?"</em>,
              list: [
                'Markdown + activation contract',
                'Loaded conditionally',
                'Cost: tokens, only when relevant',
                <>
                  <em>Add when</em> domain expertise is needed
                </>,
              ],
            },
          ]}
        />
      </DetailPageShell>

      {/* ---- Open SKILL.md modal ---- */}
      {selectedSkill && (
        <SkillModal
          skill={selectedSkill}
          onClose={() => setSelectedSkill(null)}
        />
      )}
    </>
  )
}


/* ---- Triangle section — uses SectionFrame ---- */
function TriangleSection() {
  return (
    <SectionFrame
      eyebrow="The mental model"
      title={
        <>
          Agents, tools, <em>skills.</em>
        </>
      }
      description="Three corners, three responsibilities. Every agent capability is some combination of the three. If you can't tell which one is doing the work, you've muddled them."
    >
      <div className="sk-tri-grid">
        <div>
          <svg
            className="sk-tri-svg"
            viewBox="0 0 360 280"
            xmlns="http://www.w3.org/2000/svg"
          >
            <line x1="180" y1="44" x2="76" y2="240" stroke="rgba(31,20,16,0.18)" strokeWidth="1" />
            <line x1="180" y1="44" x2="284" y2="240" stroke="rgba(31,20,16,0.18)" strokeWidth="1" />
            <line x1="76" y1="240" x2="284" y2="240" stroke="rgba(31,20,16,0.18)" strokeWidth="1" />

            <circle cx="180" cy="44" r="6" fill="#a8423a" />
            <text x="180" y="22" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" letterSpacing="2" fill="#a8423a" fontWeight="500">AGENTS</text>
            <text x="180" y="78" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="14" fill="rgba(31,20,16,0.66)">who</text>

            <circle cx="76" cy="240" r="6" fill="#a8423a" />
            <text x="76" y="265" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" letterSpacing="2" fill="#a8423a" fontWeight="500">TOOLS</text>
            <text x="76" y="225" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="14" fill="rgba(31,20,16,0.66)">what</text>

            <circle cx="284" cy="240" r="6" fill="#a8423a" />
            <text x="284" y="265" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" letterSpacing="2" fill="#a8423a" fontWeight="500">SKILLS</text>
            <text x="284" y="225" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="14" fill="rgba(31,20,16,0.66)">how</text>

            <text x="180" y="156" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontWeight="300" fontSize="42" letterSpacing="-1" fill="#1f1410">Pellier</text>
            <line x1="155" y1="170" x2="205" y2="170" stroke="#a8423a" strokeWidth="1" />
          </svg>
        </div>

        <div className="sk-tri-rows">
          <div className="sk-tri-row">
            <div className="sk-tri-label">
              <span className="sk-tri-key">WHO</span>
              Agents.
            </div>
            <div className="sk-tri-text">
              Autonomous specialists with their own system prompts and
              decision-making. Pellier ships <em>five</em>:{' '}
              <span className="sk-mono">orchestrator</span>,{' '}
              <span className="sk-mono">search</span>,{' '}
              <span className="sk-mono">recommendation</span>,{' '}
              <span className="sk-mono">pricing</span>,{' '}
              <span className="sk-mono">support</span>. They reason. They route.
            </div>
          </div>
          <div className="sk-tri-row">
            <div className="sk-tri-label">
              <span className="sk-tri-key">WHAT</span>
              Tools.
            </div>
            <div className="sk-tri-text">
              Discrete, deterministic functions an agent invokes. Typed
              inputs and outputs, no opinions.{' '}
              <span className="sk-mono">find_pieces</span>,{' '}
              <span className="sk-mono">get_whats_trending</span>,{' '}
              <span className="sk-mono">check_inventory</span>,{' '}
              <span className="sk-mono">get_pricing</span>.
            </div>
          </div>
          <div className="sk-tri-row">
            <div className="sk-tri-label">
              <span className="sk-tri-key">HOW</span>
              Skills.
            </div>
            <div className="sk-tri-text">
              Folders of domain expertise loaded into context when the
              conversation calls for them. <em>Not</em> a system prompt —
              small, scoped, conditional. Today:{' '}
              <span className="sk-mono">style-advisor</span> and{' '}
              <span className="sk-mono">gift-concierge</span>.
            </div>
          </div>
        </div>
      </div>
    </SectionFrame>
  )
}


/* ---- Skill library card — uses StatusBadge ---- */
function SkillLibraryCard({
  skill,
  state,
  onOpen,
}: {
  skill: SkillMeta
  state: SkillState
  onOpen: () => void
}) {
  const headline =
    skill.description.split('. ')[0].replace(/\.$/, '') + '.'
  const body = skill.description.slice(headline.length).trim()

  const statusLabel =
    state === 'active' ? 'Active · this turn'
    : state === 'considered' ? 'Considered'
    : 'Dormant'

  return (
    <article className={`sk-card ${state === 'active' ? 'sk-card-active' : ''}`}>
      <div className="sk-card-head">
        <div className="sk-card-head-left">
          <div className="sk-card-name-row">
            <span className="sk-card-name">{skill.name}</span>
            <span className="sk-card-version">v{skill.version}</span>
          </div>
          <div className="sk-card-headline">
            <em>{headline}</em>
          </div>
          <p className="sk-card-desc">{body || skill.description}</p>
        </div>
        <StatusBadge variant={state}>{statusLabel}</StatusBadge>
      </div>
      <div className="sk-card-divider" />
      <div className="sk-card-meta">
        <div className="sk-card-meta-left">
          <span>
            ~<span className="sk-card-meta-num">{skill.token_estimate}</span> tokens
          </span>
          <span>
            display · <span className="sk-card-meta-num">{skill.display_name}</span>
          </span>
        </div>
        <button type="button" className="sk-open-link" onClick={onOpen}>
          Open SKILL.md →
        </button>
      </div>
    </article>
  )
}

/* ---- Live activation log ---- */
function LiveActivationLog({
  routing,
  userMessage,
  tokensAdded,
}: {
  routing: SkillRouting | null
  userMessage: string | null
  tokensAdded: number
}) {
  if (!routing) {
    return (
      <div className="sk-live-frame">
        <div className="sk-live-pulse">
          <span className="sk-pulse-dot" />
          Awaiting first turn
        </div>
        <div className="sk-empty-log">
          Send a query in the chat on the left. The router's decision
          will land here — what loaded, what was considered, and why.
        </div>
      </div>
    )
  }

  const timeStr = new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

  return (
    <div className="sk-live-frame">
      <div className="sk-live-pulse">
        <span className="sk-pulse-dot" />
        Last turn
      </div>
      <div className="sk-quote-meta">User · {timeStr}</div>
      <div className="sk-user-quote">
        {userMessage || routing.user_message || '(query unavailable)'}
      </div>

      <div className="sk-routing">
        <div className="sk-routing-eyebrow">
          Skill router · {routing.elapsed_ms} ms
        </div>

        {routing.loaded_skills.map((name) => {
          const considered = routing.considered.find((c) => c.name === name)
          return (
            <div className="sk-routing-step" key={`load-${name}`}>
              <span className="sk-check">✓</span>
              <div style={{ flex: 1 }}>
                <span className="sk-routing-name">{name}</span>
                {' — '}
                <span className="sk-routing-verdict">loaded</span>
                {considered && (
                  <span className="sk-routing-reason">{considered.reason}</span>
                )}
              </div>
            </div>
          )
        })}

        {routing.considered
          .filter((c) => !routing.loaded_skills.includes(c.name))
          .map((c) => (
            <div className="sk-routing-step" key={`considered-${c.name}`}>
              <span className="sk-x">·</span>
              <div style={{ flex: 1 }}>
                <span className="sk-routing-name">{c.name}</span>
                {' — '}
                <span className="sk-routing-verdict">
                  considered, not loaded
                </span>
                <span className="sk-routing-reason">{c.reason}</span>
              </div>
            </div>
          ))}
      </div>

      <div className="sk-routing-summary">
        <span className="sk-num">{routing.loaded_skills.length}</span> skill
        {routing.loaded_skills.length === 1 ? '' : 's'} loaded ·{' '}
        <span className="sk-num">{tokensAdded}</span> tokens added to system
        context for this turn only. Loaded skills are dropped at turn end
        and re-evaluated on the next message.
      </div>
    </div>
  )
}


/* ---- Impact section (static teaching example for v1) — uses SectionFrame ---- */
function ImpactSection() {
  return (
    <SectionFrame
      eyebrow="The impact"
      title={
        <>
          Same agent, same tools, <em>different reply.</em>
        </>
      }
      description={
        <>
          The recommendation agent ran identical tool calls in both versions —
          <span className="sk-mono">semantic_search</span>,{' '}
          <span className="sk-mono">get_pricing</span>,{' '}
          <span className="sk-mono">check_inventory</span>. The skills changed
          only how the result was handled.
        </>
      }
    >
      <div className="sk-impact-grid">
        <div className="sk-impact-card">
          <div className="sk-impact-head sk-impact-head-before">
            <span>Without skills</span>
            <span className="sk-impact-stamp">baseline</span>
          </div>
          <div className="sk-impact-body">
            <p>
              Here are three linen pieces in your price range — the{' '}
              <span className="sk-product">Italian Linen Camp Shirt</span> at{' '}
              <span className="sk-price">$128</span>, the{' '}
              <span className="sk-product">Linen Wrap Dress</span> at{' '}
              <span className="sk-price">$158</span>, and the{' '}
              <span className="sk-product">Italian Linen Camp Shirt</span> at{' '}
              <span className="sk-price">$148</span>.
            </p>
            <div className="sk-impact-callouts">
              <span className="sk-impact-tag">What's missing</span>
              No engagement with the gift-ness. No milestone acknowledgment.
              No fit-tolerance reasoning. No timing or packaging offer. The
              agent answered the literal query and left every gift-specific
              decision on the customer.
            </div>
          </div>
        </div>

        <div className="sk-impact-card">
          <div className="sk-impact-head sk-impact-head-after">
            <span>With style-advisor + gift-concierge</span>
            <span className="sk-impact-stamp">+2,202 tokens</span>
          </div>
          <div className="sk-impact-body">
            <p>
              Sixty's a milestone — for that, I'd lean toward something she'll
              associate with the year, not just the season. Three to consider:
            </p>
            <p>
              · <span className="sk-product">Linen Wrap Dress</span>{' '}
              <span className="sk-price">($158)</span> — heavy linen in russet,
              ties at the waist so fit is flexible.
            </p>
            <p>
              · <span className="sk-product">Italian Linen Camp Shirt</span>{' '}
              <span className="sk-price">($148)</span> — natural fibers, golden
              ochre colorway that photographs warmer than the russet.
            </p>
            <p>
              · <span className="sk-product">Italian Linen Camp Shirt</span>{' '}
              <span className="sk-price">($128)</span> — if she'd rather have
              an everyday piece than an occasion one.
            </p>
            <p>
              If size is uncertain, the wrap dress is the safest bet — ties
              forgive a half-size either way. Want me to flag what's in stock
              for delivery before the birthday?
            </p>
            <div className="sk-impact-callouts">
              <span className="sk-impact-tag">What changed</span>
              <em>gift-concierge</em> named the milestone and surfaced sizing
              risk. <em>style-advisor</em> shaped each line — heavy linen,
              golden ochre colorway, ties at the waist. Same products,
              transformed handling.
            </div>
          </div>
        </div>
      </div>

      <p className="sk-impact-note">
        Static teaching example for v1. Live before/after comparison
        against the current session is tracked in{' '}
        <span style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>
          docs/SKILLS_NOTES.md
        </span>
        .
      </p>
    </SectionFrame>
  )
}


/* ---- SKILL.md modal ---- */
function SkillModal({
  skill,
  onClose,
}: {
  skill: SkillMeta
  onClose: () => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="sk-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-label={`SKILL.md: ${skill.name}`}
    >
      <div className="sk-modal" onClick={(e) => e.stopPropagation()}>
        <div className="sk-modal-head">
          <div className="sk-modal-title">
            /skills/{skill.name}/SKILL.md · v{skill.version}
          </div>
          <button type="button" className="sk-modal-close" onClick={onClose}>
            Close ✕
          </button>
        </div>
        <div className="sk-modal-body">
          <MarkdownMessage content={skill.body} />
        </div>
      </div>
    </div>
  )
}
