/**
 * User-facing error formatting (Step 3).
 * Lockstep with btf_viewer_pkg/error_format.py.
 *
 * Primary message is actionable; technical detail is preserved separately.
 */

const PARSE_HINTS = [
  [/invalid timestamp/i, 'Check for malformed timestamps near the reported line.'],
  [/unexpected token|parse error|syntax/i, 'Verify the file is a valid BTF/XML trace.'],
  [/encoding|utf-8|unicode/i, 'Save the trace as UTF-8 and try again.'],
  [/empty|no events/i, 'The file appears to contain no trace events.'],
]

/**
 * @typedef {Object} FormattedError
 * @property {string} title
 * @property {string} message
 * @property {string} [suggestion]
 * @property {string} [detail]
 */

/**
 * @param {Object} opts
 * @param {string} opts.operation
 * @param {string} [opts.subject]
 * @param {string} [opts.reason]
 * @param {string} [opts.suggestion]
 * @param {string} [opts.detail]
 * @returns {FormattedError}
 */
export function formatError({
  operation,
  subject = '',
  reason = '',
  suggestion = '',
  detail = '',
}) {
  const op = String(operation || 'Operation').trim()
  const title = subject ? `${op}: ${subject}` : op
  const parts = []
  if (reason) parts.push(String(reason).trim())
  if (suggestion) parts.push(String(suggestion).trim())
  return {
    title,
    message: parts.join(' ') || `${op} failed.`,
    suggestion: suggestion || '',
    detail: detail || '',
  }
}

/** Flat string for toast / status bar (title + message). */
export function formatErrorToast(err) {
  if (!err) return 'An error occurred.'
  if (typeof err === 'string') return err
  const title = err.title || ''
  const msg = err.message || ''
  if (title && msg && !msg.startsWith(title)) return `${title}\n${msg}`
  return msg || title || 'An error occurred.'
}

function guessParseSuggestion(text) {
  const blob = String(text || '')
  for (const [re, hint] of PARSE_HINTS) {
    if (re.test(blob)) return hint
  }
  return 'Check that the file is a valid .btf/.xml trace and try again.'
}

/**
 * @param {Error|string} err
 * @param {string} [fileName]
 * @returns {FormattedError}
 */
export function formatParseError(err, fileName = '') {
  const raw = typeof err === 'string' ? err : (err?.message || String(err))
  const detail = typeof err === 'object' && err?.stack ? String(err.stack) : raw
  const subject = fileName || 'trace file'
  return formatError({
    operation: 'Could not open trace',
    subject,
    reason: raw.replace(/^Error:\s*/i, '').trim() || 'The trace could not be parsed.',
    suggestion: guessParseSuggestion(raw),
    detail,
  })
}

/**
 * @param {Error|string} err
 * @param {string} [fileName]
 * @returns {FormattedError}
 */
export function formatIoError(err, fileName = '') {
  const raw = typeof err === 'string' ? err : (err?.message || String(err))
  const detail = typeof err === 'object' && err?.stack ? String(err.stack) : raw
  const subject = fileName || 'file'
  let suggestion = 'Check that the file exists and is readable.'
  if (/permission|denied/i.test(raw)) {
    suggestion = 'Check file permissions and try again.'
  } else if (/not found|enoent/i.test(raw)) {
    suggestion = 'Verify the path and try opening the file again.'
  }
  return formatError({
    operation: 'Could not read file',
    subject,
    reason: raw.replace(/^Error:\s*/i, '').trim() || 'The file could not be read.',
    suggestion,
    detail,
  })
}

/**
 * @param {Error|string} err
 * @param {string} [provider]
 * @returns {FormattedError}
 */
export function formatAiError(err, provider = '') {
  const raw = typeof err === 'string' ? err : (err?.message || String(err))
  const detail = typeof err === 'object' && err?.stack ? String(err.stack) : raw
  const subject = provider ? `AI provider (${provider})` : 'AI provider'
  let suggestion = 'Check Settings → AI for provider URL, model, and authentication.'
  if (/timeout|timed out/i.test(raw)) {
    suggestion = 'The provider did not respond in time — check network connectivity.'
  } else if (/401|403|unauthorized|forbidden/i.test(raw)) {
    suggestion = 'Verify API key or authentication settings.'
  }
  return formatError({
    operation: 'AI request failed',
    subject,
    reason: raw.replace(/^Error:\s*/i, '').trim(),
    suggestion,
    detail,
  })
}

/**
 * @param {Error|string} err
 * @param {string} [kind] export | report | session
 * @returns {FormattedError}
 */
export function formatExportError(err, kind = 'export') {
  const raw = typeof err === 'string' ? err : (err?.message || String(err))
  const detail = typeof err === 'object' && err?.stack ? String(err.stack) : raw
  const labels = {
    export: 'Could not export',
    report: 'Could not generate report',
    session: 'Could not save session',
  }
  return formatError({
    operation: labels[kind] || labels.export,
    reason: raw.replace(/^Error:\s*/i, '').trim(),
    suggestion: 'Try again or choose a different destination.',
    detail,
  })
}
