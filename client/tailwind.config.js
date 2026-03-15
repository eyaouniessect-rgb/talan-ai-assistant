export default {
  content: ["./index.html","./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT:'#1B2B5E', light:'#243770', dark:'#121e42' },
        cyan: { DEFAULT:'#00B4D8', light:'#22c9eb', dark:'#0090ac' },
      },
      fontFamily: {
        sans: ['DM Sans','sans-serif'],
        display: ['Syne','sans-serif'],
      }
    }
  },
  plugins: []
}
