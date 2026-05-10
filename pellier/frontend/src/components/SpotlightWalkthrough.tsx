/**
 * Spotlight Walkthrough — Full-screen overlay with cutout highlighting + tooltip card.
 * Uses box-shadow cutout technique and rAF tracking for smooth spotlight positioning.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useLayout } from '../contexts/LayoutContext'
import { TOUR_STEPS, type TourAction } from '../data/tourSteps'
import { ChevronRight, X, Sparkles, PartyPopper, Github, Check } from 'lucide-react'

interface SpotlightWalkthroughProps {
  onAction: (actionKey: TourAction['actionKey']) => void
}

interface TargetRect {
  top: number
  left: number
  width: number
  height: number
}

const SpotlightWalkthrough = ({ onAction }: SpotlightWalkthroughProps) => {
  const { activeTour, tourStep, advanceTour, endTour } = useLayout()
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null)
  const rafRef = useRef<number>(0)
  const prevRectRef = useRef<TargetRect | null>(null)

  const steps = activeTour ? TOUR_STEPS[activeTour] : []
  const currentStep = steps[tourStep]
  const totalSteps = steps.length
  const isLastStep = tourStep === totalSteps - 1
  const padding = currentStep?.spotlightPadding ?? 8

  // Track target element position with rAF
  const trackTarget = useCallback(() => {
    if (!currentStep) return
    const el = document.querySelector(currentStep.selector)
    if (el) {
      const rect = el.getBoundingClientRect()
      const newRect = {
        top: rect.top - padding,
        left: rect.left - padding,
        width: rect.width + padding * 2,
        height: rect.height + padding * 2,
      }
      const prev = prevRectRef.current
      if (!prev || prev.top !== newRect.top || prev.left !== newRect.left ||
          prev.width !== newRect.width || prev.height !== newRect.height) {
        prevRectRef.current = newRect
        setTargetRect(newRect)
      }
    } else {
      if (prevRectRef.current !== null) {
        prevRectRef.current = null
        setTargetRect(null)
      }
    }
    rafRef.current = requestAnimationFrame(trackTarget)
  }, [currentStep, padding])

  useEffect(() => {
    if (!activeTour || !currentStep) return
    const el = document.querySelector(currentStep.selector)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    rafRef.current = requestAnimationFrame(trackTarget)
    return () => cancelAnimationFrame(rafRef.current)
  }, [activeTour, currentStep, trackTarget])

  // Keyboard navigation
  useEffect(() => {
    if (!activeTour) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') endTour()
      if (e.key === 'ArrowRight' || e.key === 'Enter') advanceTour()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [activeTour, advanceTour, endTour])

  if (!activeTour || !currentStep) return null

  // Compute tooltip position
  const getTooltipStyle = (): React.CSSProperties => {
    if (!targetRect) return { opacity: 0 }
    const gap = 16
    const tooltipWidth = 360

    switch (currentStep.position) {
      case 'bottom':
        return {
          top: targetRect.top + targetRect.height + gap,
          left: Math.max(16, Math.min(
            targetRect.left + targetRect.width / 2 - tooltipWidth / 2,
            window.innerWidth - tooltipWidth - 16
          )),
        }
      case 'top':
        return {
          bottom: window.innerHeight - targetRect.top + gap,
          left: Math.max(16, Math.min(
            targetRect.left + targetRect.width / 2 - tooltipWidth / 2,
            window.innerWidth - tooltipWidth - 16
          )),
        }
      case 'right':
        return {
          top: targetRect.top + targetRect.height / 2 - 80,
          left: targetRect.left + targetRect.width + gap,
        }
      case 'left':
        return {
          top: targetRect.top + targetRect.height / 2 - 80,
          right: window.innerWidth - targetRect.left + gap,
        }
      default:
        return {
          top: targetRect.top + targetRect.height + gap,
          left: targetRect.left,
        }
    }
  }

  // Celebration card — editorial cream card on espresso scrim.
  // Mirrors the storefront's Fraunces-italic + Inter register; no iOS
  // dark-mode carry-over. Red-1 for the primary action, mono for
  // meta, cream-1 for the card body.
  const celebrationCard = (
    <motion.div
      className="fixed inset-0 z-[2500] flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(31, 20, 16, 0.55)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' }}
        onClick={endTour}
      />
      <motion.div
        className="relative w-[480px] max-w-[92vw]"
        initial={{ opacity: 0, scale: 0.95, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 260, damping: 26, delay: 0.08 }}
      >
        <div
          className="rounded-2xl px-10 py-9 text-center"
          style={{
            background: 'var(--cream-1)',
            border: '1px solid var(--rule-1)',
            boxShadow: '0 24px 80px -16px rgba(31, 20, 16, 0.35)',
          }}
        >
          {/* Eyebrow — mono edition stamp, matches the hero register */}
          <div
            className="mb-6"
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10.5,
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: 'var(--red-1)',
              fontWeight: 500,
            }}
          >
            <span aria-hidden>●</span>&nbsp;&nbsp;The workshop&nbsp;&nbsp;<span aria-hidden>●</span>
          </div>

          {/* Animated check — ink circle with cream check, editorial */}
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.18, type: 'spring', stiffness: 220 }}
            style={{
              width: 56, height: 56, borderRadius: '50%', margin: '0 auto 18px',
              background: 'var(--ink-1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Check className="h-6 w-6" style={{ color: 'var(--cream-1)', strokeWidth: 2.5 }} />
          </motion.div>

          <h2
            className="mb-3"
            style={{
              fontFamily: 'var(--serif)',
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 30,
              lineHeight: 1.1,
              color: 'var(--ink-1)',
              letterSpacing: '-0.01em',
            }}
          >
            {currentStep.title}
          </h2>

          <p
            className="mb-7"
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 14,
              lineHeight: 1.6,
              letterSpacing: '-0.003em',
              color: 'var(--ink-3)',
              maxWidth: 380,
              margin: '0 auto',
            }}
          >
            {currentStep.description}
          </p>

          {/* Tech stack — editorial pill strip */}
          <div className="flex flex-wrap justify-center gap-1.5 mb-7">
            {['Aurora PostgreSQL', 'pgvector', 'Bedrock', 'Strands', 'AgentCore'].map(tech => (
              <span
                key={tech}
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-4)',
                  background: 'var(--cream-2)',
                  border: '1px solid var(--rule-1)',
                  padding: '4px 10px',
                  borderRadius: 999,
                }}
              >
                {tech}
              </span>
            ))}
          </div>

          <div className="flex items-center justify-center gap-2.5">
            <a
              href="https://github.com/aws-samples/sample-pellier-agentic-search-apg"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 transition-colors"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: 13,
                fontWeight: 500,
                letterSpacing: '-0.003em',
                padding: '9px 18px',
                borderRadius: 999,
                background: 'transparent',
                border: '1px solid var(--rule-2)',
                color: 'var(--ink-2)',
              }}
            >
              <Github className="h-3.5 w-3.5" />
              Source
            </a>
            <button
              onClick={advanceTour}
              className="flex items-center gap-1.5 transition-transform"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: 13,
                fontWeight: 500,
                letterSpacing: '-0.003em',
                padding: '9px 20px',
                borderRadius: 999,
                background: 'var(--red-1)',
                color: 'var(--cream-1)',
                boxShadow: '0 4px 12px rgba(196, 69, 54, 0.25)',
              }}
            >
              <PartyPopper className="h-3.5 w-3.5" />
              Start exploring
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )

  // Regular tooltip overlay
  const regularOverlay = (
    <motion.div
      key="spotlight-overlay"
      className="fixed inset-0 z-[2500]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
    >
      {/* Espresso scrim with cutout — matches editorial palette */}
      <div
        className="absolute inset-0"
        onClick={endTour}
        style={{ background: 'rgba(31, 20, 16, 0.62)' }}
      />

      {/* Spotlight cutout */}
      {targetRect && (
        <motion.div
          className="absolute"
          style={{
            top: targetRect.top,
            left: targetRect.left,
            width: targetRect.width,
            height: targetRect.height,
            borderRadius: 14,
            boxShadow: '0 0 0 9999px rgba(31, 20, 16, 0.62)',
            pointerEvents: 'none',
          }}
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 28 }}
        >
          {/* Subtle ring — burgundy, in register with the storefront */}
          <motion.div
            className="absolute inset-0"
            style={{ borderRadius: 14 }}
            animate={{
              boxShadow: [
                '0 0 0 2px rgba(196, 69, 54, 0.45), 0 0 18px rgba(196, 69, 54, 0.18)',
                '0 0 0 2px rgba(196, 69, 54, 0.65), 0 0 26px rgba(196, 69, 54, 0.24)',
                '0 0 0 2px rgba(196, 69, 54, 0.45), 0 0 18px rgba(196, 69, 54, 0.18)',
              ],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          />
        </motion.div>
      )}

      {/* Tooltip card */}
      <motion.div
        key={`tooltip-${tourStep}`}
        className="absolute"
        style={{
          ...getTooltipStyle(),
          width: 360,
          pointerEvents: 'auto',
        }}
        initial={{ opacity: 0, y: currentStep.position === 'top' ? 10 : -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28, delay: 0.08 }}
      >
        <div
          className="rounded-2xl"
          style={{
            background: 'var(--cream-1)',
            border: '1px solid var(--rule-1)',
            boxShadow: '0 16px 48px -8px rgba(31, 20, 16, 0.35)',
            padding: '18px 20px 16px',
          }}
        >
          {/* Header row: edition stamp + close */}
          <div className="flex items-center justify-between mb-3">
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'var(--red-1)',
                fontWeight: 500,
              }}
            >
              No. {String(tourStep + 1).padStart(2, '0')} / {String(totalSteps).padStart(2, '0')}
            </span>
            <button
              onClick={endTour}
              className="p-1 rounded-full transition-colors"
              aria-label="Close tour"
              style={{ color: 'var(--ink-4)' }}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Progress rule — thin burgundy line, not a progress bar */}
          <div
            className="mb-4 overflow-hidden"
            style={{ height: 1, background: 'var(--rule-1)' }}
          >
            <motion.div
              className="h-full"
              style={{ background: 'var(--red-1)' }}
              initial={{ width: 0 }}
              animate={{ width: `${((tourStep + 1) / totalSteps) * 100}%` }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            />
          </div>

          {/* Content */}
          <h3
            className="mb-2"
            style={{
              fontFamily: 'var(--serif)',
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 19,
              lineHeight: 1.15,
              letterSpacing: '-0.005em',
              color: 'var(--ink-1)',
            }}
          >
            {currentStep.title}
          </h3>
          <p
            className="mb-5"
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 13.5,
              lineHeight: 1.6,
              letterSpacing: '-0.003em',
              color: 'var(--ink-3)',
            }}
          >
            {currentStep.description}
          </p>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {currentStep.tryItAction && (
              <motion.button
                onClick={() => {
                  onAction(currentStep.tryItAction!.actionKey)
                  setTimeout(() => advanceTour(), 600)
                }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="flex items-center gap-1.5"
                style={{
                  fontFamily: 'var(--sans)',
                  fontSize: 12.5,
                  fontWeight: 500,
                  letterSpacing: '-0.003em',
                  padding: '8px 16px',
                  borderRadius: 999,
                  background: 'var(--red-1)',
                  color: 'var(--cream-1)',
                  boxShadow: '0 2px 8px rgba(196, 69, 54, 0.25)',
                }}
              >
                <Sparkles className="h-3.5 w-3.5" />
                {currentStep.tryItAction.label}
              </motion.button>
            )}
            <motion.button
              onClick={advanceTour}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="flex items-center gap-1 ml-auto"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: 12.5,
                fontWeight: 500,
                letterSpacing: '-0.003em',
                padding: '8px 14px',
                borderRadius: 999,
                background: 'var(--cream-2)',
                border: '1px solid var(--rule-2)',
                color: 'var(--ink-2)',
              }}
            >
              {isLastStep ? 'Done' : 'Next'}
              {!isLastStep && <ChevronRight className="h-3.5 w-3.5" />}
            </motion.button>
          </div>

          {/* Skip link */}
          {!isLastStep && (
            <button
              onClick={endTour}
              className="mt-3 block mx-auto transition-colors"
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                color: 'var(--ink-4)',
              }}
            >
              Skip tour
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )

  const overlay = (
    <AnimatePresence>
      {currentStep.celebration ? celebrationCard : regularOverlay}
    </AnimatePresence>
  )

  return createPortal(overlay, document.body)
}

export default SpotlightWalkthrough
