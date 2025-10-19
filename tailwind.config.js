/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./*.html",
    "./src/**/*.{html,js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        prologisCyan: '#00FFFF',
        darkBg: '#0D1117',
        darkCard: '#161B22',
      },
    },
  },
  plugins: [],
}
