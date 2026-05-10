/**
 * McpArchPage — Atelier · Architecture · MCP (Template C · Network)
 *
 * Matches docs/atelier-mcp-architecture.html:
 *   - Breadcrumb / title / subtitle / meta strip
 *   - Network section: three-node SVG (agent top, gateway bottom-left,
 *     tools bottom-right) with "discovers" / "invokes" edge pills
 *   - Three node descriptions with status tags
 *   - Two-edges sub-block
 *   - Tool catalog grid (Fired / Idle status per tool, p50 latency)
 *   - Live strip: rows of stamp · tool · args · elapsed for the
 *     current turn's tool calls
 *
 * Data sources:
 *   - Agents / tools / grants: /api/atelier/catalog
 *   - Live tool calls: localStorage "pellier-last-tool-calls"
 *     (written by useAgentChat on every ``tool_call`` SSE event)
 */
import { useEffect, useMemo, useState } from 'react'
import {
  DetailPageShell,
  SectionFrame,
  LiveStrip,
  StatusBadge,
  DiagramFrame,
} from '../atelier'
import { useCatalog, useRecentToolCalls } from './shared-catalog'
import '../../styles/atelier-arch.css'

interface GatewayStatus {
  configured: boolean
  source: string
  gateway_url?: string
  fallback_reason?: string | null
}

function useGatewayStatus(): GatewayStatus | null {
  const [status, setStatus] = useState<GatewayStatus | null>(null)
  useEffect(() => {
    let alive = true
    fetch('/api/agentcore/gateway/status')
      .then(r => r.json())
      .then(d => {
        if (alive) setStatus(d as GatewayStatus)
      })
      .catch(() => {
        if (alive) setStatus(null)
      })
    return () => {
      alive = false
    }
  }, [])
  return status
}

