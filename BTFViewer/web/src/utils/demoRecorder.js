/**
 * Capture this tab with MediaRecorder (getDisplayMedia).
 *
 * Tab capture (`displaySurface: 'browser'`) does not include the OS pointer, so
 * the shared demo pointer overlay is used. Window / monitor shares use the
 * `cursor: 'always'` constraint instead (native pointer is already in the frame).
 *
 * Native HTML `title` tooltips and `<select>` dropdown lists are drawn outside
 * the page and are not included in tab capture (`getDisplayMedia` / MediaRecorder).
 * The Web app uses in-DOM tips (`domTooltip.js`) and pickers (`DomSelect.vue`)
 * so hover captions and dropdown lists appear in the recording.
 *
 * Quality is tuned for UI/text (timeline lines, small glyphs), not video-call
 * defaults: device-pixel capture with `resizeMode: 'none'`, VP9 over realtime
 * AV1, a `detail` content hint, and a bitrate that scales with pixel count.
 */

import { acquirePointer, releasePointer } from './demoPointer.js'

const RECORD_AUDIO_BITS_PER_SECOND = 192_000
const RECORD_VIDEO_BITS_MIN = 24_000_000
const RECORD_VIDEO_BITS_MAX = 80_000_000
/** Bits per pixel per frame — high enough that thin lines and UI text stay sharp. */
const RECORD_BITS_PER_PIXEL = 0.5

/**
 * Prefer VP9 for screen/UI. Realtime AV1 in Chromium is cheaper/softer and
 * blocks glyphs and 1px timeline lines; VP8 is worse still.
 */
export function pickRecordMimeType(isTypeSupported = MediaRecorder?.isTypeSupported?.bind(MediaRecorder)) {
  if (typeof isTypeSupported !== 'function') return ''
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp09,opus',
    'video/webm;codecs=av01,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
    'video/mp4',
  ]
  return candidates.find(t => {
    try { return isTypeSupported(t) } catch { return false }
  }) || ''
}

export function videoBitrateForCapture(width, height, fps = 30) {
  const w = Math.max(1, Number(width) || 1920)
  const h = Math.max(1, Number(height) || 1080)
  const f = Math.max(1, Number(fps) || 30)
  const bits = Math.round(w * h * f * RECORD_BITS_PER_PIXEL)
  return Math.min(RECORD_VIDEO_BITS_MAX, Math.max(RECORD_VIDEO_BITS_MIN, bits))
}

export function displayCaptureVideoConstraints(dpr, innerWidth, innerHeight) {
  const scale = Math.max(1, Number(dpr) || 1)
  const width = Math.min(3840, Math.round((Number(innerWidth) || 1920) * scale))
  const height = Math.min(2160, Math.round((Number(innerHeight) || 1080) * scale))
  return {
    displaySurface: 'browser',
    cursor: 'always',
    // Do not let the UA downscale the tab for "performance".
    resizeMode: 'none',
    frameRate: { ideal: 30, max: 30 },
    width: { ideal: width, max: 3840 },
    height: { ideal: height, max: 2160 },
  }
}

function stampName(mime) {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  const ext = (mime || '').includes('mp4') ? 'mp4' : 'webm'
  return `btf-demo-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.${ext}`
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/** Tab capture never includes the OS pointer; unknown surface is treated as tab. */
export function displaySurfaceNeedsCursorOverlay(displaySurface) {
  return displaySurface == null || displaySurface === '' || displaySurface === 'browser'
}

export function installCursorOverlay() {
  acquirePointer('record')
  return () => releasePointer('record')
}

async function sharpenDisplayTrack(track, constraints) {
  if (!track) return
  if ('contentHint' in track) track.contentHint = 'detail'
  if (typeof track.applyConstraints !== 'function') return
  try {
    await track.applyConstraints({
      resizeMode: 'none',
      frameRate: constraints.frameRate,
      width: constraints.width,
      height: constraints.height,
    })
  } catch {
    try {
      await track.applyConstraints({
        width: constraints.width,
        height: constraints.height,
      })
    } catch { /* UA may ignore size; bitrate still helps */ }
  }
}

function createMediaRecorder(stream, mime, videoBps, audioBps) {
  const attempts = [
    {
      mimeType: mime,
      videoBitsPerSecond: videoBps,
      audioBitsPerSecond: audioBps,
      bitsPerSecond: videoBps + audioBps,
    },
    {
      mimeType: mime,
      videoBitsPerSecond: videoBps,
      audioBitsPerSecond: audioBps,
    },
    mime ? { mimeType: mime } : {},
    {},
  ]
  let lastErr
  for (const opts of attempts) {
    const clean = { ...opts }
    if (!clean.mimeType) delete clean.mimeType
    try {
      return new MediaRecorder(stream, clean)
    } catch (err) {
      lastErr = err
    }
  }
  throw lastErr || new Error('MediaRecorder is not available')
}

/**
 * @returns {Promise<{ stop: () => Promise<void>, stream: MediaStream }>}
 */
export async function startDemoRecording() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getDisplayMedia) {
    throw new Error('Screen recording is not supported in this browser')
  }
  const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1
  const videoConstraints = displayCaptureVideoConstraints(
    dpr,
    window.innerWidth,
    window.innerHeight,
  )
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: videoConstraints,
    audio: true,
    preferCurrentTab: true,
    selfBrowserSurface: 'include',
    surfaceSwitching: 'exclude',
    systemAudio: 'include',
  })
  const videoTrack = stream.getVideoTracks()[0]
  await sharpenDisplayTrack(videoTrack, videoConstraints)
  const settings = videoTrack?.getSettings?.() || {}
  const videoBps = videoBitrateForCapture(
    settings.width || videoConstraints.width.ideal,
    settings.height || videoConstraints.height.ideal,
    settings.frameRate || 30,
  )
  const mime = pickRecordMimeType()
  const rec = createMediaRecorder(stream, mime, videoBps, RECORD_AUDIO_BITS_PER_SECOND)
  const chunks = []
  rec.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data)
  }
  let settle
  const stopped = new Promise((resolve) => { settle = resolve })
  rec.onstop = () => settle()
  rec.onerror = () => settle()

  const surface = videoTrack?.getSettings?.()?.displaySurface
  const removeOverlay = displaySurfaceNeedsCursorOverlay(surface)
    ? installCursorOverlay()
    : () => {}

  let stopping = false
  async function stop() {
    if (stopping) return
    stopping = true
    removeOverlay()
    if (rec.state !== 'inactive') rec.stop()
    await stopped
    for (const t of stream.getTracks()) t.stop()
    const type = rec.mimeType || mime || 'video/webm'
    const blob = new Blob(chunks, { type })
    if (blob.size) downloadBlob(blob, stampName(type))
  }

  videoTrack?.addEventListener('ended', () => { void stop() })
  rec.start(1000)

  return { stop, stream }
}
