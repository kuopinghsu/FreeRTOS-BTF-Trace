import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'
import { gzipSync } from 'zlib'

const require = createRequire(import.meta.url)
const pkg = require('./package.json')

const __dirname = dirname(fileURLToPath(import.meta.url))

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
        const btfPath = resolve(__dirname, 'example.btf')
        const raw = readFileSync(btfPath)
        const gz = gzipSync(raw, { level: 9 })
        const b64 = gz.toString('base64')
        return `export default "${b64}"`
      }
    },
  }
}

export default defineConfig({
  plugins: [vue(), viteSingleFile(), inlineExampleBtfPlugin()],
  base: './',
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
  },
})
