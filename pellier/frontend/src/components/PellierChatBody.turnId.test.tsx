/**
 * The turn id in the storefront chat body.
 *
 * In the Builder view each settled turn names its id: the key its
 * tool_audit rows and CloudWatch spans are filed under. Shoppers never see
 * it, and a turn still revealing does not show it, so it never moves the
 * answer above it.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PellierChatBody from './PellierChatBody'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const TURN = 'turn-6f424b82ec064c07aa0f00d7e121be12'

function answer(over: Partial<AgentChatMessage> = {}): AgentChatMessage {
  return {
    role: 'assistant',
    content: 'The linen throw is in stock.',
    timestamp: new Date('2026-10-09T17:00:00Z'),
    agentStatus: 'complete',
    turnId: TURN,
    ...over,
  }
}

function renderBody(messages: AgentChatMessage[], builderView: boolean) {
  return render(
    <PellierChatBody
      messages={messages}
      sendMessage={vi.fn()}
      retryMessage={vi.fn()}
      onEditRequest={vi.fn()}
      onAuthenticate={vi.fn()}
      addToCart={vi.fn()}
      persona={null}
      builderView={builderView}
    />,
  )
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'clipboard')
  window.getSelection()?.removeAllRanges()
})

describe('the turn id in the Builder view', () => {
  it('names each settled turn by the id the backend sent', () => {
    renderBody([answer(), answer({ turnId: 'turn-2' })], true)
    const lines = screen.getAllByTestId('turn-id').map(line => line.textContent)
    expect(lines).toEqual([`Turn${TURN}`, 'Turnturn-2'])
  })

  it('is hidden from shoppers when the Builder view is off', () => {
    renderBody([answer()], false)
    expect(screen.queryByTestId('turn-id')).not.toBeInTheDocument()
  })

  it('waits for a streaming turn to settle, and shows nothing without an id', () => {
    renderBody([answer({ agentStatus: 'streaming' }), answer({ turnId: undefined })], true)
    expect(screen.queryByTestId('turn-id')).not.toBeInTheDocument()
  })

  it('names a failed turn too, since its spans are filed under the same id', () => {
    const failure = { code: 'service_unavailable' as const, retryable: true, query: 'a linen throw' }
    renderBody([answer({ content: '', failure })], true)
    expect(screen.getByTestId('turn-id')).toHaveTextContent(TURN)
  })

  it('copies the id and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    stubClipboard(writeText)
    renderBody([answer()], true)
    fireEvent.click(screen.getByRole('button', { name: 'Copy turn id' }))
    expect(writeText).toHaveBeenCalledWith(TURN)
    expect(await screen.findByRole('button', { name: 'Turn id copied' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Turn id copied')
  })

  it('selects the id when the clipboard refuses, so the shortcut still copies it', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('NotAllowedError')))
    renderBody([answer()], true)
    fireEvent.click(screen.getByRole('button', { name: 'Copy turn id' }))
    await waitFor(() => expect(window.getSelection()?.toString()).toBe(TURN))
    expect(screen.getByRole('button', { name: 'Copy turn id' })).toBeInTheDocument()
  })
})
