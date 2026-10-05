/**
 * EditorialBrief: the About band plus a colophon strip.
 *
 * Two-part closer before the footer:
 *
 *   1. About band: editorial still life left; eyebrow, headline,
 *      Pellier/Observatory label, two paragraphs, and stack chips right.
 *      Every string comes from `ABOUT_BRIEF` in copy.ts so the page and
 *      the copy file cannot drift apart.
 *   2. Colophon strip: a single centred line under a hairline, doubling as
 *      the visual page-end signal.
 *
 * Both sit on the page ground (`--cream`, the page token): white in light and
 * black in dark. The title is Instrument Sans like every heading.
 */
import { Fragment } from 'react'
import { ABOUT_BRIEF } from '../copy'
import ResponsiveImage from './ResponsiveImage'

const BRIEF_IMAGE = ABOUT_BRIEF.IMAGE

const BODY_STYLE = {
  fontSize: '15px',
  lineHeight: 1.7,
  maxWidth: '520px',
  color: 'var(--ink-soft)',
} as const

export default function EditorialBrief() {
  return (
    <>
      <section
        id="about"
        data-testid="editorial-brief"
        aria-label="About Pellier"
        className="w-full"
        style={{
          background: 'var(--cream)',
          scrollMarginTop: 84,
        }}
      >
        <div className="max-w-[1440px] mx-auto px-container-x py-20 md:py-28">
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-[1.3fr_1fr] gap-x-12 lg:gap-x-16 gap-y-6 items-start">
            <div
              className="relative rounded-[var(--pellier-image-radius-lg)] overflow-hidden shadow-lift lg:col-start-1 lg:row-start-2 lg:mt-[5px]"
              style={{ aspectRatio: '4 / 3' }}
            >
              <ResponsiveImage
                src={BRIEF_IMAGE}
                widths={[480, 960]}
                sizes="(min-width: 1024px) 760px, 100vw"
                alt={ABOUT_BRIEF.IMAGE_ALT}
                pictureClassName="block h-full w-full"
                className="w-full h-full object-cover"
              />
              <div
                className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-frame"
                aria-hidden
              />
            </div>

            <div className="lg:col-start-2 flex flex-col gap-6">
              <div className="flex items-center gap-2">
                <span aria-hidden style={{ color: 'var(--accent)', fontSize: '9px' }}>
                  &#9679;
                </span>
                <span
                  className="font-sans"
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--accent)',
                  }}
                >
                  {ABOUT_BRIEF.EYEBROW}
                </span>
              </div>

              <h1
                className="text-ink"
                style={{
                  fontFamily: 'var(--dl-font-heading)',
                  fontSize: 'clamp(28px, 3.5vw, 44px)',
                  lineHeight: 1.1,
                  letterSpacing: 'var(--dl-track-tight)',
                  fontWeight: 500,
                }}
              >
                {ABOUT_BRIEF.TITLE_LINES.map((line, index) => (
                  <Fragment key={line}>
                    {index > 0 && <br />}
                    {line}
                  </Fragment>
                ))}
              </h1>
            </div>

            <div className="lg:col-start-2 lg:row-start-2 flex flex-col gap-6">
              <div
                className="font-sans"
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  letterSpacing: '0.2em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-quiet)',
                }}
              >
                {ABOUT_BRIEF.LABEL}
              </div>

              {ABOUT_BRIEF.PARAGRAPHS.map((paragraph) => (
                <p key={paragraph.slice(0, 32)} className="font-sans" style={BODY_STYLE}>
                  {paragraph}
                </p>
              ))}

              <ul
                aria-label="Built with"
                className="flex flex-wrap gap-2 mt-2 list-none p-0 m-0"
                style={{ maxWidth: '520px' }}
              >
                {ABOUT_BRIEF.STACK.map((tech) => (
                  <li
                    key={tech}
                    className="font-mono"
                    style={{
                      fontSize: '11px',
                      fontWeight: 500,
                      letterSpacing: '0.06em',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      border: '1px solid var(--dl-line-strong)',
                      color: 'var(--ink-soft)',
                    }}
                  >
                    {tech}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <div
        className="w-full text-center"
        style={{
          background: 'var(--cream)',
          borderTop: '1px solid var(--rule-1)',
          padding: '28px 24px',
        }}
      >
        <p
          className="font-sans"
          style={{
            fontSize: '15px',
            lineHeight: 1.5,
            color: 'var(--ink-soft)',
            letterSpacing: '0.01em',
          }}
        >
          {ABOUT_BRIEF.COLOPHON}
        </p>
      </div>
    </>
  )
}
