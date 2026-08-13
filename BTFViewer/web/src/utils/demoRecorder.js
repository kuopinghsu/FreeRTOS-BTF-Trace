/**
 * Capture this tab with MediaRecorder (getDisplayMedia).
 *
 * Tab capture (`displaySurface: 'browser'`) does not include the OS pointer, so
 * the shared demo pointer overlay is used. Window / monitor shares use the
 * `cursor: 'always'` constraint instead (native pointer is already in the frame).
 */

import { acquirePointer, releasePointer } from './demoPointer.js'

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm;codecs=vp9',
    'video/webm',
    'video/mp4',
  ]
  return candidates.find(t => MediaRecorder.isTypeSupported(t)) || ''
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

/**
 * @returns {Promise<{ stop: () => Promise<void>, stream: MediaStream }>}
 */
export async function startDemoRecording() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getDisplayMedia) {
    throw new Error('Screen recording is not supported in this browser')
  }
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: {
      displaySurface: 'browser',
      frameRate: 30,
      cursor: 'always',
    },
    audio: true,
    preferCurrentTab: true,
    selfBrowserSurface: 'include',
    surfaceSwitching: 'exclude',
    systemAudio: 'include',
  })
  const mime = pickMimeType()
  const rec = mime
    ? new MediaRecorder(stream, { mimeType: mime })
    : new MediaRecorder(stream)
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
