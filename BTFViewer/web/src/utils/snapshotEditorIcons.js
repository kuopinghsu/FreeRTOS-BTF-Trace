/**
 * Snapshot editor icons — Bootstrap Icons paths (filled), matching main toolbar + desktop config.py.
 */

export const SNAP_ICON_PATHS = {
  arrow: 'M14 0.5a.5.5 0 0 0-.5-.5h-6a.5.5 0 0 0 0 1h4.793L2.146 13.146a.5.5 0 0 0 .708.708L13 2.707V7.5a.5.5 0 0 0 1 0v-7z',
  dblarrow: 'M3.854 4.146a.5.5 0 0 1 0 .708L1.707 7H14.5a.5.5 0 0 1 0 1H1.707l2.147 2.146a.5.5 0 0 1-.708.708l-3-3a.5.5 0 0 1 0-.708l3-3a.5.5 0 0 1 .708 0zm8.292 0a.5.5 0 0 0 0 .708L14.293 7H1.5a.5.5 0 0 0 0 1h12.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708 0z',
  line: 'M13.854 2.146a.5.5 0 0 1 0 .708l-11 11a.5.5 0 0 1-.708-.708l11-11a.5.5 0 0 1 .708 0z',
  rect: 'M14 1a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z',
  circle: 'M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z',
  text: 'M3 2h10v1.5H9.25V13h-2.5V3.5H3V2z',
  undo: 'M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1zM8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z',
  redo: 'M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2v1zM8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466z',
  clear: 'M2 2.5l.5-.5 5.5 5.5 5.5-5.5.5.5L8.5 8 14 13.5l-.5.5L8 8.5 2.5 14l-.5-.5L7.5 8 2 2.5z',
  trash: 'M6.5 1a1 1 0 0 0-1 1v.5H2.5a.5.5 0 0 0 0 1H3V13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V3.5h.5a.5.5 0 0 0 0-1H10.5V2a1 1 0 0 0-1-1h-3zm0 1.5V2h3v.5h-3zM6 5.5a.5.5 0 0 1 1 0v6a.5.5 0 0 1-1 0v-6zm3 0a.5.5 0 0 1 1 0v6a.5.5 0 0 1-1 0v-6z',
  copy: 'M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1zM5 0h6a1 1 0 0 1 1 1v3H4V1a1 1 0 0 1 1-1z',
  save: 'M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.5L11.5 1H2zm2 1h5v3H4V2zm4 8a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM3 10h10v4H3v-4z',
  palette: 'M8 5a1.5 1.5 0 0 0-1.5 1.5v.5A1.5 1.5 0 0 0 8 8.5a1.5 1.5 0 0 0 1.5-1.5v-.5A1.5 1.5 0 0 0 8 5zm-4 0a1.5 1.5 0 0 0-1.5 1.5v.5A1.5 1.5 0 0 0 4 8.5a1.5 1.5 0 0 0 1.5-1.5v-.5A1.5 1.5 0 0 0 4 5zm8 0a1.5 1.5 0 0 0-1.5 1.5v.5a1.5 1.5 0 0 0 3 0v-.5A1.5 1.5 0 0 0 12 5zM8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0z',
}

/** Filled 16×16 SVG matching main app toolbar icons. */
export function snapIcon(d, size = 16) {
  return `<svg viewBox="0 0 16 16" width="${size}" height="${size}" fill="currentColor"><path d="${d}"/></svg>`
}

/** Stroke 16×16 SVG — used for the Phase 4 tools (highlighter / badge / blur / crop). */
export function snapIconStroke(inner, size = 16) {
  return `<svg viewBox="0 0 16 16" width="${size}" height="${size}" fill="none" stroke="currentColor" `
    + `stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
}

const NEW_TOOL_ICONS = {
  select:    '<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor"><path d="M3 2.2l8.4 4.9-3.5.9 2.1 4.6-1.7.8-2.1-4.6-2.5 2.6z"/></svg>',
  highlight: snapIconStroke('<path d="M4 12.5 9.5 7l2.5 2.5-5.5 5.5H4z"/><path d="M9.5 7 12 4.5 14 6.5 11.5 9"/><path d="M3.5 15.5h5"/>'),
  badge:     snapIconStroke('<circle cx="8" cy="8" r="6.3"/><path d="M6.9 6.2 8.4 5.1v5.9M6.3 11h3.6"/>'),
  blur:      snapIconStroke('<rect x="2.4" y="2.4" width="4.6" height="4.6" rx=".8"/><rect x="9" y="4.7" width="4.6" height="4.6" rx=".8"/><rect x="4.6" y="9" width="4.6" height="4.6" rx=".8"/>'),
  crop:      snapIconStroke('<path d="M4.5 1.5v9.6a.9.9 0 0 0 .9.9H15"/><path d="M1 4.5h9.6a.9.9 0 0 1 .9.9V15"/>'),
}

export const SNAP_TOOL_ICONS = {
  ...Object.fromEntries(
    Object.entries(SNAP_ICON_PATHS).filter(([k]) =>
      ['arrow', 'dblarrow', 'line', 'rect', 'circle', 'text'].includes(k),
    ).map(([k, d]) => [k, snapIcon(d)]),
  ),
  ...NEW_TOOL_ICONS,
}

export const ICON_UNDO = snapIcon(SNAP_ICON_PATHS.undo)
export const ICON_REDO = snapIcon(SNAP_ICON_PATHS.redo)
export const ICON_CLEAR = snapIcon(SNAP_ICON_PATHS.clear)
export const ICON_TRASH = snapIcon(SNAP_ICON_PATHS.trash)
export const ICON_COPY = snapIcon(SNAP_ICON_PATHS.copy, 14)
export const ICON_SAVE = snapIcon(SNAP_ICON_PATHS.save, 14)
export const ICON_PALETTE = snapIcon(SNAP_ICON_PATHS.palette, 12)
