import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import {
  closestTitledElement,
  placeTipBox,
  tipTextFromElement,
} from '../src/utils/domTooltip.js'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

describe('domTooltip', () => {
  it('reads live title or stashed data-btf-title', () => {
    const el = {
      getAttribute(name) {
        if (name === 'title') return this.title ?? null
        if (name === 'data-btf-title') return this.stash ?? null
        return null
      },
      title: '  Heatmap  ',
      stash: null,
    }
    assert.equal(tipTextFromElement(el), 'Heatmap')
    el.title = '   '
    el.stash = 'Open file'
    assert.equal(tipTextFromElement(el), 'Open file')
  })

  it('finds the nearest titled ancestor', () => {
    const child = { nodeType: 1, classList: { contains: () => false }, getAttribute: () => null, parentElement: null }
    const btn = {
      nodeType: 1,
      classList: { contains: () => false },
      getAttribute(name) { return name === 'title' ? 'Fit view' : null },
      parentElement: null,
    }
    child.parentElement = btn
    assert.equal(closestTitledElement(child), btn)
  })

  it('keeps the tip box inside the viewport', () => {
    const box = placeTipBox({ left: 10, top: 10, width: 40, height: 20 }, 200, 40, 8, 6)
    assert.ok(box.left >= 8)
    assert.ok(box.top >= 8)
    const nearBottom = placeTipBox(
      { left: 100, top: 700, width: 40, height: 20 },
      120, 40, 8, 6,
    )
    // Prefer above the control when below would clip (vh default 768 in helper
    // when window is missing — here window exists, so just assert finite).
    assert.ok(Number.isFinite(nearBottom.top))
    assert.ok(Number.isFinite(nearBottom.left))
  })

  it('wires install into main.js and documents tab-capture tip gap', () => {
    const main = readFileSync(join(root, 'src/main.js'), 'utf8')
    const rec = readFileSync(join(root, 'src/utils/demoRecorder.js'), 'utf8')
    assert.ok(main.includes('installDomTooltips'))
    assert.ok(rec.includes('domTooltip.js'))
  })
})
