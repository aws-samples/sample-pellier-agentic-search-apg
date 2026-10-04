import tailwindcssAnimate from 'tailwindcss-animate'

/*
 * A colour that resolves to a CSS variable cannot take Tailwind's `/NN`
 * opacity modifier on its own: v3 needs colour channels and a hex variable has
 * none. Handing Tailwind a function keeps every unmodified class a plain
 * `var()` and resolves a modifier with `color-mix()`.
 */
const withAlpha = (variable) => ({ opacityValue }) =>
  opacityValue === undefined || String(opacityValue).startsWith('var(')
    ? `var(${variable})`
    : `color-mix(in srgb, var(${variable}) calc(${opacityValue} * 100%), transparent)`

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Every name resolves to a Daylight token (styles/daylight-tokens.css),
        // which switches with `[data-theme]` on <html>. The names are roles,
        // not values: `page`, `paper` and `ink` mean the same thing in both
        // themes. A hard-coded hex or a fixed Tailwind palette class has no
        // place in src/ (see src/__tests__/token_guard.test.ts).
        'page': withAlpha('--dl-bg'),
        'dock': withAlpha('--dl-dock'),
        'paper': withAlpha('--dl-paper'),
        'recessed': withAlpha('--dl-paper-2'),
        'line': withAlpha('--dl-line'),
        'line-strong': withAlpha('--dl-line-strong'),
        'ink': withAlpha('--dl-ink'),
        'ink-2': withAlpha('--dl-ink-2'),
        'muted': withAlpha('--dl-muted'),
        'faint': withAlpha('--dl-faint'),
        'on-ink': withAlpha('--dl-on-ink'),
        'on-photo': withAlpha('--dl-on-photo'),
        'copper': withAlpha('--dl-accent'),
        'copper-tint': withAlpha('--dl-accent-soft'),
        'ok': withAlpha('--dl-ok'),
        'ok-tint': withAlpha('--dl-ok-soft'),
        'err': withAlpha('--dl-err'),
        'err-tint': withAlpha('--dl-err-soft'),
        'warn': withAlpha('--dl-warn'),
        'scrim': 'var(--dl-scrim)',
      },
      // Tailwind's preflight paints every border in its own gray-200 unless
      // a color utility says otherwise; on black that is a near-white rule.
      // The default border is the hairline token, so a bare `border-b` and
      // the preflight itself follow the theme.
      borderColor: {
        DEFAULT: 'var(--dl-line)',
      },
      boxShadow: {
        // Soft and low; the ask field is the one surface with a resting shadow.
        'ask': 'var(--dl-sh-ask)',
        'paper': 'var(--dl-sh-paper)',
        'lift': 'var(--dl-sh-lift)',
        'deep': 'var(--dl-sh-deep)',
        'frame': 'var(--dl-frame)',
      },
      fontFamily: {
        // Instrument Sans carries every heading and all prose. Fraunces is
        // the wordmark's face only, through `.pellier-brand`.
        sans: [
          '"Instrument Sans"',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          '"Liberation Mono"',
          '"Courier New"',
          'monospace',
        ],
      },
      fontWeight: {
        'light': '300',
        'normal': '400',
        'medium': '500',
      },
      backdropBlur: {
        'xs': '2px',
        'xl': '30px',
      },
      animation: {
        'float': 'float 3s ease-in-out infinite',
        'fadeIn': 'fadeIn 0.6s ease-in-out forwards',
        'slideUp': 'slideUp 0.3s ease-out',
        'pulse-glow': 'pulse 2s infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        fadeIn: {
          'to': { opacity: '1' },
        },
        slideUp: {
          'from': { opacity: '0', transform: 'translateY(10px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
      },

      screens: {
        'wide': '1440px',
        'expansion-stack': '1280px',
      },
      spacing: {
        'container-x': 'clamp(16px, 3.5vw, 44px)',
      },
      transitionDuration: {
        'fade': '180ms',
        'slide': '240ms',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
