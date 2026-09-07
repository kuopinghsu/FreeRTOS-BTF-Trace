/**
 * Stable `Task-N` aliasing for the Export dialog's Anonymize option.
 * Keep in sync with btf_viewer_pkg/anonymize_export.py.
 *
 * One alias map is built per export from the trace's task set (sorted, so web
 * and desktop agree on the numbering), then applied to every artifact the
 * export writes: the embedded / sliced raw BTF text, Perfetto thread + slice
 * names, and the bundled Trace Health / Findings / notebook JSON.
 *
 * Only whole-token task-name occurrences are replaced (`ControlTask` does not
 * match inside `ControlTaskHelper`), so the alias is reversible by eye.
 */

export const ANON_PREFIX = 'Task-'

/** `Map<real_name, "Task-N">` for the unique, sorted, non-empty names. */
export function buildTaskAliasMap(names) {
  const uniq = [...new Set(
    [...(names || [])].map((n) => String(n ?? '').trim()).filter(Boolean),
  )].sort()
  return new Map(uniq.map((n, i) => [n, `${ANON_PREFIX}${i + 1}`]))
}

function escapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function aliasRegex(names) {
  const ordered = [...names]
    .filter((n) => String(n))
    .sort((a, b) => b.length - a.length)
    .map(escapeRe)
  if (!ordered.length) return null
  // No word char / hyphen / dot on either side → whole-identifier match only.
  return new RegExp(`(?<![\\w.\\-])(?:${ordered.join('|')})(?![\\w.\\-])`, 'g')
}

/** Replace every whole-token task name in `text` with its `Task-N` alias. */
export function anonymizeWithMap(text, aliasMap) {
  if (text == null || text === '') return text == null ? '' : text
  if (!aliasMap || !aliasMap.size) return text
  const rx = aliasRegex(aliasMap.keys())
  if (!rx) return text
  return String(text).replace(rx, (m) => aliasMap.get(m) ?? m)
}

// Raw BTF text and Perfetto/JSON strings use the same whole-token substitution.
export const anonymizeBtfText = anonymizeWithMap

/** Recursively rewrite every string value in a JSON-able structure. */
export function anonymizeJsonStrings(obj, aliasMap) {
  if (typeof obj === 'string') return anonymizeWithMap(obj, aliasMap)
  if (Array.isArray(obj)) return obj.map((v) => anonymizeJsonStrings(v, aliasMap))
  if (obj && typeof obj === 'object') {
    const out = {}
    for (const k of Object.keys(obj)) out[k] = anonymizeJsonStrings(obj[k], aliasMap)
    return out
  }
  return obj
}
