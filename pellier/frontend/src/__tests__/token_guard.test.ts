/**
 * Every color on the direction A surfaces comes from a token.
 *
 * Scans the files cut 5a restyled (the Storefront and Ask Pellier) for a
 * hard-coded hex color, a literal rgb()/rgba()/hsl()/hsla()/hwb(), a CSS
 * named color in a color-bearing declaration, or a fixed Tailwind palette
 * class, and fails on the first one. The token files are the one place a
 * value may be written. The repository-wide guard is cut 5b; the sweep-only
 * files it still owns (CartPanel, the editorial pages, the ui primitives)
 * join this list when they are themed.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(here, '..')

/** Values live here and nowhere else. */
const TOKEN_FILES = ['styles/daylight-tokens.css']

const GUARDED_FILES = [
  'index.css',
  'App.tsx',
  'styles/daylight-bridge.css',
  'styles/pellier-landing.css',
  'styles/surface-navigation.css',
  'styles/chat-drawer.css',
  'styles/pellier-chat.css',
  'styles/pellier-welcome.css',
  'styles/product-artifact.css',
  'styles/chat-outcomes.css',
  'styles/persona-modal.css',
  'styles/navigation-polish.css',
  'styles/pellier-signin.css',
  'styles/turn.css',
  'theme/theme.css',
  'theme/ThemeControl.tsx',
  'theme/theme.ts',
  'components/SurfaceNavigation.tsx',
  'components/Wordmark.tsx',
  'components/PellierMark.tsx',
  'components/Header.tsx',
  'components/Footer.tsx',
  'components/SignInPage.tsx',
  'components/PellierHero.tsx',
  'components/PellierSpotlight.tsx',
  'components/PersonaConcierge.tsx',
  'components/ProductCard.tsx',
  'components/ProductGrid.tsx',
  'components/ProductAvailabilityPanel.tsx',
  'components/ChatDrawer.tsx',
  'components/PellierChatBody.tsx',
  'components/PellierWelcome.tsx',
  'components/ProductArtifactCard.tsx',
  'components/AuthModal.tsx',
  'components/PreferencesModal.tsx',
  'components/turn/StatusLine.tsx',
  'components/turn/StatusTag.tsx',
  'components/turn/StepList.tsx',
  'components/turn/RevealedProse.tsx',
  'components/turn/RankingPanel.tsx',
  'components/turn/BuilderViewSwitch.tsx',
  'components/turn/LayerTag.tsx',
  'design/primitives/Avatar.tsx',
  'design/primitives/IconButton.tsx',
  'pages/PellierPage.tsx',
  'pages/ProductDetailPage.tsx',
  'components/WorkshopSignIn.tsx',
  'components/StatusLines.tsx',
  'operator/styles/operator.css',
  'operator/shell/OperatorFrame.tsx',
  'operator/surfaces/ClientBook.tsx',
  'operator/surfaces/ClientRecord.tsx',
  'operator/surfaces/ReviewQueue.tsx',
  'operator/surfaces/ReviewRecord.tsx',
  'operator/investigation/InvestigationSteps.tsx',
  'operator/components/ProposedCreditCard.tsx',
  'operator/components/ClientAvatar.tsx',
  'operator/components/OperatorState.tsx',
  'operator/components/OperatorSignInAction.tsx',
  'operator/hooks/useInvestigation.ts',
  'operator/hooks/useReview.ts',
]

/* The CSS named colors (CSS Color Level 4). `transparent` and
   `currentColor` are keywords, not values, and stay allowed. */
const NAMED_COLORS = `
  aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond
  blue blueviolet brown burlywood cadetblue chartreuse chocolate coral
  cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
  darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
  darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey
  darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue
  firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod
  gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
  lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
  lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon
  lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue
  lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
  mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
  mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
  navajowhite navy oldlace olive olivedrab orange orangered orchid
  palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
  pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown
  salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray
  slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet
  wheat white whitesmoke yellow yellowgreen
`
  .trim()
  .split(/\s+/)
  .join('|')

