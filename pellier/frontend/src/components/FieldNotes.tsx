import { cssVar as c } from '../design/cssVars'
/**
 * FieldNotes — short editorial essays for the Storyboard route.
 *
 * Five notes total: one for each returning persona (Marco, Anna,
 * Theo, Jessica) and one editorial note written in the Pellier voice. Each
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
    kicker: 'From the editors',
    title: 'On asking for the piece, not the product.',
    body: [
      'A store that knows its floor should understand "a linen piece that travels well" as readily as "linen camp shirt." You know what you want before you know its name.',
    ],
    signature: 'The editors',
  },
  {
    id: 'field-note-anna',
    kicker: 'Field note No. 01',
    title: 'Anna, on gifting as a practiced art.',
    body: [
      'Anna is choosing a housewarming gift under $100. It needs to be in stock, and candles are off the list. Even when she asks for another idea, those limits still matter.',
    ],
    signature: 'Anna, a gift-giver',
  },
  {
    id: 'field-note-marco',
    kicker: 'Field note No. 02',
    title: 'Marco, on checking before the trip.',
    body: [
      'Seven orders, from a Hadley linen shirt to a leather holdall, point to travel. Before his next trip, Marco wants the count in Brooklyn and the dispatch window. A piece the store does not carry needs a different answer from one that is sold out.',
    ],
    signature: 'Marco, a regular',
  },
  {
    id: 'field-note-theo',
    kicker: 'Field note No. 03',
    title: 'Theo, on caring for what you keep.',
    body: [
      'Theo\'s orders trace a path from a brass incense holder to ceramic tumblers, a stoneware pour-over set and a wabi-sabi bowl. The bowl arrived chipped, and he wants an update on his ticket. Sharing a home with Jessica does not give him access to her case.',
    ],
    signature: 'Theo, a slow shopper',
  },
  {
    id: 'field-note-jessica',
    kicker: 'Field note No. 04',
    title: 'Jessica, on being made whole.',
    body: [
      'Jessica\'s sage waffle robe and reed diffuser were received back at the store. She paid $64 and $36, making a $100 credit request. Nadia must approve the request before a credit can be issued; asking again must not issue it twice.',
    ],
    signature: 'Jessica, a returning customer',
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
            <span style={{ color: c.ink2 }}>in five notes.</span>
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
