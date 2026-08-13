import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  buildVariables,
  demoTimeToTraceUnits,
  expandVars,
  parseDemoXml,
  parseXmlRoot,
  resolveDemoXy,
  splitCsv,
  stripXmlComments,
  truthy,
} from '../src/utils/demoXml.js'
import { createDemoRunner, shouldSkipStep } from '../src/utils/demoRunner.js'
import { classifyOpenFiles, classifyPickedOpen, normalizePackPath, packFromFileMap } from '../src/utils/demoPack.js'

const SAMPLE = `<?xml version="1.0" encoding="UTF-8"?>
<!-- comment: no double-hyphen inside -->
<demo name="sample" version="1">
  <meta>
    <title>Sample demo</title>
    <trace>\${XML_DIR}/demo.btf.gz</trace>
  </meta>
  <defaults after_voice="1.5" pause="0.8" ai_wait="35" audio_block="false"/>
  <targets>
    <point name="timeline" x="0.42" y="0.42"/>
  </targets>
  <macros>
    <macro name="fit">
      <hotkey keys="mod+0"/>
    </macro>
    <macro name="settings">
      <hotkey keys="mod+,"/>
    </macro>
  </macros>
  <steps>
    <step id="1" title="Open" tags="intro">
      <audio file="\${XML_DIR}/voice/01.mp3"/>
      <macro ref="fit"/>
      <view_mode mode="core"/>
      <cpu_load on="true"/>
      <panel name="stats"/>
      <move target="timeline" duration="0"/>
    </step>
    <step id="2" title="WCET" tags="ladder">
      <stats_section id="tasks,exec" expand="true" collapse_others="true" scroll="exec"/>
      <highlight task="CS[27]"/>
      <jump_wcet task="CS[27]"/>
      <cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>
      <wait seconds="0.5"/>
      <stats_reset/>
    </step>
    <step id="3" title="AI" tags="ai" optional="true">
      <confirm prompt="Click template"/>
      <wait ai="true" why="model reply"/>
    </step>
  </steps>
</demo>
`

describe('demoXml', () => {
  it('strips comments and expands nested vars', () => {
    assert.equal(stripXmlComments('a<!-- x -->b'), 'ab')
    const vars = { XML_DIR: '/pack', voice: '${XML_DIR}/voice' }
    assert.equal(expandVars('${voice}/01.mp3', vars), '/pack/voice/01.mp3')
  })

  it('parses sample demo XML', () => {
    const demo = parseDemoXml(SAMPLE, { xmlDir: '/pack' })
    assert.equal(demo.name, 'sample')
    assert.equal(demo.title, 'Sample demo')
    assert.equal(demo.trace, '/pack/demo.btf.gz')
    assert.equal(demo.defaults.pause, 0.8)
    assert.equal(demo.defaults.audio_block, false)
    assert.deepEqual(demo.targets.timeline, { x: 0.42, y: 0.42 })
    assert.ok(demo.macros.fit)
    assert.equal(demo.steps.length, 3)
    assert.equal(demo.steps[1].title, 'WCET')
    assert.ok(demo.steps[2].tags.has('ai'))
    assert.equal(demo.steps[2].optional, true)
    const section = demo.steps[1].children.find(c => c.tag === 'stats_section')
    assert.equal(section.attrib.scroll, 'exec')
    assert.deepEqual(splitCsv(section.attrib.id), ['tasks', 'exec'])
  })

  it('resolves named targets like desktop resolve_xy', () => {
    const box = { left: 10, top: 20, width: 1000, height: 500 }
    const targets = { timeline: { x: 0.42, y: 0.42 } }
    assert.deepEqual(
      resolveDemoXy({ attrib: { target: 'timeline' } }, targets, box),
      { x: 430, y: 230 },
    )
    assert.deepEqual(
      resolveDemoXy({ attrib: { x: '0.5', y: '0.25' } }, {}, box),
      { x: 510, y: 145 },
    )
    assert.equal(resolveDemoXy({ attrib: { target: 'missing' } }, targets, box), null)
  })

  it('converts demo times to trace units', () => {
    assert.equal(demoTimeToTraceUnits('3.085', 's', 'us'), 3085000)
    assert.equal(demoTimeToTraceUnits('3.085 s', '', 'us'), 3085000)
    assert.equal(demoTimeToTraceUnits('1000', '', 'us'), 1000)
    assert.equal(demoTimeToTraceUnits('1', 'ms', 'us'), 1000)
  })

  it('truthy matches desktop flags', () => {
    assert.equal(truthy('true', false), true)
    assert.equal(truthy('0', true), false)
    assert.equal(truthy(undefined, true), true)
  })
})

