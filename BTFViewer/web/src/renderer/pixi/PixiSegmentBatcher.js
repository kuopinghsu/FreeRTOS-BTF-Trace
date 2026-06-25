/**
 * Batches timeline segment rectangles by color/alpha for Pixi Graphics fill passes.
 */
import { Graphics } from 'pixi.js'

function batchKey(color, alpha) {
  return `${color}\0${alpha}`
}

export class PixiSegmentBatcher {
  /** @param {Container} root */
  constructor(root) {
    this._root = root
    /** @type {Map<string, { g: Graphics, rects: number[], color: string|number, alpha: number }>} */
    this._batches = new Map()
  }

  clear() {
    for (const batch of this._batches.values()) {
      batch.rects.length = 0
      batch.g.clear()
      batch.g.visible = false
    }
  }

  /**
   * @param {number} x
   * @param {number} y
   * @param {number} w
   * @param {number} h
   * @param {string|number} color
   * @param {number} [alpha]
   */
  addRect(x, y, w, h, color, alpha = 1) {
    if (w <= 0 || h <= 0) return
    const key = batchKey(color, alpha)
    let batch = this._batches.get(key)
    if (!batch) {
      const g = new Graphics()
      g.roundPixels = true
      this._root.addChild(g)
      batch = { g, rects: [], color, alpha }
      this._batches.set(key, batch)
    }
    batch.rects.push(x, y, w, h)
  }

  flush() {
    for (const batch of this._batches.values()) {
      const { g, rects, color, alpha } = batch
      g.clear()
      if (rects.length === 0) {
        g.visible = false
        continue
      }
      for (let i = 0; i < rects.length; i += 4) {
        g.rect(rects[i], rects[i + 1], rects[i + 2], rects[i + 3])
      }
      g.fill({ color, alpha: alpha ?? 1 })
      g.visible = true
    }
  }
}
