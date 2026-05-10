/**
 * UserMessage tests — right-aligned ink bubble.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import UserMessage from './UserMessage'

describe('UserMessage', () => {
  it('renders the text content', () => {
    render(<UserMessage text="find me the best linen shirt" />)
    expect(
      screen.getByText('find me the best linen shirt'),
    ).toBeInTheDocument()
  })

  it('has the user-message testid for composition assertions', () => {
    render(<UserMessage text="hi" />)
    expect(screen.getByTestId('user-message')).toBeInTheDocument()
  })
})