describe('demoPack', () => {
  it('classifies xml packs vs btf files', () => {
    assert.equal(classifyOpenFiles(new Map([['demo.xml', {}]])), 'demo')
    assert.equal(classifyOpenFiles(new Map([['a.btf.gz', {}]])), 'btf')
    assert.equal(classifyOpenFiles(new Map([['demo.xml', {}], ['a.btf.gz', {}]])), 'demo')
    assert.equal(classifyOpenFiles(new Map([['notes.txt', {}]])), 'unknown')
  })

  it('asks for the pack folder when only the xml is opened', async () => {
    const xml = new File([SAMPLE], 'demo.xml', { type: 'text/xml' })
    const result = await classifyPickedOpen(new Map([['demo.xml', xml]]))
    assert.equal(result.kind, 'demo-folder')
    assert.equal(result.xmlName, 'demo.xml')
  })

  it('starts a demo when xml and btf are opened together', async () => {
    const xml = new File([SAMPLE], 'demo.xml', { type: 'text/xml' })
    const btf = new File([new Uint8Array([1])], 'demo.btf.gz')
    const result = await classifyPickedOpen(new Map([
      ['demo.xml', xml],
      ['demo.btf.gz', btf],
    ]))
    assert.equal(result.kind, 'demo')
    assert.equal(result.pack.traceFile, btf)
  })

  it('normalizes relative paths', () => {
    assert.equal(normalizePackPath('./voice/01.mp3'), 'voice/01.mp3')
    assert.equal(normalizePackPath('a\\\\b'), 'a/b')
  })

  it('picks the xml next to a btf and resolves ${XML_DIR}', async () => {
    const xml = new File([SAMPLE], 'demo_8cores.xml', { type: 'text/xml' })
    const btf = new File([new Uint8Array([1, 2, 3])], 'demo.btf.gz')
    const mp3 = new File([new Uint8Array([0])], '01.mp3', { type: 'audio/mpeg' })
    const files = new Map([
      ['demo_8cores/demo_8cores.xml', xml],
      ['demo_8cores/demo.btf.gz', btf],
      ['demo_8cores/voice/01.mp3', mp3],
    ])
    const pack = await packFromFileMap(files)
    assert.equal(pack.xmlRel, 'demo_8cores/demo_8cores.xml')
    assert.equal(pack.parsed.trace, 'demo_8cores/demo.btf.gz')
    assert.equal(pack.traceFile, btf)
    assert.equal(pack.resolve('demo_8cores/voice/01.mp3'), mp3)
  })
})

