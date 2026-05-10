/**
 * PreferencesModal tests - Challenge 9.4b verification.
 *
 * Validates Requirement 2.6.6 (preferences modal half) and the
 * `storefront.md` "Preferences onboarding modal" spec.
 *
 * Coverage:
 *   - Modal renders only when UIContext.activeModal === 'preferences'.
 *   - Four groups render with the correct headings, chip counts, and
 *     chip kinds (card vs pill).
 *   - Chip toggle: click selects, click again deselects.
 *   - Selected chip visual state matches storefront.md exactly:
 *       background #2d1810, color #fbf4e8, border-color #2d1810.
 *   - Submit triggers `useAuth().savePreferences` with the tag-mapped
 *     payload, then closes the modal.
 *   - "Skip for now" closes the modal without posting.
 *   - Footer strip uses 10px mono and has a shield icon.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
} from 'vitest'

import PreferencesModal from './PreferencesModal'
import { PREFERENCES_MODAL } from '../copy'
import { UIProvider, useUI } from '../contexts/UIContext'
import type { Preferences } from '../services/types'

// Mock useAuth from utils/auth so we can observe savePreferences calls
// without hydrating the full AuthContext (which fires network requests).
const mockSavePreferences: Mock<(prefs: Preferences) => Promise<void>> = vi.fn()

vi.mock('../utils/auth', () => ({
  useAuth: () => ({
    user: { sub: 'u-1', email: 'e@x.com', givenName: 'Test' },
    preferences: null,
    prefsVersion: 0,
    isLoading: false,
    refresh: vi.fn(),
    savePreferences: mockSavePreferences,
    // Legacy fields we don't need, but kept for shape parity with the real hook.
    isAuthenticated: true,
    accessToken: null,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
  }),
}))

/**
 * Probe that opens the preferences modal and surfaces the current
 * activeModal so tests can assert close behavior.
 */
function Probe() {
  const { openModal, activeModal } = useUI()
  return (
    <div>
      <span data-testid="active">{activeModal ?? 'none'}</span>
      <button onClick={() => openModal('preferences')}>open-prefs</button>
    </div>
  )
}

function renderModal() {
  return render(
    <UIProvider>
      <Probe />
      <PreferencesModal />
    </UIProvider>,
  )
}

beforeEach(() => {
  mockSavePreferences.mockReset()
  mockSavePreferences.mockResolvedValue()
})

afterEach(() => {
  vi.clearAllMocks()
})

// ------------------------------------------------------------------
// Visibility + singleton
// ------------------------------------------------------------------

describe('PreferencesModal visibility', () => {
  it('renders nothing until activeModal === "preferences"', () => {
    renderModal()
    expect(screen.queryByTestId('prefs-modal')).toBeNull()
  })

  it('mounts when openModal("preferences") is called', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-prefs'))
    expect(screen.getByTestId('prefs-modal')).toBeInTheDocument()
  })

  it('closes when the backdrop is clicked', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-prefs'))
    expect(screen.getByTestId('prefs-modal')).toBeInTheDocument()

    await user.click(screen.getByTestId('prefs-modal-backdrop'))

    expect(screen.queryByTestId('prefs-modal')).toBeNull()
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })
})

// ------------------------------------------------------------------
// Structure: four groups, correct counts
// ------------------------------------------------------------------

describe('PreferencesModal structure (storefront.md)', () => {
  it('renders all four preference groups with correct headings', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    // Groups 0..3 correspond to vibe / colors / occasions / categories.
    for (let i = 0; i < 4; i += 1) {
      expect(screen.getByTestId(`prefs-group-${i}`)).toBeInTheDocument()
      expect(screen.getByTestId(`prefs-group-${i}-heading`)).toHaveTextContent(
        PREFERENCES_MODAL.GROUPS[i].heading,
      )
    }
  })

  it('Group 1 (Vibe) renders 6 cards with 2-word descriptors', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    const group = screen.getByTestId('prefs-group-0')
    expect(group.getAttribute('data-group-kind')).toBe('card')

    for (let chipIdx = 0; chipIdx < 6; chipIdx += 1) {
      const chip = screen.getByTestId(`prefs-chip-0-${chipIdx}`)
      expect(chip).toBeInTheDocument()
      // Each vibe chip carries a descriptor sub-line.
      const descriptor = PREFERENCES_MODAL.GROUPS[0].chips[chipIdx].descriptor
      if (descriptor) {
        expect(chip).toHaveTextContent(descriptor)
      }
    }

    // There is no 7th card.
    expect(screen.queryByTestId('prefs-chip-0-6')).toBeNull()
  })

  it('Group 2 (Colors) renders 5 pill chips with gradient swatches', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    expect(
      screen.getByTestId('prefs-group-1').getAttribute('data-group-kind'),
    ).toBe('pill')

    for (let chipIdx = 0; chipIdx < 5; chipIdx += 1) {
      expect(screen.getByTestId(`prefs-chip-1-${chipIdx}`)).toBeInTheDocument()
      // Each color chip has a swatch element.
      expect(
        screen.getByTestId(`prefs-chip-1-${chipIdx}-swatch`),
      ).toBeInTheDocument()
    }
    expect(screen.queryByTestId('prefs-chip-1-5')).toBeNull()
  })

  it('Group 3 (Occasions) renders 6 pill chips', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    expect(
      screen.getByTestId('prefs-group-2').getAttribute('data-group-kind'),
    ).toBe('pill')

    for (let chipIdx = 0; chipIdx < 6; chipIdx += 1) {
      expect(screen.getByTestId(`prefs-chip-2-${chipIdx}`)).toBeInTheDocument()
    }
    expect(screen.queryByTestId('prefs-chip-2-6')).toBeNull()
  })

  it('Group 4 (Categories) renders 6 pill chips', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    expect(
      screen.getByTestId('prefs-group-3').getAttribute('data-group-kind'),
    ).toBe('pill')

    for (let chipIdx = 0; chipIdx < 6; chipIdx += 1) {
      expect(screen.getByTestId(`prefs-chip-3-${chipIdx}`)).toBeInTheDocument()
    }
    expect(screen.queryByTestId('prefs-chip-3-6')).toBeNull()
  })

  it('renders the submit row with Skip + Save copy', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    expect(screen.getByTestId('prefs-modal-skip')).toHaveTextContent(
      PREFERENCES_MODAL.SKIP,
    )
    expect(screen.getByTestId('prefs-modal-submit')).toHaveTextContent(
      PREFERENCES_MODAL.SUBMIT,
    )
  })

  it('renders the 10px mono footer with shield icon', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    const footer = screen.getByTestId('prefs-modal-footer')
    expect(footer).toHaveTextContent(PREFERENCES_MODAL.FOOTER)
    expect(footer.style.fontSize).toBe('10px')
    expect(footer.style.fontFamily.toLowerCase()).toMatch(/mono/)
    expect(screen.getByTestId('prefs-modal-shield')).toBeInTheDocument()
  })
})

