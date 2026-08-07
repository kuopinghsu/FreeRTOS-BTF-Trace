import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { formatAiMessageHtml, markdownToSafeHtml } from '../src/utils/aiMarkdown.js'

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
