import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/business': {
        target: 'http://localhost:5613',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:5613',
        changeOrigin: true
      },
      '/rpc-api': {
        target: 'http://localhost:5613',
        changeOrigin: true
      }
    }
  }
})
