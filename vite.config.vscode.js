import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, 'vscode-strudel-bundle.js'),
      name: 'Strudel',
      formats: ['es'],
      fileName: () => 'strudel.js'
    },
    outDir: 'dist-vscode',
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      }
    },
    target: 'es2021',
    minify: false // Keep readable for debugging
  }
});
