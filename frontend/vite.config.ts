import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Forward API calls to the backend (in Docker, nginx does this), so the family hub's login cookie is the page's own:
// port 8000 in development, or API_PROXY
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.API_PROXY || 'http://localhost:8000' } },
})
