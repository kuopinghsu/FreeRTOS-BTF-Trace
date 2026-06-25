/**
 * Pixi WebGL host for the timeline segment layer (batched rectangle fills).
 */
import { Application, Container, Graphics } from 'pixi.js'
import { PixiSegmentBatcher } from './PixiSegmentBatcher.js'

export class PixiTimelineHost {
  constructor() {
    /** @type {Application | null} */
    this.app = null
    /** @type {Container | null} */
    this.stage = null
    /** @type {PixiSegmentBatcher | null} */
    this.batcher = null
    /** @type {import('pixi.js').Graphics | null} */
    this._bg = null
    this._bgColor = 0x1e1e1e
    this.ready = false
    this.failed = false
  }

  /** @param {HTMLElement} containerEl */
  async init(containerEl) {
    if (this.failed || this.ready) return this.ready
    try {
      const app = new Application()
      await app.init({
        backgroundAlpha: 0,
        antialias: false,
        autoDensity: true,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        preference: 'webgl',
      })
      const canvas = app.canvas
      canvas.className = 'pixi-timeline-canvas'
      canvas.style.position = 'absolute'
      canvas.style.inset = '0'
      canvas.style.width = '100%'
      canvas.style.height = '100%'
      canvas.style.pointerEvents = 'none'
      containerEl.appendChild(canvas)

      this.app = app
      this.stage = app.stage
      this._bg = new Graphics()
      this.stage.addChild(this._bg)
      this.batcher = new PixiSegmentBatcher(this.stage)
      this.ready = true
      return true
    } catch (err) {
      console.warn('[BTF Viewer] WebGL (PixiJS) unavailable; using Canvas 2D only.', err)
      this.failed = true
      return false
    }
  }

  /** @param {number} color Pixi color (e.g. 0x1E1E1E) */
  setBackground(color) {
    this._bgColor = color
  }

  /** @param {number} w CSS pixels */
  /** @param {number} h CSS pixels */
  resize(w, h) {
    if (!this.app || w <= 0 || h <= 0) return
    this.app.renderer.resize(w, h)
    if (this._bg) {
      this._bg.clear()
      this._bg.rect(0, 0, w, h).fill(this._bgColor)
    }
  }

  beginFrame() {
    this.batcher?.clear()
  }

  endFrame() {
    this.batcher?.flush()
  }

  destroy() {
    this.batcher = null
    this._bg = null
    this.stage = null
    if (this.app) {
      this.app.canvas?.remove()
      this.app.destroy(true, { children: true })
      this.app = null
    }
    this.ready = false
  }
}

/** Singleton host reused by TimelinePanel. */
export const pixiTimelineHost = new PixiTimelineHost()
