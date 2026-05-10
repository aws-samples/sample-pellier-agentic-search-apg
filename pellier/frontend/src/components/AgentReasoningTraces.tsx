/**
 * Agent Reasoning Traces - Collapsible Side Panel
 *
 * Real-time visualization of multi-agent reasoning, tool calls, and decision flow.
 * Auto-opens during agent execution and collapses when done.
 */
import { useState, useEffect } from 'react';
import { X, Brain, Zap, Database, CheckCircle, AlertCircle, Clock, ArrowRight, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react';
import { resolveAgentType, AGENT_IDENTITIES } from '../utils/agentIdentity';

interface AgentStep {
  id: string;
  agent: string;
  action: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  timestamp: number;
  duration_ms?: number;
  tool_calls?: ToolCall[];
  result?: string;
}

interface ToolCall {
  tool: string;
  params: Record<string, any>;
  result?: any;
  duration_ms?: number;
}

interface AgentReasoningTracesProps {
  mode: 'hidden' | 'collapsed' | 'expanded';
  onCollapse: () => void;
  onClose: () => void;
  onExpand: () => void;
}

interface WaterfallSpan {
  name: string;
  agent?: string;
  tool?: string;
  start_ms: number;
  duration_ms: number;
  tokens?: number;
}

const AgentReasoningTraces = ({ mode, onCollapse, onClose, onExpand }: AgentReasoningTracesProps) => {
  const [traces, setTraces] = useState<AgentStep[]>([]);
  const [activeTab, setActiveTab] = useState<'timeline' | 'waterfall'>('timeline');
  const [waterfallData, setWaterfallData] = useState<WaterfallSpan[]>([]);
  // Fail-loud state: when the backend reports otel_enabled=false the UI
  // renders an amber banner and disables the waterfall, rather than
  // falling back to synthetic "Simulate" spans (Bug 3 audit). The
  // reason string is rendered verbatim and must match the backend's
  // guidance copy.
  const [otelFailure, setOtelFailure] = useState<string | null>(null);

  // Auto-open on agent execution events
  useEffect(() => {
    const handleAgentTrace = () => {
      if (mode === 'hidden') onExpand();
    };

    const handleAgentExecution = (event: CustomEvent) => {
      const { agent_steps, tool_calls, waterfall, otel_enabled, reason } = event.detail;

      if (otel_enabled === false) {
        setOtelFailure(reason || 'Telemetry unavailable — see docs/troubleshooting-otel.md.');
        setTraces([]);
        setWaterfallData([]);
        return;
      }
      setOtelFailure(null);

      if (!agent_steps || agent_steps.length === 0) return;

      const steps: AgentStep[] = agent_steps.map((step: any, idx: number) => ({
        id: `${Date.now()}-${idx}`,
        agent: step.agent,
        action: step.action,
        status: 'completed',
        timestamp: step.timestamp,
        duration_ms: step.duration_ms,
        tool_calls: idx === agent_steps.length - 1 ? tool_calls?.map((tc: any) => ({
          tool: tc.tool,
          params: { tool: tc.tool },
          duration_ms: tc.duration_ms
        })) : undefined
      }));

      setTraces(steps);

      if (waterfall && waterfall.length > 0) {
        setWaterfallData(waterfall);
      }
    };

    window.addEventListener('agent-trace' as any, handleAgentTrace);
    window.addEventListener('agent-execution-complete' as any, handleAgentExecution);
    return () => {
      window.removeEventListener('agent-trace' as any, handleAgentTrace);
      window.removeEventListener('agent-execution-complete' as any, handleAgentExecution);
    };
  }, [mode, onExpand]);

  const getStatusIcon = (status: AgentStep['status']) => {
    switch (status) {
      case 'completed': return <CheckCircle className="h-4 w-4 text-green-400" />;
      case 'in_progress': return <Clock className="h-4 w-4 text-blue-400 animate-spin" />;
      case 'error': return <AlertCircle className="h-4 w-4 text-red-400" />;
      default: return <div className="h-4 w-4 rounded-full border-2 border-gray-600" />;
    }
  };

  const getAgentGradient = (agent: string) => {
    return AGENT_IDENTITIES[resolveAgentType(agent)]?.gradient || 'linear-gradient(135deg, #6b7280 0%, #4b5563 100%)';
  };

  if (mode === 'hidden') return null;

  // Collapsed: show a thin tab on the right edge
  if (mode === 'collapsed') {
    return (
      <div
        className="fixed right-0 top-1/2 -translate-y-1/2 z-40 cursor-pointer"
        onClick={onExpand}
      >
        <div
          className="flex flex-col items-center gap-2 px-2 py-4 rounded-l-xl transition-all hover:px-3"
          style={{
            background: 'rgba(0, 0, 0, 0.95)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRight: 'none',
          }}
        >
          <Brain className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.6)' }} />
          <ChevronLeft className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
          {traces.length > 0 && (
            <span className="text-[10px] text-white/40 font-semibold">{traces.length}</span>
          )}
        </div>
      </div>
    );
  }

  // Expanded: right side panel
  return (
    <div
      className="fixed right-0 top-[72px] w-[380px] h-[calc(100vh-72px)] z-40 flex flex-col animate-slideIn"
      style={{
        background: 'rgba(0, 0, 0, 0.95)',
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
        borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
        boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center justify-between flex-shrink-0"
        style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}
      >
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.6)' }} />
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Agent Traces</h2>
            <p className="text-[10px] text-text-secondary">
              <span className="inline-flex items-center gap-1">
                {otelFailure ? (
                  <><span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse inline-block" /> Telemetry unavailable</>
                ) : traces.length > 0 ? (
                  <><span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse inline-block" /> Live</>
                ) : (
                  <><span className="w-1.5 h-1.5 rounded-full bg-white/30 inline-block" /> Idle</>
                )}
              </span> · {traces.length} steps
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onCollapse} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <ChevronRight className="h-4 w-4 text-text-secondary" />
          </button>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-4 w-4 text-text-secondary" />
          </button>
        </div>
      </div>

      {/* Controls */}
      <div className="px-4 py-2 flex items-center gap-2 border-b flex-shrink-0" style={{ borderColor: 'rgba(75, 85, 99, 0.3)' }}>
        {/* Tab buttons */}
        <div className="flex items-center gap-1 mr-2">
          {(['timeline', 'waterfall'] as const).map(tab => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className="px-2.5 py-1 rounded-md text-[10px] font-medium transition-all capitalize"
              style={{
                background: activeTab === tab ? 'rgba(255, 255, 255, 0.12)' : 'transparent',
                color: activeTab === tab ? '#ffffff' : 'rgba(255, 255, 255, 0.4)',
                border: activeTab === tab ? '1px solid rgba(255, 255, 255, 0.15)' : '1px solid transparent',
              }}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {(traces.length > 0 || waterfallData.length > 0 || otelFailure) && (
          <button
            type="button"
            onClick={() => { setTraces([]); setWaterfallData([]); setOtelFailure(null); }}
            className="text-[10px] text-text-secondary hover:text-text-primary"
          >
            Clear
          </button>
        )}
      </div>

      {/* Fail-loud banner — amber when OTEL isn't SDK-backed. Copy is
          rendered verbatim from the backend's `reason` field so the
          troubleshooting guidance stays authoritative. */}
      {otelFailure && (
        <div
          className="mx-4 mt-3 px-3 py-2 rounded-lg flex items-start gap-2"
          style={{
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.35)',
          }}
        >
          <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(253, 230, 138, 0.95)' }}>
            {otelFailure}
          </p>
        </div>
      )}

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 search-scroll">
        {activeTab === 'timeline' ? (
          /* Timeline View */
          traces.length === 0 ? (
            <div className="text-center py-12">
              <Brain className="h-12 w-12 text-white/20 mx-auto mb-3" />
              <p className="text-xs text-text-secondary">
                {otelFailure
                  ? 'Trace timeline disabled while telemetry is unavailable.'
                  : 'No traces yet. Send a chat query to capture real OTEL spans.'}
              </p>
            </div>
          ) : (
            traces.map((step, index) => (
              <div key={step.id} className="relative">
                {index < traces.length - 1 && (
                  <div className="absolute left-5 top-10 w-0.5 h-6 bg-gradient-to-b from-white/20 to-transparent" />
                )}
                <div
                  className="relative rounded-lg border p-3 transition-all"
                  style={{
                    background: step.status === 'in_progress' ? 'rgba(255, 255, 255, 0.06)' : 'rgba(31, 41, 55, 0.5)',
                    borderColor: step.status === 'in_progress' ? 'rgba(255, 255, 255, 0.15)' : step.status === 'completed' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(75, 85, 99, 0.3)',
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">{getStatusIcon(step.status)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium text-white" style={{ background: getAgentGradient(step.agent) }}>
                          {step.agent}
                        </span>
                        {step.duration_ms && <span className="text-[10px] text-text-secondary">{step.duration_ms}ms</span>}
                      </div>
                      <p className="text-xs text-text-primary mb-1">{step.action}</p>
                      {step.tool_calls && step.tool_calls.length > 0 && (
                        <div className="space-y-1 mt-2">
                          {step.tool_calls.map((tool, ti) => (
                            <div key={ti} className="flex items-center gap-1.5 p-1.5 rounded bg-white/[0.04] border border-white/[0.08]">
                              <Database className="h-3 w-3 text-white/50" />
                              <span className="text-[10px] font-mono text-white/40">{tool.tool}</span>
                              {tool.duration_ms && (
                                <>
                                  <ArrowRight className="h-2 w-2 text-gray-500" />
                                  <span className="text-[10px] text-green-400">{tool.duration_ms}ms</span>
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {step.result && (
                        <div className="mt-2 p-1.5 rounded bg-green-500/10 border border-green-500/20">
                          <div className="flex items-center gap-1.5">
                            <Zap className="h-3 w-3 text-green-400" />
                            <span className="text-[10px] text-green-300">{step.result}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )
        ) : (
          /* Waterfall View */
          waterfallData.length === 0 ? (
            <div className="text-center py-12">
              <Brain className="h-12 w-12 text-white/20 mx-auto mb-3" />
              <p className="text-xs text-text-secondary">
                {otelFailure
                  ? 'Waterfall disabled while telemetry is unavailable.'
                  : 'No waterfall data yet. Send a chat query to capture real OTEL spans.'}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="flex items-center justify-between mb-3">
                <span className="text-[10px] font-medium" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{waterfallData.length} spans captured</span>
                <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>
                  Total: {Math.max(...waterfallData.map(w => w.start_ms + w.duration_ms))}ms
                </span>
              </div>
              {(() => {
                const maxEnd = Math.max(...waterfallData.map(w => w.start_ms + w.duration_ms), 1);
                return waterfallData.map((span, idx) => {
                  const leftPct = (span.start_ms / maxEnd) * 100;
                  const widthPct = Math.max((span.duration_ms / maxEnd) * 100, 1);
                  const barColor = span.tool
                    ? 'rgba(52, 211, 153, 0.6)'
                    : span.agent
                    ? 'rgba(96, 165, 250, 0.6)'
                    : 'rgba(255, 255, 255, 0.2)';
                  return (
                    <div key={idx} className="flex items-center gap-2 group">
                      <div className="w-[100px] flex-shrink-0 text-right pr-2 truncate">
                        <span className="text-[10px] font-mono" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                          {span.tool || span.agent || span.name.slice(0, 20)}
                        </span>
                      </div>
                      <div className="flex-1 h-5 relative rounded" style={{ background: 'rgba(255, 255, 255, 0.03)' }}>
                        <div
                          className="absolute top-0.5 bottom-0.5 rounded transition-all"
                          style={{
                            left: `${leftPct}%`,
                            width: `${widthPct}%`,
                            background: barColor,
                            minWidth: '2px',
                          }}
                        />
                      </div>
                      <div className="w-[50px] flex-shrink-0 text-right">
                        <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{span.duration_ms}ms</span>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 flex-shrink-0" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
        <p className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
          <strong style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Strands OpenTelemetry</strong> · Auto-captured traces
        </p>
      </div>
    </div>
  );
};

export default AgentReasoningTraces;
