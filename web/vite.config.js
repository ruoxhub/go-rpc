import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/business': {
        target: 'http://localhost:5612',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:5612',
        changeOrigin: true
      },
      '/sekiro-api': {
        target: 'http://localhost:5612',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sekiro-api/, '/api')
      }
    }
  }
})
