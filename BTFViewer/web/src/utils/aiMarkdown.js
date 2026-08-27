/**
 * Safe Markdown → HTML for AI Assistant reply preview.
 * Keep in sync with btf_viewer_pkg/ai_assistant.py::markdown_to_safe_html.
 */

import { mermaidBlockHtml } from './aiMermaid.js'
import { btfHighlightHref, btfJumpHref, btfRangeHref, parseBtfHighlightHref, formatToolActionLabel, summariseToolCall } from './aiTools.js'
import { btfHtmlReportDocument } from './htmlReport.js'

import { evidencePanelLabels, evidencePanelSummaryLine, evidencePanelToggleLabel } from './aiInvestigation.js'
import { DEFAULT_AI_RESPONSE_LANGUAGE } from './aiClient.js'

/** Visible role labels (panel + Save As). Keep in sync with ai_assistant.py. */
export const AI_ROLE_LABEL_USER = 'Your prompt'
export const AI_ROLE_LABEL_ASSISTANT = 'AI Assistant'
export const AI_ROLE_LABEL_EVIDENCE = 'Evidence & Validation'

export function aiRoleLabel(role, responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  if (role === 'user') return AI_ROLE_LABEL_USER
  if (role === 'evidence') return evidencePanelLabels(responseLanguage).role
  return AI_ROLE_LABEL_ASSISTANT
}

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/g
const RANGE_RE = /range:([0-9]+(?:\.[0-9]+)?)\/([0-9]+(?:\.[0-9]+)?)/g
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
      // Models often wrap jump:TIME in backticks; keep those clickable.
      const rm = String(val || '').trim().match(/^range:([0-9]+(?:\.[0-9]+)?)\/([0-9]+(?:\.[0-9]+)?)$/)
      if (rm) {
        out.push(stash(
          `<a href="${btfRangeHref(rm[1], rm[2])}" class="ai-jump">range:${rm[1]}/${rm[2]}</a>`,
        ))
        continue
      }
      const jm = String(val || '').trim().match(/^jump:([0-9]+(?:\.[0-9]+)?)$/)
      if (jm) {
        out.push(stash(
          `<a href="${btfJumpHref(jm[1])}" class="ai-jump" data-jump="${jm[1]}">jump:${jm[1]}</a>`,
        ))
      } else {
        out.push(stash(`<code>${escapeHtml(val)}</code>`))
      }
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
      let href = String(lm[2] || '').trim()
      let low = href.toLowerCase()
      if (low.startsWith('btfhighlight:')) {
        const name = parseBtfHighlightHref(href)
        if (name) href = btfHighlightHref(name)
        low = href.toLowerCase()
      }
      if (low.startsWith('http://') || low.startsWith('https://')) {
        // Same-tab navigation would discard every loaded trace.
        buf.push(stash(
          `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`,
        ))
      } else if (
        low.startsWith('btfjump:')
        || low.startsWith('btfrange:')
        || low.startsWith('btfhighlight:')
        || low.startsWith('btfhyp:')
        || low.startsWith('btfscope:')
        || low.startsWith('btfexp:')
        || low.startsWith('btftool:')
        || low.startsWith('btfstats:')
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
    chunk = chunk.replace(RANGE_RE, (_, lo, hi) => stash(
      `<a href="${btfRangeHref(lo, hi)}" class="ai-jump">range:${lo}/${hi}</a>`,
    ))
    chunk = chunk.replace(JUMP_RE, (_, n) => stash(
      `<a href="${btfJumpHref(n)}" class="ai-jump" data-jump="${n}">jump:${n}</a>`,
    ))
    out.push(chunk)
  }

  let result = out.join('')
  placeholders.forEach((frag, i) => {
    result = result.split(`\0MD${i}\0`).join(frag)
  })
  return result
}

const MD_TABLE_ALIGN_RE = /^:?-{1,}:?$/
const HTML_TABLE_START_RE = /^<table\b/i
const HTML_TABLE_END_RE = /<\/table\s*>/i
const AI_MD_TABLE_OPEN = (
  '<table class="ai-md-table" width="100%" cellspacing="0" cellpadding="4" '
  + 'style="table-layout:fixed;">'
)

