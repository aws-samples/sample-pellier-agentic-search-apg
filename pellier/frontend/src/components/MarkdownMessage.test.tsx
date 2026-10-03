import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarkdownMessage from './MarkdownMessage'

describe('MarkdownMessage editorial streaming', () => {
  it('places a live caret at the end of streaming prose and removes it on completion', () => {
    const { container, rerender } = render(
      <MarkdownMessage content="A considered linen edit." streaming />,
    )

    const streamingRoot = container.firstElementChild
    const caret = container.querySelector('[data-testid="editorial-streaming-caret"]')

    expect(streamingRoot).toHaveAttribute('aria-busy', 'true')
    expect(caret).toBeInTheDocument()
    expect(caret?.parentElement).toHaveTextContent('A considered linen edit.')

    rerender(<MarkdownMessage content="A considered linen edit." />)

    expect(container.firstElementChild).toHaveAttribute('aria-busy', 'false')
    expect(
      container.querySelector('[data-testid="editorial-streaming-caret"]'),
    ).not.toBeInTheDocument()
  })

  it('keeps the caret inside the final list item', () => {
    const { container } = render(
      <MarkdownMessage content={'- Linen shirt\n- Drawstring trousers'} streaming />,
    )

    const items = container.querySelectorAll('li')
    expect(items).toHaveLength(2)
    expect(items[1].querySelector('.editorial-streaming-caret')).toBeInTheDocument()
  })

  it('does not expose an unmatched bold delimiter while prose is streaming', () => {
    const { container } = render(
      <MarkdownMessage content="Just the **" streaming />,
    )

    expect(container).toHaveTextContent('Just the')
    expect(container).not.toHaveTextContent('**')
  })

  it('preserves bold product names inside recommendation lists', () => {
    const { container } = render(
      <MarkdownMessage content="- **Merino Travel Socks** by Pellier" />,
    )

    expect(container.querySelector('strong')).toHaveTextContent(
      'Merino Travel Socks',
    )
  })
})
