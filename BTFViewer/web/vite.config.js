import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { existsSync, readFileSync, renameSync, unlinkSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import pkg from './package.json' with { type: 'json' }

const __dirname = dirname(fileURLToPath(import.meta.url))
const BUILDS_DIR = resolve(__dirname, '../builds')
const RELEASE_HTML = 'btf_viewer.html'

function inlineExampleBtfPlugin() {
  const virtualId = 'virtual:example-btf'
  const resolvedId = '\0virtual:example-btf'
  return {
    name: 'inline-example-btf',
    resolveId(id) {
      if (id === virtualId) return resolvedId
    },
    load(id) {
      if (id === resolvedId) {
        // Pre-compressed demo trace (already gzip); embed as base64.
        const btfPath = resolve(__dirname, 'example-2cores.btf.gz')
        const gz = readFileSync(btfPath)
        return `export default "${gz.toString('base64')}"`
      }
    },
  }
}

/** Vite always emits index.html; rename to builds/btf_viewer.html (keep desktop .py alongside). */
function releaseHtmlPlugin() {
  return {
    name: 'release-btf-viewer-html',
    closeBundle() {
      const indexPath = join(BUILDS_DIR, 'index.html')
      const releasePath = join(BUILDS_DIR, RELEASE_HTML)
      if (!existsSync(indexPath)) {
        return
      }
      if (existsSync(releasePath)) {
        unlinkSync(releasePath)
      }
      renameSync(indexPath, releasePath)
    },
  }
}

export default defineConfig({
  plugins: [vue(), viteSingleFile(), inlineExampleBtfPlugin(), releaseHtmlPlugin()],
  base: './',
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)),
  },
  build: {
    outDir: BUILDS_DIR,
    emptyOutDir: false,
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
  },
})
