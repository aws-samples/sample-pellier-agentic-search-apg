/**
 * StoryboardTeaser - the 3-card editorial grid below the product sections.
 *
 * Validates Requirements 1.9.1, 1.9.2, 1.9.3, 1.9.4.
 *
 * Contract:
 *   - Renders exactly three cards in the authored order from
 *     `STORYBOARD_TEASERS` in copy.ts. Never a single editorial block
 *     (Req 1.9.1).
 *   - Each card has: editorial image with a golden wash overlay, a
 *     category badge, a volume number, a theme token, an italic
 *     Fraunces title, a 2-3 sentence excerpt, and a
 *     `Read the full vision \u203a` link in terracotta (Req 1.9.2).
 *   - Hovering a card scales its image to 1.05 (Req 1.9.3).
 *   - The eyebrow line composes to
 *     `{badge} \u00b7 {volume} \u00b7 {theme}` so the three cards read,
 *     in order, as: `MOOD FILM \u00b7 Vol. 12 \u00b7 Summer`,
 *     `VISION BOARD \u00b7 Vol. 11 \u00b7 The Makers`,
 *     `BEHIND THE SCENES \u00b7 Vol. 10 \u00b7 The Edit` (Req 1.9.4).
 *
 * Kept intentionally presentational - the home page composes it below
 * the product grid, and the Storyboard route (4.11) reuses it as-is.
 */
import { useState } from 'react'

import { STORYBOARD_TEASERS, type StoryboardTeaser as StoryboardTeaserCard } from '../copy'

// --- Design tokens (storefront.md) ---------------------------------------
const CREAM = '#fbf4e8'
const INK = '#2d1810'
const ACCENT = '#c44536'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'

const INTER_STACK = 'Inter, system-ui, sans-serif'
const FRAUNCES_STACK = 'Fraunces, Georgia, serif'

// Warm amber gradient over every editorial image so the grid reads as
// a single "golden hour" series rather than three disconnected photos.
// Req 1.9.2 calls this the "golden wash".
const GOLDEN_WASH =
  'linear-gradient(180deg, rgba(196, 69, 54, 0.08) 0%, rgba(45, 24, 16, 0.18) 45%, rgba(166, 134, 104, 0.22) 100%)'

// --- Public component ----------------------------------------------------

export default function StoryboardTeaser() {
  return (
    <section
      data-testid="storyboard-teaser"
      aria-labelledby="storyboard-teaser-heading"
      style={{
        background: CREAM,
        color: INK,
        padding: '96px 24px',
        fontFamily: INTER_STACK,
      }}
    >
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <header style={{ marginBottom: 48 }}>
          <p
            style={{
              fontFamily: INTER_STACK,
              fontSize: 11,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: INK_QUIET,
              margin: 0,
            }}
          >
            From the Storyboard
          </p>
          <h2
            id="storyboard-teaser-heading"
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 36,
              lineHeight: 1.1,
              color: INK,
              margin: '12px 0 0',
            }}
          >
            Field notes from a slower kind of shopping.
          </h2>
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
        background: CREAM,
      }}
    >
      {/* --- Image panel with golden wash ----------------------------- */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '4 / 5',
          overflow: 'hidden',
          borderRadius: 2,
          background: '#e8d8bc',
        }}
      >
        <img
          data-testid={`storyboard-card-image-${index}`}
          src={card.imageUrl}
          alt={card.imageAlt}
          loading="lazy"
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
            fontFamily: INTER_STACK,
            fontSize: 11,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: INK_QUIET,
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
            color: INK,
            margin: 0,
          }}
        >
          {card.title}
        </h3>
        <p
          data-testid={`storyboard-card-excerpt-${index}`}
          style={{
            fontFamily: INTER_STACK,
            fontSize: 14,
            lineHeight: 1.6,
            color: INK_SOFT,
            margin: 0,
          }}
        >
          {card.excerpt}
        </p>
        <a
          data-testid={`storyboard-card-link-${index}`}
          href="#storyboard"
          style={{
            // Req 1.9.2 - terracotta link.
            color: ACCENT,
            fontFamily: INTER_STACK,
            fontSize: 13,
            fontWeight: 500,
            letterSpacing: '0.02em',
            textDecoration: 'none',
            marginTop: 4,
            alignSelf: 'flex-start',
          }}
        >
          {card.link}
        </a>
      </div>
    </article>
  )
}
