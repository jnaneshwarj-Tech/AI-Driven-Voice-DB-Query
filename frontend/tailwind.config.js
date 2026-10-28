/** @type {import('tailwindcss').Config} */
// Every colour below resolves to a design token in src/index.css. Nothing here
// is a literal value — that is what keeps light/dark consistent across 22 files.
const ch = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',   // enable class-based dark mode
  theme: {
    extend: {
      colors: {
        // 60% — surfaces
        canvas: ch('--canvas-rgb'),
        surface: ch('--surface-rgb'),
        'surface-elev': ch('--surface-elev-rgb'),
        sunken: ch('--sunken-rgb'),
        cream: ch('--cream-rgb'),
        beige: ch('--beige-rgb'),

        // 30% — chrome (deep navy structure in light and dark)
        nav: ch('--nav-rgb'),
        'nav-fg': ch('--nav-fg-rgb'),
        'nav-fg-mute': ch('--nav-fg-mute-rgb'),
        'nav-line': ch('--nav-line-rgb'),
        brand: {
          DEFAULT: ch('--brand-rgb'),
          deep: ch('--brand-deep-rgb'),
          mid: ch('--brand-mid-rgb'),
          soft: ch('--brand-soft-rgb'),
          // Brand as text/icon: stays AA when the surface flips theme, which
          // the fill colour above cannot do in both directions at once.
          fg: ch('--brand-fg-rgb'),
        },

        // Text
        ink: {
          DEFAULT: ch('--ink-rgb'),
          soft: ch('--ink-soft-rgb'),
          mute: ch('--ink-mute-rgb'),
          faint: ch('--ink-faint-rgb'),
        },

        // Lines
        line: {
          DEFAULT: ch('--line-rgb'),
          strong: ch('--line-strong-rgb'),
        },

        // 10% — accent champagne & terracotta
        accent: {
          DEFAULT: ch('--accent-rgb'),
          strong: ch('--accent-strong-rgb'),
          soft: ch('--accent-soft-rgb'),
          ink: ch('--accent-ink-rgb'),
          fg: ch('--accent-fg-rgb'),
        },
        terracotta: {
          DEFAULT: ch('--terracotta-rgb'),
          soft: ch('--terracotta-soft-rgb'),
          fg: ch('--terracotta-fg-rgb'),
        },

        // Semantic
        ok: { DEFAULT: ch('--ok-rgb'), soft: ch('--ok-soft-rgb') },
        warn: { DEFAULT: ch('--warn-rgb'), soft: ch('--warn-soft-rgb') },
        err: { DEFAULT: ch('--err-rgb'), soft: ch('--err-soft-rgb') },
        info: { DEFAULT: ch('--info-rgb'), soft: ch('--info-soft-rgb') },
        ring: ch('--ring-rgb'),

        // Charts
        chart: {
          1: ch('--chart-1-rgb'), 2: ch('--chart-2-rgb'), 3: ch('--chart-3-rgb'),
          4: ch('--chart-4-rgb'), 5: ch('--chart-5-rgb'), 6: ch('--chart-6-rgb'),
        },
      },

      fontFamily: {
        ui: ['var(--font-ui)'],
        kannada: ['var(--font-kannada)'],
      },

      // §2: one corner-radius system, applied everywhere.
      borderRadius: {
        sm: 'var(--r-sm)',
        DEFAULT: 'var(--r-sm)',
        md: 'var(--r-md)',
        lg: 'var(--r-lg)',
        xl: 'var(--r-xl)',
        '2xl': 'var(--r-xl)',
        '3xl': 'var(--r-xl)',
      },

      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-lg)',
      },

      transitionProperty: {
        'colors': 'color, background-color, border-color, fill, stroke',
      },
    },
  },
  plugins: [],
}
