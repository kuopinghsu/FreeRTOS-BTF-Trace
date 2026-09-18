/** Cursor marker colours (up to 8 — matches desktop _CURSOR_COLORS). */
export const CURSOR_COLORS = [
  '#FF4444', '#44FF88', '#4499FF', '#FFAA22',
  '#FF44FF', '#44FFFF', '#FFFF44', '#CC44FF',
]

/**
 * Darker, saturated variants for light backgrounds (timeline rows are
 * white/light gray) — matches desktop _CURSOR_COLORS_LIGHT. Same color
 * index (C1-C8) as CURSOR_COLORS so cursors keep their identity across
 * theme switches.
 */
export const CURSOR_COLORS_LIGHT = [
  '#C62828', '#2E7D32', '#1565C0', '#E65100',
  '#8E24AA', '#00838F', '#F9A825', '#6A1B9A',
]

/** Select the cursor palette for the active theme (matches desktop _cursor_colors). */
export function cursorColors(darkMode = true) {
  return darkMode ? CURSOR_COLORS : CURSOR_COLORS_LIGHT
}
