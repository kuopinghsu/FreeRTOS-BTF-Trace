import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  aiFileStamp,
  formatAiConversationHtml,
  formatAiConversationMarkdown,
  formatAiConversationText,
  formatAiMessageHtml,
  markdownToSafeHtml,
} from '../src/utils/aiMarkdown.js'

describe('aiMarkdown', () => {
  it('renders headings, lists, bold, code, and jump links', () => {
    const html = markdownToSafeHtml(
      '## Title\n\n'
      + 'See **bold** and `code`, then jump:42.\n\n'
      + '- item one\n'
      + '- item two\n\n'
      + '```\nraw <tag>\n```\n',
    )
    assert.match(html, /<h2>/)
    assert.match(html, /<strong>bold<\/strong>/)
    assert.match(html, /<code>code<\/code>/)
    assert.match(html, /href="btfjump:time\/42"/)
    assert.match(html, /<ul>/)
    assert.match(html, /&lt;tag&gt;/)
    assert.equal(html.includes('<tag>'), false)
  })

  it('promotes backtick-wrapped jump tokens to links', () => {
    const html = markdownToSafeHtml('關注 `jump:1501325` 附近')
    assert.match(html, /href="btfjump:time\/1501325"/)
    assert.match(html, /class="ai-jump"/)
    assert.equal(html.includes('<code>jump:1501325</code>'), false)
  })

  it('preserves source numbers when ordered lists are interrupted', () => {
    // Same shape as models often emit: 1. title, prose, bullet, then 2./3.
    const html = markdownToSafeHtml(
      '1. **First issue**\n\n'
      + 'Details about thrashing.\n\n'
      + '- **Open:** Migration Heatmap\n\n'
      + '2. **Second issue**\n\n'
      + 'Priority inversion risk.\n\n'
      + '3. **Third issue**\n',
    )
    assert.match(html, /<ol><li><strong>First issue<\/strong><\/li><\/ol>/)
    assert.match(html, /<ol start="2"><li><strong>Second issue<\/strong><\/li><\/ol>/)
    assert.match(html, /<ol start="3"><li><strong>Third issue<\/strong><\/li><\/ol>/)
    assert.match(html, /<ul><li><strong>Open:<\/strong> Migration Heatmap<\/li><\/ul>/)
  })

  it('opens external links in a new tab, keeps jump links in place', () => {
    const html = markdownToSafeHtml('See [docs](https://example.com/a) and [t](btfjump:42).')
    assert.match(html, /<a href="https:\/\/example\.com\/a" target="_blank" rel="noopener noreferrer">/)
    assert.match(html, /<a href="btfjump:42">/)
    assert.equal(/<a href="btfjump:42"[^>]*target=/.test(html), false)
  })

  it('escapes raw HTML', () => {
    const html = markdownToSafeHtml('<script>alert(1)</script>')
    assert.match(html, /&lt;script&gt;/)
    assert.equal(html.includes('<script>'), false)
  })

  it('renders GFM pipe tables as HTML tables', () => {
    const html = markdownToSafeHtml(
      '| Task | CPU% |\n'
      + '| --- | ---: |\n'
      + '| Idle | 40 |\n'
      + '| CS[1] | jump:1000 |\n',
    )
    assert.match(html, /class="ai-md-table"/)
    assert.match(html, /<thead>/)
    assert.match(html, /Idle/)
    assert.match(html, /href="btfjump:time\/1000"/)
    assert.match(html, /align="right"/)
    assert.equal(html.includes('| Task |'), false)
  })

  it('sanitizes HTML tables copied into the reply', () => {
    const html = markdownToSafeHtml(
      '<table><tr><th onclick="x()">A</th></tr>'
      + '<tr><td><script>alert(1)</script>ok</td></tr></table>',
    )
    assert.match(html, /class="ai-md-table"/)
    assert.match(html, />ok</)
    assert.equal(html.includes('<script>'), false)
    assert.equal(html.includes('onclick'), false)
    assert.equal(html.includes('alert(1)'), false)
  })

  it('formats assistant as markdown and user as plain', () => {
    const asst = formatAiMessageHtml('assistant', '**ok**')
    assert.match(asst, /<strong>ok<\/strong>/)
    const user = formatAiMessageHtml('user', '**ok**\nline')
    assert.match(user, /\*\*ok\*\*/)
    assert.match(user, /<br>/)
  })
})

describe('ai conversation export', () => {
  const entries = [
    { role: 'user', content: 'Why is CS[22] late?' },
    { role: 'assistant', content: '## Answer\n\nIt migrates at jump:1805000.' },
  ]
  const when = new Date(2026, 7, 8, 8, 41, 2)

  it('writes markdown with roles and original text', () => {
    const md = formatAiConversationMarkdown(entries, when)
    assert.match(md, /^# BTF Viewer — AI Conversation/)
    assert.match(md, /_Saved 2026-08-08 08:41:02_/)
    assert.match(md, /## Your prompt\n\nWhy is CS\[22\] late\?/)
    assert.match(md, /## AI Assistant\n\n## Answer\n\nIt migrates at jump:1805000\./)
    assert.equal(md.endsWith('\n'), true)
  })

  it('writes plain text without markup', () => {
    const txt = formatAiConversationText(entries, when)
    assert.match(txt, /Your prompt:\nWhy is CS\[22\] late\?/)
    assert.match(txt, /AI Assistant:\n## Answer\n\nIt migrates at jump:1805000\./)
    assert.equal(txt.includes('<'), false)
  })

  it('writes standalone html with rendered markdown', () => {
    const html = formatAiConversationHtml(entries, when)
    assert.match(html, /^<!DOCTYPE html>/)
    assert.match(html, /<title>BTFViewer — AI Conversation<\/title>/)
    assert.match(html, /class="report-head"/)
    assert.match(html, /class="brand-icon"/)
    assert.match(html, /fill="#1C3A6E"/)
    assert.match(html, />BTFViewer</)
    assert.match(html, /<h2>Answer<\/h2>/)
    assert.match(html, /href="btfjump:time\/1805000"/)
    assert.match(html, /<section class="msg user"><h3>Your prompt<\/h3>/)
    assert.match(html, /<section class="msg assistant"><h3>AI Assistant<\/h3>/)
  })

  it('html export keeps mermaid SVG without the chat zoom wrapper', () => {
    const html = formatAiConversationHtml([{
      role: 'assistant',
      content: '```mermaid\ngraph LR\n  C0[Core_0] --> C1[Core_1]\n```',
    }], when)
    assert.match(html, /<svg/)
    assert.doesNotMatch(html, /#mermaid-zoom/)
    assert.doesNotMatch(html, /ai-mermaid-zoom/)
  })

  it('exports tool cards with summarised labels', () => {
    const withTools = [{
      role: 'assistant',
      content: 'Placing cursors.',
      tools: [{
        name: 'set_cursors',
        arguments: { timestamps: [10, 20] },
        status: 'pending',
      }],
    }]
    const md = formatAiConversationMarkdown(withTools, when)
    assert.match(md, /set_cursors|cursors/)
    assert.doesNotMatch(md, /^- ⚡ set_cursors \(pending\)$/m)
    const html = formatAiConversationHtml(withTools, when)
    assert.match(html, /ai-tool-card/)
    assert.match(html, /pending/)
  })

  it('builds a sortable file stamp', () => {
    assert.equal(aiFileStamp(when), '20260808-084102')
  })
})
