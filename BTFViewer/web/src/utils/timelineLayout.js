/** Mutable timeline layout (synced from Settings). */

export const DEFAULT_TIMELINE_LAYOUT = {
  labelW: 160,
  rulerH: 40,
  rowH: 22,
  rowGap: 4,
  stiRowH: 18,
  stiWaveformH: 80,
  labelFontSize: 8,
  stiLineStyle: 'linear',
  timescalePerPxDefault: 2,
  cpuLoadRowH: 30,
}

let _layout = { ...DEFAULT_TIMELINE_LAYOUT }

export function getTimelineLayout() {
  return _layout
}

export function setTimelineLayout(patch) {
  _layout = { ..._layout, ...patch }
}

export function resetTimelineLayout() {
  _layout = { ...DEFAULT_TIMELINE_LAYOUT }
}

export function syncTimelineLayoutFromSettings(settings) {
  if (!settings) return
  setTimelineLayout({
    labelW: settings.labelWidth,
    rowH: settings.rowHeight,
    rowGap: settings.rowGap,
    stiRowH: settings.stiRowH,
    stiWaveformH: settings.stiWaveformH,
    labelFontSize: settings.labelFontSize,
    stiLineStyle: settings.stiLineStyle,
    timescalePerPxDefault: settings.timescalePerPxDefault,
    cpuLoadRowH: settings.cpuLoadRowH,
  })
}
