import { defineConfig } from 'vite';
import { resolve } from 'node:path';
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        simulator: resolve(import.meta.dirname,'index.html'),
        review: resolve(import.meta.dirname,'review.html')
      }
    }
  }
});
