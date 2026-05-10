/**
 * LoginButton — Cognito login/logout + user avatar.
 * Visible when Cognito is configured (any mode) or in 'production' mode.
 */
import { useAuth } from '../contexts/AuthContext'
import { LogIn, LogOut, User } from 'lucide-react'

export default function LoginButton() {
  const { user, isAuthenticated, login, logout, loading } = useAuth()

  const cognitoConfigured = !!(import.meta.env.VITE_COGNITO_DOMAIN && import.meta.env.VITE_COGNITO_CLIENT_ID)

  // Only show when Cognito is actually configured
  if (!cognitoConfigured) return null

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 animate-pulse">
        <div className="w-6 h-6 rounded-full bg-white/10" />
        <div className="w-16 h-3 rounded bg-white/10" />
      </div>
    )
  }

  if (isAuthenticated && user) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-emerald-500/10 to-cyan-500/10 border border-emerald-500/20">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-emerald-400 to-cyan-400 flex items-center justify-center">
            <User className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-xs font-medium text-emerald-300 max-w-[120px] truncate">
            {user.email}
          </span>
        </div>
        <button
          onClick={logout}
          className="p-1.5 rounded-lg hover:bg-white/5 text-white/40 hover:text-white/70 transition-colors"
          title="Sign out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={login}
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-amber-500/10 to-orange-500/10 border border-amber-500/20 hover:border-amber-500/40 transition-all hover:scale-[1.02] active:scale-[0.98]"
    >
      <LogIn className="w-4 h-4 text-amber-400" />
      <span className="text-xs font-medium text-amber-300">Sign In</span>
    </button>
  )
}
