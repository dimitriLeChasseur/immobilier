import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Bibliothèques lourdes isolées : mises en cache séparément du code applicatif.
        manualChunks(id: string) {
          if (id.includes('node_modules/leaflet')) return 'leaflet'
          if (id.includes('node_modules/chart.js')) return 'charts'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
    coverage: {
      reporter: ['text-summary'],
      // Seuils un peu sous la couverture mesurée : ils arrêtent une régression nette.
      thresholds: { statements: 68, branches: 55, functions: 60, lines: 70 },
    },
  },
})
