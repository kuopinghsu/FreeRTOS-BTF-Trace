/**
 * Safe Markdown → HTML for AI Assistant reply preview.
 * Keep in sync with btf_viewer_pkg/ai_assistant.py::markdown_to_safe_html.
 */

import { mermaidBlockHtml } from './aiMermaid.js'
import { summariseToolCall } from './aiTools.js'

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
      if (low.startsWith('http://') || low.startsWith('https://')) {
        // Same-tab navigation would discard every loaded trace.
        buf.push(stash(
          `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`,
        ))
      } else if (low.startsWith('btfjump:') || low.startsWith('mailto:')) {
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

/** @param {string} text @param {{ inlineSvg?: boolean, zoomable?: boolean }} [opts] */
export function markdownToSafeHtml(text, { inlineSvg = true, zoomable = true } = {}) {
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
      if (String(lang).toLowerCase() === 'mermaid') {
        out.push(mermaidBlockHtml(codeLines.join('\n'), { inlineSvg, zoomable }))
        continue
      }
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
      let startNum = 0
      while (i < lines.length) {
        const s = lines[i].trim()
        if (ordered) {
          // Models often interrupt 1./2./3. with paragraphs and nested bullets;
          // each run becomes its own <ol>, so honour the source number.
          const m = /^(\d+)\.\s+(.*)$/.exec(s)
          if (!m) break
          const n = Number(m[1])
          if (!startNum) startNum = n
          const val = n === startNum + items.length ? '' : ` value="${n}"`
          items.push(`<li${val}>${inlineToHtml(m[2])}</li>`)
        } else {
          const m = /^[-*+]\s+(.*)$/.exec(s)
          if (!m) break
          items.push(`<li>${inlineToHtml(m[1])}</li>`)
        }
        i += 1
      }
      const startAttr = ordered && startNum > 1 ? ` start="${startNum}"` : ''
      out.push(`<${tag}${startAttr}>${items.join('')}</${tag}>`)
      continue
    }

    para.push(stripped)
    i += 1
  }
  flushPara()
  return out.join('')
}

function conversationStamp(date = new Date()) {
  const p = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} `
    + `${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`
}

/** File-name stamp such as 20260808-084102. */
export function aiFileStamp(date = new Date()) {
  const p = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}`
    + `-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`
}

/**
 * Markdown transcript of the conversation (assistant replies kept as-is).
 * Keep in sync with ai_assistant.py::format_ai_conversation_markdown.
 */
export function formatAiConversationMarkdown(entries, date = new Date()) {
  const out = ['# BTF Viewer — AI Conversation', '', `_Saved ${conversationStamp(date)}_`, '']
  for (const entry of entries || []) {
    const role = entry.role
    out.push(role === 'user' ? '## You' : '## Assistant', '')
    const text = String(entry.content || entry.text || '').trim()
    if (text) {
      out.push(text, '')
    }
    for (const t of entry.tools || []) {
      const st = t.status || 'pending'
      const label = summariseToolCall(t.name || '', t.arguments || {})
      out.push(`- ⚡ ${label} (${st})`)
    }
    if (entry.tools?.length) out.push('')
  }
  return `${out.join('\n').replace(/\s+$/, '')}\n`
}

/** Plain-text transcript of the conversation. */
export function formatAiConversationText(entries, date = new Date()) {
  const out = ['BTF Viewer — AI Conversation', `Saved ${conversationStamp(date)}`, '']
  for (const entry of entries || []) {
    out.push(entry.role === 'user' ? 'You:' : 'Assistant:')
    const text = String(entry.content || entry.text || '').trim()
    if (text) out.push(text)
    for (const t of entry.tools || []) {
      const label = summariseToolCall(t.name || '', t.arguments || {})
      out.push(`- ⚡ ${label} (${t.status || 'pending'})`)
    }
    out.push('')
  }
  return `${out.join('\n').replace(/\s+$/, '')}\n`
}

function toolCardsHtml(tools) {
  if (!tools?.length) return ''
  const rows = tools.map((t) => {
    const label = escapeHtml(summariseToolCall(t.name || '', t.arguments || {}))
    const st = escapeHtml(t.status || 'pending')
    return `<p>⚡ ${label} <span style="color:#8b98a8">(${st})</span></p>`
  }).join('')
  return `<div class="ai-tool-card" style="margin-top:8px;padding:8px 10px;`
    + `border-left:3px solid #c9a227;background:#2a2418;color:#e6d48a;">${rows}</div>`
}

/** Standalone HTML transcript (Markdown rendered, same styling as the panel). */
export function formatAiConversationHtml(entries, date = new Date()) {
  const body = (entries || []).map((entry) => {
    const role = entry.role
    const content = entry.content || entry.text || ''
    return (
      `<section class="msg ${role === 'user' ? 'user' : 'assistant'}">`
      + `<h3>${role === 'user' ? 'You' : 'Assistant'}</h3>`
      + `<div class="body">${formatAiMessageHtml(role, content, { zoomable: false })}${toolCardsHtml(entry.tools)}</div>`
      + '</section>'
    )
  }).join('\n')
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BTF Viewer — AI Conversation</title>
<style>
body{background:#12161d;color:#dbe2ea;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:13px;line-height:1.5;margin:0;padding:20px;}
h1{font-size:18px;margin:0 0 4px;}
.saved{color:#8b98a8;font-size:12px;margin:0 0 16px;}
.msg{padding:12px 0;border-top:1px solid #2b3442;}
.msg:first-of-type{border-top:none;padding-top:0;}
.msg h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 6px;color:#8b98a8;}
.msg.user h3{color:#6ea8e0;}
.msg.assistant h3{color:#6fbf9a;}
.msg .body{padding:8px 10px;border-left:3px solid #5b9bd5;background:#1e3348;border-radius:0 6px 6px 0;}
.msg.assistant .body{border-left-color:#3d9a72;background:#1a2620;}
pre{background:#1a2230;border:1px solid #3a4658;border-radius:4px;padding:8px;overflow:auto;}
code{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;font-size:12px;}
blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid #5b9bd5;color:#a8b4c4;}
a{color:#5b9bd5;}
</style>
</head>
<body>
<h1>BTF Viewer — AI Conversation</h1>
<p class="saved">Saved ${conversationStamp(date)}</p>
${body}
</body>
</html>
`
}

/** Format a chat message; assistant = Markdown preview, user = plain. */
export function formatAiMessageHtml(role, text, { inlineSvg = true, zoomable = true } = {}) {
  const body = String(text || '').trim()
  if (role === 'assistant') {
    return markdownToSafeHtml(body, { inlineSvg, zoomable }) || '<p></p>'
  }
  return escapeHtml(body)
    .replace(
      /jump:([0-9]+(?:\.[0-9]+)?)/g,
      '<a href="btfjump:$1" class="ai-jump" data-jump="$1">jump:$1</a>',
    )
    .replace(/\n/g, '<br>')
}
