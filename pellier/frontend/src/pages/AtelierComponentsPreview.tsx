/**
 * AtelierComponentsPreview — dev-only Storybook-style gallery of the
 * shared atelier/ components.
 *
 * Route: ``/atelier/_components`` (mounted in App.tsx only when
 * ``import.meta.env.DEV`` is true). Production bundle never sees it.
 *
 * Purpose: isolate every shared component so visual regressions on
 * a page can be debugged here rather than in context. When you build
 * a new atelier page and something looks off, open this route first.
 */
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  LiveStrip,
  StatusBadge,
  DiagramFrame,
  MonoBlock,
} from '../components/atelier'
import type { StatusBadgeVariant } from '../components/atelier'

const CREAM = '#fbf4e8'

const BADGE_VARIANTS: StatusBadgeVariant[] = [
  'active',
  'considered',
  'dormant',
  'fired',
  'idle',
  'touched',
  'pass',
  'watch',
  'fail',
  'success',
  'warning',
  'error',
]

export default function AtelierComponentsPreview() {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--cream-2)',
        padding: '40px 32px',
      }}
    >
      <DetailPageShell
        crumb={['Atelier', 'Architecture', '_components']}
        title={
          <>
            Shared components, <em>in isolation.</em>
          </>
        }
        subtitle="Every atelier/ primitive rendered on a single page. When a page on the Architecture tab looks off, start here — if a primitive looks wrong in isolation, the fix belongs in atelier/, not in the page."
        meta={[
          { label: 'Scope', value: 'dev only' },
          { label: 'Route', value: '/atelier/_components' },
          { label: 'Primitives', value: 8 },
        ]}
      >
        {/* SectionFrame variants */}
        <SectionFrame
          eyebrow="SectionFrame · default"
          title={
            <>
              A cream-1 box with <em>burgundy tick.</em>
            </>
          }
          description="Hairline border, rounded corners, top-left tick. The standard conceptual hero container — used by every page at least once."
        >
          <p style={{ fontFamily: 'var(--serif)', fontSize: 15, color: 'var(--ink-3)' }}>
            Body content renders here. Anything from two-column grids
            to inline SVG diagrams to table canvases fits inside.
          </p>
        </SectionFrame>

        <SectionFrame
          eyebrow="SectionFrame · elevated"
          title={
            <>
              Same frame, <em>cream-elev background.</em>
            </>
          }
          description="Variant used sparingly — when a section needs to sit visually above its neighbors (e.g., the impact callout on Skills)."
          variant="elevated"
        >
          <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink-3)' }}>
            Cream-elev is <code>#fffaf0</code> — very slight lift, reads as warmer paper.
          </p>
        </SectionFrame>

        {/* StatusBadge gallery */}
        <SectionFrame
          eyebrow="StatusBadge"
          title={
            <>
              Twelve variants, <em>scoped by meaning.</em>
            </>
          }
          description="Semantic groups: skills (active/considered/dormant), tool-firing (fired/idle), schema touch (touched), eval (pass/watch/fail), generic (success/warning/error)."
        >
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {BADGE_VARIANTS.map((variant) => (
              <StatusBadge key={variant} variant={variant}>
                {variant}
              </StatusBadge>
            ))}
          </div>
        </SectionFrame>

        {/* MonoBlock gallery */}
        <SectionFrame
          eyebrow="MonoBlock"
          title={
            <>
              Cream-2 code blocks, <em>four inline flavors.</em>
            </>
          }
          description="Comments (ink-4 italic), keys (burgundy), strings (green), arrows (burgundy bold). Labels are optional."
        >
          <div style={{ display: 'grid', gap: 16, gridTemplateColumns: '1fr 1fr' }}>
            <MonoBlock>
              <MonoBlock.Comment># request enters with session</MonoBlock.Comment>
              <br />
              session = <MonoBlock.Key>agentcore</MonoBlock.Key>.open(
              <br />
              &nbsp;&nbsp;session_id=<MonoBlock.Str>"sess_4f"</MonoBlock.Str>,
              <br />
              &nbsp;&nbsp;customer_id=<MonoBlock.Str>"cust_a3"</MonoBlock.Str>,
              <br />)
            </MonoBlock>
            <MonoBlock label="Handoff · orchestrator → specialist">
              <MonoBlock.Arrow>→</MonoBlock.Arrow> in: <MonoBlock.Str>"what's in stock"</MonoBlock.Str>
              <br />
              <MonoBlock.Arrow>→</MonoBlock.Arrow> out:{' '}
              <MonoBlock.Key>agent</MonoBlock.Key>=recommendation
            </MonoBlock>
          </div>
        </SectionFrame>


        {/* DiagramFrame — with and without legend */}
        <SectionFrame
          eyebrow="DiagramFrame"
          title={
            <>
              SVG container with <em>optional label, meta, and legend.</em>
            </>
          }
          description="Used by MCP and Tool Registry (graph diagrams) and Evaluations (multi-color triangle)."
        >
          <div style={{ display: 'grid', gap: 20, gridTemplateColumns: '1fr 1fr' }}>
            <DiagramFrame
              label="Network · this turn"
              meta="3 nodes · 2 edges"
              legend={[
                {
                  marker: (
                    <svg width="22" height="8" aria-hidden>
                      <line x1="0" y1="4" x2="22" y2="4" stroke="rgba(31,20,16,0.45)" strokeWidth="1.2" />
                    </svg>
                  ),
                  label: (
                    <>
                      solid · <em>everyday access</em>
                    </>
                  ),
                },
                {
                  marker: (
                    <svg width="22" height="8" aria-hidden>
                      <line
                        x1="0"
                        y1="4"
                        x2="22"
                        y2="4"
                        stroke="rgba(31,20,16,0.45)"
                        strokeWidth="1.2"
                        strokeDasharray="3,3"
                      />
                    </svg>
                  ),
                  label: (
                    <>
                      dashed · <em>read-only or rare</em>
                    </>
                  ),
                },
              ]}
            >
              <svg viewBox="0 0 360 180" xmlns="http://www.w3.org/2000/svg">
                <line x1="180" y1="40" x2="90" y2="140" stroke="rgba(31,20,16,0.22)" strokeWidth="1" />
                <line x1="180" y1="40" x2="270" y2="140" stroke="rgba(31,20,16,0.22)" strokeWidth="1" />
                <line
                  x1="90"
                  y1="140"
                  x2="270"
                  y2="140"
                  stroke="rgba(31,20,16,0.10)"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                />
                <rect x="148" y="22" width="64" height="36" rx="6" fill="#1f1410" />
                <text
                  x="180"
                  y="45"
                  textAnchor="middle"
                  fontFamily="JetBrains Mono, monospace"
                  fontSize="11"
                  fill="#faf3e8"
                  fontWeight="500"
                >
                  agent
                </text>
                <rect
                  x="58"
                  y="122"
                  width="64"
                  height="36"
                  rx="6"
                  fill="#faf3e8"
                  stroke="#a8423a"
                  strokeWidth="1.5"
                />
                <text
                  x="90"
                  y="145"
                  textAnchor="middle"
                  fontFamily="JetBrains Mono, monospace"
                  fontSize="11"
                  fill="#a8423a"
                  fontWeight="500"
                >
                  gateway
                </text>
                <rect
                  x="238"
                  y="122"
                  width="64"
                  height="36"
                  rx="6"
                  fill="#faf3e8"
                  stroke="rgba(31,20,16,0.22)"
                  strokeWidth="1"
                />
                <text
                  x="270"
                  y="145"
                  textAnchor="middle"
                  fontFamily="JetBrains Mono, monospace"
                  fontSize="11"
                  fill="#1f1410"
                  fontWeight="500"
                >
                  tool
                </text>
              </svg>
            </DiagramFrame>

            <DiagramFrame label="No legend · simple frame">
              <svg viewBox="0 0 360 180" xmlns="http://www.w3.org/2000/svg">
                <line x1="180" y1="30" x2="90" y2="150" stroke="rgba(31,20,16,0.18)" strokeWidth="1" />
                <line x1="180" y1="30" x2="270" y2="150" stroke="rgba(31,20,16,0.18)" strokeWidth="1" />
                <line
                  x1="90"
                  y1="150"
                  x2="270"
                  y2="150"
                  stroke="rgba(31,20,16,0.18)"
                  strokeWidth="1"
                />
                <circle cx="180" cy="30" r="5" fill="#a8423a" />
                <circle cx="90" cy="150" r="5" fill="#a8423a" />
                <circle cx="270" cy="150" r="5" fill="#a8423a" />
                <text
                  x="180"
                  y="95"
                  textAnchor="middle"
                  fontFamily="Fraunces, serif"
                  fontStyle="italic"
                  fontWeight="300"
                  fontSize="32"
                  fill="#1f1410"
                >
                  topic
                </text>
              </svg>
            </DiagramFrame>
          </div>
        </SectionFrame>

        {/* CheatSheet */}
        <CheatSheet
          eyebrow="CheatSheet"
          title={
            <>
              Three columns, <em>one contract.</em>
            </>
          }
          cells={[
            {
              key: 'EXAMPLE · A',
              name: 'First question.',
              question: <em>"The distinguishing question."</em>,
              list: [
                'Observation one',
                'Observation two',
                <>
                  Observation with <em>inline emphasis</em>
                </>,
                <>
                  <em>Add when</em> a new role is needed
                </>,
              ],
            },
            {
              key: 'EXAMPLE · B',
              name: 'Second question.',
              question: <em>"Another angle."</em>,
              list: [
                'Typed inputs and outputs',
                'Deterministic, no opinions',
                'Cost: one function call',
              ],
            },
            {
              key: 'EXAMPLE · C',
              name: 'Third question.',
              question: <em>"Different again."</em>,
              list: [
                'Markdown + activation contract',
                'Loaded conditionally',
                'Cost: tokens, only when relevant',
              ],
            },
          ]}
        />

        {/* LiveStrip — with and without stub caption */}
        <LiveStrip
          title={
            <>
              What loaded, <em>and why.</em>
            </>
          }
          meta="turn 04 · 11:47:32 · sess_4f"
        >
          <div
            style={{
              padding: '16px 22px',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 1,
              background: 'var(--rule-1)',
            }}
          >
            <div style={{ background: 'var(--cream-1)', padding: '14px 16px' }}>
              <div style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 15 }}>
                Left cell — page-specific content.
              </div>
              <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)', marginTop: 6 }}>
                Each page fills the live strip with its own body. Skills shows routing
                decisions, Memory shows STM/LTM cells, MCP shows tool-call rows.
              </p>
            </div>
            <div style={{ background: 'var(--cream-1)', padding: '14px 16px' }}>
              <div style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 15 }}>
                Right cell.
              </div>
              <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)', marginTop: 6 }}>
                Mixed mode — some pages have two cells here, some have a single list.
              </p>
            </div>
          </div>
        </LiveStrip>

        <LiveStrip
          eyebrow="Stubbed · demo data"
          title={
            <>
              Scores, <em>plausible but mocked.</em>
            </>
          }
          meta="turn 04 · 11:47:32"
          stubCaption="// demo data — eval harness not yet wired"
        >
          <div style={{ padding: '16px 22px' }}>
            <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)' }}>
              When a page renders stub data, always pair it with the caption above.
              Participants can see what's real vs mocked at a glance.
            </p>
          </div>
        </LiveStrip>
      </DetailPageShell>
    </div>
  )
}

// Re-export cream constant for component consumers that want to know
// the surrounding background without a second import.
export { CREAM }
