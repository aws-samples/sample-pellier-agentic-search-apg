/**
 * ToolRegistryArchPage — Atelier · Architecture · Tool Registry
 * (Template C · Network variant — bipartite graph)
 *
 * Matches docs/atelier-tool-registry-architecture.html:
 *   - Title / subtitle / meta strip
 *   - Bipartite graph: agents on the left, tools on the right,
 *     edges by grant style (solid = everyday, dashed = read-only,
 *     espresso-dashed = gated)
 *   - Tool detail rows below the graph showing granted-to chips +
 *     per-tool stats
 *   - Cheat sheet: three rules about granting
 *   - Live strip: grants exercised this turn (stamp · agent · → tool · ms)
 *
 * Data sources: /api/atelier/catalog (agents + tools + grants);
 * localStorage "pellier-last-tool-calls" for the live strip.
 */
import { useMemo } from 'react'
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  LiveStrip,
  DiagramFrame,
} from '../atelier'
import {
  useCatalog,
  useRecentToolCalls,
  type AtelierGrant,
} from './shared-catalog'
import '../../styles/atelier-arch.css'

export default function ToolRegistryArchPage() {
  const { catalog, loading } = useCatalog()
  const recentCalls = useRecentToolCalls()

  const { agentCount, toolCount, grantCount, gatedCount } = useMemo(() => {
    if (!catalog)
      return { agentCount: 0, toolCount: 0, grantCount: 0, gatedCount: 0 }
    return {
      agentCount: catalog.agents.length,
      toolCount: catalog.tools.length,
      grantCount: catalog.grants.length,
      gatedCount: catalog.grants.filter((g) => g.style === 'gated').length,
    }
  }, [catalog])

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'Tool Registry']}
      title={
        <>
          Access, <em>the bipartite way.</em>
        </>
      }
      subtitle="Every tool the agents can touch is granted explicitly. Solid lines are everyday access; dashed are read-only; one gated grant — support → restock — requires explicit user confirmation."
      meta={[
        { label: 'Agents', value: agentCount || '—' },
        { label: 'Tools', value: toolCount || '—' },
        { label: 'Grants', value: `${grantCount} of ${agentCount * toolCount}` },
        { label: 'Gated', value: gatedCount ? `${gatedCount} · restock` : '0' },
      ]}
    >
      {/* ---- Bipartite graph ---- */}
      <SectionFrame
        eyebrow="The grants"
        title={
          <>
            {agentCount} agents, <em>{toolCount} tools.</em>
          </>
        }
        description="A bipartite graph: agents on the left, tools on the right, lines for each grant. The orchestrator holds no tool grants — it dispatches to specialists; specialists invoke. The espresso-dashed line is the one gated grant."
      >
        <DiagramFrame
          label="Access graph · all routes"
          meta={
            <>
              <span className="arch-num">{grantCount}</span> grants ·{' '}
              <span className="arch-num">
                {agentCount * toolCount - grantCount}
              </span>{' '}
              blocked · <span className="arch-num">{gatedCount}</span> gated
            </>
          }
          legend={[
            {
              marker: (
                <svg width="22" height="8" aria-hidden>
                  <line
                    x1="0"
                    y1="4"
                    x2="22"
                    y2="4"
                    stroke="rgba(168,66,58,0.7)"
                    strokeWidth="1.5"
                  />
                </svg>
              ),
              label: (
                <>
                  <em>Everyday access</em> · used in normal flows
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
                    stroke="rgba(168,66,58,0.4)"
                    strokeWidth="1.5"
                    strokeDasharray="4,4"
                  />
                </svg>
              ),
              label: (
                <>
                  <em>Read-only / rare</em> · for context, not action
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
                    stroke="#1f1410"
                    strokeWidth="2"
                    strokeDasharray="6,6"
                  />
                </svg>
              ),
              label: (
                <>
                  <em>Gated</em> · requires user confirmation
                </>
              ),
            },
          ]}
        >
          <BipartiteGraph catalog={catalog} />
        </DiagramFrame>
      </SectionFrame>

      {/* ---- Tool detail rows ---- */}
      <SectionFrame
        eyebrow="The catalog"
        title={
          <>
            Each tool, <em>and who has it.</em>
          </>
        }
        description="One row per tool. The middle shows which agents hold the grant; the right shows the cost. Bind a tool to fewer agents than you think — access creep is real."
      >
        {loading ? (
          <div className="arch-empty">Loading the catalog…</div>
        ) : (
          <div className="tr-detail-grid">
            {catalog?.tools.map((tool) => {
              const tGrants = catalog.grants.filter((g) => g.tool === tool.name)
              const callCount = recentCalls.filter(
                (c) => c.tool === tool.name,
              ).length
              return (
                <div className="tr-detail-row" key={tool.name}>
                  <div className="tr-detail-head">
                    <div className="tr-detail-id">
                      <span className="tr-detail-name">{tool.name}</span>
                      <span className="tr-detail-headline">
                        <em>{tool.headline}</em>
                      </span>
                    </div>
                    <div className="tr-detail-access">
                      Held by{' '}
                      <strong>
                        {tGrants.length} agent{tGrants.length === 1 ? '' : 's'}
                      </strong>
                      {tool.gated && (
                        <span className="tr-gated-tag">Gated</span>
                      )}
                    </div>
                    <div className="tr-detail-stats">
                      <span>
                        ~<span className="arch-num">{tool.p50_ms}</span>ms p50
                      </span>
                      <span>
                        <span className="arch-num">{callCount}</span> call
                        {callCount === 1 ? '' : 's'} this turn
                      </span>
                    </div>
                  </div>
                  <div className="tr-detail-grants">
                    <span className="tr-grants-label">Granted to</span>
                    {tGrants.map((g) => (
                      <span
                        className={`tr-agent-chip ${g.style === 'gated' ? 'tr-agent-chip-gated' : ''} ${g.style === 'dashed' ? 'tr-agent-chip-dashed' : ''}`}
                        key={`${g.agent}-${g.tool}`}
                      >
                        {g.agent}
                        {g.style === 'gated' && ' · gated'}
                      </span>
                    ))}
                    {tGrants.length === 0 && (
                      <span className="tr-agent-chip tr-agent-chip-none">
                        no grants
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </SectionFrame>

      {/* ---- Cheat sheet ---- */}
      <CheatSheet
        eyebrow="When in doubt"
        title={
          <>
            Three rules <em>about granting.</em>
          </>
        }
        cells={[
          {
            key: 'DEFAULT DENY',
            name: 'Bind less, not more.',
            question: <em>"Should this agent really need it?"</em>,
            list: [
              'New tool starts with zero grants',
              'Each grant is added explicitly, with a reason',
              'Access creep happens silently — review periodically',
              <>
                <em>Capability sprawl is a risk surface, not a feature</em>
              </>,
            ],
          },
          {
            key: 'ROLE FIT',
            name: 'Tool to job, not to convenience.',
            question: <em>"Is this central to the agent's role?"</em>,
            list: [
              <>
                Recommendation owns <em>get_recommendations</em>
              </>,
              "Support reads it; doesn't own it",
              'Multiple owners is a smell — pick one',
              <>
                <em>If two agents fight over a tool, you have a missing agent</em>
              </>,
            ],
          },
          {
            key: 'GATE SIDE EFFECTS',
            name: 'Writes need confirmation.',
            question: <em>"Does this change something durable?"</em>,
            list: [
              'Reads are free; writes are gated',
              <>
                <em>restock</em> requires explicit user "yes"
              </>,
              'The gate is at the tool, not the agent',
              <>
                <em>Don't trust an agent to ask the question on your behalf</em>
              </>,
            ],
          },
        ]}
      />

      {/* ---- Live strip ---- */}
      <LiveStrip
        title={
          <>
            Grants exercised, <em>this turn.</em>
          </>
        }
        meta={`${recentCalls.length} ${recentCalls.length === 1 ? 'invocation' : 'invocations'} · 0 denials`}
      >
        {recentCalls.length === 0 ? (
          <div className="arch-empty">
            No invocations yet. Send a query in the chat on the left — each
            grant exercised will appear here.
          </div>
        ) : (
          <div className="arch-live-table tr-live">
            <div className="arch-live-row arch-live-row-head">
              <span>Stamp</span>
              <span>Agent</span>
              <span>Tool</span>
              <span style={{ textAlign: 'right' }}>Elapsed</span>
            </div>
            {recentCalls.slice(-8).reverse().map((c, i) => (
              <div className="arch-live-row" key={`${c.timestamp}-${i}`}>
                <span className="arch-live-stamp">
                  {formatTimestamp(c.timestamp)}
                </span>
                <span className="tr-live-agent">{c.agent || 'specialist'}</span>
                <span className="tr-live-tool">
                  <span className="arch-arrow">→</span>{' '}
                  <span className="tr-live-tool-name">{c.tool}</span>
                </span>
                <span className="arch-live-ms">
                  {c.duration_ms ? `${c.duration_ms}ms` : '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </LiveStrip>
    </DetailPageShell>
  )
}

/* ---- Bipartite graph SVG ---- */

function BipartiteGraph({ catalog }: { catalog: ReturnType<typeof useCatalog>['catalog'] }) {
  if (!catalog) {
    return (
      <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg">
        <text
          x="360"
          y="230"
          textAnchor="middle"
          fontFamily="Fraunces, serif"
          fontStyle="italic"
          fontSize="14"
          fill="rgba(31,20,16,0.42)"
        >
          Loading…
        </text>
      </svg>
    )
  }

  // Fixed y-positions so the graph reads cleanly at demo-scale.
  // Agents: 6 slots (1 orchestrator + 5 specialists) evenly spaced.
  // Tools: 9 slots from the catalog above.
  const agentYs: Record<string, number> = {}
  const agentSpacing = 62
  const agentStartY = 55
  catalog.agents.forEach((agent, i) => {
    agentYs[agent.name] = agentStartY + i * agentSpacing + 22
  })

  const toolYs: Record<string, number> = {}
  const toolSpacing = 40
  const toolStartY = 60
  catalog.tools.forEach((tool, i) => {
    toolYs[tool.name] = toolStartY + i * toolSpacing + 17
  })

  const totalHeight = Math.max(
    agentStartY + catalog.agents.length * agentSpacing + 40,
    toolStartY + catalog.tools.length * toolSpacing + 40,
  )

  return (
    <svg
      viewBox={`0 0 720 ${totalHeight}`}
      xmlns="http://www.w3.org/2000/svg"
      style={{ maxHeight: 520 }}
    >
      {/* Column labels */}
      <text
        x="120"
        y="30"
        textAnchor="middle"
        fontFamily="JetBrains Mono, monospace"
        fontSize="10"
        letterSpacing="2.5"
        fill="#a8423a"
        fontWeight="500"
      >
        AGENTS · {catalog.agents.length}
      </text>
      <text
        x="600"
        y="30"
        textAnchor="middle"
        fontFamily="JetBrains Mono, monospace"
        fontSize="10"
        letterSpacing="2.5"
        fill="#a8423a"
        fontWeight="500"
      >
        TOOLS · {catalog.tools.length}
      </text>

      {/* EDGES drawn first so nodes sit on top */}
      {catalog.grants.map((g: AtelierGrant, i) => {
        const y1 = agentYs[g.agent]
        const y2 = toolYs[g.tool]
        if (y1 == null || y2 == null) return null
        if (g.style === 'gated') {
          return (
            <line
              key={`edge-${i}`}
              x1="200"
              y1={y1}
              x2="520"
              y2={y2}
              stroke="#1f1410"
              strokeWidth="2.5"
              strokeDasharray="6,6"
            />
          )
        }
        if (g.style === 'dashed') {
          return (
            <line
              key={`edge-${i}`}
              x1="200"
              y1={y1}
              x2="520"
              y2={y2}
              stroke="rgba(168,66,58,0.4)"
              strokeWidth="1.5"
              strokeDasharray="4,4"
            />
          )
        }
        return (
          <line
            key={`edge-${i}`}
            x1="200"
            y1={y1}
            x2="520"
            y2={y2}
            stroke="rgba(168,66,58,0.7)"
            strokeWidth="1.5"
          />
        )
      })}

      {/* AGENT nodes (left column) */}
      {catalog.agents.map((agent, i) => {
        const y = agentStartY + i * agentSpacing
        const isOrch = agent.name === 'orchestrator'
        return (
          <g key={agent.name}>
            <rect
              x="40"
              y={y}
              width="160"
              height="44"
              rx="8"
              fill={isOrch ? '#1f1410' : '#faf3e8'}
              stroke={isOrch ? '#1f1410' : 'rgba(31,20,16,0.30)'}
              strokeWidth="1"
            />
            <text
              x="120"
              y={y + 20}
              textAnchor="middle"
              fontFamily="Fraunces, serif"
              fontStyle="italic"
              fontSize="15"
              fill={isOrch ? '#faf3e8' : '#1f1410'}
            >
              {agent.name}
            </text>
            <text
              x="120"
              y={y + 36}
              textAnchor="middle"
              fontFamily="JetBrains Mono, monospace"
              fontSize="9"
              fill={isOrch ? 'rgba(250,243,232,0.55)' : 'rgba(31,20,16,0.42)'}
              letterSpacing="1"
            >
              {agent.role}
            </text>
          </g>
        )
      })}

      {/* TOOL nodes (right column) */}
      {catalog.tools.map((tool, i) => {
        const y = toolStartY + i * toolSpacing
        const isGated = Boolean(tool.gated)
        return (
          <g key={tool.name}>
            <rect
              x="520"
              y={y}
              width="160"
              height="34"
              rx="6"
              fill={isGated ? '#1f1410' : '#faf3e8'}
              stroke={isGated ? '#1f1410' : 'rgba(31,20,16,0.30)'}
              strokeWidth="1"
            />
            <text
              x="600"
              y={y + 22}
              textAnchor="middle"
              fontFamily="JetBrains Mono, monospace"
              fontSize="11"
              fill={isGated ? '#faf3e8' : '#1f1410'}
              fontWeight="500"
            >
              {tool.name}
            </text>
            {isGated && (
              <text
                x="690"
                y={y + 16}
                textAnchor="end"
                fontFamily="JetBrains Mono, monospace"
                fontSize="8"
                fill="rgba(250,243,232,0.7)"
                letterSpacing="1.5"
              >
                GATED
              </text>
            )}
          </g>
        )
      })}

      {/* Caption */}
      <text
        x="360"
        y={totalHeight - 20}
        textAnchor="middle"
        fontFamily="Fraunces, serif"
        fontStyle="italic"
        fontSize="13"
        fill="rgba(31,20,16,0.66)"
      >
        Orchestrator routes; specialists invoke. The dispatcher itself holds no tool grants.
      </text>
    </svg>
  )
}

function formatTimestamp(ts?: number): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return (
    d.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) +
    '.' +
    String(d.getMilliseconds()).padStart(3, '0')
  )
}