function aiMdThStyle(dark = true) {
  if (dark) {
    return (
      'border:1px solid #3a4658;padding:4px 8px;'
      + 'background:#243044;color:#e8eef6;font-weight:600;'
      + 'word-wrap:break-word;'
    )
  }
  return (
    'border:1px solid #DDDDDD;padding:4px 8px;'
    + 'background:#E8EEF4;color:#1E1E1E;font-weight:600;'
    + 'word-wrap:break-word;'
  )
}

function aiMdTdStyle(dark = true) {
  if (dark) {
    return (
      'border:1px solid #3a4658;padding:4px 8px;'
      + 'background:#1a2230;color:#dbe2ea;'
      + 'word-wrap:break-word;'
    )
  }
  return (
    'border:1px solid #DDDDDD;padding:4px 8px;'
    + 'background:#FFFFFF;color:#1E1E1E;'
    + 'word-wrap:break-word;'
  )
}

function splitMdTableRow(line) {
  let s = String(line || '').trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map(p => p.trim().replace(/\\\|/g, '|'))
}

function isMdTableSeparator(line) {
  if (!String(line || '').includes('|')) return false
  const cells = splitMdTableRow(line)
  if (!cells.length) return false
  return cells.every((cell) => {
    const compact = cell.replace(/\s+/g, '')
    return compact && MD_TABLE_ALIGN_RE.test(compact)
  })
}

function mdTableAligns(sepLine, ncols) {
  const cells = splitMdTableRow(sepLine)
  const out = []
  for (let i = 0; i < ncols; i += 1) {
    const compact = (i < cells.length ? cells[i] : '').replace(/\s+/g, '')
    const left = compact.startsWith(':')
    const right = compact.endsWith(':')
    if (left && right) out.push('center')
    else if (right) out.push('right')
    else out.push('left')
  }
  return out
}

function mdTableCellHtml(tag, text, align, dark = true) {
  const style = tag === 'th' ? aiMdThStyle(dark) : aiMdTdStyle(dark)
  const al = (align === 'left' || align === 'right' || align === 'center') ? align : 'left'
  return `<${tag} align="${al}" style="${style}">${inlineToHtml(text)}</${tag}>`
}

function mdTableHtml(header, aligns, rows, dark = true) {
  const ncols = Math.max(1, header.length)
  const pad = (cells) => {
    const next = cells.slice(0, ncols)
    while (next.length < ncols) next.push('')
    return next
  }
  const heads = pad(header)
  const thead = `<tr>${heads.map((c, i) => mdTableCellHtml('th', c, aligns[i] || 'left', dark)).join('')}</tr>`
  const tbody = rows.map((row) => {
    const cells = pad(row)
    return `<tr>${cells.map((c, i) => mdTableCellHtml('td', c, aligns[i] || 'left', dark)).join('')}</tr>`
  }).join('')
  return `${AI_MD_TABLE_OPEN}<thead>${thead}</thead><tbody>${tbody}</tbody></table>`
}

