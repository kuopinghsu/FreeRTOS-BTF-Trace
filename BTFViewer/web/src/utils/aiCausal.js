/** Causal / temporal investigation engines. Keep in sync with btf_viewer_pkg/ai_causal.py. */

const TASK_RE = /([A-Za-z_][\w.-]*\s*\[[^\]]+\])/g
const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/g
const NUM_RE = /([-+]?[0-9]*\.?[0-9]+)\s*(ms|us|µs|ns|%)?/i

const EDGE_KINDS = [
  ['blocks', ['block', 'wait', 'held by']],
  ['preempts', ['preempt']],
  ['migrates-to', ['migrat', 'affinity']],
  ['owns', ['mutex', 'lock', 'owns']],
  ['wakes', ['wake', 'notify', 'give']],
  ['inherits-priority-from', ['inherit', 'inversion']],
  ['depends-on', ['depend', 'after', 'caused']],
]

const BUCKETS = [
  ['mutex_blocking', ['mutex', 'lock', 'contention', 'block', 'wait']],
  ['preemption', ['preempt', 'isr', 'interrupt']],
  ['migration', ['migrat', 'affinity', 'bounce']],
  ['execution', ['wcet', 'execution', 'runtime', 'cpu']],
  ['scheduler', ['tick', 'ready', 'queue']],
]

let MEMORY = []

export function investigationMemoryStore() {
  return MEMORY.map((r) => ({ ...r }))
}

export function setInvestigationMemory(rows = []) {
  MEMORY = []
  for (const row of rows || []) {
    if (row && typeof row === 'object') MEMORY.push({ ...row })
  }
}

function items(findings) {
  return (findings || []).filter((f) => f && typeof f === 'object')
}

function blob(finding) {
  return `${finding?.title || ''} ${finding?.text || ''}`
}

function taskOf(finding) {
  const t = String(finding?.task || '').trim()
  if (t) return t
  const m = /([A-Za-z_][\w.-]*\s*\[[^\]]+\])/.exec(blob(finding))
  return m ? m[1].replace(/ /g, '') : ''
}

function timeOf(finding) {
  for (const key of ['time', 'ns', 't', 'start', 'when']) {
    const n = Number(finding?.[key])
    if (Number.isFinite(n)) return n
  }
  const m = /jump:([0-9]+(?:\.[0-9]+)?)/.exec(blob(finding))
  return m ? Number(m[1]) : null
}

function jumps(text) {
  const out = []
  const re = new RegExp(JUMP_RE.source, 'g')
  let m
  while ((m = re.exec(String(text || '')))) out.push(Number(m[1]))
  return out.filter(Number.isFinite)
}

function kindOf(text) {
  const b = String(text || '').toLowerCase()
  for (const [name, keys] of EDGE_KINDS) {
    if (keys.some((k) => b.includes(k))) return name
  }
  return 'correlates-with'
}

function bucketOf(text) {
  const b = String(text || '').toLowerCase()
  for (const [name, keys] of BUCKETS) {
    if (keys.some((k) => b.includes(k))) return name
  }
  return 'other'
}

function magnitude(finding) {
  for (const key of ['delta_ms', 'ms', 'duration', 'value', 'pct']) {
    const n = Number(finding?.[key])
    if (Number.isFinite(n)) return Math.abs(n)
  }
  const m = NUM_RE.exec(blob(finding))
  if (!m) return 1
  const n = Math.abs(Number(m[1]))
  const unit = String(m[2] || '').toLowerCase()
  if (unit === 'ms') return n
  if (unit === 'us' || unit === 'µs') return n / 1000
  if (unit === 'ns') return n / 1e6
  return n
}

export function analyzeTemporalCausality(findings = [], { task = '' } = {}) {
  const want = String(task || '').trim()
  const rows = []
  for (const f of items(findings)) {
    const t = timeOf(f)
    const name = taskOf(f)
    if (want && name && !name.includes(want) && !want.includes(name)) {
      if (!blob(f).toLowerCase().includes(want.toLowerCase())) continue
    }
    rows.push({
      time: t,
      task: name,
      title: String(f.title || f.id || ''),
      kind: kindOf(blob(f)),
      jump: t != null ? `jump:${Math.trunc(t)}` : '',
    })
  }
  rows.sort((a, b) => {
    if (a.time == null && b.time == null) return 0
    if (a.time == null) return 1
    if (b.time == null) return -1
    return a.time - b.time
  })
  const chain = rows.map((row, i) => {
    const label = row.title || row.task || `event ${i + 1}`
    return `${row.jump || 'untimed'}  ${row.kind}  ${label}`
  })
  let mermaid = 'flowchart TB\n'
  rows.slice(0, 12).forEach((row, i) => {
    mermaid += `  E${i}["${String(row.title || row.task || `E${i}`).slice(0, 48)}"]\n`
    if (i) mermaid += `  E${i - 1} --> E${i}\n`
  })
  if (!rows.length) mermaid += '  empty["No timed findings"]\n'
  const focus = want || (rows[0]?.task || '')
  return {
    ok: true,
    message: rows.length
      ? `Temporal chain for ${focus || 'scope'}: ${rows.length} events`
      : 'No timed findings to order',
    task: focus,
    events: rows,
    chain,
    mermaid,
    disclaimer: 'Heuristic happens-before from Findings times, not a kernel trace replay.',
  }
}