export default function McpArchPage() {
  const { catalog, loading } = useCatalog()
  const recentCalls = useRecentToolCalls()
  const gwStatus = useGatewayStatus()

  // The Surface meta label is honest about whether the Gateway is
  // wired this instance. 'AgentCore Gateway' when configured,
  // 'In-process imports (fallback)' otherwise — matches the backend's
  // /api/agentcore/gateway/status vocabulary.
  const surfaceLabel = gwStatus
    ? gwStatus.configured
      ? 'AgentCore Gateway'
      : 'In-process imports (fallback)'
    : 'AgentCore Gateway'

  // Tool "fired" state — fire if the tool appeared in recent calls.
  const firedSet = useMemo(() => {
    const s = new Set<string>()
    recentCalls.forEach((c) => s.add(c.tool))
    return s
  }, [recentCalls])

  const toolsFired = catalog?.tools.filter((t) => firedSet.has(t.name)).length ?? 0
  const toolsTotal = catalog?.tools.length ?? 0

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'MCP']}
      title={
        <>
          MCP, <em>the seam.</em>
        </>
      }
      subtitle="Model Context Protocol is how the agent discovers and calls tools. The Gateway publishes the surface; the agent consumes it. One address, one protocol, many tools."
      meta={[
        { label: 'Tools registered', value: toolsTotal || '—' },
        { label: 'Fired this turn', value: toolsFired },
        { label: 'Gateway p50', value: '18ms' },
        { label: 'Surface', value: surfaceLabel },
      ]}
    >
      {/* ---- Network section ---- */}
      <SectionFrame
        eyebrow="The network"
        title={
          <>
            Three nodes, <em>two edges.</em>
          </>
        }
        description="The agent never talks to a tool directly. It asks the Gateway 'what's available?', gets back a list of tool descriptions, and invokes the ones it needs through the same channel. The Gateway is the seam."
      >
        <div className="mcp-net-grid">
          <DiagramFrame
            label="Network · this session"
            meta={
              <>
                <span className="arch-num">3</span> nodes ·{' '}
                <span className="arch-num">2</span> edges
              </>
            }
          >
            <NetworkDiagram />
          </DiagramFrame>

          <div className="mcp-net-explain">
            <div className="mcp-net-row">
              <div className="mcp-net-row-head">
                <div className="mcp-net-row-name">
                  <span className="arch-node-key">A</span>
                  <em>The agent.</em>
                </div>
                <StatusBadge variant="active">Owned</StatusBadge>
              </div>
              <p className="mcp-net-row-desc">
                Strands orchestrator (Haiku) plus five specialists (Opus). On
                startup, fetches the tool catalog from the Gateway. On every
                turn, decides <em>which</em> tools to invoke and routes calls
                back through the Gateway.
              </p>
            </div>
            <div className="mcp-net-row">
              <div className="mcp-net-row-head">
                <div className="mcp-net-row-name">
                  <span className="arch-node-key">B</span>
                  <em>The Gateway.</em>
                </div>
                <StatusBadge variant="fired">Managed</StatusBadge>
              </div>
              <p className="mcp-net-row-desc">
                AgentCore Gateway. Publishes the tool surface as MCP,
                handles <em>authentication</em>, <em>observability</em>, and{' '}
                <em>rate limiting</em>. We don't run the protocol layer
                ourselves — Gateway does it.
              </p>
            </div>
            <div className="mcp-net-row">
              <div className="mcp-net-row-head">
                <div className="mcp-net-row-name">
                  <span className="arch-node-key">C</span>
                  <em>The tools.</em>
                </div>
                <StatusBadge variant="active">Owned</StatusBadge>
              </div>
              <p className="mcp-net-row-desc">
                Our <code className="arch-mono">@tool</code>-decorated
                functions. Registered with the Gateway at boot. The Gateway
                exposes their <em>signatures</em> (typed inputs, typed
                outputs, descriptions) — which is what the agent uses to
                choose between them.
              </p>
            </div>

            <div className="mcp-edges-block">
              <div className="mcp-edges-eyebrow">The two edges</div>
              <div className="mcp-edge-row">
                <span className="mcp-edge-arrow">
                  A <span className="arch-arrow">→</span> B
                </span>
                <span>
                  <em>Discovery.</em> Agent asks the Gateway for the tool
                  catalog. Returns names, signatures, descriptions.{' '}
                  <code className="arch-mono">gateway.list_tools()</code>
                </span>
              </div>
              <div className="mcp-edge-row">
                <span className="mcp-edge-arrow">
                  A <span className="arch-arrow">→</span> B
                </span>
                <span>
                  <em>Invocation.</em> Agent calls a tool by name, Gateway
                  routes to the implementation, returns the result.{' '}
                  <code className="arch-mono">gateway.invoke(name, args)</code>
                </span>
              </div>
              <div className="mcp-edge-row" style={{ color: 'var(--ink-4)' }}>
                <span className="mcp-edge-arrow">B ⇢ C</span>
                <span>
                  <em>Implementation routing.</em> Hidden from the agent.
                  Could be in-process, could be remote. The agent doesn't care.
                </span>
              </div>
            </div>
          </div>
        </div>
      </SectionFrame>

      {/* ---- Tool catalog grid ---- */}
      <SectionFrame
        eyebrow="The catalog"
        title={
          <>
            {toolsTotal} tools, <em>{toolsFired} fired.</em>
          </>
        }
        description="Every tool the Gateway publishes. Their signatures are what the agent reads at decision time. Active state shows what fired this turn."
      >
        {loading ? (
          <div className="arch-empty">Loading the catalog…</div>
        ) : (
          <div className="mcp-tools-grid">
            {catalog?.tools.map((t) => {
              const fired = firedSet.has(t.name)
              const callCount = recentCalls.filter((c) => c.tool === t.name).length
              return (
                <article
                  key={t.name}
                  className={`mcp-tool-card ${fired ? 'mcp-tool-card-active' : ''}`}
                >
                  <div className="mcp-tool-head">
                    <div>
                      <div className="mcp-tool-name-row">
                        <span className="mcp-tool-name">{t.name}</span>
                        <span className="mcp-tool-version">{t.version}</span>
                      </div>
                      <div className="mcp-tool-headline">
                        <em>{t.headline}</em>
                      </div>
                      <p className="mcp-tool-desc">{t.description}</p>
                    </div>
                    <StatusBadge variant={fired ? 'fired' : 'idle'}>
                      {fired ? 'Fired' : 'Idle'}
                    </StatusBadge>
                  </div>
                  <div className="mcp-tool-foot">
                    <span>
                      ~<span className="arch-num">{t.p50_ms}</span> ms p50
                    </span>
                    <span>
                      this turn · <span className="arch-num">{callCount}</span>{' '}
                      {callCount === 1 ? 'call' : 'calls'}
                    </span>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </SectionFrame>

      {/* ---- Live strip ---- */}
      <LiveStrip
        title={
          <>
            Tool calls, <em>through the gateway.</em>
          </>
        }
        meta={`this turn · ${recentCalls.length} ${recentCalls.length === 1 ? 'call' : 'calls'}`}
      >
        {recentCalls.length === 0 ? (
          <div className="arch-empty">
            No tool calls yet. Send a query in the chat on the left — each
            invocation will appear here as it fires.
          </div>
        ) : (
          <div className="arch-live-table">
            <div className="arch-live-row arch-live-row-head">
              <span>Stamp</span>
              <span>Tool</span>
              <span>Argument</span>
              <span style={{ textAlign: 'right' }}>Elapsed</span>
            </div>
            {recentCalls.slice(-8).reverse().map((c, i) => (
              <div className="arch-live-row" key={`${c.timestamp}-${i}`}>
                <span className="arch-live-stamp">
                  {formatTimestamp(c.timestamp)}
                </span>
                <span className="arch-live-tool">{c.tool}</span>
                <span className="arch-live-args">
                  {c.args ? truncate(c.args, 42) : <span style={{ color: 'var(--ink-4)' }}>—</span>}
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


/* ---- The three-node SVG diagram ---- */
function NetworkDiagram() {
  return (
    <svg viewBox="0 0 480 380" xmlns="http://www.w3.org/2000/svg">
      {/* Edges */}
      <line x1="240" y1="110" x2="120" y2="240" stroke="rgba(168,66,58,0.55)" strokeWidth="1.5" />
      <line x1="240" y1="110" x2="360" y2="240" stroke="rgba(168,66,58,0.55)" strokeWidth="1.5" />
      <line x1="120" y1="280" x2="360" y2="280" stroke="rgba(31,20,16,0.18)" strokeWidth="1" strokeDasharray="4,4" />

      {/* Edge labels */}
      <rect x="125" y="155" width="80" height="22" rx="11" fill="#faf3e8" stroke="rgba(168,66,58,0.4)" strokeWidth="1" />
      <text x="165" y="170" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="12" fill="#a8423a">discovers</text>

      <rect x="280" y="155" width="68" height="22" rx="11" fill="#faf3e8" stroke="rgba(168,66,58,0.4)" strokeWidth="1" />
      <text x="314" y="170" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="12" fill="#a8423a">invokes</text>

      <text x="240" y="298" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9.5" fill="rgba(31,20,16,0.42)" letterSpacing="2">PROTOCOL · MCP</text>

      {/* Agent (top) */}
      <rect x="180" y="70" width="120" height="60" rx="10" fill="#1f1410" />
      <text x="240" y="100" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="20" fill="#faf3e8" letterSpacing="-0.5">agent</text>
      <text x="240" y="118" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9" fill="rgba(250,243,232,0.55)" letterSpacing="1.5">orchestrator + 5 specs</text>

      {/* Gateway (bottom-left) */}
      <rect x="55" y="240" width="130" height="80" rx="10" fill="#faf3e8" stroke="#a8423a" strokeWidth="1.5" />
      <text x="120" y="268" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="20" fill="#a8423a" letterSpacing="-0.5">gateway</text>
      <text x="120" y="288" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9" fill="rgba(31,20,16,0.42)" letterSpacing="1.5">AGENTCORE</text>
      <text x="120" y="305" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="10" fill="rgba(31,20,16,0.66)">auth · obs · rate</text>

      {/* Tools (bottom-right) */}
      <rect x="295" y="240" width="130" height="80" rx="10" fill="#faf3e8" stroke="rgba(31,20,16,0.30)" strokeWidth="1" />
      <text x="360" y="268" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="20" fill="#1f1410" letterSpacing="-0.5">tools</text>
      <text x="360" y="288" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9" fill="rgba(31,20,16,0.42)" letterSpacing="1.5">REGISTERED</text>
      <text x="360" y="305" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="10" fill="rgba(31,20,16,0.66)">search · pricing · …</text>

      {/* Footer caption */}
      <text x="240" y="365" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="rgba(31,20,16,0.66)">The agent talks to one address. The Gateway publishes the rest.</text>
    </svg>
  )
}

function formatTimestamp(ts?: number): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
