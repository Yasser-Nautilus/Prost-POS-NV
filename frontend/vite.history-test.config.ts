// Isolated opt-in rendered regression entry, never included in the app build.
import { defineConfig, mergeConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import base from './vite.config';
export default mergeConfig(base, defineConfig({
  build: { rollupOptions: { input: fileURLToPath(new URL('./test-history/index.html', import.meta.url)) } },
}));
