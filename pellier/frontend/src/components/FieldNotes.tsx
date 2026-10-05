import { cssVar as c } from '../design/cssVars'
/**
 * FieldNotes — short editorial essays for the Storyboard route.
 *
 * Four notes total: one for each returning persona (Marco, Anna,
 * Theo) and one editorial note written in the Pellier voice. Each
 * note is a short Instrument Sans title over a prose body at 15px/1.7, so
 * the page reads as "the storefront wrote this, not a marketing page." The
 * section sits on the page ground, black in the dark theme.
 *
 * The footer tagline "Field notes from a slower kind of shopping" is
 * the section's single editorial anchor — carried over from the old
 * footer newsletter column so the phrase earns a home instead of
 * being decoration beneath a dead subscribe form.
 */
const HEADING = 'var(--dl-font-heading)'

interface Note {
  id: string
  kicker: string
  title: string
  body: string[]
  signature: string
}

const NOTES: readonly Note[] = [
  {
    id: 'field-note-editors',
    kicker: 'Field note No. 01',
    title: 'On asking for the piece, not the product.',
    body: [
      'A store that knows its floor should answer "a linen piece that travels well" as readily as "camp shirt, size 41." You know what you want before you know its name.',
    ],
    signature: 'The editors',
  },
  {
    id: 'field-note-marco',
    kicker: 'Field note No. 02',
    title: 'Marco, on being remembered.',
    body: [
      'Seven orders, from a Hadley linen shirt to a leather holdall, point to travel. When Marco signs back in, Pellier leads with the next piece for the trip.',
    ],
    signature: 'Marco, a regular',
  },
  {
    id: 'field-note-anna',
    kicker: 'Field note No. 03',
    title: 'Anna, on gifting as a practiced art.',
    body: [
      'Anna arrives with people, not products, and a gift under $100 is a real limit. Pellier holds to it, and can show that it did.',
    ],
    signature: 'Anna, a gift-giver',
  },
  {
    id: 'field-note-theo',
    kicker: 'Field note No. 04',
    title: 'Theo, on pieces that wear in.',
    body: [
      'First a brass incense holder, then ceramic tumblers, a stoneware pour-over set and a wabi-sabi bowl. Each piece earned the next, and Theo comes back for things that wear in.',
    ],
    signature: 'Theo, a slow shopper',
  },
]

export default function FieldNotes() {
  return (
    <section
      data-testid="field-notes"
      aria-labelledby="field-notes-heading"
      style={{
        background: c.bg,
        padding: '72px 24px 96px',
      }}
    >
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        <header style={{ marginBottom: 48 }}>
          <p
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 11,
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: c.accent,
              fontWeight: 500,
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: c.accent,
                display: 'inline-block',
              }}
            />
            Field notes
          </p>
          <h2
            id="field-notes-heading"
            style={{
              scrollMarginTop: 96,
              fontFamily: HEADING,
              fontWeight: 500,
              fontSize: 'var(--text-section)',
              lineHeight: 1.1,
              letterSpacing: 'var(--dl-track-tight)',
              color: c.ink,
              margin: '16px 0 0',
            }}
          >
            A slower kind of shopping,{' '}
            <span style={{ color: c.ink2 }}>in four notes.</span>
          </h2>
          <p
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 17,
              lineHeight: 1.6,
              color: c.ink2,
              margin: '16px 0 0',
              maxWidth: 560,
            }}
          >
            Short notes on how Pellier reads the floor.
          </p>
        </header>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 64 }}>
          {NOTES.map((note, i) => (
            <article
              key={note.title}
              id={note.id}
              tabIndex={-1}
              aria-labelledby={`${note.id}-heading`}
              data-testid={`field-note-${i}`}
              style={{
                scrollMarginTop: 'calc(var(--pellier-surface-bar-height, 64px) + 96px)',
                borderTop: `1px solid ${c.line}`,
                paddingTop: 32,
              }}
            >
              <p
                style={{
                  fontFamily: 'var(--sans)',
                  fontSize: 11,
                  letterSpacing: '0.22em',
                  textTransform: 'uppercase',
                  color: c.muted,
                  fontWeight: 500,
                  margin: 0,
                }}
              >
                {note.kicker}
              </p>
              <h3
                id={`${note.id}-heading`}
                style={{
                  fontFamily: HEADING,
                  fontWeight: 500,
                  fontSize: 'var(--text-sub)',
                  lineHeight: 1.25,
                  letterSpacing: 'var(--dl-track-tight)',
                  color: c.ink,
                  margin: '10px 0 14px',
                }}
              >
                {note.title}
              </h3>
              {note.body.map((paragraph, j) => (
                <p
                  key={j}
                  style={{
                    fontFamily: 'var(--sans)',
                    fontSize: 15,
                    lineHeight: 1.7,
                    letterSpacing: '-0.003em',
                    color: c.ink,
                    margin: j === 0 ? 0 : '16px 0 0',
                  }}
                >
                  {paragraph}
                </p>
              ))}
              <p
                style={{
                  fontFamily: 'var(--sans)',
                  fontWeight: 500,
                  fontSize: 13,
                  letterSpacing: '0.01em',
                  color: c.muted,
                  margin: '16px 0 0',
                }}
              >
                {note.signature}
              </p>
            </article>
          ))}
        </div>
        <div
          style={{
            marginTop: 72,
            paddingTop: 24,
            borderTop: `1px solid ${c.line}`,
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <p
            style={{
              fontFamily: 'var(--sans)',
              fontSize: 14,
              lineHeight: 1.6,
              color: c.ink2,
              textAlign: 'center',
              margin: 0,
              maxWidth: 420,
            }}
          >
            More notes arrive with each Edit.
          </p>
        </div>
      </div>
    </section>
  )
}
