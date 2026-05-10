/**
 * AssistantText tests — flow text with citation pills.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import AssistantText from './AssistantText'

describe('AssistantText', () => {
  it('renders the assistant text', () => {
    render(<AssistantText text="Three pieces stand out, all under $150." />)
    expect(
      screen.getByText(/Three pieces stand out/),
    ).toBeInTheDocument()
  })

  it('renders a citation pill when citations are provided', () => {
    render(
      <AssistantText
        text="The Italian Linen Camp Shirt is the strongest match."
        citations={[{ k: 'beans.b_colombia_huila', ref: 'trace 7' }]}
      />,
    )
    expect(screen.getByTestId('citation-pill-trace 7')).toBeInTheDocument()
    expect(screen.getByText('trace 7')).toBeInTheDocument()
  })

  it('calls onCitationClick with the pill ref when clicked', async () => {
    const onCitationClick = vi.fn()
    const user = userEvent.setup()
    render(
      <AssistantText
        text="A match."
        citations={[{ k: 'x', ref: 'trace 12' }]}
        onCitationClick={onCitationClick}
      />,
    )
    await user.click(screen.getByTestId('citation-pill-trace 12'))
    expect(onCitationClick).toHaveBeenCalledWith('trace 12')
  })

  it('does not render the citations row when none are present', () => {
    render(<AssistantText text="Flat text." />)
    expect(
      screen.queryByTestId('assistant-text-citations'),
    ).not.toBeInTheDocument()
  })
})
