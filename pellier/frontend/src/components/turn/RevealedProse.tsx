/**
 * An answer that settles in character by character.
 *
 * The reveal controller paces the text; this component draws it. While the
 * reveal runs, every character is a span that settles from copper into ink.
 * Once it finishes, the same paragraphs render as plain text with no layout
 * change. A message that mounts already complete shows at once.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from 'motion/react'
import { createRevealController, type RevealController } from '../../utils/reveal'
import { parseProse, type ProseBlock } from './prose'

export interface RevealedProseProps {
  /** The full text received so far. */
  text: string
  /** The stream has delivered its last character. */
  done: boolean
  /** Show everything now, for a stopped turn. */
  flush?: boolean
  /** A message from history: show it at once, never animate. */
  instant?: boolean
  /** Called with how much of `text` is on screen, and whether the reveal is over. */
  onProgress?: (revealedLength: number, finished: boolean) => void
  className?: string
}

interface Frame {
  revealed: string
  finished: boolean
}

function renderBlocks(blocks: ProseBlock[], live: boolean) {
  const nodes: JSX.Element[] = []
  let list: JSX.Element[] = []
  const flushList = () => {
    if (list.length === 0) return
    nodes.push(<ul key={`ul-${nodes.length}`} className="tn-prose-list">{list}</ul>)
    list = []
  }
  blocks.forEach((block, blockIndex) => {
    const runs = block.runs.map((run, runIndex) => {
      const content = live
        ? Array.from(run.text).map((char, charIndex) => (
            <span key={run.start + charIndex} className="tn-ch">{char}</span>
          ))
        : run.text
      return run.bold ? (
        <strong key={`${run.start}-${runIndex}`}>{content}</strong>
      ) : (
        <span key={`${run.start}-${runIndex}`}>{content}</span>
      )
    })
    if (block.kind === 'li') {
      list.push(<li key={`li-${blockIndex}`}>{runs}</li>)
      return
    }
    flushList()
    nodes.push(<p key={`p-${blockIndex}`}>{runs}</p>)
  })
  flushList()
  return nodes
}

export default function RevealedProse({
  text,
  done,
  flush = false,
  instant = false,
  onProgress,
  className,
}: RevealedProseProps) {
  const reducedMotion = useReducedMotion() ?? false
  const [frame, setFrame] = useState<Frame>(() => ({ revealed: instant ? text : '', finished: instant && done }))
  const controllerRef = useRef<RevealController | null>(null)
  const latest = useRef({ text, done, flush, onProgress })
  latest.current = { text, done, flush, onProgress }

  // The controller lives with the mounted component. StrictMode mounts,
  // unmounts and mounts again in development; each mount gets its own
  // controller, and the unmounted one is cancelled so it never calls back.
  useEffect(() => {
    const controller = createRevealController({
      reducedMotion: reducedMotion || instant,
      onFrame: (revealed, finished) => setFrame({ revealed, finished }),
    })
    controllerRef.current = controller
    controller.setTarget(latest.current.text)
    if (latest.current.done) controller.done()
    if (latest.current.flush) controller.flush()
    return () => {
      controller.cancel()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [reducedMotion, instant])

  useEffect(() => {
    controllerRef.current?.setTarget(text)
  }, [text])

  useEffect(() => {
    if (done) controllerRef.current?.done()
  }, [done])

  useEffect(() => {
    if (flush) controllerRef.current?.flush()
  }, [flush])

  useEffect(() => {
    latest.current.onProgress?.(frame.revealed.length, frame.finished)
  }, [frame])

  const blocks = useMemo(() => parseProse(frame.revealed), [frame.revealed])
  const live = !frame.finished

  return (
    <div
      className={['tn-prose', live ? 'tn-prose-live' : '', className ?? ''].filter(Boolean).join(' ')}
      aria-busy={live || undefined}
    >
      {renderBlocks(blocks, live)}
    </div>
  )
}
