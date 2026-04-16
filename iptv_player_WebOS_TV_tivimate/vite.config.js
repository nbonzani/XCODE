import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { nodePolyfills } from 'vite-plugin-node-polyfills';

function webosPlugin() {
  return {
    name: 'webos-fix',
    enforce: 'post',
    transformIndexHtml: {
      enforce: 'post',
      transform(html) {
        return html
          .replace(/ type="module"/g, '')
          .replace(/ crossorigin/g, '');
      },
    },
  };
}

export default defineConfig({
  plugins: [
    // Polyfills Node.js pour JMuxer (stream, buffer, events, process, etc.)
    nodePolyfills({ protocolImports: false }),
    react({
      babel: {
        plugins: [
          '@babel/plugin-transform-optional-chaining',
          '@babel/plugin-transform-nullish-coalescing-operator',
          '@babel/plugin-transform-logical-assignment-operators',
          '@babel/plugin-transform-class-properties',
        ],
      },
    }),
    webosPlugin(),
  ],

  base: './',
  publicDir: 'public',

  build: {
    outDir: 'dist',
    assetsDir: '',
    // es2015 pour Babel + esbuild cible le même niveau
    target: 'es2015',
    // Utiliser terser au lieu de esbuild pour le minify
    // terser respecte mieux la cible ES2015
    minify: false,
    sourcemap: false,
    chunkSizeWarningLimit: 3000,
    rollupOptions: {
      input: path.resolve(__dirname, 'index.html'),
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'index.js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]',
        format: 'iife',
        name: 'IPTVApp',
      },
    },
  },

  // Force esbuild à transpiler vers ES2015 pour TOUS les fichiers
  esbuild: {
    target: 'es2015',
  },

  server: {
    port: 3000,
    host: true,
  },

  resolve: {
    alias: {
      '@':      path.resolve(__dirname, './src'),
      // (stream/buffer gérés par nodePolyfills)
    },
  },
});