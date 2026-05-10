/**
 * Layout Context — Coordinates chat mode, workshop mode, and main content margin.
 * Persists workshop mode and onboarding state to localStorage.
 */
import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { TOUR_STEPS } from '../data/tourSteps'

type ChatMode = 'floating' | 'docked'
export type WorkshopMode = 'legacy' | 'search' | 'agentic' | 'production'

interface LayoutContextType {
  chatMode: ChatMode
  setChatMode: (mode: ChatMode) => void
  chatOpen: boolean
  setChatOpen: (open: boolean) => void
  mainContentMarginRight: number
  workshopMode: WorkshopMode
  setWorkshopMode: (mode: WorkshopMode) => void
  guardrailsEnabled: boolean
  setGuardrailsEnabled: (enabled: boolean) => void
  showOnboarding: boolean
  setShowOnboarding: (show: boolean) => void
  activeTour: WorkshopMode | null
  tourStep: number
  startTour: (mode: WorkshopMode) => void
  advanceTour: () => void
  endTour: () => void
  isTourComplete: (mode: WorkshopMode) => boolean
  resetWorkshop: () => void
}

const LayoutContext = createContext<LayoutContextType | undefined>(undefined)

export function useLayout() {
  const ctx = useContext(LayoutContext)
  if (!ctx) throw new Error('useLayout must be used within LayoutProvider')
  return ctx
}

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [chatMode, setChatMode] = useState<ChatMode>('docked')
  const [chatOpen, setChatOpen] = useState(false)
  const [workshopMode, setWorkshopModeRaw] = useState<WorkshopMode>(() => {
    const saved = localStorage.getItem('pellier-workshop-mode')
    if (saved && ['legacy', 'search', 'agentic', 'production'].includes(saved)) return saved as WorkshopMode
    return 'legacy'
  })
  const [guardrailsEnabled, setGuardrailsEnabled] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(() => !localStorage.getItem('pellier-onboarding-done'))
  const [activeTour, setActiveTour] = useState<WorkshopMode | null>(null)
  const [tourStep, setTourStep] = useState(0)
  const tourStepRef = useRef(0)

  const isTourComplete = useCallback((mode: WorkshopMode) => {
    return !!localStorage.getItem(`pellier-tour-${mode}-done`)
  }, [])

  const setWorkshopMode = useCallback((mode: WorkshopMode) => {
    setWorkshopModeRaw(mode)
    localStorage.setItem('pellier-workshop-mode', mode)
    // Auto-start tour for each lab if not already completed
    if (!localStorage.getItem(`pellier-tour-${mode}-done`)) {
      setTimeout(() => {
        setTourStep(0)
        tourStepRef.current = 0
        setActiveTour(mode)
      }, 800)
    }
  }, [])

  // Auto-start tour on mount for current mode (if not completed and onboarding is done)
  useEffect(() => {
    if (showOnboarding) return // let onboarding finish first
    if (!localStorage.getItem(`pellier-tour-${workshopMode}-done`)) {
      const timer = setTimeout(() => {
        setTourStep(0)
        tourStepRef.current = 0
        setActiveTour(workshopMode)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- mount only

  const startTour = useCallback((mode: WorkshopMode) => {
    setTourStep(0)
    tourStepRef.current = 0
    setActiveTour(mode)
  }, [])

  const advanceTour = useCallback(() => {
    if (!activeTour) return
    const steps = TOUR_STEPS[activeTour]
    const next = tourStepRef.current + 1
    if (next >= steps.length) {
      localStorage.setItem(`pellier-tour-${activeTour}-done`, '1')
      setActiveTour(null)
      setTourStep(0)
      tourStepRef.current = 0
    } else {
      tourStepRef.current = next
      setTourStep(next)
    }
  }, [activeTour])

  const endTour = useCallback(() => {
    if (activeTour) {
      localStorage.setItem(`pellier-tour-${activeTour}-done`, '1')
    }
    setActiveTour(null)
    setTourStep(0)
    tourStepRef.current = 0
  }, [activeTour])

  const resetWorkshop = useCallback(() => {
    // Clear all persisted state
    localStorage.removeItem('pellier-onboarding-done')
    localStorage.removeItem('pellier-workshop-mode')
    localStorage.removeItem('pellier-tour-legacy-done')
    localStorage.removeItem('pellier-tour-search-done')
    localStorage.removeItem('pellier-tour-agentic-done')
    localStorage.removeItem('pellier-tour-production-done')
    // Reset runtime state
    setActiveTour(null)
    setTourStep(0)
    tourStepRef.current = 0
    setWorkshopModeRaw('legacy')
    setShowOnboarding(true)
  }, [])

  const mainContentMarginRight = chatMode === 'docked' && chatOpen ? 420 : 0

  return (
    <LayoutContext.Provider value={{ chatMode, setChatMode, chatOpen, setChatOpen, mainContentMarginRight, workshopMode, setWorkshopMode, guardrailsEnabled, setGuardrailsEnabled, showOnboarding, setShowOnboarding, activeTour, tourStep, startTour, advanceTour, endTour, isTourComplete, resetWorkshop }}>
      {children}
    </LayoutContext.Provider>
  )
}