const GRAPH_MAX_NODES = 24
const GRAPH_MAX_EDGES = 40
const CAUSAL_EDGE_KINDS = new Set([
  'blocks', 'preempts', 'depends-on', 'owns', 'waits-for',
  'wakes', 'signals', 'inherits-priority-from',
])

function nodeType(name, hint = '') {
  if (hint) return hint
  const raw = String(name || '')
  const low = raw.toLowerCase()
  if (low.startsWith('core') || raw.startsWith('Core_')) return 'core'
  if (low.startsWith('mutex')) return 'mutex'
  if (low.startsWith('sem')) return 'sem'
  if (low.startsWith('queue')) return 'queue'
  if (low.includes('isr')) return 'isr'
  if (raw.includes('[')) return 'task'
  return 'resource'
}

function matchesFocus(name, want) {
  if (!want) return true
  const a = String(name || '')
  const b = String(want || '')
  return Boolean(a) && (a.includes(b) || b.includes(a) || a.toLowerCase().includes(b.toLowerCase()))
}

function addDepEdge(bag, src, dst, kind, {
  weight = 1, srcType = '', dstType = '',
} = {}) {
  src = String(src || '').trim()
  dst = String(dst || '').trim()
  if (!src || !dst || src === dst) return
  let w = Math.abs(Number(weight))
  if (!Number.isFinite(w) || w <= 0) w = 1
  const key = `${src}\0${dst}\0${kind}`
  const rec = bag.get(key)
  if (rec) {
    rec.count += 1
    rec.weight += w
    return
  }
  bag.set(key, {
    from: src,
    to: dst,
    kind,
    count: 1,
    weight: w,
    from_type: nodeType(src, srcType),
    to_type: nodeType(dst, dstType),
  })
}

export function collectDependencyEdges({
  syncHolds = [],
  preemptions = [],
  migrations = [],
  priorityEpisodes = [],
} = {}) {
  const bag = new Map()
  const byKey = new Map()
  for (const raw of syncHolds || []) {
    if (!raw || typeof raw !== 'object') continue
    const kind = String(raw.kind || '').toLowerCase()
    const key = String(raw.key || `${kind}:${raw.ptr || kind || 'sync'}`)
    const holder = String(raw.holder || raw.holder_label || '').trim()
    const start = Number(raw.start_ns ?? raw.startNs ?? 0) || 0
    let duration = Number(raw.duration_ns ?? raw.durationNs ?? 0)
    if (!Number.isFinite(duration) || duration <= 0) duration = 1
    const rec = {
      kind, key, holder, start, duration, signal: Boolean(raw.signal),
    }
    if (!byKey.has(key)) byKey.set(key, [])
    byKey.get(key).push(rec)
  }
  for (const [key, holds] of byKey) {
    holds.sort((a, b) => a.start - b.start)
    const kind = holds[0].kind || 'resource'
    for (const h of holds) {
      if (!h.holder) continue
      addDepEdge(bag, h.holder, key, 'owns', {
        weight: h.duration, srcType: 'task', dstType: kind,
      })
      if (h.signal || kind === 'sem' || kind === 'queue') {
        addDepEdge(bag, h.holder, key, 'signals', {
          weight: h.duration, srcType: 'task', dstType: kind,
        })
      }
    }
    for (let i = 1; i < holds.length; i++) {
      const prev = holds[i - 1]
      const cur = holds[i]
      const a = prev.holder
      const b = cur.holder
      if (!a || !b || a === b) continue
      addDepEdge(bag, b, key, 'waits-for', {
        weight: cur.duration, srcType: 'task', dstType: kind,
      })
      addDepEdge(bag, a, b, 'blocks', {
        weight: prev.duration, srcType: 'task', dstType: 'task',
      })
      addDepEdge(bag, b, a, 'depends-on', {
        weight: prev.duration, srcType: 'task', dstType: 'task',
      })
      if (prev.signal || kind === 'sem' || kind === 'queue') {
        addDepEdge(bag, a, b, 'wakes', {
          weight: prev.duration, srcType: 'task', dstType: 'task',
        })
      }
    }
  }
  for (const raw of preemptions || []) {
    if (!raw || typeof raw !== 'object') continue
    const w = Number(raw.weight ?? raw.count ?? 1)
    addDepEdge(bag, raw.preemptor, raw.victim, 'preempts', {
      weight: w, srcType: 'task', dstType: 'task',
    })
  }
  for (const raw of migrations || []) {
    if (!raw || typeof raw !== 'object') continue
    addDepEdge(bag, raw.task, raw.to_core || raw.toCore, 'migrates-to', {
      weight: 1, srcType: 'task', dstType: 'core',
    })
  }
  for (const raw of priorityEpisodes || []) {
    if (!raw || typeof raw !== 'object') continue
    const inherited = Boolean(
      raw.inherited || raw.inversion_suspect || raw.inversionSuspect)
    if (!inherited) continue
    const taskName = String(raw.task || raw.task_label || '').trim()
    const mediums = raw.medium_tasks || raw.mediumTasks || []
    let donors = mediums.map((m) => String(m || '').trim()).filter(Boolean)
    if (!donors.length) donors = ['priority']
    for (const donor of donors.slice(0, 4)) {
      addDepEdge(bag, taskName, donor, 'inherits-priority-from', {
        weight: 1,
        srcType: 'task',
        dstType: donor.includes('[') ? 'task' : 'resource',
      })
    }
  }
  return [...bag.values()].sort((a, b) => (
    (b.weight - a.weight)
    || String(a.from).localeCompare(b.from)
    || String(a.to).localeCompare(b.to)
    || String(a.kind).localeCompare(b.kind)
  ))
}

