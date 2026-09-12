/** Raw comparison evidence shared by the dialog, HTML, and CSV renderers.
 * New timing/relative deltas are B − A; migration count delta remains A − B.
 */
export const COMPARE_EVIDENCE = [
  { key: 'task_presence', title: 'New / Missing Tasks', page: 'summary', columns: ['Task', 'Present in A', 'Present in B', 'CPU A', 'CPU B', 'Runs A', 'Runs B', 'Notes'] },
  { key: 'relative_changes', title: 'Largest Relative Changes', page: 'summary', columns: ['Metric / Task', 'Baseline A', 'Candidate B', 'Absolute Δ', 'Relative Δ %', 'Direction'] },
  { key: 'core_distribution', title: 'Core Distribution Change', page: 'migrations', columns: ['Task', 'Cores A', 'Cores B', 'Primary A', 'Primary B', 'Distribution Δ'] },
  { key: 'migration_concentration', title: 'Migration Concentration', page: 'migrations', columns: ['Task', 'Migr A', 'Migr B', 'Share A %', 'Share B %', 'Share Δ'] },
  { key: 'timing_change_candidates', title: 'Timing Change Candidates', page: 'response', columns: ['Task', 'Execution Max Δ', 'Blocking Max Δ', 'Response P99 Δ', 'Migration Δ', 'Reason to inspect'] },
  { key: 'trace_comparability', title: 'Trace Quality / Comparability', page: 'summary', columns: ['Item', 'Baseline A', 'Candidate B', 'Difference', 'Compare Risk'] },
]
const compareNames = (a, b) => a < b ? -1 : a > b ? 1 : 0

export function describeCoreDistribution(a, b) {
  const ca = a.cores || [], cb = b.cores || []
  if (ca.length === cb.length && ca.every(c => cb.includes(c))) return a.primary === b.primary ? 'Stable' : 'Primary changed'
  if (ca.every(c => cb.includes(c))) return 'Expanded'
  if (cb.every(c => ca.includes(c))) return 'Reduced'
  return 'Core set changed'
}
export function buildComparisonEvidence(a, b, metadata) {
  const names = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()
  const empty = { cpu: 0, runs: 0, cores: [], primary: null, migrations: 0, execution: 0, blocking: 0, response: 0 }
  const out = Object.fromEntries(COMPARE_EVIDENCE.map(s => [s.key, []]))
  const totalA = Object.values(a).reduce((n, r) => n + r.migrations, 0)
  const totalB = Object.values(b).reduce((n, r) => n + r.migrations, 0)
  for (const name of names) {
    const x = a[name] || empty, y = b[name] || empty
    if (!a[name] || !b[name]) out.task_presence.push([name, !!a[name], !!b[name], x.cpu, y.cpu, x.runs, y.runs, a[name] ? 'Missing in Candidate' : 'New in Candidate'])
    out.core_distribution.push([name, x.cores, y.cores, x.primary, y.primary, describeCoreDistribution(x, y)])
    const sa = totalA ? x.migrations / totalA * 100 : 0, sb = totalB ? y.migrations / totalB * 100 : 0
    if (x.migrations || y.migrations) out.migration_concentration.push([name, x.migrations, y.migrations, sa, sb, sb - sa])
    const reasons = [], deltas = []
    for (const [key, label] of [['execution', 'Execution Max'], ['blocking', 'Blocking Max'], ['response', 'Response P99'], ['migrations', 'Migrations']]) {
      const av = x[key], bv = y[key], d = bv - av
      deltas.push(key === 'migrations' ? -d : d)
      if (d) reasons.push(key === 'execution' ? `Execution max ${d > 0 ? 'increased' : 'decreased'}` : key === 'migrations' ? 'Migration activity changed' : `${label} changed`)
      if (d) out.relative_changes.push([`${label} / ${name}`, av, bv, d, av === 0 ? null : d / av * 100, d > 0 ? 'Increased' : 'Decreased'])
    }
    if (reasons.length) out.timing_change_candidates.push([name, ...deltas, reasons.length > 1 ? 'Multiple timing metrics changed' : reasons[0]])
  }
  out.relative_changes.sort((x, y) => Math.abs(y[4] ?? Infinity) - Math.abs(x[4] ?? Infinity) || compareNames(x[0], y[0]))
  out.migration_concentration.sort((x, y) => Math.max(y[3], y[4]) - Math.max(x[3], x[4]) || compareNames(x[0], y[0]))
  out.timing_change_candidates.sort((x, y) => Math.max(...y.slice(1, 4).map(Math.abs)) - Math.max(...x.slice(1, 4).map(Math.abs)) || Math.abs(y[4]) - Math.abs(x[4]) || compareNames(x[0], y[0]))
  out.trace_comparability = metadata.map(([item, av, bv]) => [item, av, bv, av === bv ? 'Same' : 'Different', av === bv ? 'No structural difference' : 'Review difference; workload equivalence unknown'])
  return out
}
export function formatEvidenceCell(key, value, column) {
  if (value == null) return key === 'relative_changes' && column === 4 ? 'new' : '—'
  if (Array.isArray(value)) return value.join(', ') || '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    const percent = (key === 'task_presence' && [3, 4].includes(column)) || (key === 'relative_changes' && column === 4) || (key === 'migration_concentration' && column >= 3)
    return percent ? value.toFixed(1) : String(value)
  }
  return String(value)
}
