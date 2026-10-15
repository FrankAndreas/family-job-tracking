import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, forward API calls to the backend on port 8000 (in Docker, nginx does this)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