function filterGraphNeighborhood(edges, want, hops = 2) {
  if (!want) return [...edges]
  let keep = new Set()
  for (const e of edges) {
    if (matchesFocus(e.from, want)) keep.add(e.from)
    if (matchesFocus(e.to, want)) keep.add(e.to)
  }
  if (!keep.size) return [...edges]
  for (let i = 0; i < hops; i++) {
    const extra = new Set()
    for (const e of edges) {
      if (keep.has(e.from) || keep.has(e.to)) {
        extra.add(e.from)
        extra.add(e.to)
      }
    }
    keep = new Set([...keep, ...extra])
  }
  return edges.filter((e) => keep.has(e.from) && keep.has(e.to))
}

function responsibleTasks(edges, want) {
  if (!want) return []
  const seeds = new Set()
  for (const e of edges) {
    if (matchesFocus(e.to, want)) seeds.add(e.to)
    if (matchesFocus(e.from, want)) seeds.add(e.from)
  }
  if (!seeds.size) return []
  const rev = new Map()
  const types = {}
  for (const e of edges) {
    types[e.from] = e.from_type || nodeType(e.from)
    types[e.to] = e.to_type || nodeType(e.to)
    if (!CAUSAL_EDGE_KINDS.has(e.kind)) continue
    if (!rev.has(e.to)) rev.set(e.to, [])
    rev.get(e.to).push(e.from)
  }
  const seen = new Set(seeds)
  const stack = [...seeds]
  while (stack.length) {
    const cur = stack.pop()
    for (const src of rev.get(cur) || []) {
      if (seen.has(src)) continue
      seen.add(src)
      stack.push(src)
    }
  }
  return [...seen]
    .filter((name) => !seeds.has(name) && (types[name] === 'task' || String(name).includes('[')))
    .sort()
    .slice(0, 12)
}

function capGraphEdges(edges, maxNodes = GRAPH_MAX_NODES, maxEdges = GRAPH_MAX_EDGES) {
  const picked = []
  const nodes = new Set()
  for (const e of edges) {
    const nxt = new Set([...nodes, e.from, e.to])
    if (picked.length >= maxEdges) break
    if (nxt.size > maxNodes) continue
    picked.push(e)
    nodes.add(e.from)
    nodes.add(e.to)
  }
  return picked
}

function edgesFromFindings(findings) {
  const bag = new Map()
  for (const f of items(findings)) {
    const src = taskOf(f) || String(f.title || f.id || 'finding')
    const kind = kindOf(blob(f))
    const others = []
    const re = new RegExp(TASK_RE.source, 'g')
    let m
    const text = blob(f)
    while ((m = re.exec(text))) others.push(m[1].replace(/ /g, ''))
    let dsts = others.filter((o) => o !== src).slice(0, 3)
    if (!dsts.length) {
      const low = text.toLowerCase()
      for (const token of ['Mutex', 'Sem', 'Queue', 'ISR']) {
        if (low.includes(token.toLowerCase())) {
          dsts = [token]
          break
        }
      }
    }
    for (const dst of dsts) addDepEdge(bag, src, dst, kind)
  }
  return [...bag.values()]
}