/* A hex color, but not an HTML entity such as `&#9733;`. */
const HEX = /(?<!&)#[0-9a-fA-F]{3,8}\b/g
const RGB_LITERAL = /\brgba?\(\s*\d/g
const HSL_LITERAL = /\b(?:hsla?|hwb)\(/g
/* A named color as the value of a color-bearing property, in a stylesheet
   (`border-bottom: 1px solid white`) or an inline style object
   (`backgroundColor: 'white'`). The property list keeps prose and copy out
   of it: a product in "White" is not a color declaration. */
const COLOR_PROPERTY =
  '(?:color|background(?:-?color|-?image)?|border(?:-?(?:top|right|bottom|left|inline|block))?(?:-?color)?|outline(?:-?color)?|box-?shadow|text-?shadow|caret-?color|accent-?color|text-?decoration-?color|scrollbar-?color|fill|stroke)'
const NAMED_COLOR = new RegExp(
  `\\b${COLOR_PROPERTY}\\s*:\\s*['"\`]?[^;'"\`}\\n]*?(?<![\\w-])(?:${NAMED_COLORS})(?![\\w-])`,
  'gi',
)
/* Fixed Tailwind palette classes and arbitrary color values. The palette
   names in tailwind.config.js (page, paper, ink, copper, ...) resolve to
   tokens and are allowed. */
const FIXED_TAILWIND =
  /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text|border|ring|fill|stroke|from|to|via|outline|divide|shadow|placeholder)-(?:white|black|gray|neutral|stone|zinc|slate|red|green|amber|yellow|blue|emerald|rose|orange|indigo|purple|pink|sky|teal|cyan|lime)(?:-\d{2,3})?(?:\/\d+)?(?=[\s"'`])/g
const ARBITRARY_COLOR = new RegExp(
  `\\[(?:#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?|hwb)\\([^\\]]*\\)|(?:${NAMED_COLORS}))\\]`,
  'gi',
)

const PATTERNS = [HEX, RGB_LITERAL, HSL_LITERAL, NAMED_COLOR, FIXED_TAILWIND, ARBITRARY_COLOR]

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

function violations(file: string): string[] {
  const source = stripComments(readFileSync(resolve(SRC, file), 'utf8'))
  const found: string[] = []
  for (const pattern of PATTERNS) {
    pattern.lastIndex = 0
    for (const match of source.matchAll(pattern)) found.push(`${file}: ${match[0].trim()}`)
  }
  return found
}

describe('token guard (direction A surfaces)', () => {
  it('writes color values only in the token files', () => {
    const all = GUARDED_FILES.flatMap(violations)
    expect(all).toEqual([])
  })

  it('defines both themes in the token file', () => {
    for (const file of TOKEN_FILES) {
      const css = readFileSync(resolve(SRC, file), 'utf8')
      expect(css).toMatch(/:root\s*\{[\s\S]*color-scheme:\s*light/)
      expect(css).toMatch(/:root\[data-theme="dark"\]\s*\{[\s\S]*color-scheme:\s*dark/)
    }
  })

  it('no longer pins color-scheme to light on the storefront surfaces', () => {
    const css = readFileSync(resolve(SRC, 'index.css'), 'utf8')
    expect(css).not.toMatch(/color-scheme:\s*light/)
  })

  it('catches the literal forms the guard is for', () => {
    const bad = [
      'color: #abc;',
      'background: rgba(0, 0, 0, 0.5);',
      'border-color: hsl(20 50% 50%);',
      'outline: 2px solid hwb(20 10% 10%);',
      'border-bottom: 1px solid white;',
      "style={{ backgroundColor: 'black' }}",
      'className="bg-white text-neutral-900"',
      'className="text-[white] bg-[hsl(0,0%,0%)]"',
    ]
    for (const line of bad) {
      expect(PATTERNS.some((p) => { p.lastIndex = 0; return p.test(line) }), line).toBe(true)
    }
    const fine = [
      'color: var(--dl-ink);',
      'white-space: nowrap;',
      'alt="Linen napkins in white"',
      '<span>White</span>',
      'className="bg-page border-line text-on-photo/70"',
      'background: transparent; color: currentColor;',
      '--link-color: var(--dl-accent);',
    ]
    for (const line of fine) {
      expect(PATTERNS.some((p) => { p.lastIndex = 0; return p.test(line) }), line).toBe(false)
    }
  })
})
