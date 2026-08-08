/** Mutable timeline layout (synced from Settings). Defaults live in ``src/config.js``. */
import {
  CPU_LOAD_ROW_H,
  FONT_SIZE,
  LABEL_WIDTH,
  ROW_GAP,
  ROW_HEIGHT,
  RULER_HEIGHT,
  STI_LINE_STYLE,
  STI_ROW_H,
  STI_WAVEFORM_H,
  TIMESCALE_PER_PX_DEFAULT,
} from '../config.js'

export const DEFAULT_TIMELINE_LAYOUT = {
  labelW: LABEL_WIDTH,
  rulerH: RULER_HEIGHT,
  rowH: ROW_HEIGHT,
  rowGap: ROW_GAP,
  stiRowH: STI_ROW_H,
  stiWaveformH: STI_WAVEFORM_H,
  labelFontSize: FONT_SIZE,
  stiLineStyle: STI_LINE_STYLE,
  timescalePerPxDefault: TIMESCALE_PER_PX_DEFAULT,
  cpuLoadRowH: CPU_LOAD_ROW_H,
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
