import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { REVEAL_TIMING, createRevealController } from './reveal'

interface Frame {
  revealed: string
  finished: boolean
}

function harness(options: Partial<Parameters<typeof createRevealController>[0]> = {}) {
  const frames: Frame[] = []
  const controller = createRevealController({
    onFrame: (revealed, finished) => frames.push({ revealed, finished }),
    ...options,
  })
  const last = () => frames[frames.length - 1]
  return { controller, frames, last }
}

describe('the reveal controller', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses the owner-confirmed values', () => {
    expect(REVEAL_TIMING).toEqual({
      cadenceMs: 24,
      sentencePause: 9,
      commaPause: 4,
      catchUpAt: [60, 120],
      catchUpFactors: [0.6, 0.35],
      finishWithinMs: 1500,
    })
  })

  it('reveals one character per 24 ms at the steady cadence', () => {
    const { controller, last } = harness()
    controller.setTarget('abcd')
    vi.advanceTimersByTime(0)
    expect(last().revealed).toBe('a')
    vi.advanceTimersByTime(24)
    expect(last().revealed).toBe('ab')
    vi.advanceTimersByTime(24)
    expect(last().revealed).toBe('abc')
    vi.advanceTimersByTime(23)
    expect(last().revealed).toBe('abc')
    vi.advanceTimersByTime(1)
    expect(last().revealed).toBe('abcd')
  })

  it('pauses nine times longer after a sentence end and four times after a comma', () => {
    const { controller, last } = harness()
    controller.setTarget('a. b, c')
    vi.advanceTimersByTime(0)
    vi.advanceTimersByTime(24)
    expect(last().revealed).toBe('a.')
    vi.advanceTimersByTime(24 * 9 - 1)
    expect(last().revealed).toBe('a.')
    vi.advanceTimersByTime(1)
    expect(last().revealed).toBe('a. ')
    vi.advanceTimersByTime(24 * 2)
    expect(last().revealed).toBe('a. b,')
    vi.advanceTimersByTime(24 * 4 - 1)
    expect(last().revealed).toBe('a. b,')
    vi.advanceTimersByTime(1)
    expect(last().revealed).toBe('a. b, ')
  })

  it('catches up when the queue passes 60 and 120 characters', () => {
    // A 100 ms cadence keeps the catch-up delays whole: 35 ms past 120
    // queued characters, 60 ms past 60, 100 ms below that.
    const { controller, last } = harness({ cadenceMs: 100 })
    controller.setTarget('x'.repeat(200))
    vi.advanceTimersByTime(0)
    expect(last().revealed.length).toBe(1)
    vi.advanceTimersByTime(35)
    expect(last().revealed.length).toBe(2)
    // Walk to a backlog of 120 (80 revealed), then the slower factor applies.
    vi.advanceTimersByTime(35 * 78)
    expect(last().revealed.length).toBe(80)
    vi.advanceTimersByTime(59)
    expect(last().revealed.length).toBe(80)
    vi.advanceTimersByTime(1)
    expect(last().revealed.length).toBe(81)
    // Walk to a backlog of 60 (140 revealed), then the steady cadence returns.
    vi.advanceTimersByTime(60 * 59)
    expect(last().revealed.length).toBe(140)
    vi.advanceTimersByTime(99)
    expect(last().revealed.length).toBe(140)
    vi.advanceTimersByTime(1)
    expect(last().revealed.length).toBe(141)
  })

  it('finishes no later than the bound after the stream completes', () => {
    const { controller, last } = harness()
    controller.setTarget('The reply. '.repeat(90))
    vi.advanceTimersByTime(0)
    controller.done()
    expect(last().finished).toBe(false)
    vi.advanceTimersByTime(1500)
    expect(last().finished).toBe(true)
    expect(last().revealed).toBe('The reply. '.repeat(90))
  })

  it('reports finished exactly once when the target was already revealed', () => {
    const { controller, frames } = harness()
    controller.setTarget('ab')
    vi.advanceTimersByTime(100)
    controller.done()
    controller.done()
    expect(frames.filter(frame => frame.finished)).toHaveLength(1)
  })

  it('shows text instantly under reduced motion', () => {
    const { controller, last } = harness({ reducedMotion: true })
    controller.setTarget('No artificial pacing.')
    expect(last().revealed).toBe('No artificial pacing.')
    controller.done()
    expect(last().finished).toBe(true)
  })

  it('continues from the shared prefix when the final text differs from the stream', () => {
    const { controller, last } = harness()
    controller.setTarget('Hello world')
    vi.advanceTimersByTime(24 * 9)
    expect(last().revealed).toBe('Hello worl')
    controller.setTarget('Hello there')
    expect(last().revealed).toBe('Hello ')
    vi.advanceTimersByTime(24 * 6)
    expect(last().revealed).toBe('Hello there')
  })

  it('reports finished again after the final text corrects a finished reveal', () => {
    const { controller, frames, last } = harness()
    controller.setTarget('Start with the mugs.')
    controller.done()
    vi.advanceTimersByTime(2000)
    expect(last().finished).toBe(true)
    // The complete event bolds the product name, which rewrites the text.
    controller.setTarget('Start with the **mugs**.')
    expect(last().finished).toBe(false)
    vi.advanceTimersByTime(2000)
    expect(last()).toEqual({ revealed: 'Start with the **mugs**.', finished: true })
    expect(frames.filter(frame => frame.finished)).toHaveLength(2)
  })

  it('flush shows everything and cancel stops every callback', () => {
    const { controller, frames, last } = harness()
    controller.setTarget('abcdef')
    controller.done()
    controller.flush()
    expect(last()).toEqual({ revealed: 'abcdef', finished: true })
    const count = frames.length
    controller.cancel()
    controller.setTarget('abcdefgh')
    vi.advanceTimersByTime(1000)
    expect(frames.length).toBe(count)
  })
})
