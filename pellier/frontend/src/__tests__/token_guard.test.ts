/**
 * Every color in src/ comes from a token.
 *
 * Scans every `.ts`, `.tsx` and `.css` file under src/ for a hard-coded hex
 * color, a literal rgb()/hsl()/hwb()/lab()/lch()/oklab()/oklch(), a CSS
 * named color in a color-bearing declaration, an SVG paint attribute or a
 * ternary branch, or a fixed Tailwind palette class or arbitrary color, and
 * fails on every one it finds. Values live in the token file only; the
 * bridge files (`daylight-bridge.css`, `governed-tokens.css`) are scanned too,
 * because they only rename tokens and must never fork a value. Tests are not
 * scanned: they hold literals on purpose, to prove what the guard catches.
 *
 * A file that genuinely needs a literal goes in EXEMPT with its reason.
 *
 * The second guard below keeps type to the owner's rule: Fraunces sets the
 * wordmark and nothing else, and every heading and title is Instrument Sans.
 *
 * Known limits of a regex guard, accepted: a named color held in a constant
 * (`const ACCENT = 'white'`), a capitalized named color (`'White'`, which is
 * how product data writes a colorway), `WebkitTextFillColor`, Tailwind variant
 * prefixes such as `[&>svg]:text-white`, and a `}` inside a template value all
 * pass; an order number such as `'Order #301'` reads as a hex color.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(here, '..')

/** Values live here and nowhere else. */
const TOKEN_FILES = ['styles/daylight-tokens.css']

/** Files the scan skips, each with the reason it may hold a literal. */
const EXEMPT = new Map<string, string>([
  ['styles/daylight-tokens.css', 'the token file: every value is written here, in both themes'],
])

const SCANNED_EXTENSIONS = new Set(['.ts', '.tsx', '.css'])

function isTest(file: string): boolean {
  return (
    file.split('/').includes('__tests__') ||
    /\.test\.(ts|tsx)$/.test(file) ||
    file === 'test-setup.ts'
  )
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return SCANNED_EXTENSIONS.has(extname(name)) ? [relative(SRC, path).split('\\').join('/')] : []
  })
}

const SCANNED = walk(SRC).filter((file) => !isTest(file) && !EXEMPT.has(file))

/* The CSS named colors (CSS Color Level 4), matched in lowercase only: a
   stylesheet writes `white`, while product data writes a colorway such as
   'White' or 'Ivory'. `transparent` and `currentColor` are keywords, not
   values, and stay allowed. */
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
const NAMED = `(?<![\\w-])(?:${NAMED_COLORS})(?![\\w-])`
const QUOTE = `['"\`]`

