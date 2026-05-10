/**
 * Toast — warm slide-in notification for cart and system events.
 *
 * Boutique palette: cream background, espresso text, burgundy check.
 * Slides in from top-right, auto-dismisses after `duration` ms.
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
      className={`fixed top-6 right-6 z-[1100] transition-all duration-300 ease-out ${
        isVisible
          ? 'translate-x-0 opacity-100'
          : 'translate-x-[120%] opacity-0'
      }`}
    >
      <div
        className="flex items-center gap-3 pl-4 pr-3 py-3 rounded-xl font-sans"
        style={{
          background: '#FAF3E8',
          border: '1px solid rgba(31, 20, 16, 0.12)',
          boxShadow:
            '0 8px 32px rgba(31, 20, 16, 0.12), 0 2px 8px rgba(31, 20, 16, 0.06)',
          color: '#1f1410',
        }}
      >
        <CheckCircle
          className="h-[18px] w-[18px] flex-shrink-0"
          style={{ color: '#a8423a' }}
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
          style={{ color: '#a68668' }}
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

export default Toast
