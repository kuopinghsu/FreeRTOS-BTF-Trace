import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, describe, it } from 'node:test'
import {
  PALETTE_COLORBLIND,
  PALETTE_COLORBLIND_DARK,
  setColorblindMode,
  setDarkMode,
  taskColor,
  coreColor,
  stiMarkerShape,
} from '../src/utils/colors.js'

const EXPECTED_LIGHT = [
  '#0072B2', '#E69F00', '#009E73', '#CC79A7',
  '#56B4E9', '#D55E00', '#F0E442', '#000000',
]
const EXPECTED_DARK = [...EXPECTED_LIGHT.slice(0, -1), '#FFFFFF']

// Reset shared module state so other test files never see it enabled.
after(() => { setColorblindMode(false); setDarkMode(true) })

describe('Colorblind-safe (Okabe-Ito) palette', () => {
  it('light palette matches the Okabe-Ito spec (TODO.bak/COLORBLIND.md item 18)', () => {
    assert.deepEqual(PALETTE_COLORBLIND.map(c => c.toUpperCase()), EXPECTED_LIGHT)
  })

  it('dark palette swaps black for white, keeps the other 7 identical', () => {
    assert.deepEqual(PALETTE_COLORBLIND_DARK.map(c => c.toUpperCase()), EXPECTED_DARK)
    assert.deepEqual(PALETTE_COLORBLIND_DARK.slice(0, -1), PALETTE_COLORBLIND.slice(0, -1))
  })

  it('taskColor only uses Okabe-Ito when colorblindSafe is enabled (item 19)', () => {
    setColorblindMode(false)
    const normal = taskColor('Task_Alpha[1]').toUpperCase()
    assert.ok(!PALETTE_COLORBLIND.map(c => c.toUpperCase()).includes(normal))

    setColorblindMode(true)
    setDarkMode(false)
    const light = taskColor('Task_Alpha[1]').toUpperCase()
    assert.ok(PALETTE_COLORBLIND.map(c => c.toUpperCase()).includes(light))

    setDarkMode(true)
    const dark = taskColor('Task_Alpha[1]').toUpperCase()
    assert.ok(PALETTE_COLORBLIND_DARK.map(c => c.toUpperCase()).includes(dark))
    assert.notEqual(dark, '#000000')

    setColorblindMode(false)
    setDarkMode(true)
  })

  it('coreColor switches to Okabe-Ito alongside taskColor', () => {
    setColorblindMode(false)
    const normal = coreColor('Core_0').toUpperCase()
    assert.ok(!PALETTE_COLORBLIND.map(c => c.toUpperCase()).includes(normal))

    setColorblindMode(true)
    setDarkMode(false)
    const colorblind = coreColor('Core_0').toUpperCase()
    assert.ok(PALETTE_COLORBLIND.map(c => c.toUpperCase()).includes(colorblind))

    setColorblindMode(false)
    setDarkMode(true)
  })

  it('take/give mutex markers never rely on the red/green fill alone (item 5/21)', () => {
    assert.equal(stiMarkerShape('take_mutex'), 'take')
    assert.equal(stiMarkerShape('give_mutex'), 'give')
    assert.equal(stiMarkerShape('create_mutex'), 'diamond')
    assert.equal(stiMarkerShape('trigger'), 'diamond')
    assert.equal(stiMarkerShape('some_unknown_note'), 'diamond')
  })

  it('web palette source matches desktop byte-for-byte (item 20 lockstep)', () => {
    const configPy = readFileSync(
      new URL('../../btf_viewer_pkg/config.py', import.meta.url), 'utf8')
    const m = configPy.match(/_PALETTE_COLORBLIND = \[([\s\S]*?)\]/)
    assert.ok(m, '_PALETTE_COLORBLIND not found in config.py')
    const desktopLight = [...m[1].matchAll(/#[0-9A-Fa-f]{6}/g)].map(x => x[0].toUpperCase())
    assert.deepEqual(desktopLight, EXPECTED_LIGHT)
    assert.deepEqual(PALETTE_COLORBLIND.map(c => c.toUpperCase()), desktopLight)
  })

  it('setting label/tooltip describe task/core scope only (item 1/2)', () => {
    const dlgVue = readFileSync(
      new URL('../src/components/SettingsDialog.vue', import.meta.url), 'utf8')
    assert.ok(dlgVue.includes('Colorblind-safe palette (Okabe-Ito)'))
    assert.ok(!dlgVue.includes('Colorblind-safe colors (Okabe-Ito palette)'))
    assert.ok(dlgVue.includes(
      'Important status information also uses text, symbols, or labels'))
  })
})