const TABLE_KEEP = new Set(['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'br'])
const TABLE_SKIP = new Set(['script', 'style', 'iframe', 'object', 'embed', 'link', 'meta', 'svg'])

function sanitizeHtmlTableBlock(block, dark = true) {
  let skip = 0
  let sawTable = false
  const parts = []
  const src = String(block || '')
  const tok = /<\/?([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>|([^<]+)|./g
  let m
  while ((m = tok.exec(src))) {
    if (m[3] != null || (m[1] == null && m[0])) {
      if (!skip) parts.push(inlineToHtml(m[3] != null ? m[3] : m[0]))
      continue
    }
    const tag = String(m[1] || '').toLowerCase()
    const close = m[0].startsWith('</')
    const selfClose = /\/\s*>$/.test(m[0])
    if (TABLE_SKIP.has(tag)) {
      if (!close) skip += 1
      else skip = Math.max(0, skip - 1)
      continue
    }
    if (skip || !TABLE_KEEP.has(tag)) continue
    if (tag === 'br') {
      parts.push('<br>')
      continue
    }
    if (close) {
      parts.push(`</${tag}>`)
      continue
    }
    if (tag === 'table') {
      sawTable = true
      parts.push(AI_MD_TABLE_OPEN)
      continue
    }
    const attrs = m[2] || ''
    const extra = []
    const alignM = /\balign\s*=\s*["']?(left|right|center)/i.exec(attrs)
    const colspanM = /\bcolspan\s*=\s*["']?(\d+)/i.exec(attrs)
    const rowspanM = /\browspan\s*=\s*["']?(\d+)/i.exec(attrs)
    if (colspanM && Number(colspanM[1]) >= 1 && Number(colspanM[1]) <= 32) {
      extra.push(`colspan="${Number(colspanM[1])}"`)
    }
    if (rowspanM && Number(rowspanM[1]) >= 1 && Number(rowspanM[1]) <= 32) {
      extra.push(`rowspan="${Number(rowspanM[1])}"`)
    }
    if (tag === 'th' || tag === 'td') {
      if (alignM) extra.push(`align="${alignM[1].toLowerCase()}"`)
      extra.push(`style="${tag === 'th' ? aiMdThStyle(dark) : aiMdTdStyle(dark)}"`)
    }
    const attr = extra.length ? ` ${extra.join(' ')}` : ''
    parts.push(`<${tag}${attr}>`)
    if (selfClose && tag !== 'table') parts.push(`</${tag}>`)
  }
  const html = parts.join('').trim()
  if (!sawTable || !/<table/i.test(html)) return ''
  return html
}

/** @param {string} text @param {{ inlineSvg?: boolean, zoomable?: boolean, dark?: boolean }} [opts] */
export function markdownToSafeHtml(text, { inlineSvg = true, zoomable = true, dark = true, foldDepth = 0 } = {}) {
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
        out.push(mermaidBlockHtml(codeLines.join('\n'), { inlineSvg, zoomable, dark }))
        continue
      }
      const cls = lang ? ` class="language-${escapeAttr(lang)}"` : ''
      out.push(`<pre><code${cls}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    // Models often omit ```mermaid; bare graph/flowchart/sequenceDiagram.
    if (/^(graph|flowchart|sequencediagram)\b/i.test(stripped)) {
      flushPara()
      const codeLines = []
      while (i < lines.length) {
        const s = lines[i].trim()
        if (!s) break
        if (s.startsWith('```')) break
        if (codeLines.length && /^(#{1,4}\s+|[-*+]\s+|\d+\.\s+)/.test(s)) break
        codeLines.push(lines[i])
        i += 1
      }
      out.push(mermaidBlockHtml(codeLines.join('\n'), { inlineSvg, zoomable, dark }))
      continue
    }

    if (!stripped) {
      flushPara()
      i += 1
      continue
    }

    // Collapsible Evidence folds: <details class="ai-ev-fold">…</details>
    if (/^<details\b/i.test(stripped)) {
      flushPara()
      const open = /\bopen\b/i.test(stripped)
      i += 1
      let summary = ''
      const bodyLines = []
      let depth = 1
      while (i < lines.length && depth > 0) {
        const s = lines[i].trim()
        if (/^<details\b/i.test(s)) {
          depth += 1
          bodyLines.push(lines[i])
          i += 1
          continue
        }
        if (/^<\/details>\s*$/i.test(s)) {
          depth -= 1
          if (depth > 0) bodyLines.push(lines[i])
          i += 1
          continue
        }
        if (!summary && /^<summary>/i.test(s)) {
          summary = s.replace(/^<summary>/i, '').replace(/<\/summary>\s*$/i, '').trim()
          i += 1
          continue
        }
        bodyLines.push(lines[i])
        i += 1
      }
      const title = summary || 'Details'
      let levelClass = 'ai-ev-fold-l1'
      const classMatch = stripped.match(/\bclass="([^"]*)"/i)
      if (classMatch) {
        if (/\bai-ev-fold-l2\b/.test(classMatch[1])) levelClass = 'ai-ev-fold-l2'
        else if (/\bai-ev-fold-l1\b/.test(classMatch[1])) levelClass = 'ai-ev-fold-l1'
      } else if (foldDepth >= 1) {
        levelClass = 'ai-ev-fold-l2'
      }
      const inner = markdownToSafeHtml(bodyLines.join('\n').trim(), {
        inlineSvg, zoomable, dark, foldDepth: foldDepth + 1,
      })
      out.push(
        `<details class="ai-ev-fold ${levelClass}"${open ? ' open' : ''}>`
        + `<summary>${inlineToHtml(title)}</summary>`
        + `<div class="ai-ev-fold-body">${inner}</div></details>`,
      )
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

    if (HTML_TABLE_START_RE.test(stripped)) {
      flushPara()
      const buf = [stripped]
      let foundEnd = HTML_TABLE_END_RE.test(stripped)
      i += 1
      while (i < lines.length && !foundEnd) {
        buf.push(lines[i])
        if (HTML_TABLE_END_RE.test(lines[i])) foundEnd = true
        i += 1
      }
      const block = buf.join('\n')
      const safe = sanitizeHtmlTableBlock(block, dark)
      out.push(safe || `<p>${inlineToHtml(block)}</p>`)
      continue
    }

    if (
      stripped.includes('|')
      && i + 1 < lines.length
      && isMdTableSeparator(lines[i + 1].trim())
    ) {
      flushPara()
      const headerCells = splitMdTableRow(stripped)
      const aligns = mdTableAligns(lines[i + 1].trim(), Math.max(1, headerCells.length))
      i += 2
      const bodyRows = []
      while (i < lines.length) {
        const s = lines[i].trim()
        if (!s || !s.includes('|') || s.startsWith('```')) break
        if (/^#{1,4}\s+/.test(s) || HTML_TABLE_START_RE.test(s)) break
        if (isMdTableSeparator(s)) {
          i += 1
          continue
        }
        bodyRows.push(splitMdTableRow(s))
        i += 1
      }
      out.push(mdTableHtml(headerCells, aligns, bodyRows, dark))
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
export function formatAiConversationMarkdown(entries, date = new Date(), responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  const out = ['# BTF Viewer — AI Conversation', '', `_Saved ${conversationStamp(date)}_`, '']
  for (const entry of entries || []) {
    const role = entry.role
    const text = String(entry.content || entry.text || '').trim()
    out.push(`## ${aiRoleLabel(role, responseLanguage)}`, '')
    if (text) {
      out.push(text, '')
    }
    for (const t of entry.tools || []) {
      const st = t.status || 'pending'
      const label = formatToolActionLabel(t.name || '', t.arguments || {})
      out.push(`- ⚡ ${label} (${st})`)
    }
    if (entry.tools?.length) out.push('')
  }
  return `${out.join('\n').replace(/\s+$/, '')}\n`
}

/** Plain-text transcript of the conversation. */
export function formatAiConversationText(entries, date = new Date(), responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  const out = ['BTF Viewer — AI Conversation', `Saved ${conversationStamp(date)}`, '']
  for (const entry of entries || []) {
    const text = String(entry.content || entry.text || '').trim()
    out.push(`${aiRoleLabel(entry.role, responseLanguage)}:`)
    if (text) out.push(text)
    for (const t of entry.tools || []) {
      const label = formatToolActionLabel(t.name || '', t.arguments || {})
      out.push(`- ⚡ ${label} (${t.status || 'pending'})`)
    }
    out.push('')
  }
  return `${out.join('\n').replace(/\s+$/, '')}\n`
}

function toolCardsHtml(tools) {
  if (!tools?.length) return ''
  const rows = tools.map((t) => {
    const label = escapeHtml(formatToolActionLabel(t.name || '', t.arguments || {}))
    const st = escapeHtml(t.status || 'pending')
    let html = `<p>⚡ ${label} <span style="color:#6b7280">(${st})</span></p>`
    if (String(t.status || '') === 'failed') {
      const detail = String(t.result || t.error || '').trim()
      if (detail) {
        html += `<p style="margin:2px 0 6px 1.2em;color:#6b7280;font-size:11px;">`
          + `${escapeHtml(detail)}</p>`
      }
    }
    return html
  }).join('')
  return `<div class="ai-tool-card" style="margin-top:8px;padding:8px 10px;`
    + `border-left:3px solid #c9a227;background:#fff8e8;color:#6b5508;">${rows}</div>`
}

/** Expand all / Collapse all for Evidence folds in standalone HTML export. */
export const AI_EVIDENCE_PANEL_EXPORT_SCRIPT = `
<script>
(function () {
  document.querySelectorAll('.msg.evidence .ai-ev-panel-toggle').forEach(function (btn) {
    if (btn.getAttribute('data-bound') === '1') return;
    btn.setAttribute('data-bound', '1');
    btn.addEventListener('click', function () {
      var root = btn.closest('.msg.evidence');
      if (!root) return;
      var folds = root.querySelectorAll('details.ai-ev-fold');
      var open = btn.getAttribute('data-open') === '1';
      folds.forEach(function (d) {
        if (open) d.removeAttribute('open');
        else d.setAttribute('open', '');
      });
      var next = !open;
      btn.setAttribute('data-open', next ? '1' : '0');
      btn.textContent = next
        ? (btn.getAttribute('data-collapse') || 'Collapse all')
        : (btn.getAttribute('data-expand') || 'Expand all');
    });
  });
})();
</script>
`.trim()

/** Conversation turn markup only (no document chrome). For report embedding. */
export function formatAiConversationHtmlBody(entries, responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  let hasEvidence = false
  const turns = (entries || []).map((entry) => {
    const role = entry.role
    const content = entry.content || entry.text || ''
    const cls = role === 'user' ? 'user' : (role === 'evidence' ? 'evidence' : 'assistant')
    const label = aiRoleLabel(role, responseLanguage)
    const bodyHtml = formatAiMessageHtml(role, content, { zoomable: false, dark: false })
    const cards = toolCardsHtml(entry.tools)
    if (role === 'evidence') {
      hasEvidence = true
      const expand = evidencePanelToggleLabel(false, responseLanguage)
      const collapse = evidencePanelToggleLabel(true, responseLanguage)
      return (
        `<section class="msg ${cls} ai-ev-panel">`
        + `<h3>${escapeHtml(label)} · `
        + `<button type="button" class="ai-ev-panel-toggle" data-open="0" `
        + `data-expand="${escapeAttr(expand)}" data-collapse="${escapeAttr(collapse)}">`
        + `${escapeHtml(expand)}</button></h3>`
        + `<div class="body">${bodyHtml}${cards}</div>`
        + '</section>'
      )
    }
    const head = `<h3>${escapeHtml(label)}</h3>`
    return (
      `<section class="msg ${cls}">`
      + head
      + `<div class="body">${bodyHtml}${cards}</div>`
      + '</section>'
    )
  }).join('\n')
  if (!hasEvidence) return turns
  return `${turns}\n${AI_EVIDENCE_PANEL_EXPORT_SCRIPT}`
}

/** Standalone HTML transcript (Markdown rendered). Keep in sync with ai_assistant.py. */
export function formatAiConversationHtml(entries, date = new Date(), responseLanguage = DEFAULT_AI_RESPONSE_LANGUAGE) {
  const turns = formatAiConversationHtmlBody(entries, responseLanguage)
  const body = (
    '<section class="report-card">\n'
    + '<h2>Conversation</h2>\n'
    + `${turns}\n`
    + '</section>'
  )
  return btfHtmlReportDocument('AI Conversation', body, {
    subtitle: `Saved ${conversationStamp(date)}`,
    docTitle: 'BTFViewer — AI Conversation',
  })
}

/** Format a chat message; assistant = Markdown preview, user = plain. */
export function formatAiMessageHtml(role, text, { inlineSvg = true, zoomable = true, dark = true } = {}) {
  const body = String(text || '').trim()
  if (role === 'assistant' || role === 'evidence') {
    return markdownToSafeHtml(body, { inlineSvg, zoomable, dark }) || '<p></p>'
  }
  return escapeHtml(body)
    .replace(
      /jump:([0-9]+(?:\.[0-9]+)?)/g,
      (_, n) => `<a href="${btfJumpHref(n)}" class="ai-jump" data-jump="${n}">jump:${n}</a>`,
    )
    .replace(/\n/g, '<br>')
}
