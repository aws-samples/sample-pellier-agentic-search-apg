import { cssVar as c } from '../design/cssVars'
/**
 * FieldNotes — short editorial essays for the Storyboard route.
 *
 * Four notes total: one for each returning persona (Marco, Anna,
 * Theo) and one editorial note written in the Pellier voice. Each
 * note is a tight italic Fraunces dek + a prose body in Instrument Sans, 15px/
 * 1.7, matching the Observatory AssistantText register so the page reads
 * as "the storefront wrote this, not a marketing page."
 *
 * The footer tagline "Field notes from a slower kind of shopping" is
 * the section's single editorial anchor — carried over from the old
 * footer newsletter column so the phrase earns a home instead of
 * being decoration beneath a dead subscribe form.
 */
const RULE_1 = 'rgba(45, 24, 16, 0.08)'

const FRAUNCES_STACK = 'Fraunces, Georgia, serif'

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
    kicker: 'Field note · No. 01',
    title: 'On asking for the piece, not the product.',
    body: [
      'A boutique that knows its floor should answer "a linen piece that travels well" as readily as "camp shirt, size 41." They are the same question dressed differently. The first is softer. The second assumes you already know the name.',
      'Pellier is built on the smaller, quieter assumption: that you know what you want, not what it is called.',
    ],
    signature: 'The editors',
  },
  {
    id: 'field-note-marco',
    kicker: 'Field note · No. 02',
    title: 'Marco, on being remembered.',
    body: [
      'A run of orders tells a story. A Hadley linen shirt, then the camp shirt, drawstring trousers, an overshirt, a crew tee. Then a leather holdall and merino travel socks. Nobody who buys in that order is dressing for the office.',
      'When Marco signs back in, Pellier does not start over. It leads with the next piece for the trip rather than another copy of what he already owns, because the thread of his orders points there.',
    ],
    signature: 'Marco, a regular',
  },
  {
    id: 'field-note-anna',
    kicker: 'Field note · No. 03',
    title: 'Anna, on gifting as a practiced art.',
    body: [
      'Gifts are the hardest requests a boutique will take. They are indirect by design: the shopper is not the recipient, the recipient is not in the room, and the occasion matters more than the object.',
      'Anna arrives with people, not products. A milestone gift under a hundred is a real constraint, and a useful one. Pellier holds to it, and can show that it did.',
    ],
    signature: 'Anna, a gift-giver',
  },
  {
    id: 'field-note-theo',
    kicker: 'Field note · No. 04',
    title: 'Theo, on pieces that wear in.',
    body: [
      'First a brass incense holder. Then ceramic tumblers, a stoneware pour-over set, and most recently a wabi-sabi bowl. Nothing in that sequence was an impulse. Each piece earned the next.',
      'Slow craft is what happens when a shopper does not want to be told what is new. Theo returns for ceramics, linen throws and stoneware: pieces that do more of their work later than sooner.',
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
        background: c.paper,
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
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 44,
              lineHeight: 1.1,
              letterSpacing: '-0.01em',
              color: c.ink,
              margin: '16px 0 0',
            }}
          >
            A slower kind of shopping,{' '}
            <span style={{ color: c.ink2 }}>in four notes.</span>
          </h2>
          <p
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 17,
              lineHeight: 1.6,
              color: c.ink2,
              margin: '16px 0 0',
              maxWidth: 560,
            }}
          >
            Short pieces Pellier wrote about how it reads the
            floor, what it remembers, and why it answers the way it
            does.
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
                borderTop: `1px solid ${RULE_1}`,
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
                  fontFamily: FRAUNCES_STACK,
                  fontStyle: 'italic',
                  fontWeight: 400,
                  fontSize: 28,
                  lineHeight: 1.2,
                  letterSpacing: '-0.005em',
                  color: c.ink,
                  margin: '10px 0 18px',
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
                  fontFamily: FRAUNCES_STACK,
                  fontStyle: 'italic',
                  fontWeight: 400,
                  fontSize: 14,
                  color: c.ink2,
                  margin: '18px 0 0',
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
            borderTop: `1px solid ${RULE_1}`,
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <p
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 15,
              lineHeight: 1.6,
              color: c.ink2,
              textAlign: 'center',
              margin: 0,
              maxWidth: 420,
            }}
          >
            More notes arrive with each Edit. Until then, four short essays
            on how Pellier reads the floor.
          </p>
        </div>
      </div>
    </section>
  )
}