describe('demoRunner', () => {
  it('skips optional and tagged steps', () => {
    const ai = { optional: true, tags: new Set(['ai']) }
    assert.equal(shouldSkipStep(ai, { skipOptional: true }), true)
    assert.equal(shouldSkipStep(ai, { skipTags: ['ai'] }), true)
    assert.equal(shouldSkipStep(ai, {}), false)
  })

  it('drives host ops including pointer moves', async () => {
    const parsed = parseDemoXml(SAMPLE, { xmlDir: '.' })
    parsed.defaults.pause = 0
    for (const step of parsed.steps) {
      for (const child of step.children) {
        if (child.tag === 'wait') child.attrib.seconds = '0'
      }
    }
    const calls = []
    const host = {
      loadTraceFile: async (f) => { calls.push(['load', f.name]) },
      fit: async () => { calls.push(['fit']) },
      setViewMode: async (m) => { calls.push(['view', m]) },
      setCpuLoad: async (on) => { calls.push(['loadStrip', on]) },
      setPanel: async (n) => { calls.push(['panel', n]) },
      statsSection: async (p) => { calls.push(['stats', p.id, p.scroll]) },
      highlight: async (t) => { calls.push(['hl', t]) },
      jumpWcet: async (t) => { calls.push(['wcet', t]) },
      setCursors: async (p) => { calls.push(['cursors', p.times, p.unit, p.limit, p.zoom]) },
      statsReset: async () => { calls.push(['reset']) },
      pointerBox: () => ({ left: 0, top: 0, width: 1000, height: 500 }),
      movePointer: async (p) => { calls.push(['move', Math.round(p.x), Math.round(p.y)]) },
      toast: () => {},
      setStatus: () => {},
    }
    const xml = new File([SAMPLE], 'demo.xml')
    const btf = new File([new Uint8Array([1])], 'demo.btf.gz')
    const pack = {
      parsed,
      traceFile: btf,
      resolve: () => null,
    }
    const runner = createDemoRunner(host, pack, { skipTags: ['ai'], aiWaitCapSec: 0 })
    await runner.run()
    assert.deepEqual(calls[0], ['load', 'demo.btf.gz'])
    assert.ok(calls.some(c => c[0] === 'fit'))
    assert.ok(calls.some(c => c[0] === 'view' && c[1] === 'core'))
    assert.ok(calls.some(c => c[0] === 'stats' && c[1] === 'tasks,exec' && c[2] === 'exec'))
    assert.ok(calls.some(c => c[0] === 'cursors' && c[4] === true))
    assert.ok(calls.some(c => c[0] === 'move' && c[1] === 420 && c[2] === 210))
    assert.ok(!calls.some(c => c[0] === 'toast'))
    assert.equal(xml.name, 'demo.xml')
  })

  it('clears cursors, bookmarks, and annotations via demo API tags', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {
        clear_bookmarks: [{ tag: 'hotkey', attrib: { keys: 'shift+b' }, children: [], text: '', tail: '' }],
      },
      targets: {},
      steps: [
        {
          id: '1', title: 'Title', optional: false, tags: new Set(),
          children: [
            { tag: 'clear_cursors', attrib: {}, children: [], text: '', tail: '' },
            { tag: 'clear_bookmarks', attrib: {}, children: [], text: '', tail: '' },
            { tag: 'clear_annotations', attrib: {}, children: [], text: '', tail: '' },
            { tag: 'macro', attrib: { ref: 'clear_bookmarks' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const host = {
      clearCursors: async () => { calls.push('cursors') },
      clearBookmarks: async () => { calls.push('bookmarks') },
      clearAnnotations: async () => { calls.push('annotations') },
      setStatus: () => {},
      setDemoNav: () => {},
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    await runner.run()
    assert.deepEqual(calls, ['cursors', 'bookmarks', 'annotations', 'bookmarks'])
  })

  it('does not advance to the next section without skipNext', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '0.12' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
        {
          id: '2', title: 'Second', optional: false, tags: new Set(),
          children: [
            { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const host = {
      highlight: async (t) => { calls.push(t) },
      setStatus: () => {},
      setDemoNav: () => {},
    }
    const t0 = Date.now()
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    await runner.run()
    assert.deepEqual(calls, ['A', 'B'])
    assert.ok(Date.now() - t0 >= 100)
  })

  it('skipNext aborts the current section and starts the next', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '2' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
        {
          id: '2', title: 'Second', optional: false, tags: new Set(),
          children: [
            { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const nav = []
    const host = {
      highlight: async (t) => { calls.push(t) },
      setStatus: () => {},
      setDemoNav: (n) => { if (n) nav.push(n.index) },
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    const done = runner.run()
    await new Promise(r => setTimeout(r, 40))
    runner.skipNext()
    await done
    assert.deepEqual(calls, ['B'])
    assert.ok(nav.includes(0))
    assert.ok(nav.includes(1))
  })

  it('skipNext during wait_audio advances without waiting for ended', async () => {
    class FakeAudio {
      constructor() {
        this._listeners = { error: [], ended: [] }
        FakeAudio.instances.push(this)
      }
      addEventListener(ev, fn) { (this._listeners[ev] || []).push(fn) }
      removeEventListener() {}
      play() { return Promise.resolve() }
      pause() {}
      load() {}
      removeAttribute() {}
      set src(v) { this._src = v }
    }
    FakeAudio.instances = []
    const prevAudio = globalThis.Audio
    const prevCreate = URL.createObjectURL
    const prevRevoke = URL.revokeObjectURL
    globalThis.Audio = FakeAudio
    URL.createObjectURL = () => 'blob:fake'
    URL.revokeObjectURL = () => {}
    try {
      const parsed = {
        vars: {},
        defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
        macros: {},
        targets: {},
        steps: [
          {
            id: '1', title: 'First', optional: false, tags: new Set(),
            children: [
              { tag: 'audio', attrib: { file: 'a.mp3' }, children: [], text: '', tail: '' },
              { tag: 'wait_audio', attrib: {}, children: [], text: '', tail: '' },
              { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
            ],
          },
          {
            id: '2', title: 'Second', optional: false, tags: new Set(),
            children: [
              { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
            ],
          },
        ],
      }
      const calls = []
      const host = {
        highlight: async (t) => { calls.push(t) },
        setStatus: () => {},
        setDemoNav: () => {},
      }
      const blob = new File([new Uint8Array([1])], 'a.mp3')
      const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => blob })
      const done = runner.run()
      await new Promise(r => setTimeout(r, 30))
      runner.skipNext()
      await Promise.race([
        done,
        new Promise((_, rej) => setTimeout(() => rej(new Error('skipNext hung on wait_audio')), 800)),
      ])
      assert.deepEqual(calls, ['B'])
    } finally {
      globalThis.Audio = prevAudio
      URL.createObjectURL = prevCreate
      URL.revokeObjectURL = prevRevoke
    }
  })

  it('stale audio error after skipNext does not end the next section', async () => {
    class FakeAudio {
      constructor() {
        this._listeners = { error: [], ended: [] }
        FakeAudio.instances.push(this)
      }
      addEventListener(ev, fn) { (this._listeners[ev] || []).push(fn) }
      removeEventListener(ev, fn) {
        const list = this._listeners[ev]
        if (list) this._listeners[ev] = list.filter(f => f !== fn)
      }
      play() { return Promise.resolve() }
      pause() {}
      load() {}
      removeAttribute() {}
      set src(v) { this._src = v }
      fire(ev) { for (const fn of this._listeners[ev] || []) fn() }
    }
    FakeAudio.instances = []
    const prevAudio = globalThis.Audio
    const prevCreate = URL.createObjectURL
    const prevRevoke = URL.revokeObjectURL
    globalThis.Audio = FakeAudio
    URL.createObjectURL = () => 'blob:fake'
    URL.revokeObjectURL = () => {}
    try {
      const parsed = {
        vars: {},
        defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
        macros: {},
        targets: {},
        steps: [
          {
            id: '1', title: 'First', optional: false, tags: new Set(),
            children: [
              { tag: 'audio', attrib: { file: 'a.mp3' }, children: [], text: '', tail: '' },
              { tag: 'wait', attrib: { seconds: '2' }, children: [], text: '', tail: '' },
            ],
          },
          {
            id: '2', title: 'Second', optional: false, tags: new Set(),
            children: [
              { tag: 'audio', attrib: { file: 'b.mp3' }, children: [], text: '', tail: '' },
              { tag: 'wait', attrib: { seconds: '0.12' }, children: [], text: '', tail: '' },
              { tag: 'wait_audio', attrib: {}, children: [], text: '', tail: '' },
              { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
            ],
          },
        ],
      }
      const calls = []
      const host = {
        highlight: async (t) => { calls.push(t) },
        setStatus: () => {},
        setDemoNav: () => {},
      }
      const blob = new File([new Uint8Array([1])], 'a.mp3')
      const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => blob })
      const done = runner.run()
      await new Promise(r => setTimeout(r, 30))
      runner.skipNext()
      await new Promise(r => setTimeout(r, 20))
      FakeAudio.instances[0]?.fire('error')
      await new Promise(r => setTimeout(r, 180))
      assert.deepEqual(calls, [])
      FakeAudio.instances[1]?.fire('ended')
      await done
      assert.deepEqual(calls, ['B'])
    } finally {
      globalThis.Audio = prevAudio
      URL.createObjectURL = prevCreate
      URL.revokeObjectURL = prevRevoke
    }
  })

  it('skipPrev restarts the previous section', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '2' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
        {
          id: '2', title: 'Second', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '2' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const nav = []
    const host = {
      highlight: async () => {},
      setStatus: () => {},
      setDemoNav: (n) => { if (n) nav.push(n.index) },
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    const done = runner.run()
    await new Promise(r => setTimeout(r, 30))
    runner.skipNext()
    await new Promise(r => setTimeout(r, 30))
    runner.skipPrev()
    await new Promise(r => setTimeout(r, 30))
    runner.abort()
    await done
    assert.equal(nav[0], 0)
    assert.ok(nav.includes(1))
    assert.equal(nav[nav.length - 1], 0)
  })

  it('pause holds a wait until resume', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '0.12' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const pausedFlags = []
    const host = {
      highlight: async (t) => { calls.push(t) },
      setStatus: () => {},
      setDemoNav: () => {},
      setDemoPaused: (on) => { pausedFlags.push(!!on) },
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    const done = runner.run()
    await new Promise(r => setTimeout(r, 30))
    runner.pause()
    await new Promise(r => setTimeout(r, 200))
    assert.deepEqual(calls, [])
    assert.equal(runner.paused, true)
    runner.resume()
    await done
    assert.deepEqual(calls, ['A'])
    assert.equal(runner.paused, false)
    assert.ok(pausedFlags.includes(true))
    assert.equal(pausedFlags[pausedFlags.length - 1], false)
  })

  it('skipNext while paused still advances', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'wait', attrib: { seconds: '2' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
        {
          id: '2', title: 'Second', optional: false, tags: new Set(),
          children: [
            { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const host = {
      highlight: async (t) => { calls.push(t) },
      setStatus: () => {},
      setDemoNav: () => {},
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    const done = runner.run()
    await new Promise(r => setTimeout(r, 30))
    runner.pause()
    runner.skipNext()
    await Promise.race([
      done,
      new Promise((_, rej) => setTimeout(() => rej(new Error('skipNext while paused hung')), 800)),
    ])
    assert.deepEqual(calls, ['B'])
    assert.equal(runner.paused, false)
  })

  it('opens AI settings then closes them', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '18', title: 'AI setup', optional: false, tags: new Set(),
          children: [
            { tag: 'settings', attrib: { page: 'AI' }, children: [], text: '', tail: '' },
            { tag: 'settings', attrib: { close: 'true' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const host = {
      openSettings: async (spec) => { calls.push(['open', spec]) },
      closeSettings: async () => { calls.push(['close']) },
      setStatus: () => {},
      setDemoNav: () => {},
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    await runner.run()
    assert.deepEqual(calls, [
      ['open', { page: 'AI', close: false }],
      ['close'],
    ])
  })

  it('falls back to pressEscape when closeSettings is missing', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'AI setup', optional: false, tags: new Set(),
          children: [
            { tag: 'settings', attrib: { close: 'true' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const host = {
      pressEscape: async () => { calls.push('esc') },
      setStatus: () => {},
      setDemoNav: () => {},
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null })
    await runner.run()
    assert.deepEqual(calls, ['esc'])
  })

  it('setVoiceLang restarts the current section instead of skipping ahead', async () => {
    const parsed = {
      vars: {},
      defaults: { pause: 0, after_voice: 0, ai_wait: 0, move_duration: 0, audio_block: false },
      languages: {
        defaultId: 'en',
        list: [
          { id: 'en', label: 'English' },
          { id: 'zh-tw', label: '中文' },
        ],
      },
      macros: {},
      targets: {},
      steps: [
        {
          id: '1', title: 'First', optional: false, tags: new Set(),
          children: [
            { tag: 'highlight', attrib: { task: 'START' }, children: [], text: '', tail: '' },
            { tag: 'wait', attrib: { seconds: '0.08' }, children: [], text: '', tail: '' },
            { tag: 'highlight', attrib: { task: 'A' }, children: [], text: '', tail: '' },
          ],
        },
        {
          id: '2', title: 'Second', optional: false, tags: new Set(),
          children: [
            { tag: 'highlight', attrib: { task: 'B' }, children: [], text: '', tail: '' },
          ],
        },
      ],
    }
    const calls = []
    const langs = []
    const host = {
      highlight: async (t) => { calls.push(t) },
      setStatus: () => {},
      setDemoNav: () => {},
      setDemoVoiceLang: (id) => { langs.push(id) },
    }
    const runner = createDemoRunner(host, { parsed, traceFile: null, resolve: () => null }, {
      voiceLang: 'en',
    })
    const done = runner.run()
    await new Promise(r => setTimeout(r, 20))
    assert.deepEqual(calls, ['START'])
    assert.equal(runner.voiceLang, 'en')
    runner.setVoiceLang('zh-TW')
    await Promise.race([
      done,
      new Promise((_, rej) => setTimeout(() => rej(new Error('setVoiceLang restart hung')), 800)),
    ])
    assert.equal(runner.voiceLang, 'zh-tw')
    assert.deepEqual(langs, ['zh-tw'])
    assert.deepEqual(calls, ['START', 'START', 'A', 'B'])
  })
})

describe('demo_8cores.xml', () => {
  it('parses the shipped 8-core pack', () => {
    const path = fileURLToPath(new URL('../../demos/demo_8cores/demo_8cores.xml', import.meta.url))
    const xml = readFileSync(path, 'utf8')
    const root = parseXmlRoot(xml)
    assert.equal(root.tag, 'demo')
    const demo = parseDemoXml(xml, { xmlDir: '/demos/demo_8cores' })
    assert.match(demo.trace, /demo_8cores\.btf\.gz$/)
    assert.deepEqual(demo.targets.timeline, { x: 0.42, y: 0.42 })
    assert.ok(demo.steps.length >= 20)
    const title = demo.steps.find(s => s.id === '1')
    const titleTags = title.children.map(c => c.tag)
    assert.ok(titleTags.includes('clear_cursors'))
    assert.ok(titleTags.includes('clear_bookmarks'))
    assert.ok(titleTags.includes('clear_annotations'))
    assert.ok(titleTags.indexOf('clear_cursors') < titleTags.indexOf('audio'))
    assert.ok(titleTags.indexOf('clear_bookmarks') < titleTags.indexOf('audio'))
    assert.ok(titleTags.indexOf('clear_annotations') < titleTags.indexOf('audio'))
    for (const step of demo.steps) {
      let lastPlace = -1
      let lastClear = -1
      step.children.forEach((c, i) => {
        if (c.tag === 'cursors' || (c.tag === 'macro' && c.attrib.ref === 'place_cursor')) {
          lastPlace = i
        }
        if (c.tag === 'clear_cursors') lastClear = i
      })
      if (lastPlace < 0) continue
      assert.ok(
        lastClear > lastPlace,
        `step ${step.id} places cursors but does not clear them afterwards`,
      )
    }
    const toolbar = demo.steps.find(s => s.id === '4')
    assert.ok(toolbar.children.some(c => c.tag === 'view_mode'))
    const wcet = demo.steps.find(s => s.id === '11')
    const section = wcet.children.find(c => c.tag === 'stats_section')
    assert.equal(section.attrib.scroll, 'exec')
    const aiSetup = demo.steps.find(s => s.id === '18')
    assert.equal(aiSetup.title, 'AI setup')
    const settings = aiSetup.children.filter(c => c.tag === 'settings')
    assert.equal(settings[0].attrib.page, 'AI')
    assert.equal(settings[1].attrib.close, 'true')
    const vars = buildVariables(root, { xmlDir: '/demos/demo_8cores' })
    assert.equal(expandVars('${XML_DIR}/voice/01_title.mp3', vars), '/demos/demo_8cores/voice/01_title.mp3')
    assert.equal(vars.languages, undefined)
    assert.equal(demo.languages.defaultId, 'en')
    assert.deepEqual(
      demo.languages.list.map(l => l.id),
      ['en', 'zh-tw', 'ja'],
    )
  })
})
