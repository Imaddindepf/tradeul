import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
    resolve: {
        alias: {
            '@': path.resolve(__dirname, '.'),
        },
    },
    test: {
        include: ['lib/**/*.test.ts', 'hooks/**/*.test.ts', 'components/**/*.test.ts'],
        // __tests__/TickerSearch.test.tsx es un test legacy de Jest (sin runner
        // instalado); requiere jsdom + testing-library. Migrarlo antes de
        // incluirlo aquí.
        exclude: ['node_modules/**', '__tests__/**'],
    },
});