export function buildTaskDependencyGraph(findings = [], {
  edges = null,
  syncHolds = [],
  preemptions = [],
  migrations = [],
  priorityEpisodes = [],
  task = '',
  maxNodes = GRAPH_MAX_NODES,
  maxEdges = GRAPH_MAX_EDGES,
} = {}) {
  const want = String(task || '').trim()
  let source = 'btf'
  let raw = (edges || []).filter((e) => e && e.from && e.to)
  if (!raw.length) {
    raw = collectDependencyEdges({
      syncHolds, preemptions, migrations, priorityEpisodes,
    })
  }
  if (!raw.length) {
    raw = edgesFromFindings(findings)
    source = 'findings'
  }
  const scoped = filterGraphNeighborhood(raw, want)
  const responsible = responsibleTasks(scoped, want)
  const capped = capGraphEdges(scoped, maxNodes, maxEdges)
  const nodes = {}
  for (const e of capped) {
    if (!nodes[e.from]) nodes[e.from] = e.from_type || nodeType(e.from)
    if (!nodes[e.to]) nodes[e.to] = e.to_type || nodeType(e.to)
  }
  let mermaid = 'flowchart LR\n'
  const names = Object.keys(nodes)
  names.forEach((name, i) => { mermaid += `  N${i}["${name.slice(0, 40)}"]\n` })
  const ids = Object.fromEntries(names.map((n, i) => [n, `N${i}`]))
  for (const e of capped) {
    const a = ids[e.from]
    const b = ids[e.to]
    if (a && b && a !== b) mermaid += `  ${a} -->|${e.kind}| ${b}\n`
  }
  if (!names.length) mermaid += '  empty["No dependency nodes"]\n'
  const focus = want || names[0] || ''
  const extra = responsible.length
    ? `; ${responsible.length} task(s) upstream of ${focus}`
    : ''
  const origin = source === 'btf' ? 'BTF sync/preempt/migrate' : 'finding wording'
  return {
    ok: true,
    message: `${names.length} nodes, ${capped.length} edges (${origin})${extra}`,
    task: focus,
    source,
    nodes: Object.entries(nodes).map(([id, type]) => ({ id, type })),
    edges: capped,
    responsible,
    mermaid,
    disclaimer: source === 'btf'
      ? 'BTF edges from sync holds, preemption chains, migrations, and priority inheritance in the current cursor (or full trace).'
      : 'Edges inferred from finding wording, not from the BTF wait graph.',
  }
}

export function decomposeResponseTime(findings = [], { task = '' } = {}) {
  const want = String(task || '').trim()
  const buckets = { mutex_blocking: 0, preemption: 0, migration: 0, execution: 0, scheduler: 0, other: 0 }
  let used = 0
  for (const f of items(findings)) {
    const name = taskOf(f)
    if (want && name && !name.includes(want) && !want.includes(name)) {
      if (!blob(f).toLowerCase().includes(want.toLowerCase())) continue
    }
    buckets[bucketOf(blob(f))] += magnitude(f)
    used += 1
  }
  const total = Object.values(buckets).reduce((a, b) => a + b, 0) || 1
  const parts = Object.entries(buckets)
    .filter(([, v]) => v > 0)
    .map(([bucket, v]) => ({ bucket, ms: Math.round(v * 10000) / 10000, pct: Math.round(1000 * v / total) / 10 }))
    .sort((a, b) => b.pct - a.pct)
  const leader = parts[0]?.bucket || 'unknown'
  const tree = [`Response time ~ ${total.toFixed(3)} (relative units)`]
  for (const p of parts) tree.push(`  └─ +${p.pct}% ${p.bucket}`)
  return {
    ok: true,
    message: parts.length ? `Dominant delay: ${leader}` : 'No delay components',
    task: want,
    parts,
    tree,
    dominant: leader,
    findings_used: used,
    disclaimer: 'Shares are relative magnitudes from finding text/metrics, not cycle-accurate.',
  }
}

