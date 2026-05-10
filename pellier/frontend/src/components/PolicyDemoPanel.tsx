/**
 * PolicyDemoPanel — Cedar policy evaluation demo.
 * Left: policy definitions. Right: test area with action + parameters.
 */
import { useState, useEffect } from 'react'
import { X, Shield, ShieldCheck, ShieldAlert, Play, FileCode } from 'lucide-react'

interface PolicyDemoPanelProps {
  isOpen: boolean
  onClose: () => void
}

interface Policy {
  id: string
  name: string
  description: string
  cedar: string
  applies_to: string
}

interface Violation {
  policy_id: string
  policy_name: string
  reason: string
  cedar_condition: string
}

interface EvalResult {
  decision: 'ALLOW' | 'DENY'
  action: string
  parameters: Record<string, any>
  violations: Violation[]
  matching_policies: string[]
  policies_evaluated: number
}

const TEST_SCENARIOS = [
  { label: 'Restock 100 units', action: 'restock_shelf', params: { quantity: 100 } },
  { label: 'Restock 1000 units', action: 'restock_shelf', params: { quantity: 1000 } },
  { label: 'Search headphones', action: 'find_pieces', params: { query: 'wireless headphones' } },
  { label: 'Search weapons', action: 'find_pieces', params: { query: 'best weapons for hunting' } },
  { label: 'Set price $50', action: 'set_price', params: { price: 50 } },
  { label: 'Set price $15,000', action: 'set_price', params: { price: 15000 } },
]

