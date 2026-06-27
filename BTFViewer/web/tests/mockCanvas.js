/** Minimal canvas 2D context recorder for overlay draw smoke tests. */
export function createMockCanvas(textWidth = 80) {
  const log = {
    fillRects: [],
    fillTexts: [],
    lines: [],
    save: 0,
    restore: 0,
  }

  const ctx = {
    save() {
      log.save += 1
    },
    restore() {
      log.restore += 1
    },
    font: '',
    textBaseline: 'alphabetic',
    textAlign: 'left',
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 1,
    measureText() {
      return { width: textWidth }
    },
    setLineDash() {},
    beginPath() {},
    moveTo(x, y) {
      log.lines.push({ op: 'moveTo', x, y })
    },
    lineTo(x, y) {
      log.lines.push({ op: 'lineTo', x, y })
    },
    stroke() {},
    fillRect(x, y, w, h) {
      log.fillRects.push({ x, y, w, h })
    },
    fillText(text, x, y) {
      log.fillTexts.push({ text, x, y })
    },
  }

  return { ctx, log }
}
