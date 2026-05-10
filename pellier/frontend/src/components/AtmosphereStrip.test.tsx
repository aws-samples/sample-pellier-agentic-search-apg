/**
 * AtmosphereStrip tests — LIVE ticker below the hero.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import AtmosphereStrip from './AtmosphereStrip'

describe('AtmosphereStrip', () => {
  it('renders the LIVE state + skills loaded + median ms', () => {
    render(<AtmosphereStrip skillCount={2} medianMs={412} />)
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(screen.getByText(/2 SKILLS LOADED/)).toBeInTheDocument()
    expect(screen.getByText(/412MS MEDIAN/)).toBeInTheDocument()
  })

  it('pluralizes SKILLS correctly (singular at 1)', () => {
    render(<AtmosphereStrip skillCount={1} medianMs={120} />)
    expect(screen.getByText(/1 SKILL LOADED$/)).toBeInTheDocument()
  })

  it('shows 0 SKILLS LOADED in pre-turn empty state', () => {
    render(<AtmosphereStrip skillCount={0} medianMs={null} />)
    expect(screen.getByText(/0 SKILLS LOADED$/)).toBeInTheDocument()
  })

  it('shows em-dash when medianMs is null (pre-turn empty state)', () => {
    render(<AtmosphereStrip skillCount={0} medianMs={null} />)
    expect(screen.getByText(/^—$/)).toBeInTheDocument()
  })

  it('singular ACTIVE SESSION at default count of 1', () => {
    render(<AtmosphereStrip skillCount={0} medianMs={null} />)
    expect(screen.getByText(/1 ACTIVE SESSION$/)).toBeInTheDocument()
  })
})
