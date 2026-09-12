import { asset } from '../utils/assetPath'

/** The same outlined p. mark used by the browser icon and compact brand cues. */
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
    <img
      src={asset('/favicon.svg')}
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
      className={className}
      data-testid={testId}
      style={{ flexShrink: 0 }}
    />
  )
}
