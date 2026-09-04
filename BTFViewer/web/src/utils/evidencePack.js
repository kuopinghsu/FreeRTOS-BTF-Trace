/**
 * Bundle investigation artifacts into a downloadable zip (fflate).
 */
import { zipSync, strToU8 } from 'fflate'

/**
 * @param {{
 *   baseName?: string,
 *   findingsText?: string,
 *   sessionJson?: string,
 *   statsHtml?: string,
 *   notes?: string,
 * }} parts
 * @returns {{ filename: string, blob: Blob }}
 */
export function buildEvidencePackZip(parts = {}) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const base = String(parts.baseName || 'btf-evidence').replace(/[^\w.-]+/g, '_') || 'btf-evidence'
  const files = {}
  if (parts.findingsText) files['analysis-findings.txt'] = strToU8(parts.findingsText)
  if (parts.sessionJson) files['session.json'] = strToU8(parts.sessionJson)
  if (parts.statsHtml) files['statistics-report.html'] = strToU8(parts.statsHtml)
  if (parts.notes) files['notes.txt'] = strToU8(parts.notes)
  files['README.txt'] = strToU8(
    'BTFViewer evidence pack\n'
    + '----------------------\n'
    + 'analysis-findings.txt — Analysis Findings snapshot\n'
    + 'session.json — portable session (marks, cursors, layout)\n'
    + 'statistics-report.html — optional HTML stats export\n'
    + 'Open the matching .btf in BTFViewer to verify events.\n',
  )
  const zipped = zipSync(files, { level: 6 })
  return {
    filename: `${base}-evidence-${stamp}.zip`,
    blob: new Blob([zipped], { type: 'application/zip' }),
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
