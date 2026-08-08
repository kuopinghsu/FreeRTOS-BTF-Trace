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
    assert.match(html, /href="btfjump:42"/)
    assert.match(html, /<ul>/)
    assert.match(html, /&lt;tag&gt;/)
    assert.equal(html.includes('<tag>'), false)
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
    assert.match(md, /## You\n\nWhy is CS\[22\] late\?/)
    assert.match(md, /## Assistant\n\n## Answer/)
    assert.equal(md.endsWith('\n'), true)
  })

  it('writes plain text without markup', () => {
    const txt = formatAiConversationText(entries, when)
    assert.match(txt, /You:\nWhy is CS\[22\] late\?/)
    assert.match(txt, /Assistant:\n## Answer/)
    assert.equal(txt.includes('<'), false)
  })

  it('writes standalone html with rendered markdown', () => {
    const html = formatAiConversationHtml(entries, when)
    assert.match(html, /^<!DOCTYPE html>/)
    assert.match(html, /<h2>Answer<\/h2>/)
    assert.match(html, /href="btfjump:1805000"/)
  })

  it('builds a sortable file stamp', () => {
    assert.equal(aiFileStamp(when), '20260808-084102')
  })
})
