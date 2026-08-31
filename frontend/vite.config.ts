import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * stripCrossOrigin plugin:
 * The built index.html gets `crossorigin` attributes on <script> and <link> tags.
 * These attributes cause the browser (QtWebEngineView) to block loading local
 * file:// resources with a CORS error. This plugin removes them from the final HTML.
 */
function stripCrossOrigin() {
  return {
    name: 'strip-crossorigin',
    transformIndexHtml(html: string) {
      return html
        .replace(/ crossorigin=""/g, '')
        .replace(/ crossorigin/g, '');
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [
    react(),
    tailwindcss(),
    stripCrossOrigin(),
  ],
})
