/**
 * Capture this tab with MediaRecorder (getDisplayMedia).
 *
 * Tab capture (`displaySurface: 'browser'`) does not include the OS pointer, so
 * the shared demo pointer overlay is used. Window / monitor shares use the
 * `cursor: 'always'` constraint instead (native pointer is already in the frame).
 *
 * Quality is tuned for UI/text screen content rather than the browser's video-call
 * defaults: native device-pixel resolution, a high explicit bitrate, a `detail`
 * content hint, and the best real-time codec available (AV1 > VP9 > VP8).
 */

import { acquirePointer, releasePointer } from './demoPointer.js'

// VP9 (or AV1, where MediaRecorder support it) compresses screen/UI content
// — sharp edges, small text — much better than VP8 at the same bitrate, so
// prefer the highest-quality codec the browser can encode in real time.
function pickMimeType() {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  const candidates = [
    'video/webm;codecs=av01,opus',
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm;codecs=vp9',
    'video/webm',
    'video/mp4',
  ]
  return candidates.find(t => MediaRecorder.isTypeSupported(t)) || ''
}

// Bitrate the browser picks with no explicit target (a couple Mbps, tuned for
// webcam/motion video) visibly blocks fine text and thin timeline lines.
// These are generous "near-lossless for UI content" targets instead.
const RECORD_VIDEO_BITS_PER_SECOND = 12_000_000
const RECORD_AUDIO_BITS_PER_SECOND = 128_000

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

/**
 * @returns {Promise<{ stop: () => Promise<void>, stream: MediaStream }>}
 */
export async function startDemoRecording() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getDisplayMedia) {
    throw new Error('Screen recording is not supported in this browser')
  }
  // Request the tab's actual device-pixel size (not the CSS pixel size) so
  // HiDPI/Retina displays aren't captured blurrier than the screen itself.
  const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1
  const idealWidth = Math.min(3840, Math.round((window.innerWidth || 1920) * dpr))
  const idealHeight = Math.min(2160, Math.round((window.innerHeight || 1080) * dpr))
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: {
      displaySurface: 'browser',
      frameRate: 30,
      width: { ideal: idealWidth },
      height: { ideal: idealHeight },
      cursor: 'always',
    },
    audio: true,
    preferCurrentTab: true,
    selfBrowserSurface: 'include',
    surfaceSwitching: 'exclude',
    systemAudio: 'include',
  })
  // 'detail' tells the encoder to favor sharpness over motion smoothness —
  // right trade-off for a mostly-static UI full of small text and thin lines.
  const videoTrack = stream.getVideoTracks()[0]
  if (videoTrack && 'contentHint' in videoTrack) videoTrack.contentHint = 'detail'
  const mime = pickMimeType()
  const recOptions = {
    videoBitsPerSecond: RECORD_VIDEO_BITS_PER_SECOND,
    audioBitsPerSecond: RECORD_AUDIO_BITS_PER_SECOND,
  }
  if (mime) recOptions.mimeType = mime
  const rec = new MediaRecorder(stream, recOptions)
  const chunks = []
  rec.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data)
  }
  let settle
  const stopped = new Promise((resolve) => { settle = resolve })
  rec.onstop = () => settle()
  rec.onerror = () => settle()

  const surface = stream.getVideoTracks()[0]?.getSettings?.()?.displaySurface
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

  stream.getVideoTracks()[0]?.addEventListener('ended', () => { void stop() })
  rec.start(1000)

  return { stop, stream }
}
