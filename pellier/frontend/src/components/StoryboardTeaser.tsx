/**
 * Three editorial introductions to the corresponding FieldNotes essays.
 * Each title, excerpt and named link describes the note it opens.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { STORYBOARD_TEASERS, type StoryboardTeaser as StoryboardTeaserCard } from '../copy'
import ResponsiveImage from './ResponsiveImage'
import { cssVar as c } from '../design/cssVars'

// --- Design tokens (storefront.md) ---------------------------------------
const FRAUNCES_STACK = 'Fraunces, Georgia, serif'

// Warm amber gradient over every editorial image so the grid reads as
// a single "golden hour" series rather than three disconnected photos.
// Req 1.9.2 calls this the "golden wash".
const GOLDEN_WASH =
  'linear-gradient(180deg, rgba(196, 69, 54, 0.08) 0%, rgba(45, 24, 16, 0.18) 45%, rgba(166, 134, 104, 0.22) 100%)'

// --- Public component ----------------------------------------------------

export default function StoryboardTeaser({ headingLevel = 2 }: { headingLevel?: 1 | 2 }) {
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  return (
    <section
      data-testid="storyboard-teaser"
      aria-labelledby="storyboard-teaser-heading"
      style={{
        background: c.paper,
        color: c.ink,
        padding: '96px 24px',
        fontFamily: 'var(--sans)',
      }}
    >
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <header style={{ marginBottom: 48 }}>
          <p
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 11,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: c.muted,
              margin: 0,
            }}
          >
            Pellier Stories
          </p>
          <Heading
            id="storyboard-teaser-heading"
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 36,
              lineHeight: 1.1,
              color: c.ink,
              margin: '12px 0 0',
            }}
          >
            A few familiar faces.
          </Heading>
        </header>

        <div
          role="list"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 32,
          }}
        >
          {STORYBOARD_TEASERS.map((card, index) => (
            <StoryboardCard key={`${card.badge}-${card.volume}`} card={card} index={index} />
          ))}
        </div>
      </div>
    </section>
  )
}

// --- Card ---------------------------------------------------------------

interface StoryboardCardProps {
  card: StoryboardTeaserCard
  index: number
}

function StoryboardCard({ card, index }: StoryboardCardProps) {
  const [hovered, setHovered] = useState(false)

  // Eyebrow line: `{badge} \u00b7 {volume} \u00b7 {theme}` per Req 1.9.4.
  const eyebrow = `${card.badge} \u00b7 ${card.volume} \u00b7 ${card.theme}`

  return (
    <article
      role="listitem"
      data-testid={`storyboard-card-${index}`}
      data-hovered={hovered ? 'true' : 'false'}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        background: c.paper,
      }}
    >
      {/* --- Image panel with golden wash ----------------------------- */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '4 / 5',
          overflow: 'hidden',
          borderRadius: 'var(--pellier-image-radius-md)',
          background: '#e8d8bc',
        }}
      >
        <ResponsiveImage
          data-testid={`storyboard-card-image-${index}`}
          src={card.imageUrl}
          alt={card.imageAlt}
          loading="lazy"
          sizes="(min-width: 1024px) 405px, 90vw"
          pictureClassName="block h-full w-full"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
            // Req 1.9.3 - image scales to 1.05 on hover.
            transform: hovered ? 'scale(1.05)' : 'scale(1)',
            transition: 'transform 600ms ease-out',
            willChange: 'transform',
          }}
        />
        {/* Golden wash overlay sits above the image and below the text. */}
        <div
          aria-hidden
          data-testid={`storyboard-card-wash-${index}`}
          style={{
            position: 'absolute',
            inset: 0,
            background: GOLDEN_WASH,
            pointerEvents: 'none',
          }}
        />
      </div>

      {/* --- Text block --------------------------------------------- */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <p
          data-testid={`storyboard-card-eyebrow-${index}`}
          style={{
            fontFamily: 'var(--sans)',
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: c.muted,
            margin: 0,
          }}
        >
          {eyebrow}
        </p>
        <h3
          data-testid={`storyboard-card-title-${index}`}
          style={{
            fontFamily: FRAUNCES_STACK,
            fontStyle: 'italic',
            fontWeight: 400,
            fontSize: 24,
            lineHeight: 1.2,
            color: c.ink,
            margin: 0,
          }}
        >
          {card.title}
        </h3>
        <p
          data-testid={`storyboard-card-excerpt-${index}`}
          style={{
            fontFamily: 'var(--sans)',
            fontSize: 14,
            lineHeight: 1.6,
            color: c.ink2,
            margin: 0,
          }}
        >
          {card.excerpt}
        </p>
        <Link
          data-testid={`storyboard-card-link-${index}`}
          to={`#${card.noteId}`}
          style={{
            // Req 1.9.2 - terracotta link.
            color: c.accent,
            fontFamily: 'var(--sans)',
            fontSize: 13,
            fontWeight: 500,
            letterSpacing: '0.02em',
            textDecoration: 'none',
            marginTop: 4,
            alignSelf: 'flex-start',
          }}
        >
          {card.link}
        </Link>
      </div>
    </article>
  )
}
