import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { markdownToSafeHtml } from '../src/utils/aiMarkdown.js'
import { mermaidBlockHtml, mermaidLinkTargets, mermaidToSvg } from '../src/utils/aiMermaid.js'
import { AI_MERMAID_SEQUENCE_EXAMPLE } from '../src/utils/aiTools.js'

describe('aiMermaid', () => {
  it('renders sequence and flowchart SVG', () => {
    const seq = mermaidToSvg(
      'sequenceDiagram\n  participant L as Low[266]\n  L->>H: take\n',
    )
    assert.match(seq, /<svg/)
    assert.match(seq, /Low\[266\]/)
    const flow = mermaidToSvg('graph LR\n  C0[Core_0] -->|12| C1[Core_1]\n')
    assert.match(flow, /Core_0/)
    assert.match(flow, /12/)
    const labels = mermaidLinkTargets('graph LR\n  C0[Core_0] -->|12| C1[Core_1]\n')
      .filter(t => t.kind === 'highlight')
      .map(t => t.value)
    assert.ok(labels.includes('Core_0'))
    assert.ok(labels.includes('Core_1'))
  })

  it('markdown turns mermaid fences into SVG', () => {
    const html = markdownToSafeHtml(AI_MERMAID_SEQUENCE_EXAMPLE)
    assert.match(html, /ai-mermaid/)
    assert.match(html, /<svg/)
    assert.match(html, /btfhighlight:/)
    assert.match(html, /ai-mermaid-zoom/)
    const exported = markdownToSafeHtml(AI_MERMAID_SEQUENCE_EXAMPLE, { zoomable: false })
    assert.doesNotMatch(exported, /ai-mermaid-zoom/)
    assert.doesNotMatch(exported, /#mermaid-zoom/)
  })

  it('inlineSvg false embeds a data-URI image like desktop chat', () => {
    const src = 'sequenceDiagram\n  participant L as Low[266]\n  L->>H: take\n'
    const html = mermaidBlockHtml(src, { inlineSvg: false })
    assert.match(html, /data:image\/svg\+xml;base64,/)
    assert.match(html, /ai-mermaid-img/)
  })

  it('wraps the figure in a zoom control', () => {
    const src = 'sequenceDiagram\n  participant L as Low[266]\n  L->>H: take\n'
    const html = mermaidBlockHtml(src)
    assert.match(html, /ai-mermaid-zoom/)
    assert.match(html, /Open larger view/)
    assert.match(html, /#mermaid-zoom/)
  })
})