const PolicyDemoPanel = ({ isOpen, onClose }: PolicyDemoPanelProps) => {
  const [policies, setPolicies] = useState<Policy[]>([])
  const [action, setAction] = useState('restock_shelf')
  const [paramJson, setParamJson] = useState('{"quantity": 1000}')
  const [result, setResult] = useState<EvalResult | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen) {
      fetch('/api/agentcore/policy/list')
        .then(r => r.json())
        .then(d => setPolicies(d.policies || []))
        .catch(() => {})
    }
  }, [isOpen])

  const evaluate = async () => {
    setLoading(true)
    setResult(null)
    try {
      let params: Record<string, any> = {}
      try { params = JSON.parse(paramJson) } catch { /* ignore */ }
      const res = await fetch('/api/agentcore/policy/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, parameters: params }),
      })
      if (res.ok) setResult(await res.json())
    } catch (err) {
      console.error('Policy check failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const applyScenario = (s: typeof TEST_SCENARIOS[0]) => {
    setAction(s.action)
    setParamJson(JSON.stringify(s.params, null, 2))
    setResult(null)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[95vw] max-w-[1100px] max-h-[85vh] rounded-[20px] flex flex-col overflow-hidden shadow-2xl"
        style={{ background: 'rgba(0, 0, 0, 0.95)', backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <div className="flex items-center gap-3">
            <Shield className="h-6 w-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }} />
            <div>
              <h2 className="text-xl font-semibold" style={{ color: '#ffffff' }}>Cedar Policy Engine</h2>
              <p className="text-xs mt-0.5" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>AgentCore Policy — Real-time action authorization</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
          </button>
        </div>

        {/* Two-column layout */}
        <div className="flex-1 overflow-hidden flex">
          {/* Left: Policies */}
          <div className="w-[45%] overflow-y-auto px-5 py-5 search-scroll" style={{ borderRight: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <div className="flex items-center gap-2 mb-4">
              <FileCode className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
              <h3 className="text-sm font-semibold" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Active Policies</h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.4)' }}>
                {policies.length}
              </span>
            </div>
            <div className="space-y-3">
              {policies.map(p => (
                <div key={p.id} className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                  <h4 className="text-sm font-medium mb-1" style={{ color: '#ffffff' }}>{p.name}</h4>
                  <p className="text-[10px] mb-3" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{p.description}</p>
                  <pre className="text-[11px] p-3 rounded-lg overflow-x-auto leading-relaxed" style={{ background: 'rgba(0, 0, 0, 0.5)', color: 'rgba(52, 211, 153, 0.75)', fontFamily: 'JetBrains Mono, monospace' }}>
                    {p.cedar}
                  </pre>
                  <div className="mt-2 flex items-center gap-1.5">
                    <span className="text-[9px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(168, 85, 247, 0.1)', color: '#c084fc' }}>
                      {p.applies_to}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Test area */}
          <div className="flex-1 overflow-y-auto px-5 py-5 search-scroll">
            <h3 className="text-sm font-semibold mb-3" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>Test Policy Evaluation</h3>

            {/* Scenarios */}
            <div className="flex flex-wrap gap-1.5 mb-4">
              {TEST_SCENARIOS.map(s => (
                <button
                  key={s.label}
                  onClick={() => applyScenario(s)}
                  className="text-[10px] px-2.5 py-1 rounded-full transition-colors hover:bg-white/10"
                  style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.08)', color: 'rgba(255, 255, 255, 0.6)' }}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* Action select */}
            <div className="mb-3">
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Action</label>
              <select
                value={action}
                onChange={e => { setAction(e.target.value); setResult(null) }}
                className="w-full px-3 py-2 rounded-lg text-sm text-white focus:outline-none"
                style={{ background: 'rgba(255, 255, 255, 0.06)', border: '1px solid rgba(255, 255, 255, 0.1)' }}
              >
                <option value="restock_shelf" style={{ background: '#1a1a1a' }}>restock_shelf</option>
                <option value="find_pieces" style={{ background: '#1a1a1a' }}>find_pieces</option>
                <option value="set_price" style={{ background: '#1a1a1a' }}>set_price</option>
              </select>
            </div>

            {/* Parameters */}
            <div className="mb-4">
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Parameters (JSON)</label>
              <textarea
                value={paramJson}
                onChange={e => { setParamJson(e.target.value); setResult(null) }}
                rows={4}
                className="w-full px-3 py-2 rounded-lg text-sm text-white font-mono focus:outline-none resize-none"
                style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
              />
            </div>

            {/* Evaluate button */}
            <button
              onClick={evaluate}
              disabled={loading}
              className="w-full px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 flex items-center justify-center gap-2 mb-5"
              style={{ background: 'rgba(255, 255, 255, 0.1)', border: '1px solid rgba(255, 255, 255, 0.12)', color: '#ffffff' }}
            >
              {loading ? (
                <><div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" /> Evaluating...</>
              ) : (
                <><Play className="h-4 w-4" /> Evaluate</>
              )}
            </button>

            {/* Result */}
            {result && (
              <div className="space-y-3">
                {/* Decision banner */}
                <div className="p-4 rounded-xl flex items-center gap-3" style={{
                  background: result.decision === 'ALLOW' ? 'rgba(52, 211, 153, 0.08)' : 'rgba(248, 113, 113, 0.08)',
                  border: `1px solid ${result.decision === 'ALLOW' ? 'rgba(52, 211, 153, 0.2)' : 'rgba(248, 113, 113, 0.2)'}`,
                }}>
                  {result.decision === 'ALLOW' ? (
                    <ShieldCheck className="h-6 w-6" style={{ color: '#34d399' }} />
                  ) : (
                    <ShieldAlert className="h-6 w-6" style={{ color: '#f87171' }} />
                  )}
                  <div>
                    <div className="text-lg font-bold" style={{ color: result.decision === 'ALLOW' ? '#34d399' : '#f87171' }}>
                      {result.decision}
                    </div>
                    <p className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                      {result.policies_evaluated} policies evaluated · Action: {result.action}
                    </p>
                  </div>
                </div>

                {/* Violations */}
                {result.violations.length > 0 && (
                  <div className="space-y-2">
                    {result.violations.map((v, i) => (
                      <div key={i} className="p-3 rounded-xl" style={{ background: 'rgba(248, 113, 113, 0.05)', border: '1px solid rgba(248, 113, 113, 0.12)' }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: '#f87171' }}>{v.policy_name}</div>
                        <p className="text-xs mb-2" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{v.reason}</p>
                        <code className="text-[10px] px-2 py-0.5 rounded" style={{ background: 'rgba(0, 0, 0, 0.4)', color: 'rgba(52, 211, 153, 0.7)' }}>
                          {v.cedar_condition}
                        </code>
                      </div>
                    ))}
                  </div>
                )}

                {/* No violations */}
                {result.decision === 'ALLOW' && (
                  <p className="text-xs text-center" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                    Action permitted — no policy violations detected
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="flex items-center gap-2 text-xs" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            <Shield className="h-3.5 w-3.5" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
            <span>
              <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Cedar Policy Language</span> — Default-deny authorization for agent tool calls. Policies intercept actions before execution.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PolicyDemoPanel
