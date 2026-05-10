/**
 * SignInPage — Full-screen Cognito sign-in landing page.
 * Gates the entire app when Cognito is configured.
 */
import { motion } from 'framer-motion'
import { useAuth } from '../contexts/AuthContext'
import { Sparkles, Brain, Shield, Database, LogIn } from 'lucide-react'

const FEATURES = [
  {
    icon: <Database className="h-6 w-6" />,
    title: 'Semantic Search',
    desc: 'pgvector embeddings powered by Amazon Aurora PostgreSQL',
    color: '#60a5fa',
  },
  {
    icon: <Brain className="h-6 w-6" />,
    title: 'AI Agents',
    desc: 'Multi-agent orchestration with Strands SDK on Amazon Bedrock',
    color: '#a78bfa',
  },
  {
    icon: <Shield className="h-6 w-6" />,
    title: 'Guardrails & Policy',
    desc: 'Content safety, PII detection, and Cedar authorization',
    color: '#34d399',
  },
  {
    icon: <Sparkles className="h-6 w-6" />,
    title: 'AgentCore',
    desc: 'Persistent memory, observability, and MCP gateway',
    color: '#f59e0b',
  },
]

export default function SignInPage() {
  const { login } = useAuth()

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6"
      style={{
        background: 'linear-gradient(180deg, #000000 0%, #0a0a1a 50%, #0f0f23 100%)',
      }}
    >
      {/* Logo & Title */}
      <motion.div
        className="text-center mb-10"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="inline-flex items-center gap-3 mb-4">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2))',
              border: '1px solid rgba(139, 92, 246, 0.3)',
            }}
          >
            <Sparkles className="h-6 w-6" style={{ color: '#a78bfa' }} />
          </div>
          <h1
            className="text-4xl md:text-5xl font-bold tracking-tight"
            style={{ color: '#ffffff', letterSpacing: '-0.03em' }}
          >
            Pellier
          </h1>
        </div>
        <p className="text-lg" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          AI-Powered Product Search
        </p>
        <p className="text-sm mt-1" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>
          Pellier Workshop
        </p>
      </motion.div>

      {/* Feature Cards */}
      <motion.div
        className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-[800px] w-full mb-10"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.15 }}
      >
        {FEATURES.map((f, i) => (
          <div
            key={i}
            className="p-4 rounded-xl text-center"
            style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.06)',
            }}
          >
            <div
              className="w-10 h-10 rounded-lg mx-auto mb-3 flex items-center justify-center"
              style={{ background: `${f.color}15`, color: f.color }}
            >
              {f.icon}
            </div>
            <h3 className="text-sm font-semibold mb-1" style={{ color: '#ffffff' }}>
              {f.title}
            </h3>
            <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
              {f.desc}
            </p>
          </div>
        ))}
      </motion.div>

      {/* Sign In Button */}
      <motion.div
        className="flex flex-col items-center gap-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
      >
        <button
          onClick={login}
          className="flex items-center gap-3 px-8 py-3.5 rounded-xl text-base font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]"
          style={{
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            color: '#ffffff',
            boxShadow: '0 4px 24px rgba(99, 102, 241, 0.3)',
          }}
        >
          <LogIn className="h-5 w-5" />
          Sign in with AWS
        </button>
        <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>
          Authenticate with Amazon Cognito to access the workshop
        </p>
      </motion.div>

      {/* Footer */}
      <motion.p
        className="absolute bottom-6 text-xs text-center"
        style={{ color: 'rgba(255, 255, 255, 0.15)' }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.5 }}
      >
        Powered by Amazon Bedrock, Aurora PostgreSQL, and Strands SDK
      </motion.p>
    </div>
  )
}
