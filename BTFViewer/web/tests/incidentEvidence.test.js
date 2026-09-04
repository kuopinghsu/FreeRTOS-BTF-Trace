import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { mergeIncidentOverlayTimes } from '../src/utils/incidentOverlay.js'
import { buildEvidencePackZip } from '../src/utils/evidencePack.js'

describe('incidentOverlay', () => {
  it('merges findings then anomaly starts without duplicates', () => {
    const times = mergeIncidentOverlayTimes(
      [{ start: 100 }, { jump_ns: 100 }, { start: 200 }],
      [50, 100],
      { includeAnomalies: true, limit: 10 },
    )
    assert.deepEqual(times, [50, 100, 200])
  })

  it('can skip anomalies', () => {
    const times = mergeIncidentOverlayTimes(
      [{ start: 200 }],
      [50],
      { includeAnomalies: false },
    )
    assert.deepEqual(times, [50])
  })
})

describe('evidencePack', () => {
  it('builds a zip blob with findings and session', () => {
    const { filename, blob } = buildEvidencePackZip({
      baseName: 'demo',
      findingsText: 'Analysis Findings\n',
      sessionJson: '{"v":1}',
    })
    assert.match(filename, /^demo-evidence-.*\.zip$/)
    assert.ok(blob.size > 20)
  })
})
