import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { markdownToSafeHtml } from '../src/utils/aiMarkdown.js'
import { hitTestMermaid, mermaidBlockHtml, mermaidHitRegions, mermaidLinkTargets, mermaidPalette, mermaidToSvg, wrapNodeLabel, actionableDiagramHighlight } from '../src/utils/aiMermaid.js'
import { AI_MERMAID_MIGRATION_EXAMPLE, AI_MERMAID_SEQUENCE_EXAMPLE } from '../src/utils/aiTools.js'

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
    const both = mermaidToSvg(
      'graph LR\n  C0[Core_0] -->|12| C1[Core_1]\n  C1 -->|3| C0\n',
    )
    const y12 = Number(both.match(/<text x="[-\d.]+" y="([-\d.]+)"[^>]*>12<\/text>/)[1])
    const y3 = Number(both.match(/<text x="[-\d.]+" y="([-\d.]+)"[^>]*>3<\/text>/)[1])
    assert.ok(Math.abs(y12 - y3) > 8)
    assert.ok(y12 > y3)
    const labels = mermaidLinkTargets('graph LR\n  C0[Core_0] -->|12| C1[Core_1]\n')
      .filter(t => t.kind === 'highlight')
      .map(t => t.value)
    assert.ok(labels.includes('Core_0'))
    assert.ok(labels.includes('Core_1'))
    assert.equal(labels.includes('C0'), false)
  })

  it('omits evidence-graph prose from the link row', () => {
    const src = (
      'graph TD\n'
      + '  F[Excessive bouncing / core thrashing]\n'
      + '  C0[Focus task CS20]\n'
      + '  C1[Core migration / thrash]\n'
      + '  H0(Likely affinity / lock bounce)\n'
      + '  F --> C0\n'
      + '  C0 --> C1\n'
      + '  F --> H0\n'
    )
    assert.deepEqual(mermaidLinkTargets(src), [])
    const html = mermaidBlockHtml(src)
    assert.doesNotMatch(html, /ai-mermaid-links/)
    assert.equal(actionableDiagramHighlight('Low[266]'), 'Low[266]')
    assert.equal(actionableDiagramHighlight('Core_0'), 'Core_0')
    assert.equal(actionableDiagramHighlight('F'), null)
  })

  it('renders A -- text --> B edge labels and ignores style lines', () => {
    const src = (
      'graph LR\n'
      + '    Core_X[Core X] -- 595 migrations --> Core_Y[Core Y]\n'
      + '    style CS[20] fill:#f9f,stroke:#333,stroke-width:2px\n'
    )
    const svg = mermaidToSvg(src)
    assert.match(svg, /<svg/)
    assert.match(svg, /Core X/)
    assert.match(svg, /595 migrations/)
    const html = mermaidBlockHtml(src)
    assert.match(html, /ai-mermaid/)
    assert.doesNotMatch(html, /language-mermaid/)
  })

  it('wraps long flowchart node labels inside taller rectangles', () => {
    const label = 'Mutex contention on the shared queue blocks the high priority worker'
    const lines = wrapNodeLabel(label)
    assert.ok(lines.length > 1)
    assert.equal(lines.join(' '), label)
    assert.ok(lines.every(ln => ln.length <= 22))
    const src = `graph TD\n  S0[${label}]\n`
    const svg = mermaidToSvg(src)
    for (const word of ['Mutex', 'contention', 'priority', 'worker']) {
      assert.match(svg, new RegExp(word))
    }
    assert.doesNotMatch(svg, /<tspan/)
    const hs = [...svg.matchAll(/height="([\d.]+)" rx="6"/g)].map(m => Number(m[1]))
    assert.ok(hs.some(h => h > 32), JSON.stringify(hs))
    const hits = mermaidHitRegions(src)
    assert.equal(hits[0].value, label)
    assert.ok(hits[0].h > 32)
  })

  it('markdown turns mermaid fences into SVG', () => {
    const html = markdownToSafeHtml(AI_MERMAID_SEQUENCE_EXAMPLE)
    assert.match(html, /ai-mermaid/)
    assert.match(html, /<svg/)
    assert.match(html, /btfhighlight:task\//)
    assert.doesNotMatch(html, /<a[^>]*class="ai-mermaid-zoom"/)
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

  it('hit-tests sequence participant boxes', () => {
    const src = 'sequenceDiagram\n  participant L as Low[266] (Core 0)\n  L->>H: take\n'
    const hits = mermaidHitRegions(src)
    assert.equal(hits[0].value, 'Low[266] (Core 0)')
    const cx = hits[0].x + hits[0].w / 2
    const cy = hits[0].y + hits[0].h / 2
    assert.deepEqual(hitTestMermaid(src, cx, cy), { kind: 'highlight', value: 'Low[266] (Core 0)' })
    assert.equal(hitTestMermaid(src, 2, 2), null)
  })

  it('avoids SVG markers and keeps boxes inside the viewBox', () => {
    const seqSrc = AI_MERMAID_SEQUENCE_EXAMPLE.replace(/```mermaid/, '').replace(/```/, '').trim()
    const flowSrc = AI_MERMAID_MIGRATION_EXAMPLE.replace(/```mermaid/, '').replace(/```/, '').trim()
    for (const src of [seqSrc, flowSrc]) {
      const svg = mermaidToSvg(src)
      assert.doesNotMatch(svg, /<marker/i)
      assert.doesNotMatch(svg, /marker-end/)
      assert.doesNotMatch(svg, /system-ui/)
      const xs = [...svg.matchAll(/<rect[^>]*\bx="(-?[\d.]+)"/g)].map(m => Number(m[1]))
      assert.ok(xs.length)
      assert.ok(xs.every(x => x >= 0), JSON.stringify(xs))
      for (const hit of mermaidHitRegions(src)) {
        assert.ok(hit.x >= 0)
        assert.ok(hit.y >= 0)
      }
    }
  })

  it('wraps the figure in a zoom control', () => {
    const src = 'sequenceDiagram\n  participant L as Low[266]\n  L->>H: take\n'
    const html = mermaidBlockHtml(src)
    assert.match(html, /class="ai-mermaid-zoom"/)
    assert.match(html, /Open larger view/)
    assert.doesNotMatch(html, /#mermaid-zoom/)
    assert.match(html, /btfhighlight:task\//)
  })

  it('parses hexagon evidence nodes and jump:TIME clicks', () => {
    const src = 'graph TD\n  F[Finding]\n  E0{{preempt Low jump:12345}}\n  F --> E0\n'
    const svg = mermaidToSvg(src)
    assert.match(svg, /preempt Low/)
    assert.match(svg, /btfjump:time\/12345/)
    const hits = mermaidHitRegions(src)
    const ev = hits.find(h => h.kind === 'jump')
    assert.equal(ev.value, '12345')
    const cx = ev.x + ev.w / 2
    const cy = ev.y + ev.h / 2
    assert.deepEqual(hitTestMermaid(src, cx, cy), { kind: 'jump', value: '12345' })
  })

  it('uses light-theme ink for flowchart diagrams', () => {
    const src = 'graph TD\n  F[Finding]\n  E0[evidence]\n  F --> E0\n'
    const dark = mermaidToSvg(src, { dark: true })
    const light = mermaidToSvg(src, { dark: false })
    assert.match(dark, /#12161d/)
    assert.match(light, /#F7F9FC/)
    assert.match(light, /#1E1E1E/)
    assert.doesNotMatch(light, /#12161d/)
    assert.doesNotMatch(light, /#dbe2ea/)
    const html = markdownToSafeHtml('```mermaid\n' + src + '```', { dark: false })
    assert.match(html, /#F7F9FC/)
  })

  it('exposes the same dark and light palette keys as desktop', () => {
    for (const dark of [true, false]) {
      const pal = mermaidPalette(dark)
      assert.equal(pal.nodeText, dark ? '#dbe2ea' : '#1E1E1E')
      assert.equal(pal.bg, dark ? '#12161d' : '#F7F9FC')
      assert.equal(pal.arrow, dark ? '#6fbf9a' : '#166534')
    }
  })
})
