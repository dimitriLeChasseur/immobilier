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
      // Seuils un peu sous la couverture mesurée par la CI en octobre 2026 (79,3 / 65,8 / 73,8 /
      // 81,5 %) : ils arrêtent une régression nette. Un .env local couvre plus de branches,
      // d'où une mesure locale plus haute : c'est celle de la CI qui compte.
      thresholds: { statements: 78, branches: 64, functions: 72, lines: 80 },
    },
  },
})
