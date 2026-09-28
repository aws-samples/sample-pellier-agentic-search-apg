/**
 * Toast — warm slide-in notification for cart and system events.
 *
 * Pellier palette: cream background, espresso text, burgundy check.
^ * Slides in at top centre, auto-dismisses after `duration` ms.
 */
import { useEffect, useState } from 'react'
import { CheckCircle, X } from 'lucide-react'

interface ToastProps {
  message: string
  show: boolean
  onClose: () => void
  duration?: number
}

const Toast = ({ message, show, onClose, duration = 3000 }: ToastProps) => {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (show) {
      setIsVisible(true)
      const timer = setTimeout(() => {
        setIsVisible(false)
        setTimeout(onClose, 300)
      }, duration)
      return () => clearTimeout(timer)
    }
  }, [show, duration, onClose])

  if (!show) return null

  return (
    <div
      // Top centre, not top right: the cart drawer opens on the right and the
      // "Added to bag" toast used to land on its "Your Bag" heading. It sits
      // below both header rows, because at the viewport top it covered the
      // surface switcher for its whole three seconds.
      className={`fixed left-1/2 z-[1100] -translate-x-1/2 transition-all duration-300 ease-out ${
        isVisible
          ? 'translate-y-0 opacity-100'
          : '-translate-y-3 opacity-0'
      }`}
      style={{
        top: 'calc(var(--pellier-surface-bar-height, 64px) + var(--pellier-storefront-nav-height, 60px) + 16px)',
      }}
    >
      <div
        className="flex items-center gap-3 pl-4 pr-3 py-3 rounded-xl font-sans"
        style={{
          background: 'var(--dl-paper)',
          border: '1px solid var(--rule-1)',
          boxShadow:
            '0 8px 32px rgba(31, 20, 16, 0.12), 0 2px 8px rgba(31, 20, 16, 0.06)',
          color: 'var(--dl-ink)',
        }}
      >
        <CheckCircle
          className="h-[18px] w-[18px] flex-shrink-0"
          style={{ color: 'var(--pellier-burgundy)' }}
          strokeWidth={2}
        />
        <span
          style={{
            fontSize: '14px',
            fontWeight: 500,
            lineHeight: 1.35,
            maxWidth: '260px',
          }}
        >
          {message}
        </span>
        <button
          onClick={() => {
            setIsVisible(false)
            setTimeout(onClose, 300)
          }}
          className="ml-1 p-1 rounded-md transition-colors duration-150"
          style={{ color: 'var(--ink-quiet)' }}
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

export default Toast
