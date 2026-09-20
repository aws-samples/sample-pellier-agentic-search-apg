import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

/** A recoverable service failure must not look like a rejected sign-in. */
export default function SessionStatusNotice() {
  const { authUnavailable, preferencesUnavailable, refresh } = useAuth()
  const [retrying, setRetrying] = useState(false)
  if (!authUnavailable && !preferencesUnavailable) return null

  const retry = async () => {
    setRetrying(true)
    try {
      await refresh()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="pellier-session-notice" role="status">
      <p>
        {authUnavailable
          ? 'We couldn’t check your session. Please try again in a moment.'
          : 'Your saved preferences are temporarily unavailable.'}
      </p>
      <button type="button" onClick={() => void retry()} disabled={retrying}>
        {retrying ? 'Checking…' : 'Try again'}
      </button>
    </div>
  )
}