export function rankRootCauses(findings = [], { hypotheses = [] } = {}) {
  const list = items(findings)
  const hyps = (hypotheses || []).filter((h) => h && typeof h === 'object')
  let ranked = []
  if (hyps.length) {
    ranked = hyps.map((h, i) => {
      const text = String(h.hypothesis || h.description || '')
      let score = 0.4 + 0.15 * Math.min(magnitude({ title: text }), 4)
      const status = String(h.status || '').toLowerCase()
      if (status === 'supported') score += 0.25
      else if (status === 'rejected') score -= 0.4
      const overlap = list.filter((f) => bucketOf(blob(f)) === bucketOf(text)).length
      score += 0.08 * overlap
      return {
        id: String(h.id || `H${i + 1}`),
        cause: text || String(h.id || `H${i + 1}`),
        score: Math.round(Math.max(0.01, Math.min(0.99, score)) * 1000) / 1000,
        source: 'hypothesis',
      }
    })
  } else {
    const byBucket = {}
    for (const f of list) {
      const b = bucketOf(blob(f))
      byBucket[b] = (byBucket[b] || 0) + magnitude(f)
    }
    const total = Object.values(byBucket).reduce((a, b) => a + b, 0) || 1
    ranked = Object.entries(byBucket)
      .sort((a, b) => b[1] - a[1])
      .map(([b, v]) => ({
        id: b,
        cause: b.replace(/_/g, ' '),
        score: Math.round((v / total) * 1000) / 1000,
        source: 'finding',
      }))
  }
  ranked.sort((a, b) => b.score - a.score)
  const leader = ranked[0]?.cause || ''
  return {
    ok: true,
    message: leader ? `Leading cause: ${leader}` : 'No causes to rank',
    ranked,
    leader: ranked[0] || null,
  }
}

export function verifyClaim(claim = '', {
  claimType = 'causal', subject = '', object = '', evidence = [], findings = [],
  cursorLo = null, cursorHi = null,
} = {}) {
  const text = String(claim || '').trim()
  const subj = String(subject || '').trim()
  const obj = String(object || '').trim()
  const list = items(findings)
  const ev = []
  for (const e of evidence || []) {
    if (typeof e === 'number') ev.push(e)
    else {
      ev.push(...jumps(String(e)))
      const n = Number(String(e).replace('jump:', ''))
      if (Number.isFinite(n)) ev.push(n)
    }
  }
  const all = list.map(blob).join(' ').toLowerCase()
  const checks = []
  const add = (name, ok, detail) => { checks.push({ check: name, ok, detail }) }
  if (subj) {
    add('subject', all.includes(subj.toLowerCase()) || list.some((f) => taskOf(f).includes(subj)), `subject '${subj}'`)
  }
  if (obj) add('object', all.includes(obj.toLowerCase()), `object '${obj}'`)
  if (text) {
    const keys = (text.toLowerCase().match(/[a-z]{4,}/g) || []).filter((w) => !['this', 'that', 'with', 'from', 'task'].includes(w))
    const hit = keys.filter((k) => all.includes(k)).length
    add('evidence_lookup', hit >= Math.max(1, Math.floor(keys.length / 3)), `${hit}/${keys.length || 1} claim tokens in findings`)
  }
  if (cursorLo != null && cursorHi != null && ev.length) {
    const lo = Math.min(cursorLo, cursorHi)
    const hi = Math.max(cursorLo, cursorHi)
    add('scope', ev.every((t) => t >= lo && t <= hi), 'evidence times inside cursors')
  } else if (ev.length) {
    add('temporal', true, `${ev.length} jump times`)
  }
  let contradicted = false
  if (text.toLowerCase().includes('mutex') && all.includes('migrat') && !all.includes('mutex')) {
    contradicted = true
    add('contradiction', false, 'Findings emphasise migration, not mutex')
  }
  const oks = checks.length ? checks.map((c) => c.ok) : [false]
  let verdict = 'PARTIAL'
  if (contradicted || !oks.some(Boolean)) verdict = 'UNSUPPORTED'
  else if (oks.every(Boolean)) verdict = 'SUPPORTED'
  return {
    ok: true,
    message: verdict,
    claim: text,
    type: String(claimType || 'causal'),
    subject: subj,
    object: obj,
    verdict,
    checks,
    evidence_times: ev,
  }
}

export function challengeConclusion(conclusion = '', { findings = [], hypotheses = [] } = {}) {
  const list = items(findings)
  const conc = String(conclusion || '').trim()
  const leader = conc ? bucketOf(conc) : (list[0] ? bucketOf(blob(list[0])) : 'other')
  const alts = []
  const seen = new Set([leader])
  for (const f of list) {
    const b = bucketOf(blob(f))
    if (!seen.has(b)) {
      seen.add(b)
      alts.push(b.replace(/_/g, ' '))
    }
  }
  for (const h of hypotheses || []) {
    if (!h || typeof h !== 'object') continue
    const text = String(h.hypothesis || '')
    if (text && !seen.has(bucketOf(text))) alts.push(text)
  }
  const missing = []
  if (leader.includes('mutex') && !list.some((f) => blob(f).toLowerCase().includes('preempt'))) {
    missing.push('No preemption alternative was measured.')
  }
  if (list.length && !list.some((f) => timeOf(f) != null)) {
    missing.push('No jump:TIME on supporting findings.')
  }
  const whyNot = alts.slice(0, 4)
  return {
    ok: true,
    message: whyNot.length ? `Alternatives to ${leader}: ${whyNot.join(', ')}` : `No strong alternative to ${leader}`,
    conclusion: conc,
    leading: leader,
    alternatives: whyNot,
    missing_evidence: missing,
    why_not: whyNot,
  }
}

