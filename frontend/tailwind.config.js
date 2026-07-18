/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#E3E2DE',
        surface: '#EDECEA',
        ink: '#141414',
        'ink-2': '#444343',
        muted: '#7A7A7A',
        line: '#C7C7C7',
        accent: '#1351AA',
        'accent-ink': '#E3E2DE',
        'status-pending': '#7A7A7A',
        'status-running': '#1351AA',
        'status-done': '#1E7A46',
        'status-failed': '#B4231F',
        'status-skipped': '#9A9A9A',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        none: '0px',
        DEFAULT: '0px',
        sm: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        '3xl': '0px',
        full: '9999px',
      },
    },
  },
  plugins: [],
};
