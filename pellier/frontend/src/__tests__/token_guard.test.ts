/**
 * Every color on the direction A surfaces comes from a token.
 *
 * Scans the files cut 5a restyled (the Storefront and Ask Pellier) for a
 * hard-coded hex color, a literal rgb()/rgba(), or a fixed Tailwind palette
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
  'components/PersonaConcierge.tsx',
  'components/ProductCard.tsx',
  'components/ProductGrid.tsx',
  'components/ProductAvailabilityPanel.tsx',
  'components/ChatDrawer.tsx',
  'components/PellierChatBody.tsx',
  'components/PellierWelcome.tsx',
  'components/ProductArtifactCard.tsx',
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
]

/* A hex color, but not an HTML entity such as `&#9733;`. */
const HEX = /(?<!&)#[0-9a-fA-F]{3,8}\b/g
const RGB_LITERAL = /\brgba?\(\s*\d/g
/* Fixed Tailwind palette classes and arbitrary color values. The palette
   names in tailwind.config.js (page, paper, ink, copper, ...) resolve to
   tokens and are allowed. */
const FIXED_TAILWIND =
  /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text|border|ring|fill|stroke|from|to|via|outline|divide|shadow|placeholder)-(?:white|black|gray|neutral|stone|zinc|slate|red|green|amber|yellow|blue|emerald|rose|orange|indigo|purple|pink|sky|teal|cyan|lime)(?:-\d{2,3})?(?:\/\d+)?(?=[\s"'`])/g
const ARBITRARY_COLOR = /\[(?:#[0-9a-fA-F]{3,8}|rgba?\([^\]]*\))\]/g

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

function violations(file: string): string[] {
  const source = stripComments(readFileSync(resolve(SRC, file), 'utf8'))
  const found: string[] = []
  for (const pattern of [HEX, RGB_LITERAL, FIXED_TAILWIND, ARBITRARY_COLOR]) {
    pattern.lastIndex = 0
    for (const match of source.matchAll(pattern)) found.push(`${file}: ${match[0].trim()}`)
  }
  return found
}

describe('token guard (cut 5a surfaces)', () => {
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
})