export function investigationMemory(action = 'recall', { record = null, findings = [], limit = 5 } = {}) {
  const act = String(action || 'recall').trim().toLowerCase()
  if (['store', 'save', 'add'].includes(act) && record && typeof record === 'object') {
    const entry = { ...record }
    if (findings?.length && !entry.finding) {
      const list = items(findings)
      entry.finding = String(list[0]?.title || '')
    }
    MEMORY.push(entry)
    return {
      ok: true,
      message: `Stored memory (${MEMORY.length} entries)`,
      entry,
      count: MEMORY.length,
    }
  }
  const all = items(findings).map(blob).join(' ').toLowerCase()
  const tokens = [...new Set((all.match(/[a-z]{4,}/g) || []))]
  const ranked = MEMORY.map((row) => {
    const text = ['finding', 'root_cause', 'pattern', 'fix'].map((k) => String(row[k] || '')).join(' ').toLowerCase()
    let score = 0
    for (const tok of tokens) if (text.includes(tok)) score += 1
    return { ...row, score: Math.round(score * 100) / 100 }
  }).sort((a, b) => b.score - a.score)
  const hits = ranked.filter((r) => r.score > 0).slice(0, Math.max(1, Number(limit) || 5))
  return {
    ok: true,
    message: hits.length ? `Seen this pattern before (${hits.length} hits)` : 'No similar memories',
    matches: hits,
    count: MEMORY.length,
  }
}

export function clusterIncidents(findings = [], { windowNs = 1e6 } = {}) {
  const list = items(findings)
  const win = Number(windowNs) || 1e6
  const timed = list.map((f) => [timeOf(f), f]).sort((a, b) => {
    if (a[0] == null && b[0] == null) return 0
    if (a[0] == null) return 1
    if (b[0] == null) return -1
    return a[0] - b[0]
  })
  const clusters = []
  let current = []
  let lastT = null
  for (const [t, f] of timed) {
    if (t == null) {
      clusters.push([f])
      continue
    }
    if (lastT == null || Math.abs(t - lastT) > win) {
      if (current.length) clusters.push(current)
      current = [f]
    } else current.push(f)
    lastT = t
  }
  if (current.length) clusters.push(current)
  const out = clusters.map((group, i) => ({
    id: `I${i + 1}`,
    size: group.length,
    tasks: [...new Set(group.map(taskOf).filter(Boolean))].sort(),
    titles: group.slice(0, 6).map((f) => String(f.title || f.id || '')),
  })).sort((a, b) => b.size - a.size)
  return {
    ok: true,
    message: `${out.length} incident cluster(s)`,
    incidents: out,
    window_ns: win,
  }
}

export function closeInvestigation(conclusion = '', { findings = [], experiments = [], confidence = '' } = {}) {
  const list = items(findings)
  const conc = String(conclusion || '').trim() || String(list[0]?.title || 'unspecified')
  const exps = (experiments || []).filter((e) => e && typeof e === 'object')
  const closed = {
    conclusion: conc,
    confidence: String(confidence || 'Medium'),
    finding_count: list.length,
    experiments: exps,
    status: 'closed',
    next: 'Record outcome / recapture trace if an experiment is still open.',
  }
  return { ok: true, message: `Closed: ${conc}`, case: closed }
}