/* A hex color, but not an HTML entity such as `&#9733;`. */
const HEX = /(?<!&)#[0-9a-fA-F]{3,8}\b/g
const RGB_LITERAL = /\brgba?\(\s*\d/g
const COLOR_FUNCTION = /\b(?:hsla?|hwb|lab|lch|oklab|oklch)\(/g
/* A color-bearing property in a stylesheet (`border-bottom-color`), an inline
   style object (`borderBottomColor`), a canvas (`fillStyle`), or a custom
   property (`--rule: ...`, `'--rule': ...`). The property list keeps prose and
   data out of it: a product in "White" is not a color declaration. */
const COLOR_PROPERTY =
  '(?:\\b(?:color|background(?:-?[cC]olor|-?[iI]mage)?' +
  '|border(?:-?(?:[tT]op|[rR]ight|[bB]ottom|[lL]eft|[iI]nline|[bB]lock)(?:-?(?:[sS]tart|[eE]nd))?)?(?:-?[cC]olor)?' +
  '|outline(?:-?[cC]olor)?|box-?[sS]hadow|text-?[sS]hadow|caret-?[cC]olor|accent-?[cC]olor' +
  '|text-?[dD]ecoration(?:-?[cC]olor)?|scrollbar-?[cC]olor|column-?[rR]ule(?:-?[cC]olor)?' +
  '|fill|stroke|stop-?[cC]olor|flood-?[cC]olor|lighting-?[cC]olor|fillStyle|strokeStyle|shadowColor)' +
  '|--[a-zA-Z][\\w-]*)'
/* The value may wrap onto the next line; it ends at `;`, `}` or a quote. */
const NAMED_COLOR = new RegExp(
  `${COLOR_PROPERTY}${QUOTE}?\\s*:\\s*${QUOTE}?[^;'"\`}]*?${NAMED}`,
  'g',
)
/* SVG and icon paint attributes: `fill="white"`, `stroke={'black'}`. */
const PAINT_ATTRIBUTE = new RegExp(
  `\\b(?:fill|stroke|stop-?[cC]olor|flood-?[cC]olor|color)\\s*=\\s*\\{?\\s*${QUOTE}\\s*${NAMED}`,
  'g',
)
/* A named color as a ternary branch: `on ? 'white' : x`, `on ? x : 'black'`. */
const TERNARY_COLOR = new RegExp(
  `\\?\\s*(?:${QUOTE}${NAMED}${QUOTE}\\s*:` +
  `|(?:${QUOTE}[^'"\`\\n]*${QUOTE}|[\\w.$]+)\\s*:\\s*${QUOTE}${NAMED}${QUOTE})`,
  'g',
)
/* Fixed Tailwind palette classes. The palette names in tailwind.config.js
   (page, paper, ink, copper, ...) resolve to tokens and are allowed. */
const FIXED_TAILWIND =
  /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text|border|ring|ring-offset|fill|stroke|from|to|via|outline|divide|shadow|placeholder|accent|caret|decoration)-(?:white|black|gray|neutral|stone|zinc|slate|red|green|amber|yellow|blue|emerald|rose|orange|indigo|purple|pink|sky|teal|cyan|lime|violet|fuchsia)(?:-\d{2,3})?(?:\/\d+)?(?=[\s"'`])/g
/* Tailwind arbitrary color values: `bg-[rgba(...)]`, `accent-[#1f1410]`. */
const ARBITRARY_COLOR = new RegExp(
  `\\[(?:#[0-9a-fA-F]{3,8}|(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\\([^\\]]*\\)|(?:${NAMED_COLORS}))\\]`,
  'g',
)

const PATTERNS = [
  HEX, RGB_LITERAL, COLOR_FUNCTION, NAMED_COLOR, PAINT_ATTRIBUTE, TERNARY_COLOR,
  FIXED_TAILWIND, ARBITRARY_COLOR,
]

// Comments may name a color or a typeface; blanking them keeps line numbers.
// The walk is string-aware, so a glob string or `accept="image/*"` does not
// open a comment that swallows the code after it. A `//` starts a comment
// only in TypeScript and only after whitespace or punctuation, so a URL in
// JSX text or a regex ending in an escaped slash is left alone. Strings end
// at a newline, so a stray apostrophe in JSX text costs one line at most.
function stripComments(source: string, css = false): string {
  const out = source.split('')
  const blank = (from: number, to: number) => {
    for (let k = from; k < to; k += 1) if (out[k] !== '\n') out[k] = ' '
  }
  const LINE_COMMENT_AFTER = /[\s;,{}()[\]]/
  const templates: number[] = []
  let quote: string | null = null
  let i = 0
  while (i < source.length) {
    const ch = source[i]
    const next = source[i + 1]
    if (quote) {
      if (ch === '\\') i += 2
      else if (quote === '`' && ch === '$' && next === '{') { templates.push(0); quote = null; i += 2 }
      else { if (ch === quote || (ch === '\n' && quote !== '`')) quote = null; i += 1 }
    } else if (ch === '/' && next === '*') {
      const end = source.indexOf('*/', i + 2)
      const stop = end < 0 ? source.length : end + 2
      blank(i, stop)
      i = stop
    } else if (!css && ch === '/' && next === '/' && (i === 0 || LINE_COMMENT_AFTER.test(source[i - 1]))) {
      const end = source.indexOf('\n', i)
      const stop = end < 0 ? source.length : end
      blank(i, stop)
      i = stop
    } else if (ch === '"' || ch === "'" || (!css && ch === '`')) {
      quote = ch
      i += 1
    } else {
      if (templates.length && ch === '{') templates[templates.length - 1] += 1
      else if (templates.length && ch === '}') {
        if (templates[templates.length - 1] === 0) { templates.pop(); quote = '`' }
        else templates[templates.length - 1] -= 1
      }
      i += 1
    }
  }
  return out.join('')
}

function findings(file: string, source: string): string[] {
  const text = stripComments(source, file.endsWith('.css'))
  const found: string[] = []
  for (const pattern of PATTERNS) {
    pattern.lastIndex = 0
    for (const match of text.matchAll(pattern)) {
      const line = text.slice(0, match.index).split('\n').length
      found.push(`${file}:${line}: ${match[0].trim().replace(/\s+/g, ' ')}`)
    }
  }
  return found
}

function caught(line: string): boolean {
  return findings('sample', line).length > 0
}

/* Monochrome icon files served through <img> keep their own fill and cannot
   follow the theme. Draw them inline with `fill="currentColor"` instead. Only
   brand artwork, which must keep its own colors, may be an <img>. */
const BRAND_ICON_SETS = new Map<string, string>([
  ['aws/', 'AWS architecture icons carry their own colored tile'],
])
const ICON_FILE = /\/assets\/icons\/([\w./-]+)/g

describe('token guard (every file under src/)', () => {
  it('scans the files it claims to scan', () => {
    // A guard whose walk silently stops matching passes forever.
    expect(SCANNED.length).toBeGreaterThan(100)
    for (const file of ['App.tsx', 'components/CartPanel.tsx', 'operator/styles/operator.css', 'styles/governed-tokens.css']) {
      expect(SCANNED, file).toContain(file)
    }
    for (const file of EXEMPT.keys()) expect(walk(SRC), file).toContain(file)
  })

  it('writes color values only in the token file', () => {
    const all = SCANNED.flatMap((file) => findings(file, readFileSync(resolve(SRC, file), 'utf8')))
    expect(all).toEqual([])
  })

  it('draws monochrome icons inline so they follow the theme', () => {
    const imgIcons = SCANNED.flatMap((file) => {
      const source = stripComments(readFileSync(resolve(SRC, file), 'utf8'), file.endsWith('.css'))
      return Array.from(source.matchAll(ICON_FILE), (match) => match[1])
        .filter((icon) => ![...BRAND_ICON_SETS.keys()].some((set) => icon.startsWith(set)))
        .map((icon) => `${file}: /assets/icons/${icon}`)
    })
    expect(imgIcons).toEqual([])
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
      'color: oklch(70% 0.1 50);',
      'border-bottom: 1px solid white;',
      'border-bottom:\n    1px solid\n    white;',
      '--rule: color-mix(in srgb, black 8%, transparent);',
      "style={{ '--rule': 'black' }}",
      "style={{ backgroundColor: 'black' }}",
      "style={{ borderTopColor:\n  'white' }}",
      '<path fill="white" d="M0 0" />',
      "<circle stroke={'black'} />",
      '<Check color="white" />',
      "color: active ? 'white' : 'var(--dl-ink)'",
      "color: active ? 'var(--dl-ink)' : 'black'",
      "color: active\n  ? GREEN\n  : 'red'",
      'className="bg-white text-neutral-900"',
      'className="accent-blue-500 caret-black"',
      'className="text-[white] bg-[hsl(0,0%,0%)]"',
      'className="hover:bg-[rgba(168,66,58,0.08)] accent-[#1f1410]"',
      "const glob = '**/*.tsx'; const c = '#abc'; /* end */",
      'accept="image/*" style={{ color: \'#abc\' }} /* end */',
      "const t = `/* ${'#abc'} */`",
    ]
    for (const line of bad) expect(caught(line), line).toBe(true)
    const fine = [
      'color: var(--dl-ink);',
      'white-space: nowrap;',
      'alt="Linen napkins in white"',
      '<span>White</span>',
      "{ name: 'Hadley Linen Shirt', color: 'Ivory', tags: ['linen', 'travel'] }",
      "const CATEGORY = { Linen: 'linen', Shoes: 'footwear' }",
      'className="bg-page border-line text-on-photo/70 accent-ink"',
      'background: transparent; color: currentColor;',
      '<path fill="currentColor" stroke="none" />',
      '--link-color: var(--dl-accent);',
      'interface Props { tone?: string; label: string }',
      "const step = done ? 'Delivered' : 'In transit'",
      'color: var(--dl-ink); // was white',
      '/* border: 1px solid white; */ color: var(--dl-ink);',
      "const url = 'https://example.com' // fill: white",
    ]
    for (const line of fine) expect(caught(line), line).toBe(false)
  })
})

/* Fraunces is the wordmark's face and nothing else's (owner, 2026-10-04:
   "just the logo though"). Every heading and title is Instrument Sans, so no
   other file names Fraunces, the display token or its alias, or a serif
   family. Comments are blanked first, so a file may still explain the rule. */
const TYPE_ALLOWED = new Map<string, string>([
  ['components/Wordmark.tsx', 'the wordmark and its square p. mark, the one place Fraunces is set'],
  ['styles/daylight-tokens.css', 'the token file: --dl-font-display is defined here'],
])
const SERIF_PATTERNS = [
  /fraunces/gi,
  /--(?:dl-font-|obs-)?display\b/g,
  /--(?:dl-font-|obs-)?serif\b/g,
  /(?<![\w-])serif\b/gi,
  /\bfont-serif\b/g,
  /\bgeorgia\b/gi,
  /times new roman/gi,
]

function serifFindings(file: string, source: string): string[] {
  const text = stripComments(source, file.endsWith('.css'))
  return SERIF_PATTERNS.flatMap((pattern) =>
    Array.from(text.matchAll(pattern), (match) => {
      const line = text.slice(0, match.index).split('\n').length
      return `${file}:${line}: ${match[0]}`
    }),
  )
}

const TYPE_SCANNED = walk(SRC).filter((file) => !isTest(file) && !TYPE_ALLOWED.has(file))

describe('type guard (Fraunces only in the wordmark)', () => {
  it('scans the files it claims to scan', () => {
    expect(TYPE_SCANNED.length).toBeGreaterThan(100)
    for (const file of ['main.tsx', 'components/FieldNotes.tsx', 'styles/surface-navigation.css']) {
      expect(TYPE_SCANNED, file).toContain(file)
    }
    for (const file of TYPE_ALLOWED.keys()) expect(walk(SRC), file).toContain(file)
  })

  it('sets no heading, title or prose in Fraunces or a serif', () => {
    const all = TYPE_SCANNED.flatMap((file) => serifFindings(file, readFileSync(resolve(SRC, file), 'utf8')))
    expect(all).toEqual([])
  })

  it('catches the forms the guard is for', () => {
    const bad = [
      "fontFamily: 'Fraunces, Georgia, serif'",
      "import '@fontsource-variable/fraunces'",
      'font: 400 31px/1.2 var(--dl-font-display);',
      "fontFamily: 'var(--display, serif)'",
      'font-family: var(--serif);',
      '--obs-serif: var(--x);',
      'className="font-serif italic"',
      "fontFamily: '\"Instrument Serif\", Times New Roman'",
    ]
    for (const line of bad) expect(serifFindings('sample.tsx', line), line).not.toEqual([])
    const fine = [
      'font-family: var(--dl-font-heading);',
      "fontFamily: 'Instrument Sans, system-ui, sans-serif'",
      'font-size: var(--dl-fs-display); letter-spacing: var(--dl-track-display);',
      'font-size: min(var(--text-display), 7.4vh);',
      '/* Fraunces belongs to the wordmark. */ color: var(--dl-ink);',
    ]
    for (const line of fine) expect(serifFindings('sample.css', line), line).toEqual([])
  })
})
