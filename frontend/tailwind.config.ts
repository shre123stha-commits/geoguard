import type { Config } from 'tailwindcss';

// Tokens from docs/04-design.md §3.4. Values live in src/styles/tokens.css.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: 'var(--base)',
        cream: 'var(--text)',
        soft: 'var(--text-soft)',
        dim: 'var(--text-dim)',
        hair: 'var(--hairline)',
        'hair-strong': 'var(--hairline-strong)',
        s1: 'var(--surface-1)',
        s2: 'var(--surface-2)',
        s3: 'var(--surface-3)',
        panel: 'var(--panel)',
        glass: 'var(--glass)',
        high: 'var(--sem-high)',
        medium: 'var(--sem-medium)',
        low: 'var(--sem-low)',
        ok: 'var(--sem-ok)',
        danger: 'var(--sem-danger)',
      },
      fontFamily: {
        display: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: { card: '20px', ctl: '12px' },
      screens: { sm: '640px', md: '900px', lg: '1280px', xl: '1536px' },
      transitionTimingFunction: { out: 'var(--ease-out)' },
    },
  },
  plugins: [],
} satisfies Config;
