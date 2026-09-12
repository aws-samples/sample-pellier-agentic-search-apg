import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { fetchClientBook, OperatorApiError, type OperatorBook } from '../../services/operator'

/** Share one authenticated read between the client list and its tier navigation. */
export function useClientBookResource(enabled = true) {
  const [book, setBook] = useState<OperatorBook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(value => value + 1), [])

  useEffect(() => {
    if (!enabled) return
    let active = true
    setError(null)
    void fetchClientBook()
      .then(data => {
        if (!active) return
        if (!Array.isArray(data.clients) || !data.byMembership || !Number.isFinite(data.total)) {
          throw new Error('Invalid client book response')
        }
        setBook(data)
      })
      .catch((reason: unknown) => {
        if (!active) return
        setBook(null)
        setError(reason instanceof OperatorApiError ? reason.code : 'operator_unavailable')
      })
    return () => { active = false }
  }, [enabled, revision])

  useEffect(() => {
    if (!enabled) return
    const onFocus = () => refresh()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [enabled, refresh])

  return { book, error, refresh }
}

export const ClientBookContext = createContext<ReturnType<typeof useClientBookResource> | null>(null)

export function useClientBook() {
  const shared = useContext(ClientBookContext)
  const local = useClientBookResource(shared === null)
  return shared ?? local
}