export function analyzeDistribution(values = [], {
  findings = [], metric = '', source = '', task = '', truncated = false,
} = {}) {
  let nums = (values || []).map(Number).filter(Number.isFinite)
  let src = String(source || '').trim().toLowerCase()
  if (nums.length) src = src || 'values'
  else {
    nums = items(findings).map(magnitude)
    if (nums.length) src = 'findings'
  }
  nums.sort((a, b) => a - b)
  const n = nums.length
  if (!n) return { ok: false, message: 'No numeric samples' }
  const pct = (p) => {
    if (n === 1) return nums[0]
    return nums[Math.min(n - 1, Math.max(0, Math.round((p / 100) * (n - 1))))]
  }
  const r6 = (x) => Math.round(x * 1e6) / 1e6
  const mean = nums.reduce((a, b) => a + b, 0) / n
  const p50 = pct(50)
  const p90 = pct(90)
  const p95 = pct(95)
  const p99 = pct(99)
  const p999 = pct(99.9)
  let stddev = 0
  if (n >= 2) {
    stddev = Math.sqrt(nums.reduce((s, x) => s + (x - mean) ** 2, 0) / (n - 1))
  }
  const cv = mean ? stddev / mean : 0
  let outliers = 0
  if (stddev > 0) {
    const limit = mean + 3 * stddev
    outliers = nums.filter((x) => x > limit).length
  }
  const outlierRate = 100 * outliers / n
  let disclaimer = 'Caller-supplied samples.'
  if (src === 'findings') disclaimer = 'Magnitudes from finding text, not BTF samples.'
  else if (src === 'btf') {
    disclaimer = `Percentiles from BTF ${metric || 'sample'} samples in the current cursor (or full trace).`
  }
  return {
    ok: true,
    message: `n=${n} p50=${p50} p90=${p90} p95=${p95} p99=${p99} p99.9=${p999} cv=${cv} outliers=${outlierRate}%`,
    metric: String(metric || ''),
    task: String(task || ''),
    source: src || 'values',
    n,
    mean: r6(mean),
    stddev: r6(stddev),
    cv: Math.round(cv * 1e4) / 1e4,
    p50: r6(p50),
    p90: r6(p90),
    p95: r6(p95),
    p99: r6(p99),
    'p99.9': r6(p999),
    tail_ratio: p50 ? Math.round((p99 / p50) * 1000) / 1000 : 0,
    outlier_rate: Math.round(outlierRate * 1000) / 1000,
    min: r6(nums[0]),
    max: r6(nums[n - 1]),
    truncated: Boolean(truncated),
    disclaimer,
  }
}

function percentile(nums, p) {
  const n = nums.length
  if (n === 1) return nums[0]
  return nums[Math.min(n - 1, Math.max(0, Math.round((p / 100) * (n - 1))))]
}

function inWindow(t, lo, hi) {
  if (lo != null && t < lo) return false
  if (hi != null && t > hi) return false
  return true
}

export function collectPeriodicityTimes(times = [], {
  findings = [], source = '', tickTimes = [], stiEvents = [],
  releaseTimes = [], lo = null, hi = null,
} = {}) {
  const floats = (rows) => (rows || []).map(Number).filter((n) => Number.isFinite(n) && inWindow(n, lo, hi))
  const src = String(source || 'auto').trim().toLowerCase() || 'auto'
  const explicit = floats(times)
  if (explicit.length) return [...new Set(explicit)].sort((a, b) => a - b)
  const ticks = floats(tickTimes)
  if (src === 'tick' || src === 'sti' || (src === 'auto' && ticks.length)) {
    if (ticks.length || src === 'tick' || src === 'sti') {
      return [...new Set(ticks)].sort((a, b) => a - b)
    }
  }
  const stiMatch = (...needles) => {
    const out = []
    for (const ev of stiEvents || []) {
      if (!ev || typeof ev !== 'object') continue
      const blob = `${ev.target || ''} ${ev.event || ''} ${ev.note || ''} ${ev.channel || ''}`.toLowerCase()
      if (!needles.some((n) => blob.includes(n))) continue
      const n = Number(ev.time != null ? ev.time : ev.ns)
      if (Number.isFinite(n) && inWindow(n, lo, hi)) out.push(n)
    }
    return out
  }
  if (src === 'isr') return [...new Set(stiMatch('isr', 'interrupt'))].sort((a, b) => a - b)
  if (src === 'timer') return [...new Set(stiMatch('timer'))].sort((a, b) => a - b)
  if (src === 'release') return [...new Set(floats(releaseTimes))].sort((a, b) => a - b)
  if (src === 'auto') {
    const isr = stiMatch('isr', 'interrupt')
    if (isr.length) return [...new Set(isr)].sort((a, b) => a - b)
    const timer = stiMatch('timer')
    if (timer.length) return [...new Set(timer)].sort((a, b) => a - b)
    const releases = floats(releaseTimes)
    if (releases.length) return [...new Set(releases)].sort((a, b) => a - b)
  }
  const found = items(findings).map(timeOf).filter((t) => t != null && inWindow(t, lo, hi))
  return [...new Set(found)].sort((a, b) => a - b)
}

