/**
 * AboutPage tests — `/about` route.
 *
 * Coverage: the document title. `AboutPage` renders the site chrome
 * (Header/Footer) exactly the same way `StoryboardPage` does, so this
 * mirrors that file's provider mocks rather than duplicating full chrome
 * coverage already proven there.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    accessToken: null,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
    preferences: null,
    prefsVersion: 0,
  }),
}))

vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({
    items: [],
    setCartOpen: vi.fn(),
  }),
}))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: null,
    switchPersona: vi.fn(),
    signOut: vi.fn(),
    switching: false,
  }),
}))

vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({
    activeModal: null,
    openModal: vi.fn(),
    closeModal: vi.fn(),
    chatSurface: 'drawer',
    toggleDrawer: vi.fn(),
    openChat: vi.fn(),
    announcementDismissed: {
      legacy: false,
      search: false,
      agentic: false,
      production: false,
    },
    dismissAnnouncement: vi.fn(),
  }),
}))

import AboutPage from './AboutPage'

function renderAbout() {
  return render(
    <MemoryRouter>
      <AboutPage />
    </MemoryRouter>,
  )
}

describe('AboutPage', () => {
  it('renders the About surface', () => {
    renderAbout()
    expect(screen.getByTestId('about-page')).toBeInTheDocument()
  })

  it('titles the tab, instead of leaving the generic index.html default', () => {
    document.title = 'Pellier | Your Personal Shopping Concierge'
    const { unmount } = renderAbout()

    expect(document.title).toBe('About | Pellier')

    unmount()
    expect(document.title).toBe('Pellier | Your Personal Shopping Concierge')
  })
})
