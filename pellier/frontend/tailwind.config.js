import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Storefront palette — every name here resolves to a Daylight
        // token via styles/daylight-bridge.css. The bridge maps
        // --cream → --dl-bg, --ink → --dl-ink, --accent → --dl-accent,
        // etc. Override at scope to re-skin a section without
        // touching this file. See DAYLIGHT_INTEGRATION.md.
        'cream': 'var(--cream)',
        'cream-warm': 'var(--cream-warm)',
        'ink': 'var(--ink)',
        'ink-soft': 'var(--ink-soft)',
        'ink-quiet': 'var(--ink-quiet)',
        'accent': 'var(--accent)',
        'accent-ink': 'var(--accent-ink)',
        'dusk': 'var(--dusk)',

        // Theme-aware via CSS variables
        'bg-primary': 'var(--bg-primary)',
        'bg-secondary': 'var(--bg-secondary)',
        'text-primary': 'var(--text-primary, #f5f5f7)',
        'text-secondary': 'var(--text-secondary, #a1a1a6)',
        'text-tertiary': 'var(--text-tertiary, #636366)',
        'border-subtle': 'var(--border-color, rgba(255, 255, 255, 0.08))',

        // Apple blue links
        'apple-blue': 'var(--link-color, #0071e3)',

        // Utility
        'success': '#4ade80',
        'warning': '#fbbf24',

        // Warm-tinted hairline (ink-soft at 8% alpha). Kept as a
        // hardcoded rgba — Daylight has no equivalent token for the
        // 8%-alpha hairline use case.
        'warm': 'rgba(107, 74, 53, 0.08)',

        // Redesign tokens — also flow through the Daylight bridge.
        // 'sand' has no direct Daylight counterpart; we map it onto
        // --dl-paper-2 (recessed surface) which is visually the same
        // recessed-cream role.
        'cream-50': 'var(--cream)',
        'sand': 'var(--cream-2)',
        'espresso': 'var(--ink)',
        'olive': '#6B705C',
        'espresso-dark': 'var(--ink-1)',
        'espresso-mid': '#2A1E18',
      },
      borderColor: {
        'cream': 'var(--cream)',
        'cream-warm': 'var(--cream-warm)',
        'ink': 'var(--ink)',
        'ink-soft': 'var(--ink-soft)',
        'ink-quiet': 'var(--ink-quiet)',
        'accent': 'var(--accent)',
        'accent-ink': 'var(--accent-ink)',
        'dusk': 'var(--dusk)',
        'warm': 'rgba(107, 74, 53, 0.08)',
      },
      boxShadow: {
        // Warm-tinted shadows (ink-soft at low alpha) — the single biggest
        // contributor to the storefront "premium feel" vs cold grey drops.
        'warm':
          '0 2px 8px rgba(107, 74, 53, 0.06), 0 1px 3px rgba(107, 74, 53, 0.04)',
        'warm-lg':
          '0 8px 24px rgba(107, 74, 53, 0.10), 0 4px 8px rgba(107, 74, 53, 0.06)',

        // Redesign tokens (Phase 1) — coexist with existing tokens until Phase 5 retires them
        'warm-sm':
          '0 2px 8px rgba(107, 74, 53, 0.06), 0 1px 3px rgba(107, 74, 53, 0.04)',
        'warm-md':
          '0 4px 16px rgba(107, 74, 53, 0.08), 0 2px 6px rgba(107, 74, 53, 0.05)',
        'warm-xl':
          '0 24px 48px rgba(107, 74, 53, 0.14), 0 8px 16px rgba(107, 74, 53, 0.08)',
      },
      fontFamily: {
        // Mirror Daylight / bridge stacks (self-hosted in main.tsx).
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
        serif: [
          '"Instrument Serif"',
          '"Fraunces Variable"',
          'Fraunces',
          'Georgia',
          'serif',
        ],
        // Telemetry SQL + table monospace — ligature-friendly.
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
        // Storefront display italic — editorial product / hero titles.
        display: ['Fraunces Variable', 'Fraunces', 'Georgia', 'serif'],
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
      backgroundImage: {
        'gradient-radial': 'radial-gradient(ellipse at center, var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
      },

      // Redesign tokens (Phase 1) — coexist with existing tokens until Phase 5 retires them
      screens: {
        'wide': '1440px',
        'expansion-stack': '1280px',
      },
      spacing: {
        'container-x': 'clamp(16px, 4vw, 48px)',
      },
      transitionDuration: {
        'fade': '180ms',
        'slide': '240ms',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
