/**
 * Safe Markdown → HTML for AI Assistant reply preview.
 * Keep in sync with btf_viewer_pkg/ai_assistant.py::markdown_to_safe_html.
 */

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/g
const INLINE_CODE_RE = /`([^`\n]+)`/g
const BOLD_RE = /(\*\*|__)(.+?)\1/g
const ITALIC_RE = /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g
const LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, '&#39;')
}

function inlineToHtml(text) {
  const placeholders = []
  const stash = (frag) => {
    placeholders.push(frag)
    return `\0MD${placeholders.length - 1}\0`
  }

  const src = text || ''
  const parts = []
  let last = 0
  INLINE_CODE_RE.lastIndex = 0
  let m
  while ((m = INLINE_CODE_RE.exec(src))) {
    parts.push(['t', src.slice(last, m.index)])
    parts.push(['c', m[1]])
    last = m.index + m[0].length
  }
  parts.push(['t', src.slice(last)])

  const out = []
  for (const [kind, val] of parts) {
    if (kind === 'c') {
      out.push(stash(`<code>${escapeHtml(val)}</code>`))
      continue
    }
    let seg = val
    let seglast = 0
    const buf = []
    LINK_RE.lastIndex = 0
    let lm
    while ((lm = LINK_RE.exec(seg))) {
      buf.push(escapeHtml(seg.slice(seglast, lm.index)))
      const label = escapeHtml(lm[1])
      const href = String(lm[2] || '').trim()
      const low = href.toLowerCase()
      if (
        low.startsWith('http://')
        || low.startsWith('https://')
        || low.startsWith('btfjump:')
        || low.startsWith('mailto:')
      ) {
        buf.push(stash(`<a href="${escapeAttr(href)}">${label}</a>`))
      } else {
        buf.push(escapeHtml(lm[0]))
      }
      seglast = lm.index + lm[0].length
    }
    buf.push(escapeHtml(seg.slice(seglast)))
    let chunk = buf.join('')
    chunk = chunk.replace(BOLD_RE, '<strong>$2</strong>')
    chunk = chunk.replace(ITALIC_RE, (_, a, b) => `<em>${a != null ? a : b}</em>`)
    chunk = chunk.replace(JUMP_RE, (_, n) => stash(
      `<a href="btfjump:${n}" class="ai-jump" data-jump="${n}">jump:${n}</a>`,
    ))
    out.push(chunk)
  }

  let result = out.join('')
  placeholders.forEach((frag, i) => {
    result = result.split(`\0MD${i}\0`).join(frag)
  })
  return result
}

/** @param {string} text */
export function markdownToSafeHtml(text) {
  const raw = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  if (!raw) return ''
  const lines = raw.split('\n')
  const out = []
  let i = 0
  const para = []

  const flushPara = () => {
    if (!para.length) return
    out.push(`<p>${para.map(s => inlineToHtml(s.trim())).join('<br>')}</p>`)
    para.length = 0
  }

  while (i < lines.length) {
    const line = lines[i]
    const stripped = line.trim()

    if (stripped.startsWith('```')) {
      flushPara()
      const lang = stripped.slice(3).trim()
      i += 1
      const codeLines = []
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i += 1
      }
      if (i < lines.length) i += 1
      const cls = lang ? ` class="language-${escapeAttr(lang)}"` : ''
      out.push(`<pre><code${cls}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    if (!stripped) {
      flushPara()
      i += 1
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(stripped)) {
      flushPara()
      out.push('<hr>')
      i += 1
      continue
    }

    const hm = /^(#{1,4})\s+(.+)$/.exec(stripped)
    if (hm) {
      flushPara()
      const level = hm[1].length
      out.push(`<h${level}>${inlineToHtml(hm[2].trim())}</h${level}>`)
      i += 1
      continue
    }

    if (stripped.startsWith('>')) {
      flushPara()
      const qlines = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        qlines.push(lines[i].trim().replace(/^>\s?/, ''))
        i += 1
      }
      out.push(`<blockquote>${inlineToHtml(qlines.join(' '))}</blockquote>`)
      continue
    }

    if (/^[-*+]\s+/.test(stripped) || /^\d+\.\s+/.test(stripped)) {
      flushPara()
      const ordered = /^\d+\.\s+/.test(stripped)
      const tag = ordered ? 'ol' : 'ul'
      const items = []
      while (i < lines.length) {
        const s = lines[i].trim()
        const m = ordered ? /^\d+\.\s+(.*)$/.exec(s) : /^[-*+]\s+(.*)$/.exec(s)
        if (!m) break
        items.push(`<li>${inlineToHtml(m[1])}</li>`)
        i += 1
      }
      out.push(`<${tag}>${items.join('')}</${tag}>`)
      continue
    }

    para.push(stripped)
    i += 1
  }
  flushPara()
  return out.join('')
}

/** Format a chat message; assistant = Markdown preview, user = plain. */
export function formatAiMessageHtml(role, text) {
  const body = String(text || '').trim()
  if (role === 'assistant') {
    return markdownToSafeHtml(body) || '<p></p>'
  }
  return escapeHtml(body)
    .replace(
      /jump:([0-9]+(?:\.[0-9]+)?)/g,
      '<a href="btfjump:$1" class="ai-jump" data-jump="$1">jump:$1</a>',
    )
    .replace(/\n/g, '<br>')
}
