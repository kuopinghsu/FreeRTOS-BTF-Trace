import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  discoverVoiceLangs,
  mergeVoiceLangs,
  normalizeVoiceLang,
  pickVoiceLang,
  voicePathCandidates,
} from '../src/utils/demoVoice.js'
import { parseDemoXml } from '../src/utils/demoXml.js'
import { packFromFileMap } from '../src/utils/demoPack.js'

describe('demoVoice', () => {
  it('normalizes BCP-47 tags', () => {
    assert.equal(normalizeVoiceLang('en-US'), 'en')
    assert.equal(normalizeVoiceLang('zh_TW'), 'zh-tw')
    assert.equal(normalizeVoiceLang('zh-Hant'), 'zh-tw')
    assert.equal(normalizeVoiceLang('zh-CN'), 'zh')
    assert.equal(normalizeVoiceLang('ja-JP'), 'ja')
    assert.equal(normalizeVoiceLang(''), '')
  })

  it('picks an available language with prefix fallback', () => {
    const ids = ['en', 'zh-tw']
    assert.equal(pickVoiceLang('zh-TW', ids, 'en'), 'zh-tw')
    assert.equal(pickVoiceLang('zh-CN', ids, 'en'), 'zh-tw')
    assert.equal(pickVoiceLang('ja', ids, 'en'), 'en')
    assert.equal(pickVoiceLang('', ids, 'en'), 'en')
  })

  it('orders voice path candidates lang then flat then default', () => {
    assert.deepEqual(
      voicePathCandidates('voice/01_title.mp3', 'zh-TW', 'en'),
      [
        'voice/zh-tw/01_title.mp3',
        'voice/01_title.mp3',
        'voice/en/01_title.mp3',
      ],
    )
    assert.deepEqual(
      voicePathCandidates('pack/voice/zh-tw/01_title.mp3', 'en', 'en'),
      [
        'pack/voice/en/01_title.mp3',
        'pack/voice/01_title.mp3',
        'pack/voice/zh-tw/01_title.mp3',
      ],
    )
    assert.deepEqual(
      voicePathCandidates('clips/beep.wav', 'zh-tw', 'en'),
      ['clips/beep.wav'],
    )
  })

  it('discovers nested voice langs and merges XML labels', () => {
    const files = new Map([
      ['voice/01_title.mp3', {}],
      ['voice/zh-tw/01_title.mp3', {}],
      ['voice/ja/01_title.mp3', {}],
    ])
    const found = discoverVoiceLangs(files)
    assert.ok(found.includes('en'))
    assert.ok(found.includes('zh-tw'))
    assert.ok(found.includes('ja'))
    const merged = mergeVoiceLangs(
      { defaultId: 'en', list: [{ id: 'en', label: 'English' }, { id: 'zh-tw', label: '中文' }] },
      found,
    )
    assert.equal(merged.defaultId, 'en')
    assert.deepEqual(merged.list.map(l => l.id), ['en', 'zh-tw', 'ja'])
    assert.equal(merged.list.find(l => l.id === 'ja').label, '日本語')
  })

  it('resolves zh-tw clips before the English fallback', async () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<demo name="sample">
  <meta>
    <title>Sample</title>
    <trace>\${XML_DIR}/demo.btf.gz</trace>
    <languages default="en">
      <language id="en" label="English"/>
      <language id="zh-tw" label="中文"/>
    </languages>
  </meta>
  <steps>
    <step id="1" title="Open">
      <audio file="\${XML_DIR}/voice/01.mp3"/>
    </step>
  </steps>
</demo>
`
    const en = new File([new Uint8Array([1])], '01.mp3')
    const zh = new File([new Uint8Array([2])], '01.mp3')
    const pack = await packFromFileMap(new Map([
      ['demo.xml', new File([xml], 'demo.xml')],
      ['demo.btf.gz', new File([new Uint8Array([1])], 'demo.btf.gz')],
      ['voice/01.mp3', en],
      ['voice/zh-tw/01.mp3', zh],
    ]))
    assert.equal(pack.parsed.languages.defaultId, 'en')
    assert.deepEqual(pack.parsed.languages.list.map(l => l.id), ['en', 'zh-tw'])
    let file = null
    for (const cand of voicePathCandidates(pack.parsed.vars.XML_DIR + '/voice/01.mp3', 'zh-tw', 'en')) {
      file = pack.resolve(cand)
      if (file) break
    }
    assert.equal(file, zh)
    file = null
    for (const cand of voicePathCandidates('voice/01.mp3', 'en', 'en')) {
      file = pack.resolve(cand)
      if (file) break
    }
    assert.equal(file, en)
    assert.ok(parseDemoXml(xml).languages.list.some(l => l.id === 'zh-tw'))
  })
})

describe('demo_8cores voice pack parity', () => {
  const textRoot = fileURLToPath(new URL('../../demos/demo_8cores/text', import.meta.url))
  const xmlPath = fileURLToPath(new URL('../../demos/demo_8cores/demo_8cores.xml', import.meta.url))

  it('keeps the same script stems in en, zh-tw, and ja', () => {
    const en = readdirSync(`${textRoot}/en`).filter(n => n.endsWith('.txt')).sort()
    for (const lang of ['en', 'zh-tw', 'ja']) {
      const names = readdirSync(`${textRoot}/${lang}`).filter(n => n.endsWith('.txt')).sort()
      assert.deepEqual(names, en, lang)
      const man = JSON.parse(readFileSync(`${textRoot}/${lang}/voice.json`, 'utf8'))
      assert.equal(man.schema, 'btf-demo-voice')
      assert.equal(man.id, lang)
    }
    const xml = readFileSync(xmlPath, 'utf8')
    const demo = parseDemoXml(xml)
    assert.deepEqual(demo.languages.list.map(l => l.id), ['en', 'zh-tw', 'ja'])
  })
})
