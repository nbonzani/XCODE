import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Plugin webOS : corrections HTML obligatoires pour file://
// 1. Supprime type="module"  — les modules ES ne fonctionnent pas sous file://
// 2. Supprime crossorigin    — cause une erreur CORS entre les deux origines file://
//    (file://com.iptv.player-webos vs file:///media/developer/.../assets/)
function webosHtmlFix() {
  return {
    name: 'webos-html-fix',
    transformIndexHtml(html) {
      return html
        .replace(/<script type="module"/g, '<script defer')
        .replace(/ crossorigin/g, '')
    }
  }
}

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [
          '@babel/plugin-transform-optional-chaining',
          '@babel/plugin-transform-nullish-coalescing-operator',
          '@babel/plugin-transform-logical-assignment-operators',
        ]
      }
    }),
    webosHtmlFix()
  ],
  base: './',
  build: {
    // ES2019 : force esbuild à transpiler ?. et ?? sur TOUT le bundle
    // (node_modules inclus — les plugins Babel ne couvrent que src/)
    target: 'es2019',
    outDir: 'dist',
    assetsDir: '',
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        // IIFE : pas d'export/import dans le bundle — obligatoire pour
        // un <script> classique (sans type="module") sur webOS
        format: 'iife',
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  }
})