function classifyPeriodicity(expected, p50, p99, maxGap, cv, findings = [], durations = []) {
  const text = items(findings).map((f) => `${f?.title || ''} ${f?.text || ''}`).join(' ').toLowerCase()
  const durs = (durations || []).map(Number).filter(Number.isFinite)
  if (durs.length >= 3) {
    const dmean = durs.reduce((a, b) => a + b, 0) / durs.length
    const dvar = durs.reduce((s, d) => s + (d - dmean) ** 2, 0) / durs.length
    const dcv = dmean ? Math.sqrt(dvar) / dmean : 0
    if (dcv > Math.max(cv, 0.05) * 1.25) return 'execution-time variation'
  }
  if (expected) {
    const drift = Math.abs(p50 - expected) / expected
    if (drift > 0.12 && cv < 0.08) return 'period drift'
    if (maxGap > Math.max(expected * 2, p99 ? p99 * 1.4 : 0)) {
      if (['preempt', 'migrat', 'isr', 'interrupt'].some((k) => text.includes(k))) {
        return 'scheduler interference'
      }
      return 'release jitter'
    }
  }
  if (cv >= 0.08) {
    if (['preempt', 'migrat', 'isr', 'interrupt'].some((k) => text.includes(k))) {
      return 'scheduler interference'
    }
    return 'release jitter'
  }
  return 'stable period'
}

export function analyzePeriodicity(times = [], {
  findings = [], expected = null, source = '', durations = [],
  tickTimes = [], stiEvents = [], releaseTimes = [], lo = null, hi = null,
} = {}) {
  const ts = collectPeriodicityTimes(times, {
    findings, source, tickTimes, stiEvents, releaseTimes, lo, hi,
  })
  if (ts.length < 3) {
    return {
      ok: false,
      message: 'Need ≥3 timestamps for periodicity',
      n: ts.length,
      source: String(source || 'auto'),
    }
  }
  const gaps = []
  for (let i = 1; i < ts.length; i += 1) gaps.push(ts[i] - ts[i - 1])
  const gapsSorted = [...gaps].sort((a, b) => a - b)
  const mean = gaps.reduce((a, b) => a + b, 0) / gaps.length
  const p50 = percentile(gapsSorted, 50)
  const p99 = percentile(gapsSorted, 99)
  const maxGap = gapsSorted[gapsSorted.length - 1]
  const minGap = gapsSorted[0]
  let exp = Number(expected)
  if (!Number.isFinite(exp) || expected === '' || expected == null) exp = p50
  if (!exp) exp = mean
  const rms = Math.sqrt(gaps.reduce((s, g) => s + (g - exp) ** 2, 0) / gaps.length)
  const gapStd = Math.sqrt(gaps.reduce((s, g) => s + (g - mean) ** 2, 0) / gaps.length)
  const p2p = maxGap - minGap
  const cv = mean ? gapStd / mean : 0
  const kind = classifyPeriodicity(exp, p50, p99, maxGap, cv, findings, durations)
  return {
    ok: true,
    message:
      `Expected period: ${exp}  Measured p50=${p50} p99=${p99} max=${maxGap}  `
      + `Jitter RMS=${rms} peak-to-peak=${p2p}  (${kind})`,
    n: ts.length,
    source: String(source || 'auto'),
    expected: Math.round(exp * 1e6) / 1e6,
    period: Math.round(mean * 1e6) / 1e6,
    p50: Math.round(p50 * 1e6) / 1e6,
    p99: Math.round(p99 * 1e6) / 1e6,
    max: Math.round(maxGap * 1e6) / 1e6,
    jitter: Math.round(rms * 1e6) / 1e6,
    rms: Math.round(rms * 1e6) / 1e6,
    peak_to_peak: Math.round(p2p * 1e6) / 1e6,
    cv: Math.round(cv * 10000) / 10000,
    min_gap: Math.round(minGap * 1e6) / 1e6,
    max_gap: Math.round(maxGap * 1e6) / 1e6,
    kind,
    disclaimer:
      'Heuristic on inter-arrival gaps (tick/STI/ISR/timer/releases/findings), not a kernel period timer.',
  }
}

export function summarizeInvestigationContext(findings = [], {
  hypotheses = [], toolsRun = [], conclusion = '',
} = {}) {
  const list = items(findings)
  const hyps = (hypotheses || []).filter((h) => h && typeof h === 'object')
  const tools = (toolsRun || []).map(String)
  const summary = {
    findings: list.slice(0, 8).map((f) => String(f.title || f.id || '')),
    hypotheses: hyps.slice(0, 6).map((h) => String(h.hypothesis || h.id || '')),
    tools_run: tools,
    conclusion: String(conclusion || ''),
    finding_count: list.length,
  }
  return {
    ok: true,
    message: `${list.length} findings, ${hyps.length} hypotheses, ${tools.length} tools`,
    summary,
  }
}

export function simulateSchedule(changes = {}, { findings = [] } = {}) {
  const predicted = decomposeResponseTime(findings)
  predicted.level = 1
  predicted.changes = changes && typeof changes === 'object' ? changes : {}
  predicted.ok = true
  predicted.message = 'LEVEL 1 heuristic replay only — not a FreeRTOS-compatible scheduler.'
  predicted.disclaimer = predicted.message
  return predicted
}
