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
  [
    'utils/agentIdentity.ts',
    'byte-identical twin of solutions/the-ledger/frontend/agentIdentity.ts, which bootstrap ' +
      'copies over it in the builders format (test_solutions_parity.py); nothing in the app ' +
      'imports it. The workshop-contract cut retires the pair rather than restyling both.',
  ],
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

/* Comments may name a color; blanking them keeps line numbers. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/^(\s*)\/\/.*$/gm, '$1')
}

function findings(file: string, source: string): string[] {
  const text = stripComments(source)
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
  ['payment/', 'card and wallet marks keep their brand colors; they sit on --dl-mark-ground'],
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
      const source = stripComments(readFileSync(resolve(SRC, file), 'utf8'))
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
    ]
    for (const line of fine) expect(caught(line), line).toBe(false)
  })
})
