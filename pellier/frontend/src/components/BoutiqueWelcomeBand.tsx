/**
 * BoutiqueWelcomeBand — dismissible editorial welcome under the hero.
 *
 * Symmetric with AtelierWelcome (which lives atop /atelier/sessions).
 * Sits between the BoutiqueHero photograph and the Weekend Edit
 * section, teaching the three things a first-visit shopper should
 * know before they scroll further:
 *
 *   1. You can just ask. (hero search bar, ⌘K, mic)
 *   2. Pick a persona. (header pill — Marco/Anna/Theo)
 *   3. Peek the wires. (Atelier toggle in the header)
 *
 * Dismiss persists in sessionStorage so returning attendees inside
 * the same browser session skip past it. Fresh tabs or re-opened
 * tabs get the intro again so every live demo starts clean.
 */
import { useState } from 'react'
import { X, Sparkles, UserCircle2, Microscope } from 'lucide-react'

const DISMISS_KEY = 'boutique-welcome-dismissed'

function hasBeenDismissed(): boolean {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

interface PillarProps {
  icon: React.ReactNode
  verb: string
  title: string
  description: string
}

function Pillar({ icon, verb, title, description }: PillarProps) {
  return (
    <div
      style={{
        background: '#FAF3E8',
        border: '1px solid rgba(31, 20, 16, 0.08)',
        borderRadius: '14px',
        padding: '22px 22px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      {/* Icon tile */}
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: '10px',
          background: 'rgba(168, 66, 58, 0.10)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#a8423a',
          marginBottom: 2,
        }}
      >
        {icon}
      </div>

      {/* Verb (burgundy mono eyebrow) */}
      <div
        style={{
          fontFamily: 'var(--mono)',
          fontSize: '10.5px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: '#a8423a',
          fontWeight: 600,
        }}
      >
        {verb}
      </div>

      {/* Headline (Fraunces italic) */}
      <div
        className="font-display italic"
        style={{
          fontSize: '20px',
          fontWeight: 400,
          letterSpacing: '-0.01em',
          color: '#1f1410',
          lineHeight: 1.15,
        }}
      >
        {title}
      </div>

      {/* Description */}
      <p
        className="font-sans"
        style={{
          fontSize: '13.5px',
          lineHeight: 1.6,
          color: '#6b4a35',
          margin: 0,
        }}
      >
        {description}
      </p>
    </div>
  )
}

export default function BoutiqueWelcomeBand() {
  const [dismissed, setDismissed] = useState(hasBeenDismissed)

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      /* ignore */
    }
    setDismissed(true)
  }

  if (dismissed) return null

  return (
    <section
      aria-label="Welcome to Pellier"
      className="w-full"
      style={{
        background:
          'linear-gradient(180deg, #FAF3E8 0%, #F2E7D1 100%)',
        borderTop: '1px solid rgba(31, 20, 16, 0.06)',
        borderBottom: '1px solid rgba(31, 20, 16, 0.06)',
      }}
    >
      <div
        className="max-w-[1440px] mx-auto px-container-x"
        style={{ padding: '48px 0 56px', position: 'relative' }}
      >
        {/* Dismiss button — absolute to the band content */}
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss welcome"
          className="transition-colors duration-150"
          style={{
            position: 'absolute',
            top: 20,
            right: 20,
            width: 32,
            height: 32,
            borderRadius: '50%',
            border: 'none',
            background: 'rgba(31, 20, 16, 0.05)',
            color: '#6b4a35',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(31, 20, 16, 0.10)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(31, 20, 16, 0.05)'
          }}
        >
          <X size={14} strokeWidth={2.5} />
        </button>

        {/* Header block */}
        <div
          className="px-container-x"
          style={{ maxWidth: '780px', marginBottom: '28px' }}
        >
          {/* Eyebrow */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '14px',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#a8423a',
                display: 'inline-block',
                boxShadow: '0 0 0 3px rgba(168, 66, 58, 0.18)',
              }}
            />
            <span
              className="font-sans"
              style={{
                fontSize: '11px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: '#a8423a',
                fontWeight: 600,
              }}
            >
              Welcome to Pellier
            </span>
          </div>

          {/* Headline */}
          <h2
            className="font-display italic"
            style={{
              fontSize: 'clamp(32px, 4vw, 48px)',
              fontWeight: 400,
              lineHeight: 1.08,
              letterSpacing: '-0.02em',
              color: '#1f1410',
              margin: '0 0 14px',
            }}
          >
            Three ways to shop the floor.
          </h2>

          {/* Summary */}
          <p
            className="font-sans"
            style={{
              fontSize: '16px',
              lineHeight: 1.65,
              color: '#6b4a35',
              margin: 0,
            }}
          >
            A boutique with a concierge. Tell Pellier what you&rsquo;re after and
            watch the pieces find you — or browse the editorial floor the old
            way. Every seam is intentional, and the wires are visible if you
            peek behind the curtain.
          </p>
        </div>

        {/* Pillar cards */}
        <div
          className="px-container-x"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '18px',
          }}
        >
          <Pillar
            icon={<Sparkles size={18} strokeWidth={2} />}
            verb="Ask Pellier"
            title="Search that understands."
            description={
              "Type or speak your own words — \"a linen shirt for warm evenings,\" \"a gift for someone who runs.\" Pellier reads the catalog and pulls what fits."
            }
          />
          <Pillar
            icon={<UserCircle2 size={18} strokeWidth={2} />}
            verb="Pick a persona"
            title="Let Pellier remember you."
            description={
              'Top-right pill switches you to Marco, Anna, or Theo. The cover, the grid, and the concierge tune themselves to each signal in real time.'
            }
          />
          <Pillar
            icon={<Microscope size={18} strokeWidth={2} />}
            verb="Peek the wires"
            title="Open the Atelier."
            description={
              "Curious how the magic works? Toggle to the Atelier in the header and watch every reasoning step, tool call, and memory read as it happens."
            }
          />
        </div>
      </div>
    </section>
  )
}
