/**
 * The tour's chapters: which control each stop rings, which surface a chapter
 * belongs to, and what this browser has already seen.
 *
 * The words live in `copy.ts` (`TOUR.CHAPTERS`). A chapter never clicks
 * anything: it rings a control and says what it is.
 */
import { useEffect } from 'react'
import { TOUR } from '../copy'

export type ChapterId = keyof typeof TOUR.CHAPTERS
export type TourSurface = 'storefront' | 'operator'

type StopCopy = (typeof TOUR.CHAPTERS)[ChapterId][number]

interface Target {
  /** The first match the page lays out. */
  selector: string
  /** Take the last match instead: the newest answer in the dock. */
  latest?: boolean
  /** A card or a list, ringed with a card's corners; a control takes a pill. */
  panel?: boolean
  /** In the page, not the fixed header, so it is brought into view before it is ringed. */
  inPage?: boolean
}

export interface TourStop {
  id: StopCopy['id']
  title: string
  body: string
  target: Target
}

const TARGETS: Record<StopCopy['id'], Target> = {
  'ask-pellier': { selector: '[data-tour="ask-pellier"]' },
  'builder-view': { selector: '.pellier-builder-toggle' },
  operator: { selector: '[data-tour="operator"]' },
  'choose-shopper': { selector: '[data-testid="ask-shoppers"]', panel: true },
  'who-asked': { selector: '[data-testid="turn-principal"]', latest: true, inPage: true },
  'how-answered': { selector: '[data-testid="turn-fold"]', latest: true, inPage: true },
  // Not the panel that says the rail sent no ranking: the stop describes the table.
  'how-ranked': { selector: '.results-ranking:not(.tn-rank-unavailable)', panel: true, inPage: true },
  'desk-sections': { selector: '.op-bar-sections' },
  'asked-in-chat': { selector: '[data-testid="operator-credit-request"]', panel: true, inPage: true },
  investigate: { selector: '[data-testid="operator-investigate"]', inPage: true },
  'records-show': { selector: '[data-testid="operator-brief"]', panel: true, inPage: true },
  'three-checks': { selector: '[data-testid="operator-credit-checks"]', panel: true, inPage: true },
  decision: { selector: '[data-tour="credit-decision"]', panel: true, inPage: true },
}

/** Each surface's chapters, in the order they are told. */
const SURFACE_CHAPTERS: Record<TourSurface, ChapterId[]> = {
  storefront: ['storefront', 'answer'],
  operator: ['desk', 'proposal'],
}

const CHAPTER_ORDER = [...SURFACE_CHAPTERS.storefront, ...SURFACE_CHAPTERS.operator]

/**
 * The orientation keeps a stop whose control is folded away, as the switches
 * are in a phone's menu, and centres its card. Every other chapter describes
 * what is on the page, so a stop with nothing to ring is left out.
 */
const ORIENTATION: ChapterId = 'storefront'

/** Announced on window to open the tour: a chapter in `detail`, or none from the replay button. */
export const TOUR_START_EVENT = 'pellier:tour-start'
/** A chapter waits for the page to lay out, so its first ring lands on the control. */
export const TOUR_OPEN_DELAY_MS = 600

/** The Storefront chapter's flag in localStorage, and in sessionStorage the tab's off switch. */
export const SPOTLIGHT_SEEN_KEY = 'pellier-storefront-spotlight-seen'

export function chapterSeenKey(chapter: ChapterId): string {
  return chapter === ORIENTATION ? SPOTLIGHT_SEEN_KEY : `pellier-tour-seen-${chapter}`
}

export function chapterRank(chapter: ChapterId): number {
  return CHAPTER_ORDER.indexOf(chapter)
}

/** The control a stop rings, when the page lays it out. */
export function targetElement(target: Target): Element | null {
  const laidOut = Array.from(document.querySelectorAll(target.selector)).filter(element => {
    const rect = element.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
  })
  return (target.latest ? laidOut[laidOut.length - 1] : laidOut[0]) ?? null
}

/** A chapter's stops as the page stands now, for the replay button. */
export function chapterStops(chapter: ChapterId): TourStop[] {
  const stops = TOUR.CHAPTERS[chapter].map(stop => ({ ...stop, target: TARGETS[stop.id] }))
  return chapter === ORIENTATION ? stops : stops.filter(stop => targetElement(stop.target) !== null)
}

/**
 * A chapter's stops when the page can tell it whole, and none otherwise. A
 * chapter opens by itself once, so it waits for a page that shows every stop
 * rather than be used up half told: a stock answer has no ranking panel, and
 * a client with no chat request has no "Asked in chat".
 */
export function wholeChapter(chapter: ChapterId): TourStop[] {
  const stops = chapterStops(chapter)
  return stops.length === TOUR.CHAPTERS[chapter].length ? stops : []
}

/** Every stop the replay button plays on a surface: its chapters, one after the other. */
export function replayStops(surface: TourSurface): TourStop[] {
  return SURFACE_CHAPTERS[surface].flatMap(chapterStops)
}

/**
 * True in a tab that opened with `?tour=off`, and in the browser specs and
 * guide captures, which set the same session flag. It closes every chapter.
 * The header asks on every page, so the switch holds for the tab from
 * whichever page it opened on.
 */
export function toursOff(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('tour') === 'off') {
      window.sessionStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
      return true
    }
    return window.sessionStorage.getItem(SPOTLIGHT_SEEN_KEY) === 'true'
  } catch {
    return true
  }
}

// Seen once in this browser means seen in every tab: Lab 4 opens the
// storefront in a second tab, where a tour reopening over the header blocked
// the Operator link.
export function hasSeen(chapter: ChapterId): boolean {
  try {
    return toursOff() || window.localStorage.getItem(chapterSeenKey(chapter)) === 'true'
  } catch {
    return true
  }
}

export function markSeen(chapter: ChapterId): void {
  try {
    window.localStorage.setItem(chapterSeenKey(chapter), 'true')
  } catch {
    // Storage is optional. Without it a chapter may show again on the next page load; it never traps the visitor.
  }
}

/**
 * Asks for a chapter once the part of the page it describes is ready: an
 * answer that has settled, a record that has loaded. The chapter opens a
 * moment later, unless this browser has seen it or tours are off for the tab.
 */
export function useTourChapter(chapter: ChapterId, ready: boolean): void {
  useEffect(() => {
    if (!ready || hasSeen(chapter)) return
    const timer = window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent<ChapterId>(TOUR_START_EVENT, { detail: chapter }))
    }, TOUR_OPEN_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [chapter, ready])
}
