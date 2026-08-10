/**
 * Viewer tool-calling schema for the AI Assistant.
 * Keep in sync with btf_viewer_pkg/ai_tools.py.
 */

export const AI_TOOL_SET_CURSORS = 'set_cursors'
export const AI_TOOL_ZOOM_TO_RANGE = 'zoom_to_range'
export const AI_TOOL_HIGHLIGHT_TASK = 'highlight_task'
export const AI_TOOL_SET_VIEW_MODE = 'set_view_mode'
export const AI_TOOL_OPEN_CORRIDOR = 'open_corridor_inspector'

export const AI_VIEWER_TOOL_NAMES = [
  AI_TOOL_SET_CURSORS,
  AI_TOOL_ZOOM_TO_RANGE,
  AI_TOOL_HIGHLIGHT_TASK,
  AI_TOOL_SET_VIEW_MODE,
  AI_TOOL_OPEN_CORRIDOR,
]

export const AI_TOOL_SYSTEM_ADDENDUM =
  'When the user asks to show, focus, inspect, zoom, highlight, or jump to a '
  + 'time range, task, or core pair, you MUST invoke the matching viewer tool '
  + '(native function call) in addition to your markdown answer. Valid tools: '
  + 'set_cursors, zoom_to_range, highlight_task, set_view_mode, '
  + 'open_corridor_inspector. Tool timestamps use the same numeric trace time '
  + 'unit as jump:TIME. After tools run, summarise what you changed. '
  + 'If you cannot emit a native function call, emit one fenced btftool JSON '
  + 'object per action, for example:\n'
  + '```btftool\n'
  + '{"name": "set_cursors", "arguments": {"timestamps": [1805120, 1810000]}}\n'
  + '```\n'
  + 'When a mutex take/give, block, resume, or priority-boost sequence is the point, '
  + 'include a fenced mermaid sequenceDiagram. When summarising core-to-core '
  + 'migrations, include a fenced mermaid graph LR flowchart with cores as nodes '
  + 'and migration counts on edges.'

export const AI_MERMAID_SEQUENCE_EXAMPLE = `\`\`\`mermaid
sequenceDiagram
  autonumber
  participant L as Low[266] (Core 0)
  participant M as Med[267] (Core 0)
  participant H as High[268] (Core 0)
  L->>Mutex(0x80018700): take
  M->>Core 0: runs work
  H->>Mutex(0x80018700): take (Blocked)
  Note over L: Kernel boosts Low -> Pri 4
  L->>Mutex(0x80018700): give
  H->>Mutex(0x80018700): acquires lock
\`\`\``

export const AI_MERMAID_MIGRATION_EXAMPLE = `\`\`\`mermaid
graph LR
  C0[Core_0] -->|12| C1[Core_1]
  C1 -->|3| C0
\`\`\``

const MAX_CURSORS_TOOL = 8
export const MAX_TOOL_ROUNDS = 4

