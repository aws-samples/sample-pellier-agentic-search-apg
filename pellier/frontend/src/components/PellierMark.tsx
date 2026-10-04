/**
 * The square p. mark: Ask Pellier's avatar, drawn from tokens so it follows
 * the theme (an ink square with an on-ink p in light, ivory with a black p in
 * dark; the dot is always copper). The favicon is the same mark as an SVG.
 */
import '../styles/surface-navigation.css'

export default function PellierMark({
  size = 20,
  className,
  'data-testid': testId,
}: {
  size?: number
  className?: string
  'data-testid'?: string
}) {
  return (
    <span
      className={['pellier-mark', className ?? ''].filter(Boolean).join(' ')}
      aria-hidden="true"
      data-testid={testId}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.68) }}
    >
      p<span className="pellier-brand-dot">.</span>
    </span>
  )
}
