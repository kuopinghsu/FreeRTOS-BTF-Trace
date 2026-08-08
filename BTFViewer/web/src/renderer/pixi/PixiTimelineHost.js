/**
 * Pixi WebGL host for the timeline segment layer (batched rectangle fills).
 */
import { Application, Container } from 'pixi.js'
import { PixiSegmentBatcher } from './PixiSegmentBatcher.js'

export class PixiTimelineHost {
  constructor() {
    /** @type {Application | null} */
    this.app = null
    /** @type {Container | null} */
    this.stage = null
    /** @type {PixiSegmentBatcher | null} */
    this.batcher = null
    /** @type {PixiSegmentBatcher | null} */
    this.stripeBatcher = null
    this._bgColor = 0x1e1e1e
    this._w = 0
    this._h = 0
    this.ready = false
    this.failed = false
  }

  /** @param {HTMLElement} containerEl */
  async init(containerEl) {
    if (this.failed || this.ready) return this.ready
    try {
      const app = new Application()
      await app.init({
        // Opaque backbuffer: a transparent GL canvas premultiplies stripes
        // through segment fills and washes task colors out.
        background: this._bgColor,
        backgroundAlpha: 1,
        antialias: false,
        autoDensity: true,
        autoStart: false,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        preference: 'webgl',
        preserveDrawingBuffer: true,
      })
      app.ticker.stop()
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
      const stripeRoot = new Container()
      const segRoot = new Container()
      stripeRoot.zIndex = 0
      segRoot.zIndex = 1
      this.stage.sortableChildren = true
      this.stage.addChild(stripeRoot)
      this.stage.addChild(segRoot)
      this.stripeBatcher = new PixiSegmentBatcher(stripeRoot)
      this.batcher = new PixiSegmentBatcher(segRoot)
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
    if (this._bgColor === color) return
    this._bgColor = color
    if (this.app?.renderer?.background) {
      this.app.renderer.background.color = color
      this.app.renderer.background.alpha = 1
    }
  }

  /** @param {number} w CSS pixels */
  /** @param {number} h CSS pixels */
  resize(w, h) {
    if (!this.app || w <= 0 || h <= 0) return
    this._w = w
    this._h = h
    this.app.renderer.resize(w, h)
  }

  beginFrame() {
    this.stripeBatcher?.clear()
    this.batcher?.clear()
  }

  endFrame() {
    this.stripeBatcher?.flush()
    this.batcher?.flush()
    if (this.app?.renderer && this.stage) {
      this.app.renderer.render(this.stage)
    }
  }

  destroy() {
    this.stripeBatcher = null
    this.batcher = null
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
