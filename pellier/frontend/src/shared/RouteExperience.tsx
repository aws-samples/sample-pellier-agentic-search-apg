import { useEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

/** Keep navigation immediate, restore the browsing position, and orient keyboard users. */
export default function RouteExperience() {
  const location = useLocation()
  const navigationType = useNavigationType()
  const positions = useRef(new Map<string, number>())
  const previousPath = useRef(location.pathname)
  const keyboardNavigation = useRef(false)

  useEffect(() => {
    const previous = history.scrollRestoration
    history.scrollRestoration = 'manual'
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Tab' || event.key === 'Enter') keyboardNavigation.current = true
    }
    const onPointer = () => { keyboardNavigation.current = false }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      history.scrollRestoration = previous
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [])

  useEffect(() => {
    const changedPage = previousPath.current !== location.pathname
    previousPath.current = location.pathname
    const savedPosition = positions.current.get(location.key)
    let animation: Animation | undefined
    let observer: MutationObserver | undefined
    let resizeObserver: ResizeObserver | undefined
    let arrivalHandled = false

    const arrive = () => {
      const main = document.querySelector<HTMLElement>('main')
      if (!main || main.getClientRects().length === 0) return
      if (!main.id) main.id = 'main-content'
      main.tabIndex = -1
      // A delayed lazy route has a usable skip target of its own. Keep
      // watching until the actual page replaces it, even on a slow network.
      if (main.dataset.routeLoading === 'true') return

      if (navigationType === 'POP' && savedPosition !== undefined) {
        window.scrollTo({ top: savedPosition, behavior: 'instant' })
        // Product images and lazy routes can restore the page height after mount.
        if (!resizeObserver && typeof ResizeObserver !== 'undefined') {
          resizeObserver = new ResizeObserver(() => {
            window.scrollTo({ top: savedPosition, behavior: 'instant' })
          })
          resizeObserver.observe(main)
        }
      } else if (location.hash) {
        let anchor = location.hash.slice(1)
        try { anchor = decodeURIComponent(anchor) } catch { /* Treat malformed escapes as a literal fragment. */ }
        const target = document.getElementById(anchor)
        if (!target) return
        target.scrollIntoView({ behavior: 'instant' })
      } else if (changedPage) {
        window.scrollTo({ top: 0, behavior: 'instant' })
      }

      if (changedPage && !arrivalHandled) {
        if (keyboardNavigation.current) main.focus({ preventScroll: true })
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && main.animate) {
          animation = main.animate(
            [{ opacity: 0.86, transform: 'translateY(5px)' }, { opacity: 1, transform: 'translateY(0)' }],
            { duration: 220, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
          )
        }
      }
      arrivalHandled = true
      observer?.disconnect()
    }

    observer = new MutationObserver(arrive)
    observer.observe(document.body, { childList: true, subtree: true })
    arrive()
    const stopRestore = () => resizeObserver?.disconnect()
    const deadline = window.setTimeout(() => {
      stopRestore()
    }, 2000)
    const rememberPosition = () => {
      positions.current.set(location.key, window.scrollY)
      if (positions.current.size > 80) {
        const oldest = positions.current.keys().next().value
        if (oldest !== undefined) positions.current.delete(oldest)
      }
    }
    window.addEventListener('scroll', rememberPosition, { passive: true })
    window.addEventListener('wheel', stopRestore, { passive: true })
    window.addEventListener('touchstart', stopRestore, { passive: true })
    window.addEventListener('keydown', stopRestore)
    return () => {
      window.clearTimeout(deadline)
      observer?.disconnect()
      resizeObserver?.disconnect()
      animation?.cancel()
      window.removeEventListener('scroll', rememberPosition)
      window.removeEventListener('wheel', stopRestore)
      window.removeEventListener('touchstart', stopRestore)
      window.removeEventListener('keydown', stopRestore)
    }
  }, [location.key, location.pathname, location.hash, navigationType])

  return <a className="pellier-skip-link" href="#main-content">Skip to content</a>
}
