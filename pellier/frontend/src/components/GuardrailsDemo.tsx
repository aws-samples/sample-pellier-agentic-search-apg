/**
 * Guardrails Demo — Before/after comparison of Bedrock Guardrails.
 * Apple dark glass modal with input/output testing and PII detection.
 */
import { useState } from 'react'
import { X, Shield, ShieldAlert, ShieldCheck, AlertTriangle, Send, Eye } from 'lucide-react'

interface GuardrailsDemoProps {
  isOpen: boolean
  onClose: () => void
}

interface GuardrailResult {
  allowed: boolean
  action: string
  violations: { type: string; confidence: string }[]
  mode?: string
  pii_detection?: {
    has_pii: boolean
    findings: { type: string; count: number; examples: string[] }[]
  }
  configured: boolean
  source: string
}

const SAMPLE_INPUTS = [
  { label: 'Safe query', text: 'What are the best skincare products for dry skin?' },
  { label: 'With email PII', text: 'Ship it to john.doe@example.com please' },
  { label: 'With phone PII', text: 'Call me at 555-123-4567 for the delivery' },
  { label: 'Off-topic', text: 'Tell me a joke about politics and religion' },
]

const GuardrailsDemo = ({ isOpen, onClose }: GuardrailsDemoProps) => {
  const [inputText, setInputText] = useState('')
  const [inputResult, setInputResult] = useState<GuardrailResult | null>(null)
  const [outputText, setOutputText] = useState('')
  const [outputResult, setOutputResult] = useState<GuardrailResult | null>(null)
  const [loading, setLoading] = useState<'input' | 'output' | null>(null)

  const checkText = async (text: string, source: 'INPUT' | 'OUTPUT') => {
    if (!text.trim()) return
    setLoading(source === 'INPUT' ? 'input' : 'output')
    try {
      const res = await fetch('/api/guardrails/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source }),
      })
      if (res.ok) {
        const data = await res.json()
        if (source === 'INPUT') setInputResult(data)
        else setOutputResult(data)
      }
    } catch (err) {
      console.error('Guardrail check failed:', err)
    } finally {
      setLoading(null)
    }
  }

  if (!isOpen) return null

  const ResultCard = ({ result, label }: { result: GuardrailResult | null; label: string }) => {
    if (!result) return null
    const isBlocked = !result.allowed
    const hasPII = result.pii_detection?.has_pii

    return (
      <div className="p-3 rounded-xl mt-3" style={{
        background: isBlocked ? 'rgba(239, 68, 68, 0.06)' : hasPII ? 'rgba(251, 191, 36, 0.06)' : 'rgba(52, 211, 153, 0.06)',
        border: `1px solid ${isBlocked ? 'rgba(239, 68, 68, 0.2)' : hasPII ? 'rgba(251, 191, 36, 0.2)' : 'rgba(52, 211, 153, 0.2)'}`,
      }}>
        <div className="flex items-center gap-2 mb-2">
          {isBlocked ? (
            <ShieldAlert className="h-4 w-4" style={{ color: 'rgba(239, 68, 68, 0.8)' }} />
          ) : hasPII ? (
            <AlertTriangle className="h-4 w-4" style={{ color: 'rgba(251, 191, 36, 0.8)' }} />
          ) : (
            <ShieldCheck className="h-4 w-4" style={{ color: 'rgba(52, 211, 153, 0.8)' }} />
          )}
          <span className="text-xs font-medium" style={{
            color: isBlocked ? 'rgba(239, 68, 68, 0.8)' : hasPII ? 'rgba(251, 191, 36, 0.8)' : 'rgba(52, 211, 153, 0.8)'
          }}>
            {isBlocked ? 'Blocked' : hasPII ? 'PII Detected' : 'Allowed'} — {label}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full ml-auto" style={{
            background: 'rgba(255, 255, 255, 0.06)',
            color: 'rgba(255, 255, 255, 0.35)',
          }}>
            {result.mode || result.action}
          </span>
        </div>

        {/* Violations */}
        {result.violations.length > 0 && (
          <div className="space-y-1 mb-2">
            {result.violations.map((v, i) => (
              <div key={i} className="text-[11px] flex items-center gap-1.5" style={{ color: 'rgba(239, 68, 68, 0.7)' }}>
                <span>•</span> {v.type} (confidence: {v.confidence})
              </div>
            ))}
          </div>
        )}

        {/* PII findings */}
        {result.pii_detection?.findings && result.pii_detection.findings.length > 0 && (
          <div className="space-y-1">
            {result.pii_detection.findings.map((f, i) => (
              <div key={i} className="text-[11px] flex items-center gap-1.5" style={{ color: 'rgba(251, 191, 36, 0.7)' }}>
                <Eye className="h-3 w-3" />
                {f.type}: {f.count} found ({f.examples.join(', ')})
              </div>
            ))}
          </div>
        )}

        {!result.configured && (
          <div className="text-[10px] mt-2" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>
            No BEDROCK_GUARDRAIL_ID set — running in pass-through mode. Set env vars to enable.
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[680px] max-h-[85vh] rounded-[20px] shadow-2xl overflow-hidden flex flex-col"
        style={{
          background: 'rgba(0, 0, 0, 0.95)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
            <span className="text-sm font-semibold" style={{ color: '#ffffff' }}>Guardrails Demo</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.35)' }}>Bedrock</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5 search-scroll">
          {/* Sample inputs */}
          <div className="flex flex-wrap gap-1.5">
            {SAMPLE_INPUTS.map(s => (
              <button
                key={s.label}
                onClick={() => { setInputText(s.text); checkText(s.text, 'INPUT') }}
                className="px-2.5 py-1 rounded-full text-[11px] transition-all hover:bg-white/10"
                style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.5)' }}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Two-panel layout */}
          <div className="grid grid-cols-2 gap-4">
            {/* Input check */}
            <div className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Input Check</h3>
              <div className="flex gap-1.5">
                <textarea
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  placeholder="Type user input to check..."
                  rows={3}
                  className="flex-1 px-3 py-2 rounded-lg text-xs resize-none"
                  style={{
                    background: 'rgba(255, 255, 255, 0.06)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    color: '#ffffff',
                    outline: 'none',
                  }}
                />
                <button
                  onClick={() => checkText(inputText, 'INPUT')}
                  disabled={loading === 'input' || !inputText.trim()}
                  className="p-2 rounded-lg self-end transition-all disabled:opacity-40"
                  style={{ background: 'rgba(59, 130, 246, 0.3)' }}
                >
                  <Send className="h-4 w-4" style={{ color: 'rgba(147, 197, 253, 0.9)' }} />
                </button>
              </div>
              <ResultCard result={inputResult} label="Input" />
            </div>

            {/* Output check */}
            <div className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Output Check</h3>
              <div className="flex gap-1.5">
                <textarea
                  value={outputText}
                  onChange={e => setOutputText(e.target.value)}
                  placeholder="Type model output to check..."
                  rows={3}
                  className="flex-1 px-3 py-2 rounded-lg text-xs resize-none"
                  style={{
                    background: 'rgba(255, 255, 255, 0.06)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    color: '#ffffff',
                    outline: 'none',
                  }}
                />
                <button
                  onClick={() => checkText(outputText, 'OUTPUT')}
                  disabled={loading === 'output' || !outputText.trim()}
                  className="p-2 rounded-lg self-end transition-all disabled:opacity-40"
                  style={{ background: 'rgba(59, 130, 246, 0.3)' }}
                >
                  <Send className="h-4 w-4" style={{ color: 'rgba(147, 197, 253, 0.9)' }} />
                </button>
              </div>
              <ResultCard result={outputResult} label="Output" />
            </div>
          </div>

          {/* Educational note */}
          <div className="p-3 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <div className="flex items-start gap-2">
              <Shield className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
              <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Bedrock Guardrails</span> — Content filtering, topic control, and PII detection.
                Set <code className="px-1 py-0.5 rounded" style={{ background: 'rgba(255, 255, 255, 0.06)', fontSize: '10px' }}>BEDROCK_GUARDRAIL_ID</code> to enable real API calls.
                PII detection (email, phone, SSN) works locally via regex as a demo fallback.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default GuardrailsDemo