export function aiViewerTools() {
  return [
    {
      type: 'function',
      function: {
        name: AI_TOOL_SET_CURSORS,
        description:
          'Clear existing cursors and place new ones at the given '
          + 'trace timestamps. Enables Limit to C1–Cn statistics when '
          + 'two or more cursors are placed.',
        parameters: {
          type: 'object',
          properties: {
            timestamps: {
              type: 'array',
              items: { type: 'number' },
              description:
                'Trace time-unit timestamps (same unit as jump:TIME), '
                + 'earliest to latest. 1–8 values.',
            },
          },
          required: ['timestamps'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_ZOOM_TO_RANGE,
        description: 'Zoom and pan the timeline so start_time..end_time fills the view.',
        parameters: {
          type: 'object',
          properties: {
            start_time: {
              type: 'number',
              description: 'Range start in trace time units.',
            },
            end_time: {
              type: 'number',
              description: 'Range end in trace time units.',
            },
          },
          required: ['start_time', 'end_time'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_HIGHLIGHT_TASK,
        description:
          'Lock-highlight a task on the timeline (Task View). '
          + 'Pass empty string to clear the highlight.',
        parameters: {
          type: 'object',
          properties: {
            task_name_or_id: {
              type: 'string',
              description:
                'Task display name (e.g. Low[266]), merge key, or numeric task id.',
            },
          },
          required: ['task_name_or_id'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_SET_VIEW_MODE,
        description: 'Switch Task View vs Core View and optional timeline orientation.',
        parameters: {
          type: 'object',
          properties: {
            mode: {
              type: 'string',
              enum: ['task', 'core'],
              description: 'task = one row per task; core = one row per core.',
            },
            orientation: {
              type: 'string',
              enum: ['horizontal', 'vertical'],
              description: 'Optional layout orientation.',
            },
          },
          required: ['mode'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_OPEN_CORRIDOR,
        description:
          'Open the Migration & Corridor Inspector. Optionally focus a '
          + 'directed core pair (e.g. Core_0 → Core_1).',
        parameters: {
          type: 'object',
          properties: {
            core_from: {
              type: 'string',
              description: 'Source core name (e.g. Core_0).',
            },
            core_to: {
              type: 'string',
              description: 'Destination core name (e.g. Core_1).',
            },
          },
        },
      },
    },
  ]
}

export function parseToolArguments(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object' && !Array.isArray(raw)) return { ...raw }
  const text = String(raw).trim()
  if (!text) return {}
  try {
    const data = JSON.parse(text)
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {}
  } catch {
    return {}
  }
}

export function messageContentText(content) {
  if (content == null) return ''
  if (typeof content === 'string') return content.trim()
  if (Array.isArray(content)) {
    return content.map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') return String(item.text || item.content || '')
      return ''
    }).filter(Boolean).join('\n').trim()
  }
  return String(content).trim()
}

export function extractToolCalls(message) {
  if (!message || typeof message !== 'object') return []
  const out = []
  let calls = message.tool_calls
  if (typeof calls === 'string') {
    try { calls = JSON.parse(calls) } catch { calls = [] }
  }
  if (Array.isArray(calls)) {
    calls.forEach((call, i) => {
      if (!call || typeof call !== 'object') return
      const fn = call.function && typeof call.function === 'object' ? call.function : {}
      const name = String(fn.name || call.name || call.tool || '').trim()
      if (!name) return
      out.push({
        id: String(call.id || `call_${i}`),
        name,
        arguments: parseToolArguments(fn.arguments ?? call.arguments ?? call.args ?? call.input),
      })
    })
  }
  const legacy = message.function_call
  if (legacy && typeof legacy === 'object' && legacy.name) {
    out.push({
      id: String(legacy.id || 'call_0'),
      name: String(legacy.name).trim(),
      arguments: parseToolArguments(legacy.arguments),
    })
  }
  if (Array.isArray(message.content)) {
    message.content.forEach((part, i) => {
      if (!part || typeof part !== 'object') return
      const ptype = String(part.type || '')
      if (!['tool_use', 'function_call', 'tool_call'].includes(ptype)) return
      const name = String(part.name || '').trim()
      if (!name) return
      out.push({
        id: String(part.id || `part_${i}`),
        name,
        arguments: parseToolArguments(part.input ?? part.arguments ?? part.args),
      })
    })
  }
  return out
}

function btftoolFenceRe() {
  return /```(?:btftool|tool_call|tool-call)\s*\n(.*?)```/gis
}

function xmlToolRe() {
  return /<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/gi
}

function toolCallFromObj(obj, idx) {
  if (!obj || typeof obj !== 'object') return null
  let name = String(obj.name || obj.tool || '').trim()
  const fn = obj.function && typeof obj.function === 'object' ? obj.function : null
  let args
  if (fn) {
    name = name || String(fn.name || '').trim()
    args = parseToolArguments(fn.arguments ?? obj.arguments)
  } else {
    args = obj.arguments || obj.parameters || obj.args
    if (!args || typeof args !== 'object' || Array.isArray(args)) {
      args = parseToolArguments(args)
    }
    if (!args || !Object.keys(args).length) {
      args = Object.fromEntries(
        Object.entries(obj).filter(([k]) => !['name', 'tool', 'function', 'id', 'type'].includes(k)),
      )
    }
  }
  if (!AI_VIEWER_TOOL_NAMES.includes(name)) return null
  const checked = validateToolCall(name, args)
  if (checked.error) return null
  return { id: `text_${idx}`, name, arguments: checked.args || args }
}

export function parseToolCallsFromText(text) {
  const out = []
  const seen = new Set()
  const add = (obj) => {
    const call = toolCallFromObj(obj, out.length)
    if (!call) return
    const key = `${call.name}:${JSON.stringify(call.arguments)}`
    if (seen.has(key)) return
    seen.add(key)
    out.push(call)
  }
  const src = String(text || '')
  for (const m of src.matchAll(btftoolFenceRe())) {
    try {
      const data = JSON.parse(m[1].trim())
      if (Array.isArray(data)) data.forEach(add)
      else add(data)
    } catch { /* ignore */ }
  }
  for (const m of src.matchAll(xmlToolRe())) {
    const body = String(m[1] || '').trim()
    try {
      add(JSON.parse(body))
      continue
    } catch { /* try name\\njson */ }
    const nl = body.indexOf('\n')
    if (nl > 0) {
      try {
        add({ name: body.slice(0, nl).trim(), arguments: JSON.parse(body.slice(nl + 1)) })
      } catch { /* ignore */ }
    }
  }
  return out
}

function stableToolKey(call) {
  const args = call.arguments && typeof call.arguments === 'object' ? call.arguments : {}
  const sorted = {}
  for (const k of Object.keys(args).sort()) sorted[k] = args[k]
  return `${call.name}:${JSON.stringify(sorted)}`
}

export function mergeToolCalls(structured, fromText) {
  const out = []
  const seen = new Set()
  for (const call of [...(structured || []), ...(fromText || [])]) {
    if (!call || !call.name) continue
    const key = stableToolKey(call)
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ ...call })
  }
  return out
}

export function stripParsedToolMarkup(text) {
  return String(text || '')
    .replace(btftoolFenceRe(), '')
    .replace(xmlToolRe(), '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function asFloatList(value) {
  if (!Array.isArray(value)) return []
  const out = []
  for (const item of value) {
    const n = Number(item)
    if (Number.isFinite(n)) out.push(n)
  }
  return out
}

export function validateToolCall(name, args) {
  const a = args && typeof args === 'object' ? args : {}
  if (name === AI_TOOL_SET_CURSORS) {
    const times = asFloatList(a.timestamps).slice(0, MAX_CURSORS_TOOL)
    if (!times.length) return { args: null, error: 'timestamps must be a non-empty number array' }
    return { args: { timestamps: times }, error: '' }
  }
  if (name === AI_TOOL_ZOOM_TO_RANGE) {
    const lo = Number(a.start_time)
    const hi = Number(a.end_time)
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      return { args: null, error: 'start_time and end_time must be numbers' }
    }
    if (hi === lo) return { args: null, error: 'start_time and end_time must differ' }
    return {
      args: { start_time: Math.min(lo, hi), end_time: Math.max(lo, hi) },
      error: '',
    }
  }
  if (name === AI_TOOL_HIGHLIGHT_TASK) {
    return { args: { task_name_or_id: String(a.task_name_or_id || '').trim() }, error: '' }
  }
  if (name === AI_TOOL_SET_VIEW_MODE) {
    const mode = String(a.mode || '').trim().toLowerCase()
    if (mode !== 'task' && mode !== 'core') {
      return { args: null, error: 'mode must be "task" or "core"' }
    }
    let ori = a.orientation
    if (ori != null && ori !== '') {
      ori = String(ori).trim().toLowerCase()
      if (ori === 'h' || ori === 'horiz') ori = 'horizontal'
      if (ori === 'v' || ori === 'vert') ori = 'vertical'
      if (ori !== 'horizontal' && ori !== 'vertical') {
        return { args: null, error: 'orientation must be "horizontal" or "vertical"' }
      }
    } else {
      ori = null
    }
    const out = { mode }
    if (ori) out.orientation = ori
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_OPEN_CORRIDOR) {
    return {
      args: {
        core_from: String(a.core_from || '').trim(),
        core_to: String(a.core_to || '').trim(),
      },
      error: '',
    }
  }
  return { args: null, error: `unknown tool ${JSON.stringify(name)}` }
}

function fmtTraceNum(n) {
  const x = Number(n)
  if (!Number.isFinite(x)) return String(n)
  if (Number.isInteger(x)) return String(x)
  return String(x)
}

export function summariseToolCall(name, args) {
  const a = args && typeof args === 'object' ? args : {}
  if (name === AI_TOOL_SET_CURSORS) {
    const times = asFloatList(a.timestamps)
    if (!times.length) return 'Set cursors'
    return `Set cursors at [${times.slice(0, MAX_CURSORS_TOOL).map(fmtTraceNum).join(', ')}]`
  }
  if (name === AI_TOOL_ZOOM_TO_RANGE) {
    const lo = Number(a.start_time)
    const hi = Number(a.end_time)
    if (Number.isFinite(lo) && Number.isFinite(hi)) {
      return `Zoom to range ${fmtTraceNum(lo)}–${fmtTraceNum(hi)}`
    }
    return 'Zoom to range'
  }
  if (name === AI_TOOL_HIGHLIGHT_TASK) {
    const key = String(a.task_name_or_id || '').trim()
    return key ? `Highlight task ${key}` : 'Clear task highlight'
  }
  if (name === AI_TOOL_SET_VIEW_MODE) {
    let label = `Set view mode ${String(a.mode || '?').trim()}`
    if (a.orientation) label += `, ${a.orientation}`
    return label
  }
  if (name === AI_TOOL_OPEN_CORRIDOR) {
    const src = String(a.core_from || '').trim()
    const dst = String(a.core_to || '').trim()
    if (src && dst) return `Open corridor inspector ${src} → ${dst}`
    return 'Open corridor inspector'
  }
  return String(name || '').replace(/_/g, ' ')
}

export function parseAiAutoApply(value) {
  if (value === true) return true
  if (value === false || value == null) return false
  return ['1', 'true', 'yes', 'on'].includes(String(value).trim().toLowerCase())
}

function taskMatchAliases(raw) {
  const text = String(raw || '').trim()
  if (!text) return []
  const aliases = [text]
  if (text.charCodeAt(0) === 0) {
    const sep = text.indexOf('\x00', 1)
    if (sep > 0) {
      const tid = text.slice(1, sep)
      const name = text.slice(sep + 1)
      if (name && name !== 'TICK') aliases.push(`${name}[${tid}]`, name, tid)
      else if (name) aliases.push(name)
    }
    return aliases.filter(Boolean)
  }
  const m = /\[(\d+)\]\s*$/.exec(text)
  if (m) {
    aliases.push(m[1])
    const prefix = text.slice(0, m.index).trim()
    if (prefix) aliases.push(prefix)
  }
  if (/^\d+$/.test(text)) aliases.push(`[${text}]`)
  return aliases.filter(Boolean)
}

export function resolveTaskKey(taskNameOrId, candidates) {
  const want = String(taskNameOrId || '').trim()
  if (!want) return null
  const names = (candidates || []).map(c => String(c || '')).filter(Boolean)
  if (!names.length) return null
  if (names.includes(want)) return want
  const lower = new Map(names.map(n => [n.toLowerCase(), n]))
  if (lower.has(want.toLowerCase())) return lower.get(want.toLowerCase())

  const byAlias = new Map()
  for (const name of names) {
    for (const alias of taskMatchAliases(name)) {
      const key = alias.toLowerCase()
      const list = byAlias.get(key) || []
      if (!list.includes(name)) list.push(name)
      byAlias.set(key, list)
    }
  }
  const hits = byAlias.get(want.toLowerCase()) || []
  if (hits.length === 1) return hits[0]
  if (hits.length && /^\d+$/.test(want)) return hits[0]

  const wantL = want.toLowerCase()
  const prefix = []
  const contains = []
  for (const [alias, origs] of byAlias) {
    if (alias.startsWith(wantL)) prefix.push(...origs)
    if (alias.includes(wantL)) contains.push(...origs)
  }
  const uniq = arr => [...new Set(arr)]
  const prefixU = uniq(prefix)
  if (prefixU.length === 1) return prefixU[0]
  const containsU = uniq(contains)
  if (containsU.length === 1) return containsU[0]
  return null
}
