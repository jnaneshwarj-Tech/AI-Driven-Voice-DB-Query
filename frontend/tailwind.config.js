/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',   // enable class-based dark mode
  theme: {
    extend: {
      transitionProperty: {
        'colors': 'color, background-color, border-color, fill, stroke',
      },
    },
  },
  plugins: [],
}