// ------------------------------------------------------------------
// Chip selection toggling
// ------------------------------------------------------------------

describe('PreferencesModal chip selection', () => {
  it('clicking a chip selects it; clicking again deselects', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    const chip = screen.getByTestId('prefs-chip-0-0') // Minimal

    expect(chip.getAttribute('data-selected')).toBe('false')
    expect(chip.getAttribute('aria-pressed')).toBe('false')

    await user.click(chip)
    expect(chip.getAttribute('data-selected')).toBe('true')
    expect(chip.getAttribute('aria-pressed')).toBe('true')

    await user.click(chip)
    expect(chip.getAttribute('data-selected')).toBe('false')
    expect(chip.getAttribute('aria-pressed')).toBe('false')
  })

  it('multiple chips in a group can be selected (multi-select)', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    const minimal = screen.getByTestId('prefs-chip-0-0')
    const serene = screen.getByTestId('prefs-chip-0-2')

    await user.click(minimal)
    await user.click(serene)

    expect(minimal.getAttribute('data-selected')).toBe('true')
    expect(serene.getAttribute('data-selected')).toBe('true')
  })

  it('selected chip visual state matches storefront.md exactly', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    const chip = screen.getByTestId('prefs-chip-0-1') // Bold

    await user.click(chip)

    // The three tokens asserted verbatim from storefront.md.
    // background: #2d1810 -> CSS reports rgb(45, 24, 16).
    expect(chip.style.background).toMatch(
      /rgb\(45,\s*24,\s*16\)|#2d1810/i,
    )
    expect(chip.style.color).toMatch(/rgb\(251,\s*244,\s*232\)|#fbf4e8/i)
    expect(chip.style.borderColor).toMatch(
      /rgb\(45,\s*24,\s*16\)|#2d1810/i,
    )
  })
})

// ------------------------------------------------------------------
// Save + Skip behavior
// ------------------------------------------------------------------

describe('PreferencesModal save + skip', () => {
  it('Save triggers savePreferences with the tag-mapped payload and closes', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    // Select one chip from each group so the payload covers all four tag
    // literal types end-to-end.
    await user.click(screen.getByTestId('prefs-chip-0-0')) // Vibe: Minimal -> 'minimal'
    await user.click(screen.getByTestId('prefs-chip-1-0')) // Colors: Warm tones -> 'warm'
    await user.click(screen.getByTestId('prefs-chip-2-2')) // Occasions: Evenings out -> 'evening'
    await user.click(screen.getByTestId('prefs-chip-3-0')) // Categories: Linen -> 'linen'

    await user.click(screen.getByTestId('prefs-modal-submit'))

    await waitFor(() => expect(mockSavePreferences).toHaveBeenCalledTimes(1))
    const [payload] = mockSavePreferences.mock.calls[0]
    expect(payload).toEqual({
      vibe: ['minimal'],
      colors: ['warm'],
      occasions: ['evening'],
      categories: ['linen'],
    })

    // Modal closed via UIContext singleton after save.
    await waitFor(() =>
      expect(screen.queryByTestId('prefs-modal')).toBeNull(),
    )
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('Save without any selections posts an empty Preferences payload', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    await user.click(screen.getByTestId('prefs-modal-submit'))

    await waitFor(() => expect(mockSavePreferences).toHaveBeenCalledTimes(1))
    expect(mockSavePreferences.mock.calls[0][0]).toEqual({
      vibe: [],
      colors: [],
      occasions: [],
      categories: [],
    })
  })

  it('Skip closes the modal without calling savePreferences', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    // Select a chip to prove Skip is a hard discard (not an implicit save).
    await user.click(screen.getByTestId('prefs-chip-0-0'))

    await user.click(screen.getByTestId('prefs-modal-skip'))

    expect(mockSavePreferences).not.toHaveBeenCalled()
    expect(screen.queryByTestId('prefs-modal')).toBeNull()
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('save error surfaces inline and keeps the modal open', async () => {
    mockSavePreferences.mockRejectedValueOnce(new Error('network_fail'))

    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-prefs'))

    await user.click(screen.getByTestId('prefs-chip-0-0'))
    await user.click(screen.getByTestId('prefs-modal-submit'))

    await waitFor(() =>
      expect(screen.getByTestId('prefs-modal-error')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('prefs-modal-error')).toHaveTextContent(
      'network_fail',
    )
    // Still mounted so the user can retry or skip.
    expect(screen.getByTestId('prefs-modal')).toBeInTheDocument()
  })
})
