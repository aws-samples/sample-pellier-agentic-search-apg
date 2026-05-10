/**
 * FieldNotes — short editorial essays for the Storyboard route.
 *
 * Four notes total: one for each returning persona (Marco, Anna,
 * Theo) and one editorial note written in the boutique voice. Each
 * note is a tight italic Fraunces dek + a prose body in Inter, 15px/
 * 1.7, matching the Atelier AssistantText register so the page reads
 * as "the storefront wrote this, not a marketing page."
 *
 * The footer tagline "Field notes from a slower kind of shopping" is
 * the section's single editorial anchor — carried over from the old
 * footer newsletter column so the phrase earns a home instead of
 * being decoration beneath a dead subscribe form.
 */
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'
const CREAM = '#fbf4e8'
const RULE_1 = 'rgba(45, 24, 16, 0.08)'

const FRAUNCES_STACK = 'Fraunces, Georgia, serif'
const INTER_STACK = 'Inter, system-ui, sans-serif'
const MONO_STACK = 'JetBrains Mono, ui-monospace, monospace'

interface Note {
  kicker: string
  title: string
  body: string[]
  signature: string
}

const NOTES: readonly Note[] = [
  {
    kicker: 'Field note · No. 01',
    title: 'On asking for the piece, not the product.',
    body: [
      'A boutique that really knows its floor should answer "a linen piece that travels well" the same way it answers "medium oatmeal camp shirt, size M." Both are the same question dressed differently. The first is softer; the second assumes too much.',
      'Pellier is built on that smaller, quieter assumption — that you know what you want, not what it\'s called.',
    ],
    signature: '— The editors',
  },
  {
    kicker: 'Field note · No. 02',
    title: 'Marco, on being remembered.',
    body: [
      "Three weeks between visits is long enough to forget someone in most shops. A natural-fiber wardrobe is narrow enough that you shouldn't have to explain it twice.",
      "When Marco signs back in, the storefront leads with the piece he'd reach for next — the Italian Linen Camp Shirt in sage — not because it's trending, but because the thread of his purchases points there.",
    ],
    signature: '— Marco, a regular',
  },
  {
    kicker: 'Field note · No. 03',
    title: 'Anna, on gifting as a practiced art.',
    body: [
      "Gifts are the hardest search queries a storefront will take. They're indirect by design: the shopper isn't the recipient, the recipient isn't in the room, and the moment the piece is chosen for matters more than the piece itself.",
      "Anna walks in with recipients, not products. A milestone gift under two hundred is a meaningful constraint. The storefront should know — and does.",
    ],
    signature: '— Anna, a gift-giver',
  },
  {
    kicker: 'Field note · No. 04',
    title: 'Theo, on pieces that wear in.',
    body: [
      "A ceramic tumbler set kept for six months before the second order is the opposite of a cart abandonment. It's a purchase that earned its keep first.",
      "Slow craft is what happens when a shopper doesn't want to be told what's new. Theo returns for ceramics, linen throws, stoneware — pieces that do more of their work later than sooner.",
    ],
    signature: '— Theo, a slow shopper',
  },
]

export default function FieldNotes() {
  return (
    <section
      data-testid="field-notes"
      aria-labelledby="field-notes-heading"
      style={{
        background: CREAM,
        padding: '72px 24px 96px',
      }}
    >
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        <header style={{ marginBottom: 48 }}>
          <p
            style={{
              fontFamily: MONO_STACK,
              fontSize: 11,
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: ACCENT,
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
                background: ACCENT,
                display: 'inline-block',
              }}
            />
            Field notes
          </p>
          <h2
            id="field-notes-heading"
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 44,
              lineHeight: 1.1,
              letterSpacing: '-0.01em',
              color: INK,
              margin: '16px 0 0',
            }}
          >
            A slower kind of shopping,{' '}
            <span style={{ color: INK_SOFT }}>in four notes.</span>
          </h2>
          <p
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 17,
              lineHeight: 1.6,
              color: INK_SOFT,
              margin: '16px 0 0',
              maxWidth: 560,
            }}
          >
            Short pieces the boutique wrote about how it reads the
            floor, what it remembers, and why it answers the way it
            does.
          </p>
        </header>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 64 }}>
          {NOTES.map((note, i) => (
            <article
              key={note.title}
              data-testid={`field-note-${i}`}
              style={{
                borderTop: `1px solid ${RULE_1}`,
                paddingTop: 32,
              }}
            >
              <p
                style={{
                  fontFamily: MONO_STACK,
                  fontSize: 10,
                  letterSpacing: '0.22em',
                  textTransform: 'uppercase',
                  color: INK_QUIET,
                  fontWeight: 500,
                  margin: 0,
                }}
              >
                {note.kicker}
              </p>
              <h3
                style={{
                  fontFamily: FRAUNCES_STACK,
                  fontStyle: 'italic',
                  fontWeight: 400,
                  fontSize: 28,
                  lineHeight: 1.2,
                  letterSpacing: '-0.005em',
                  color: INK,
                  margin: '10px 0 18px',
                }}
              >
                {note.title}
              </h3>
              {note.body.map((paragraph, j) => (
                <p
                  key={j}
                  style={{
                    fontFamily: INTER_STACK,
                    fontSize: 15,
                    lineHeight: 1.7,
                    letterSpacing: '-0.003em',
                    color: INK,
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
                  color: INK_SOFT,
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
              fontWeight: 600,
              fontSize: 15,
              lineHeight: 1.6,
              color: INK_SOFT,
              textAlign: 'center',
              margin: 0,
              maxWidth: 420,
            }}
          >
            More field notes land with each Edit. For now, this is the
            Storyboard — a slower kind of shopping, in short essays.
          </p>
        </div>
      </div>
    </section>
  )
}
