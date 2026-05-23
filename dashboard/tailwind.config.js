/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './App.tsx',
    './index.tsx',
    './components/**/*.{ts,tsx}',
    './contexts/**/*.{ts,tsx}',
    './utils/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        vs: {
          orange: '#FF6A00',
          lightOrange: '#FF8A3A',
          darkBg: '#0A0A0A',
          darkCard: '#141414',
          darkBorder: '#262626',
          darkInput: '#1F1F1F',
          text: '#E5E5E5',
          muted: '#9CA3AF',
        },
      },
      boxShadow: {
        glow: '0 0 15px rgba(255, 106, 0, 0.3)',
        'orange-sm': '0 2px 8px rgba(255, 106, 0, 0.2)',
      },
      fontFamily: {
        sans: ['Inter', 'Vazirmatn', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
