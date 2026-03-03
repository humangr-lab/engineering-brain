import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['client/js/__tests__/**/*.test.js'],
    coverage: {
      provider: 'v8',
      include: [
        'client/js/inference/**',
        'client/js/design/oklch.js',
        'client/js/drill/data-cache.js',
        'client/js/search.js',
        'client/js/ui/router.js',
      ],
    },
  },
});
