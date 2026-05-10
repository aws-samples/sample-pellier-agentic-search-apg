/**
 * EditorialBrief — "About" section + colophon.
 *
 * Two-part closer before the footer:
 *
 *   1. About band — editorial portrait left, "About" eyebrow,
 *      curator credit, philosophy paragraph, and tech-stack chips.
 *   2. Colophon strip — single centered italic line on a slightly
 *      darker warm ground, doubling as the visual page-end signal.
 */

const BRIEF_IMAGE = '/products/editorial-brief-shayon.png'

export default function EditorialBrief() {
  return (
    <>
      {/* ── About band ── */}
      <section
        id="about"
        data-testid="editorial-brief"
        aria-label="About this workshop"
        className="w-full"
        style={{
          background: 'linear-gradient(180deg, #F7F3EE 0%, #EDE4D6 100%)',
          scrollMarginTop: 84,
        }}
      >
        <div className="max-w-[1440px] mx-auto px-container-x py-20 md:py-28">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            {/* Left: editorial illustration */}
            <div
              className="relative rounded-2xl overflow-hidden shadow-warm-md"
              style={{ aspectRatio: '16 / 10' }}
            >
              <img
                src={BRIEF_IMAGE}
                alt="Editorial brief — workshop curator at desk"
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                }}
              />
              <div
                className="absolute inset-0 pointer-events-none"
                aria-hidden
                style={{
                  background:
                    'linear-gradient(135deg, rgba(247,243,238,0.05) 0%, rgba(59,47,47,0.08) 100%)',
                }}
              />
            </div>

            {/* Right: editorial text */}
            <div className="flex flex-col gap-6">
              {/* Eyebrow */}
              <div className="flex items-center gap-2">
                <span
                  aria-hidden
                  style={{ color: '#a8423a', fontSize: '9px' }}
                >
                  &#9679;
                </span>
                <span
                  className="font-sans"
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: '#a8423a',
                  }}
                >
                  About
                </span>
              </div>

              {/* Headline */}
              <h2
                className="font-display italic text-espresso"
                style={{
                  fontSize: 'clamp(28px, 3.5vw, 44px)',
                  lineHeight: 1.1,
                  letterSpacing: '-0.01em',
                  fontWeight: 400,
                }}
              >
                Workshop built and
                <br />
                curated by
              </h2>

              {/* Name */}
              <div
                className="font-sans text-espresso"
                style={{
                  fontSize: 'clamp(22px, 2.5vw, 32px)',
                  fontWeight: 600,
                  letterSpacing: '-0.01em',
                }}
              >
                Shayon Sanyal
              </div>

              {/* Philosophy */}
              <p
                className="font-sans"
                style={{
                  fontSize: '15px',
                  lineHeight: 1.7,
                  maxWidth: '520px',
                  color: '#4a3a2e',
                }}
              >
                The best way to learn agentic AI is to take a working system
                apart. Every agent decision in this workshop traces back to a
                real product, a real embedding, and a real database query. The
                Boutique is built to feel like a place you'd actually shop
                &mdash; linen shirts with weight and a recommendation that
                knows what you bought last summer. The seams are visible
                because that's the point.
              </p>

              {/* Stack */}
              <div
                className="flex flex-wrap gap-2 mt-2"
                style={{ maxWidth: '520px' }}
              >
                {[
                  'Amazon Aurora',
                  'pgvector',
                  'Amazon Bedrock',
                  'AgentCore',
                  'Strands SDK',
                  'Claude',
                  'Cohere Embed v4',
                  'Amazon Transcribe',
                  'Cedar',
                ].map((tech) => (
                  <span
                    key={tech}
                    className="font-mono"
                    style={{
                      fontSize: '11px',
                      fontWeight: 500,
                      letterSpacing: '0.06em',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      background: 'rgba(31, 20, 16, 0.06)',
                      color: '#6b4a35',
                    }}
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Colophon strip ── */}
      <div
        className="w-full text-center"
        style={{ background: '#E8DFD4', padding: '28px 24px' }}
      >
        <p
          className="font-display italic"
          style={{
            fontSize: '15px',
            lineHeight: 1.5,
            color: '#6b5a4e',
            letterSpacing: '0.01em',
          }}
        >
          Built for re:Invent. Designed to be taken apart.
        </p>
      </div>
    </>
  )
}
