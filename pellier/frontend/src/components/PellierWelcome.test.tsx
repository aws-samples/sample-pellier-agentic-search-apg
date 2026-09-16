import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PellierWelcome, { composeWelcomeGreeting } from './PellierWelcome'

const onSend = vi.fn()

function liveFetch(input: RequestInfo | URL): Promise<Response> {
  const url = String(input)
  if (url.startsWith('/api/products')) {
    return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))
  }
  if (url.startsWith('/api/observatory/scenarios')) {
    return Promise.resolve(new Response(JSON.stringify({
      scenarios: [
        { id: 1, ordinal: 1, prompt: 'Required one', journeyRole: 'required' },
        { id: 2, ordinal: 2, prompt: 'Required two', journeyRole: 'required' },
        { id: 3, ordinal: 3, prompt: 'Required three', journeyRole: 'required' },
        { id: 4, ordinal: 4, prompt: 'Explore one', journeyRole: 'explore' },
        { id: 5, ordinal: 5, prompt: 'Explore two', journeyRole: 'explore' },
      ],
    }), { status: 200 }))
  }
  return Promise.reject(new Error(`Unexpected request: ${url}`))
}

describe('composeWelcomeGreeting', () => {
  beforeEach(() => {
    onSend.mockReset()
    vi.stubGlobal('fetch', vi.fn(liveFetch))
  })

  it('adds terminal punctuation to an unfinished greeting suffix', () => {
    expect(composeWelcomeGreeting('Good evening', ', Anna')).toBe(
      'Good evening, Anna.',
    )
  })

  it('does not duplicate punctuation from a complete suffix', () => {
    expect(composeWelcomeGreeting('Good morning', ', Marco.')).toBe(
      'Good morning, Marco.',
    )
  })

  it('separates the three required turns from optional exploration', async () => {
    render(<PellierWelcome onSend={onSend} persona={{
      id: 'anna',
      display_name: 'Anna',
      customer_id: 'CUST-ANNA',
    } as never} />)

    const required = await screen.findByRole('region', {
      name: 'Ideas to begin your conversation',
    })
    expect(required.querySelectorAll('button')).toHaveLength(3)
    expect(screen.getByRole('region', { name: 'Explore further' })
      .querySelectorAll('button')).toHaveLength(2)
  })

  it('keeps editorial photography available while the live edit is loading', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<PellierWelcome onSend={onSend} persona={{ id: 'marco', display_name: 'Marco' } as never} />)
    expect(screen.getByRole('img').getAttribute('src')).toMatch(/\/products\/hero-marco(?:-\d+)?\.(?:png|webp)$/)
    expect(screen.getByText(/Opening your edit and a few ideas/)).toBeInTheDocument()
    expect(screen.queryByText(/pieces in your current edit/)).not.toBeInTheDocument()
  })

  it('keeps a failed catalog read explicit without turning the photograph into a recommendation', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 503 }))))
    render(<PellierWelcome onSend={onSend} />)
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByText(/Your edit is taking a little longer/)).toBeInTheDocument()
    expect(screen.getByRole('img')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Ideas to begin your conversation' })).not.toBeInTheDocument()
    fireEvent.error(screen.getByRole('img'))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
