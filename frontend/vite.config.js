import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Set VITE_BASE=/SanD-Hacks/ in the GitHub Pages workflow.
// Leave default '/' for hosting through Vultr/Nginx.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || '/',
  server: {port: 5173, proxy: {'/api': {target: 'http://localhost:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '')}}},
})
