/**
 * Viewer tool-calling schema for the AI Assistant.
 * Keep in sync with btf_viewer_pkg/ai_tools.py.
 */
import { taskMergeKey } from './colors.js'
import { computeFindHits } from './findAnalysis.js'
import { btfHtmlReportDocument } from './htmlReport.js'
import {
  analyzeMultiTraces,
  buildCorrelationTimeline,
  buildCriticalPath,
  buildInvestigationPackage,
  buildInvestigationReplay,
  buildInvestigateContext,
  buildOptimizationAdvice,
  checkTaskBudgets,
  comparePerformanceMetrics,
  compareTasksMetrics,
  detectAnomalies,
  detectPriorityInversion,
  estimateWhatIf,
  explainRegression,
  findRelatedFindings,
  formatBookmarkLabel,
  generateStructuredReport,
  maxToolRoundsForTemplate,
  recommendValidationExperiments,
  resolveFinding,
  runOptimizationExperiments,
  scoreAgainstBaseline,
  simulateWhatIf,
  snapshotFromSummary,
} from './aiInvestigation.js'
import { coreUtilPctRows } from './traceCompare.js'

export const AI_TOOL_SET_CURSORS = 'set_cursors'
export const AI_TOOL_ZOOM_TO_RANGE = 'zoom_to_range'
export const AI_TOOL_HIGHLIGHT_TASK = 'highlight_task'
export const AI_TOOL_SET_VIEW_MODE = 'set_view_mode'
export const AI_TOOL_OPEN_CORRIDOR = 'open_corridor_inspector'
export const AI_TOOL_ADD_ANNOTATION = 'add_annotation'
export const AI_TOOL_QUERY_RAW_METRIC = 'query_raw_metric'
export const AI_TOOL_EXPORT_REPORT = 'export_report'
export const AI_TOOL_CLEAR_MARKS = 'clear_marks'
export const AI_TOOL_RESET_VIEW = 'reset_view'
export const AI_TOOL_SEARCH_TIMELINE = 'search_timeline'
export const AI_TOOL_TRIGGER_COMPARE = 'trigger_compare'
export const AI_TOOL_INVESTIGATE = 'investigate'
export const AI_TOOL_DETECT_ANOMALIES = 'detect_anomalies'
export const AI_TOOL_CORRELATE_EVENTS = 'correlate_events'
export const AI_TOOL_FIND_CRITICAL_PATH = 'find_critical_path'
export const AI_TOOL_COMPARE_PERFORMANCE = 'compare_performance'
export const AI_TOOL_GENERATE_REPORT = 'generate_report'
export const AI_TOOL_CHECK_BUDGET = 'check_budget'
export const AI_TOOL_OPTIMIZE = 'optimize'
export const AI_TOOL_REGRESSION_EXPLAIN = 'regression_explain'
export const AI_TOOL_BOOKMARK_FINDING = 'bookmark_finding'
export const AI_TOOL_INVESTIGATION_REPLAY = 'investigation_replay'
export const AI_TOOL_WHAT_IF = 'what_if'
export const AI_TOOL_OPTIMIZE_EXPERIMENT = 'optimize_experiment'
export const AI_TOOL_ANALYZE_TRACES = 'analyze_traces'
export const AI_TOOL_BASELINE_SCORE = 'baseline_score'
export const AI_TOOL_RECOMMEND_EXPERIMENTS = 'recommend_experiments'
export const AI_TOOL_EXPORT_INVESTIGATION = 'export_investigation'
export const AI_TOOL_DETECT_PRIORITY_INVERSION = 'detect_priority_inversion'
export const AI_TOOL_FIND_RELATED_FINDINGS = 'find_related_findings'
export const AI_TOOL_COMPARE_TASKS = 'compare_tasks'

export const AI_VIEWER_TOOL_NAMES = [
  AI_TOOL_SET_CURSORS,
  AI_TOOL_ZOOM_TO_RANGE,
  AI_TOOL_HIGHLIGHT_TASK,
  AI_TOOL_SET_VIEW_MODE,
  AI_TOOL_OPEN_CORRIDOR,
  AI_TOOL_ADD_ANNOTATION,
  AI_TOOL_QUERY_RAW_METRIC,
  AI_TOOL_EXPORT_REPORT,
  AI_TOOL_CLEAR_MARKS,
  AI_TOOL_RESET_VIEW,
  AI_TOOL_SEARCH_TIMELINE,
  AI_TOOL_TRIGGER_COMPARE,
  AI_TOOL_INVESTIGATE,
  AI_TOOL_DETECT_ANOMALIES,
  AI_TOOL_CORRELATE_EVENTS,
  AI_TOOL_FIND_CRITICAL_PATH,
  AI_TOOL_COMPARE_PERFORMANCE,
  AI_TOOL_GENERATE_REPORT,
  AI_TOOL_CHECK_BUDGET,
  AI_TOOL_OPTIMIZE,
  AI_TOOL_REGRESSION_EXPLAIN,
  AI_TOOL_BOOKMARK_FINDING,
  AI_TOOL_INVESTIGATION_REPLAY,
  AI_TOOL_WHAT_IF,
  AI_TOOL_OPTIMIZE_EXPERIMENT,
  AI_TOOL_ANALYZE_TRACES,
  AI_TOOL_BASELINE_SCORE,
  AI_TOOL_RECOMMEND_EXPERIMENTS,
  AI_TOOL_EXPORT_INVESTIGATION,
  AI_TOOL_DETECT_PRIORITY_INVERSION,
  AI_TOOL_FIND_RELATED_FINDINGS,
  AI_TOOL_COMPARE_TASKS,
]

export const AI_BOOKMARK_KINDS = [
  'root_cause', 'evidence', 'correlated', 'reference',
]

export const AI_FIND_MODES = [
  'contains', 'exact', 'regex', 'sti', 'tags', 'intervals',
  'lifecycle', 'pointers', 'migrations',
]
export const AI_CLEAR_MARKS_TARGETS = [
  'annotations', 'cursors', 'bookmarks', 'all', 'everything',
]

export const AI_RAW_METRIC_PRIORITY = 'priority_inheritance'
export const AI_RAW_METRIC_EXECUTION = 'execution'
export const AI_RAW_METRIC_MIGRATIONS = 'migrations'
export const AI_RAW_METRIC_BLOCKING = 'blocking'
export const AI_RAW_METRIC_SYNC = 'sync'
export const AI_RAW_METRIC_FINDINGS = 'findings'
export const AI_RAW_METRIC_NAMES = [
  AI_RAW_METRIC_PRIORITY,
  AI_RAW_METRIC_EXECUTION,
  AI_RAW_METRIC_MIGRATIONS,
  AI_RAW_METRIC_BLOCKING,
  AI_RAW_METRIC_SYNC,
  AI_RAW_METRIC_FINDINGS,
]
const RAW_METRIC_ALIASES = {
  priority_inheritance: AI_RAW_METRIC_PRIORITY,
  priority: AI_RAW_METRIC_PRIORITY,
  pi: AI_RAW_METRIC_PRIORITY,
  inversion: AI_RAW_METRIC_PRIORITY,
  inherit: AI_RAW_METRIC_PRIORITY,
  execution: AI_RAW_METRIC_EXECUTION,
  wcet: AI_RAW_METRIC_EXECUTION,
  cpu: AI_RAW_METRIC_EXECUTION,
  slices: AI_RAW_METRIC_EXECUTION,
  run: AI_RAW_METRIC_EXECUTION,
  migrations: AI_RAW_METRIC_MIGRATIONS,
  migration: AI_RAW_METRIC_MIGRATIONS,
  migr: AI_RAW_METRIC_MIGRATIONS,
  thrash: AI_RAW_METRIC_MIGRATIONS,
  blocking: AI_RAW_METRIC_BLOCKING,
  block: AI_RAW_METRIC_BLOCKING,
  wait: AI_RAW_METRIC_BLOCKING,
  latency: AI_RAW_METRIC_BLOCKING,
  sync: AI_RAW_METRIC_SYNC,
  mutex: AI_RAW_METRIC_SYNC,
  semaphore: AI_RAW_METRIC_SYNC,
  lock: AI_RAW_METRIC_SYNC,
  findings: AI_RAW_METRIC_FINDINGS,
  finding: AI_RAW_METRIC_FINDINGS,
  analysis: AI_RAW_METRIC_FINDINGS,
}
const MAX_RAW_METRIC_ROWS = 40
export const MAX_SEARCH_HITS = 40
const MAX_ANNOTATION_NOTE = 240

/** QTextBrowser truncates scheme:digits; use a path. */
const BTF_JUMP_HREF_RE = /btfjump:(?:\/\/)?(?:time\/)?([0-9]+(?:\.[0-9]+)?)/i
const BTF_HIGHLIGHT_HREF_RE = /btfhighlight:(?:\/\/)?(?:task\/)?(.+)$/i

export function btfJumpHref(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'btfjump:time/0'
  const token = Number.isInteger(n) || n === Math.trunc(n) ? String(Math.trunc(n)) : String(n)
  return `btfjump:time/${token}`
}

export function parseBtfJumpHref(href, dataJump) {
  if (dataJump != null && dataJump !== '' && Number.isFinite(Number(dataJump))) {
    return Number(dataJump)
  }
  const m = BTF_JUMP_HREF_RE.exec(String(href || ''))
  return m ? Number(m[1]) : NaN
}

export function btfHighlightHref(name) {
  return `btfhighlight:task/${encodeURIComponent(String(name || '').trim())}`
}

export function parseBtfHighlightHref(href, dataHighlight) {
  if (dataHighlight) return decodeURIComponent(String(dataHighlight))
  const m = BTF_HIGHLIGHT_HREF_RE.exec(String(href || '').trim())
  if (!m) return ''
  try {
    return decodeURIComponent(m[1].replace(/^\/+/, ''))
  } catch {
    return m[1]
  }
}

export const AI_TOOL_SYSTEM_ADDENDUM =
  'When the user asks to show, focus, inspect, zoom, highlight, annotate, '
  + 'export, investigate, explain, or jump to a time range, task, or core pair, '
  + 'you MUST invoke the '
  + 'matching viewer tool (native function call) in addition to your markdown '
  + 'answer. Valid tools: set_cursors, zoom_to_range, highlight_task, '
  + 'set_view_mode, open_corridor_inspector, add_annotation, query_raw_metric, '
  + 'export_report, clear_marks, reset_view, search_timeline, trigger_compare, '
  + 'investigate, detect_anomalies, correlate_events, find_critical_path, compare_performance, '
  + 'generate_report, check_budget, optimize, regression_explain, '
  + 'bookmark_finding, investigation_replay, what_if, optimize_experiment, analyze_traces, '
  + 'baseline_score, recommend_experiments, export_investigation, '
  + 'detect_priority_inversion, find_related_findings, compare_tasks. '
  + 'For root-cause or Investigate templates: call detect_anomalies and '
  + 'investigate(finding_id) first for a root-cause chain, then '
  + 'correlate_events / query_raw_metric / search_timeline / find_critical_path, then set_cursors '
  + '+ zoom_to_range + highlight_task on the worst episode before concluding. '
  + 'Use compare_performance for structured A vs B deltas (two tabs); '
  + 'regression_explain after compare to narrate the primary change. '
  + 'Use generate_report for a typed engineering markdown report, then '
  + 'export_report to save HTML/CSV. '
  + 'Use check_budget for WCET/response/deadline budgets; optimize for '
  + 'evidence-backed mitigations; what_if for heuristic slice-replay simulation; optimize_experiment to rank automatic candidates; '
  + 'analyze_traces to rank all open tabs; bookmark_finding to pin semantic '
  + 'marks; investigation_replay to summarise a completed investigation. '
  + 'Use baseline_score to compare current per-task metrics against a stored '
  + 'historical baseline (flags |z|>2); recommend_experiments to suggest '
  + 'simulation / firmware / measurement validation experiments; '
  + 'export_investigation to save the full investigation as JSON. '
  + 'Use detect_priority_inversion to scan priority-inheritance boost '
  + 'episodes for L/M/H inversion suspects (high/medium/low task, mutex, '
  + 'time, duration); find_related_findings to relate Analysis Findings by '
  + 'shared task, metric keyword, evidence-time proximity, or severity '
  + 'adjacency; compare_tasks for a side-by-side execution/blocking/'
  + 'migrations/priority delta table between two tasks. '
  + 'Use query_raw_metric when you need the exact per-task '
  + 'series (priority-inheritance episodes, execution slices, migrations, '
  + 'blocking gaps, sync STI, or findings lines) instead of the summarised '
  + 'findings card. Use search_timeline to locate STI, tags, task names, or '
  + 'pointers and get timestamps. Use clear_marks / reset_view to tidy the '
  + 'timeline before highlighting a new issue. Use trigger_compare when two '
  + 'tabs are open to pull Trace Compare diffs. Use add_annotation to pin a '
  + 'note on a spike. Use export_report to save findings, diagrams, and GUI '
  + 'state as HTML or CSV. '
  + 'For what-if / optimize_experiment, label results as heuristic (not FreeRTOS kernel). For optimize advice questions, label estimates as '
  + '\'Simulation / estimate — not measured behavior\' and cite evidence. '
  + 'Tool timestamps use the same numeric trace time '
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
    {
      type: 'function',
      function: {
        name: AI_TOOL_ADD_ANNOTATION,
        description:
          'Place an orange timeline annotation at a timestamp '
          + '(same unit as jump:TIME) and jump there. Use this to mark '
          + 'anomalous spikes, inversion windows, or other points of interest.',
        parameters: {
          type: 'object',
          properties: {
            time: {
              type: 'number',
              description: 'Trace time-unit timestamp.',
            },
            note: {
              type: 'string',
              description: 'Short annotation label shown on the Marks panel.',
            },
          },
          required: ['time', 'note'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_QUERY_RAW_METRIC,
        description:
          'Read the underlying per-task metric series for the current '
          + 'Statistics scope (cursor range when Limit to C1–Cn is on). '
          + 'Returns JSON samples — not a GUI change. Metrics: '
          + 'priority_inheritance, execution, migrations, blocking, '
          + 'sync, findings.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description:
                'Task display name (e.g. Low[266]), merge key, or numeric task id.',
            },
            metric: {
              type: 'string',
              enum: [...AI_RAW_METRIC_NAMES],
              description: 'Which series to return.',
            },
          },
          required: ['task', 'metric'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_EXPORT_REPORT,
        description:
          'Download a report bundling Analysis Findings, the AI '
          + 'conversation (including mermaid diagrams), annotations, '
          + 'and the current GUI state (cursors, highlight, view).',
        parameters: {
          type: 'object',
          properties: {
            format: {
              type: 'string',
              enum: ['html', 'csv', 'json'],
              description:
                'html (default), csv, or json (full investigation '
                + 'package — see export_investigation).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_CLEAR_MARKS,
        description:
          'Clear timeline clutter before focusing a new issue. '
          + 'all = annotations + cursors (default). everything also '
          + 'clears bookmarks.',
        parameters: {
          type: 'object',
          properties: {
            what: {
              type: 'string',
              enum: [...AI_CLEAR_MARKS_TARGETS],
              description:
                'annotations, cursors, bookmarks, all '
                + '(annotations+cursors), or everything.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_RESET_VIEW,
        description:
          'Fit the timeline to the full trace span and clear the '
          + 'task highlight. Does not remove cursors or annotations.',
        parameters: { type: 'object', properties: {} },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_SEARCH_TIMELINE,
        description:
          'Search the trace like Find (Ctrl+F). Returns matching '
          + 'timestamps for task names, STI/tag notes, intervals, '
          + 'lifecycle events, sync pointers, or migrations.',
        parameters: {
          type: 'object',
          properties: {
            query: {
              type: 'string',
              description: 'Text, tag value, pointer, or task name.',
            },
            mode: {
              type: 'string',
              enum: [...AI_FIND_MODES],
              description:
                'contains (default), exact, regex, sti, tags, '
                + 'intervals, lifecycle, pointers, migrations.',
            },
          },
          required: ['query'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_TRIGGER_COMPARE,
        description:
          'Compare two loaded trace tabs (Trace Compare). Returns '
          + 'diff tables as CSV. Optional tab names or 0-based indices.',
        parameters: {
          type: 'object',
          properties: {
            tab_a: {
              type: 'string',
              description: 'First tab name or 0-based tab index (default 0).',
            },
            tab_b: {
              type: 'string',
              description: 'Second tab name or 0-based tab index (default 1).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_INVESTIGATE,
        description:
          'Build a structured investigation context for one Analysis '
          + 'Finding (hypotheses, evidence chain, suggested next tools). '
          + 'Call this first during Investigate / Root cause workflows. '
          + 'finding_id may be the finding id, 1-based index, or title '
          + 'substring; omit to focus the top warning/error.',
        parameters: {
          type: 'object',
          properties: {
            finding_id: {
              type: 'string',
              description:
                'Finding id (e.g. thrashing), 1-based index, '
                + 'or title substring. Empty = top actionable finding.',
            },
            depth: {
              type: 'integer',
              description: 'Investigation depth 1–5 (default 2).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_DETECT_ANOMALIES,
        description:
          'Rank Analysis Findings as Critical / Warning / Info anomalies '
          + '(WCET spikes, thrashing, blocking, inversion, deadlines, …).',
        parameters: {
          type: 'object',
          properties: {
            limit: {
              type: 'integer',
              description: 'Max anomalies to return (1–40, default 10).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_CORRELATE_EVENTS,
        description:
          'Cross-task/cross-metric timeline correlation for a task: '
          + 'merge blocking, execution, migrations, sync, priority '
          + 'inheritance, and Find hits into one ordered event list.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description: 'Task display name, id, or merge key.',
            },
            around_time: {
              type: 'number',
              description: 'Optional center time (trace units).',
            },
            window: {
              type: 'number',
              description: 'Half-width around around_time (trace units).',
            },
          },
          required: ['task'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_FIND_CRITICAL_PATH,
        description:
          'Build a preempt/block/mutex critical path for a task around '
          + 'a timestamp by correlating blocking, sync, priority, execution, '
          + 'and migration events.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description: 'Task display name, id, or merge key.',
            },
            timestamp: {
              type: 'number',
              description: 'Optional center time (trace units).',
            },
            window: {
              type: 'number',
              description: 'Half-width around timestamp (default 2000).',
            },
          },
          required: ['task'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_COMPARE_PERFORMANCE,
        description:
          'Structured performance deltas between two open tabs '
          + '(regression rules + confidence). Prefer this over raw CSV '
          + 'when explaining A vs B; trigger_compare still opens the dialog.',
        parameters: {
          type: 'object',
          properties: {
            tab_a: {
              type: 'string',
              description: 'Candidate tab (index or name).',
            },
            tab_b: {
              type: 'string',
              description: 'Baseline tab (index or name).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_GENERATE_REPORT,
        description:
          'Build a typed engineering markdown report from Analysis '
          + 'Findings (executive / performance / root_cause / regression / '
          + 'optimization / bug / ci). Does not save a file — call '
          + 'export_report afterward to download HTML/CSV.',
        parameters: {
          type: 'object',
          properties: {
            report_type: {
              type: 'string',
              description:
                'executive|performance|root_cause|regression|'
                + 'optimization|bug|ci',
            },
            finding_id: {
              type: 'string',
              description: 'Optional focus finding id / index / title.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_CHECK_BUDGET,
        description:
          'Compare per-task WCET / response / deadline metrics against '
          + 'optional budgets. Omit tasks to let the host build rows from '
          + 'Analysis Findings task names.',
        parameters: {
          type: 'object',
          properties: {
            budgets: {
              type: 'object',
              description: 'Map of task → {wcet_us, response_us, deadline_us}.',
            },
            tasks: {
              type: 'array',
              description:
                'Optional metric rows: {task, wcet_us?, response_us?, '
                + 'deadline_us?, exec_max_us?, blocking_max_us?}.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_OPTIMIZE,
        description:
          'Evidence-backed optimization / mitigation ideas from Analysis '
          + 'Findings (labelled as estimates, not measured behavior).',
        parameters: {
          type: 'object',
          properties: {
            limit: {
              type: 'integer',
              description: 'Max recommendations (1–20, default 5).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_REGRESSION_EXPLAIN,
        description:
          'Explain the primary A vs B regression after comparing two '
          + 'open tabs (runs compare_performance then narrates).',
        parameters: {
          type: 'object',
          properties: {
            tab_a: {
              type: 'string',
              description: 'Candidate tab (index or name).',
            },
            tab_b: {
              type: 'string',
              description: 'Baseline tab (index or name).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_BOOKMARK_FINDING,
        description:
          'Pin a semantic investigation annotation at a timestamp '
          + '(root_cause / evidence / correlated / reference). GUI mutate.',
        parameters: {
          type: 'object',
          properties: {
            time: {
              type: 'number',
              description: 'Trace time-unit timestamp.',
            },
            kind: {
              type: 'string',
              enum: [...AI_BOOKMARK_KINDS],
              description: 'root_cause | evidence | correlated | reference',
            },
            note: {
              type: 'string',
              description: 'Optional short note appended to the label.',
            },
          },
          required: ['time', 'kind'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_INVESTIGATION_REPLAY,
        description:
          'Build a structured investigation-replay card (steps, tools '
          + 'run, conclusion, evidence times) for UI / export.',
        parameters: {
          type: 'object',
          properties: {
            finding_id: {
              type: 'string',
              description: 'Finding id / index / title substring.',
            },
            conclusion: {
              type: 'string',
              description: 'Short investigation conclusion text.',
            },
            tools_run: {
              type: 'array',
              items: { type: 'string' },
              description: 'Tool names already executed.',
            },
            evidence_times: {
              type: 'array',
              items: { type: 'number' },
              description: 'Evidence timestamps for cursor replay.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_WHAT_IF,
        description:
          'Heuristic what-if simulation from measured execution slices, '
          + 'migrations, blocking gaps, and core util (not FreeRTOS kernel).',
        parameters: {
          type: 'object',
          properties: {
            change: {
              type: 'string',
              description:
                'Proposed change, e.g. pin CS[28] to Core_0, '
                + 'raise priority, reduce mutex contention 50%.',
            },
            task: {
              type: 'string',
              description: 'Optional focus task (inferred from change when omitted).',
            },
          },
          required: ['change'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_OPTIMIZE_EXPERIMENT,
        description:
          'Run a small set of automatic optimization experiments '
          + '(pin/priority/contention/migration) via the heuristic '
          + 'simulator and rank by estimated cost improvement.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description: 'Focus task (defaults from top finding).',
            },
            limit: {
              type: 'integer',
              description: 'Max experiments (1–12, default 5).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_ANALYZE_TRACES,
        description:
          'Rank all loaded trace tabs by scheduling behavior '
          + '(load balance, migrations, missed ticks).',
        parameters: { type: 'object', properties: {} },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_BASELINE_SCORE,
        description:
          'Score current per-task metrics (WCET, blocking, '
          + 'migrations, response) against a stored historical '
          + 'baseline; flags entries where |z| > 2.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description: 'Optional focus task filter.',
            },
            baseline: {
              type: 'object',
              description:
                "Optional baseline profile object (defaults to the host's stored profile).",
            },
            snapshot: {
              type: 'object',
              description:
                'Optional {tasks: {task: {wcet_us, blocking_us, migrations, response_us}}} '
                + "snapshot (defaults to the host's current trace metrics).",
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_RECOMMEND_EXPERIMENTS,
        description:
          'Suggest validation experiments (simulation / firmware / '
          + 'measurement) for a finding or task, using heuristics '
          + '(thrash→pin, mutex→shorten critical section, etc.).',
        parameters: {
          type: 'object',
          properties: {
            finding_id: {
              type: 'string',
              description: 'Finding id / index / title substring.',
            },
            task: {
              type: 'string',
              description: 'Optional focus task.',
            },
            limit: {
              type: 'integer',
              description: 'Max experiments (1–20, default 5).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_EXPORT_INVESTIGATION,
        description:
          'Download the completed investigation (finding, tools '
          + 'run, queries, evidence, conclusion, confidence, '
          + 'alternatives) as a JSON package.',
        parameters: {
          type: 'object',
          properties: {
            finding_id: {
              type: 'string',
              description: 'Finding id / index / title substring.',
            },
            conclusion: {
              type: 'string',
              description: 'Short investigation conclusion text.',
            },
            tools_run: {
              type: 'array',
              items: { type: 'string' },
              description: 'Tool names already executed.',
            },
            evidence_times: {
              type: 'array',
              items: { type: 'number' },
              description: 'Evidence timestamps for cursor replay.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_DETECT_PRIORITY_INVERSION,
        description:
          'Scan priority-inheritance boost episodes flagged as '
          + 'inversion suspects (L/M/H pattern) and return '
          + 'high/medium/low task, mutex, time, and duration for each.',
        parameters: {
          type: 'object',
          properties: {
            task: {
              type: 'string',
              description:
                'Optional focus task (low or medium task name); omit to scan all tasks.',
            },
            window: {
              type: 'number',
              description:
                'Optional minimum episode duration (ns) to ignore trivial boosts.',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_FIND_RELATED_FINDINGS,
        description:
          'Relate Analysis Findings by shared task, metric keyword, '
          + 'evidence-time proximity, or severity adjacency.',
        parameters: {
          type: 'object',
          properties: {
            finding_id: {
              type: 'string',
              description: 'Focus finding id / index / title substring.',
            },
            task: {
              type: 'string',
              description: 'Optional task filter.',
            },
            metric: {
              type: 'string',
              description:
                'Optional metric filter: priority_inheritance|execution|migrations|blocking|sync|findings.',
            },
            window: {
              type: 'number',
              description:
                'Optional evidence-time proximity window (ns) relative to the focus finding.',
            },
            limit: {
              type: 'integer',
              description: 'Max related findings (1–40, default 10).',
            },
          },
        },
      },
    },
    {
      type: 'function',
      function: {
        name: AI_TOOL_COMPARE_TASKS,
        description:
          "Compare two tasks' execution / blocking / migrations / "
          + 'priority-inheritance metrics side by side with deltas.',
        parameters: {
          type: 'object',
          properties: {
            task_a: {
              type: 'string',
              description: 'First task display name, id, or merge key.',
            },
            task_b: {
              type: 'string',
              description: 'Second task display name, id, or merge key.',
            },
            metrics: {
              type: 'array',
              items: { type: 'string' },
              description:
                'Optional subset of execution|blocking|migrations|priority_inheritance (default all).',
            },
          },
          required: ['task_a', 'task_b'],
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

/** Best-effort text from an OpenAI-compatible assistant choice. */
export function assistantMessageText(message = null, choice = null) {
  const msg = message && typeof message === 'object' ? message : {}
  const choice0 = choice && typeof choice === 'object' ? choice : {}
  for (const src of [
    msg.content,
    msg.refusal,
    msg.reasoning_content,
    msg.reasoning,
    choice0.text,
    choice0.content,
  ]) {
    const text = messageContentText(src)
    if (text) return text
  }
  return ''
}

function choiceFinishReason(choice) {
  if (!choice || typeof choice !== 'object') return ''
  for (const key of ['finish_reason', 'finishReason']) {
    const val = choice[key]
    if (val != null && String(val).trim()) return String(val).trim().toLowerCase()
  }
  return ''
}

function usageCompletionTokens(body) {
  const usage = body && typeof body === 'object' ? body.usage : null
  if (!usage || typeof usage !== 'object') return -1
  for (const key of ['completion_tokens', 'completionTokens', 'output_tokens']) {
    if (!(key in usage)) continue
    const n = Number.parseInt(usage[key], 10)
    if (Number.isFinite(n)) return n
  }
  return -1
}

/**
 * Human-readable error when a chat reply has no text and no tool calls.
 * Avoid snake_case that Markdown italicizes in the AI log.
 */
export function emptyChatCompletionError(body, { hadTools = false } = {}) {
  const choices = body && typeof body === 'object' ? body.choices : null
  const choice0 = Array.isArray(choices) && choices[0] && typeof choices[0] === 'object'
    ? choices[0]
    : {}
  const reason = choiceFinishReason(choice0) || 'unknown'
  const tokens = usageCompletionTokens(body)
  const model = body && typeof body === 'object' ? String(body.model || '').trim() : ''
  const modelBit = model ? ` model=${model}` : ''
  const tokenBit = tokens >= 0 ? ` completion tokens=${tokens}` : ''

  if (reason === 'content_filter' || reason === 'safety') {
    return `The provider blocked the reply (safety / content filter).${modelBit}`
  }

  const tips = [
    `The model returned an empty assistant message (finish reason=${reason}${tokenBit}${modelBit}).`,
    'This is a known Gemini OpenAI-compat quirk with large prompts or tool calls.',
    'Retry, switch to a fuller model (for example gemini-2.5-flash), or narrow the Statistics scope.',
  ]
  if (hadTools) {
    tips.push(
      'Agent templates send tools; a plain Ask without tools may work when a lite model stalls.',
    )
  }
  return tips.join(' ')
}

export const GEMINI_SKIP_THOUGHT_SIGNATURE = 'skip_thought_signature_validator'

export function thoughtSignatureFromObj(obj) {
  if (!obj || typeof obj !== 'object') return ''
  for (const key of ['thought_signature', 'thoughtSignature']) {
    const val = obj[key]
    if (typeof val === 'string' && val.trim()) return val.trim()
  }
  const extra = obj.extra_content
  if (extra && typeof extra === 'object') {
    const google = extra.google && typeof extra.google === 'object' ? extra.google : {}
    for (const src of [google, extra]) {
      for (const key of ['thought_signature', 'thoughtSignature']) {
        const val = src[key]
        if (typeof val === 'string' && val.trim()) return val.trim()
      }
    }
  }
  const fn = obj.function
  if (fn && typeof fn === 'object') {
    for (const key of ['thought_signature', 'thoughtSignature']) {
      const val = fn[key]
      if (typeof val === 'string' && val.trim()) return val.trim()
    }
  }
  return ''
}

export function geminiThoughtExtraContent(signature) {
  return { google: { thought_signature: String(signature) } }
}

export function attachThoughtSignature(call, signature) {
  const sig = String(signature || '').trim()
  if (!sig || !call || typeof call !== 'object') return call
  const extra = call.extra_content && typeof call.extra_content === 'object'
    ? { ...call.extra_content }
    : {}
  const google = extra.google && typeof extra.google === 'object'
    ? { ...extra.google }
    : {}
  google.thought_signature = sig
  extra.google = google
  call.extra_content = extra
  return call
}

export function needsGeminiThoughtSignatures({ baseUrl = '', model = '', preset = '' } = {}) {
  void model
  const blob = `${baseUrl} ${preset}`.toLowerCase()
  return blob.includes('generativelanguage') || blob.includes('gemini')
}

export function ensureGeminiThoughtSignatures(messages) {
  const out = []
  for (const msg of messages || []) {
    if (!msg || typeof msg !== 'object') continue
    if (String(msg.role || '') !== 'assistant') {
      out.push(msg)
      continue
    }
    const calls = msg.tool_calls
    if (!Array.isArray(calls) || !calls.length) {
      out.push(msg)
      continue
    }
    const copied = { ...msg }
    copied.tool_calls = calls.map((call, i) => {
      if (!call || typeof call !== 'object') return call
      const c = { ...call }
      if (c.function && typeof c.function === 'object') c.function = { ...c.function }
      let sig = thoughtSignatureFromObj(c)
      if (i === 0 && !sig) sig = GEMINI_SKIP_THOUGHT_SIGNATURE
      if (sig) attachThoughtSignature(c, sig)
      return c
    })
    out.push(copied)
  }
  return out
}

function extractedToolCall({ id, name, arguments: args, signature = '' }) {
  const item = { id, name, arguments: args }
  if (signature) item.thought_signature = signature
  return item
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
      out.push(extractedToolCall({
        id: String(call.id || `call_${i}`),
        name,
        arguments: parseToolArguments(fn.arguments ?? call.arguments ?? call.args ?? call.input),
        signature: thoughtSignatureFromObj(call),
      }))
    })
  }
  const legacy = message.function_call
  if (legacy && typeof legacy === 'object' && legacy.name) {
    out.push(extractedToolCall({
      id: String(legacy.id || 'call_0'),
      name: String(legacy.name).trim(),
      arguments: parseToolArguments(legacy.arguments),
      signature: thoughtSignatureFromObj(legacy),
    }))
  }
  if (Array.isArray(message.content)) {
    message.content.forEach((part, i) => {
      if (!part || typeof part !== 'object') return
      const ptype = String(part.type || '')
      if (!['tool_use', 'function_call', 'tool_call'].includes(ptype)) return
      const name = String(part.name || '').trim()
      if (!name) return
      out.push(extractedToolCall({
        id: String(part.id || `part_${i}`),
        name,
        arguments: parseToolArguments(part.input ?? part.arguments ?? part.args),
        signature: thoughtSignatureFromObj(part),
      }))
    })
  }
  if (out.length && !String(out[0].thought_signature || '').trim()) {
    let fallback = thoughtSignatureFromObj(message)
    if (!fallback && Array.isArray(message.content)) {
      for (const part of message.content) {
        fallback = thoughtSignatureFromObj(part)
        if (fallback) break
      }
    }
    if (fallback) out[0].thought_signature = fallback
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

export function formatToolResultContent(result) {
  return JSON.stringify(result)
}

export function canonicalAssistantToolMessage(content, toolCalls) {
  const callsOut = []
  ;(toolCalls || []).forEach((call, i) => {
    if (!call || typeof call !== 'object') return
    const name = String(call.name || '').trim()
    if (!name) return
    const id = String(call.id || `call_${i}`).trim() || `call_${i}`
    const args = call.arguments
    const argS = typeof args === 'string'
      ? args
      : JSON.stringify(args && typeof args === 'object' ? args : {})
    const entry = {
      id,
      type: 'function',
      function: { name, arguments: argS },
    }
    const sig = String(call.thought_signature || '').trim() || thoughtSignatureFromObj(call)
    if (sig) attachThoughtSignature(entry, sig)
    callsOut.push(entry)
  })
  const text = messageContentText(content)
  const msg = { role: 'assistant', content: text || null }
  if (callsOut.length) msg.tool_calls = callsOut
  return msg
}

export function toolResultMessage({ toolCallId, name, content } = {}) {
  const cid = String(toolCallId || '').trim() || 'call_0'
  const fname = String(name || '').trim()
  let body
  if (typeof content === 'string') body = content
  else if (content && typeof content === 'object') body = formatToolResultContent(content)
  else body = formatToolResultContent({ ok: false, message: String(content ?? '') })
  const out = { role: 'tool', tool_call_id: cid, content: body }
  if (fname) out.name = fname
  return out
}

/** Gemini OpenAI-compat requires function_response.name on role=tool. */
export function normalizeToolChatMessages(messages) {
  const out = []
  let unused = []
  for (const msg of messages || []) {
    if (!msg || typeof msg !== 'object') continue
    const role = String(msg.role || '')
    if (role === 'assistant') {
      const extracted = extractToolCalls(msg)
      if (extracted.length) {
        const canon = canonicalAssistantToolMessage(msg.content, extracted)
        out.push(canon)
        unused = extractToolCalls(canon)
          .map(c => ({ id: String(c.id || ''), name: String(c.name || '').trim() }))
          .filter(c => c.id && c.name)
      } else {
        out.push({ ...msg })
        unused = []
      }
      continue
    }
    if (role === 'tool') {
      const copied = { ...msg }
      let cid = String(copied.tool_call_id || copied.id || '').trim()
      let name = String(copied.name || '').trim()
      if (!name && cid) {
        const idx = unused.findIndex(u => u.id === cid)
        if (idx >= 0) {
          name = unused[idx].name
          unused.splice(idx, 1)
        }
      }
      if (!name && unused.length) {
        const next = unused.shift()
        name = next.name
        if (!cid) cid = next.id
      } else if (name && cid) {
        unused = unused.filter(u => u.id !== cid)
      }
      if (cid) copied.tool_call_id = cid
      if (name) copied.name = name
      out.push(copied)
      continue
    }
    out.push({ ...msg })
  }
  return out
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
  if (name === AI_TOOL_ADD_ANNOTATION) {
    const t = Number(a.time)
    if (!Number.isFinite(t)) return { args: null, error: 'time must be a number' }
    let note = String(a.note || '').trim()
    if (!note) return { args: null, error: 'note must be a non-empty string' }
    if (note.length > MAX_ANNOTATION_NOTE) note = note.slice(0, MAX_ANNOTATION_NOTE).trimEnd()
    return { args: { time: t, note }, error: '' }
  }
  if (name === AI_TOOL_QUERY_RAW_METRIC) {
    const task = String(a.task || '').trim()
    if (!task) return { args: null, error: 'task must be a non-empty string' }
    const metric = normalizeRawMetric(a.metric)
    if (!metric) {
      return {
        args: null,
        error: `metric must be one of: ${AI_RAW_METRIC_NAMES.join(', ')}`,
      }
    }
    return { args: { task, metric }, error: '' }
  }
  if (name === AI_TOOL_EXPORT_REPORT) {
    let fmt = String(a.format || 'html').trim().toLowerCase()
    if (fmt === 'htm' || fmt === 'html') fmt = 'html'
    else if (fmt === 'csv') fmt = 'csv'
    else if (fmt === 'json') fmt = 'json'
    else return { args: null, error: 'format must be "html", "csv", or "json"' }
    return { args: { format: fmt }, error: '' }
  }
  if (name === AI_TOOL_CLEAR_MARKS) {
    let what = String(a.what || 'all').trim().toLowerCase()
    const aliases = {
      annotation: 'annotations', cursor: 'cursors', bookmark: 'bookmarks',
      marks: 'all', both: 'all',
    }
    what = aliases[what] || what
    if (!AI_CLEAR_MARKS_TARGETS.includes(what)) {
      return {
        args: null,
        error: `what must be one of: ${AI_CLEAR_MARKS_TARGETS.join(', ')}`,
      }
    }
    return { args: { what }, error: '' }
  }
  if (name === AI_TOOL_RESET_VIEW) return { args: {}, error: '' }
  if (name === AI_TOOL_SEARCH_TIMELINE) {
    const query = String(a.query || '').trim()
    if (!query) return { args: null, error: 'query must be a non-empty string' }
    let mode = String(a.mode || 'contains').trim().toLowerCase()
    if (mode === 'tag') mode = 'tags'
    if (!AI_FIND_MODES.includes(mode)) {
      return { args: null, error: `mode must be one of: ${AI_FIND_MODES.join(', ')}` }
    }
    return { args: { query, mode }, error: '' }
  }
  if (name === AI_TOOL_TRIGGER_COMPARE) {
    return {
      args: {
        tab_a: String(a.tab_a ?? '').trim(),
        tab_b: String(a.tab_b ?? '').trim(),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_INVESTIGATE) {
    let depth = Number(a.depth ?? 2)
    if (!Number.isFinite(depth)) {
      return { args: null, error: 'depth must be an integer 1–5' }
    }
    depth = Math.max(1, Math.min(5, Math.trunc(depth)))
    return {
      args: {
        finding_id: String(a.finding_id || '').trim(),
        depth,
      },
      error: '',
    }
  }
  if (name === AI_TOOL_DETECT_ANOMALIES) {
    let limit = Number(a.limit ?? 10)
    if (!Number.isFinite(limit)) {
      return { args: null, error: 'limit must be an integer 1–40' }
    }
    return { args: { limit: Math.max(1, Math.min(40, Math.trunc(limit))) }, error: '' }
  }
  if (name === AI_TOOL_CORRELATE_EVENTS) {
    const task = String(a.task || '').trim()
    if (!task) return { args: null, error: 'task must be a non-empty string' }
    const out = { task, around_time: null, window: 0 }
    if (a.around_time != null && String(a.around_time).trim() !== '') {
      const t = Number(a.around_time)
      if (!Number.isFinite(t)) return { args: null, error: 'around_time must be a number' }
      out.around_time = t
    }
    if (a.window != null && String(a.window).trim() !== '') {
      const w = Number(a.window)
      if (!Number.isFinite(w)) return { args: null, error: 'window must be a number' }
      out.window = Math.max(0, w)
    }
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_FIND_CRITICAL_PATH) {
    const task = String(a.task || '').trim()
    if (!task) return { args: null, error: 'task must be a non-empty string' }
    const out = { task, timestamp: null, window: 2000 }
    if (a.timestamp != null && String(a.timestamp).trim() !== '') {
      const t = Number(a.timestamp)
      if (!Number.isFinite(t)) return { args: null, error: 'timestamp must be a number' }
      out.timestamp = t
    }
    if (a.window != null && String(a.window).trim() !== '') {
      const w = Number(a.window)
      if (!Number.isFinite(w)) return { args: null, error: 'window must be a number' }
      out.window = Math.max(0, w)
    }
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_COMPARE_PERFORMANCE) {
    return {
      args: {
        tab_a: String(a.tab_a ?? '').trim(),
        tab_b: String(a.tab_b ?? '').trim(),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_GENERATE_REPORT) {
    return {
      args: {
        report_type: String(a.report_type || 'performance').trim().toLowerCase() || 'performance',
        finding_id: String(a.finding_id || '').trim(),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_CHECK_BUDGET) {
    if (a.budgets != null && (typeof a.budgets !== 'object' || Array.isArray(a.budgets))) {
      return { args: null, error: 'budgets must be an object' }
    }
    if (a.tasks != null && !Array.isArray(a.tasks)) {
      return { args: null, error: 'tasks must be an array' }
    }
    const out = {}
    if (a.budgets && typeof a.budgets === 'object') out.budgets = a.budgets
    if (Array.isArray(a.tasks)) {
      out.tasks = a.tasks.filter(t => t && typeof t === 'object' && !Array.isArray(t))
    }
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_OPTIMIZE) {
    let limit = Number(a.limit ?? 5)
    if (!Number.isFinite(limit)) {
      return { args: null, error: 'limit must be an integer 1–20' }
    }
    return { args: { limit: Math.max(1, Math.min(20, Math.trunc(limit))) }, error: '' }
  }
  if (name === AI_TOOL_REGRESSION_EXPLAIN) {
    return {
      args: {
        tab_a: String(a.tab_a ?? '').trim(),
        tab_b: String(a.tab_b ?? '').trim(),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_BOOKMARK_FINDING) {
    const t = Number(a.time)
    if (!Number.isFinite(t)) return { args: null, error: 'time must be a number' }
    let kind = String(a.kind || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
    if (['root', 'cause', 'rca'].includes(kind)) kind = 'root_cause'
    if (['corr', 'related'].includes(kind)) kind = 'correlated'
    if (['ok', 'normal', 'ref'].includes(kind)) kind = 'reference'
    if (!AI_BOOKMARK_KINDS.includes(kind)) {
      return { args: null, error: `kind must be one of: ${AI_BOOKMARK_KINDS.join(', ')}` }
    }
    let note = String(a.note || '').trim()
    if (note.length > MAX_ANNOTATION_NOTE) note = note.slice(0, MAX_ANNOTATION_NOTE).trimEnd()
    return { args: { time: t, kind, note }, error: '' }
  }
  if (name === AI_TOOL_INVESTIGATION_REPLAY) {
    const toolsRun = a.tools_run || []
    if (!Array.isArray(toolsRun)) {
      return { args: null, error: 'tools_run must be an array of strings' }
    }
    const evidence = a.evidence_times || []
    if (!Array.isArray(evidence)) {
      return { args: null, error: 'evidence_times must be an array of numbers' }
    }
    return {
      args: {
        finding_id: String(a.finding_id || '').trim(),
        conclusion: String(a.conclusion || '').trim(),
        tools_run: toolsRun.map(t => String(t)).filter(Boolean),
        evidence_times: asFloatList(evidence),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_WHAT_IF) {
    let change = String(a.change || '').trim()
    const task = String(a.task || a.task_id || a.task_name_or_id || '').trim()
    // Models often pass only a task id after "run what_if on task 9".
    if (!change && task) change = `pin ${task} to preferred core`
    if (!change) {
      return {
        args: null,
        error:
          'change must describe the experiment '
          + '(e.g. pin CS[9] to Core_0), or pass task for a default pin',
      }
    }
    return {
      args: {
        change,
        task,
      },
      error: '',
    }
  }
  if (name === AI_TOOL_OPTIMIZE_EXPERIMENT) {
    let limit = Number(a.limit ?? 5)
    if (!Number.isFinite(limit)) {
      return { args: null, error: 'limit must be an integer 1–12' }
    }
    return {
      args: {
        task: String(a.task || '').trim(),
        limit: Math.max(1, Math.min(12, Math.trunc(limit))),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_ANALYZE_TRACES) return { args: {}, error: '' }
  if (name === AI_TOOL_BASELINE_SCORE) {
    if (a.baseline != null && (typeof a.baseline !== 'object' || Array.isArray(a.baseline))) {
      return { args: null, error: 'baseline must be an object' }
    }
    if (a.snapshot != null && (typeof a.snapshot !== 'object' || Array.isArray(a.snapshot))) {
      return { args: null, error: 'snapshot must be an object' }
    }
    const out = { task: String(a.task || '').trim() }
    if (a.baseline && typeof a.baseline === 'object') out.baseline = a.baseline
    if (a.snapshot && typeof a.snapshot === 'object') out.snapshot = a.snapshot
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_RECOMMEND_EXPERIMENTS) {
    let limit = Number(a.limit ?? 5)
    if (!Number.isFinite(limit)) {
      return { args: null, error: 'limit must be an integer 1–20' }
    }
    return {
      args: {
        finding_id: String(a.finding_id || '').trim(),
        task: String(a.task || '').trim(),
        limit: Math.max(1, Math.min(20, Math.trunc(limit))),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_EXPORT_INVESTIGATION) {
    const toolsRun = a.tools_run || []
    if (!Array.isArray(toolsRun)) {
      return { args: null, error: 'tools_run must be an array of strings' }
    }
    const evidence = a.evidence_times || []
    if (!Array.isArray(evidence)) {
      return { args: null, error: 'evidence_times must be an array of numbers' }
    }
    return {
      args: {
        finding_id: String(a.finding_id || '').trim(),
        conclusion: String(a.conclusion || '').trim(),
        tools_run: toolsRun.map(t => String(t)).filter(Boolean),
        evidence_times: asFloatList(evidence),
      },
      error: '',
    }
  }
  if (name === AI_TOOL_DETECT_PRIORITY_INVERSION) {
    const out = { task: String(a.task || '').trim(), window: null }
    if (a.window != null && String(a.window).trim() !== '') {
      const w = Number(a.window)
      if (!Number.isFinite(w)) return { args: null, error: 'window must be a number' }
      out.window = Math.max(0, w)
    }
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_FIND_RELATED_FINDINGS) {
    let limit = Number(a.limit ?? 10)
    if (!Number.isFinite(limit)) {
      return { args: null, error: 'limit must be an integer 1–40' }
    }
    const out = {
      finding_id: String(a.finding_id || '').trim(),
      task: String(a.task || '').trim(),
      metric: String(a.metric || '').trim().toLowerCase(),
      window: null,
      limit: Math.max(1, Math.min(40, Math.trunc(limit))),
    }
    if (a.window != null && String(a.window).trim() !== '') {
      const w = Number(a.window)
      if (!Number.isFinite(w)) return { args: null, error: 'window must be a number' }
      out.window = Math.max(0, w)
    }
    return { args: out, error: '' }
  }
  if (name === AI_TOOL_COMPARE_TASKS) {
    const taskA = String(a.task_a || '').trim()
    const taskB = String(a.task_b || '').trim()
    if (!taskA || !taskB) {
      return { args: null, error: 'task_a and task_b must be non-empty strings' }
    }
    if (a.metrics != null && !Array.isArray(a.metrics)) {
      return { args: null, error: 'metrics must be an array' }
    }
    const out = { task_a: taskA, task_b: taskB }
    if (Array.isArray(a.metrics)) {
      out.metrics = a.metrics.map(m => String(m || '').trim().toLowerCase()).filter(Boolean)
    }
    return { args: out, error: '' }
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
  if (name === AI_TOOL_ADD_ANNOTATION) {
    const note = String(a.note || '').trim() || 'annotation'
    const t = Number(a.time)
    if (Number.isFinite(t)) return `Add annotation at ${fmtTraceNum(t)}: ${note}`
    return `Add annotation: ${note}`
  }
  if (name === AI_TOOL_QUERY_RAW_METRIC) {
    const task = String(a.task || '').trim() || '?'
    const metric = normalizeRawMetric(a.metric) || String(a.metric || '?')
    return `Query ${metric} for ${task}`
  }
  if (name === AI_TOOL_EXPORT_REPORT) {
    const fmt = String(a.format || 'html').trim().toLowerCase() || 'html'
    return `Export ${fmt} report`
  }
  if (name === AI_TOOL_CLEAR_MARKS) {
    return `Clear marks (${String(a.what || 'all').trim() || 'all'})`
  }
  if (name === AI_TOOL_RESET_VIEW) return 'Reset view'
  if (name === AI_TOOL_SEARCH_TIMELINE) {
    const q = String(a.query || '').trim()
    const mode = String(a.mode || 'contains').trim() || 'contains'
    const shown = q.length <= 40 ? q : `${q.slice(0, 37)}…`
    return `Search timeline [${mode}] ${JSON.stringify(shown)}`
  }
  if (name === AI_TOOL_TRIGGER_COMPARE) {
    const aTab = String(a.tab_a || '0').trim() || '0'
    const bTab = String(a.tab_b || '1').trim() || '1'
    return `Compare tabs ${aTab} vs ${bTab}`
  }
  if (name === AI_TOOL_INVESTIGATE) {
    const fid = String(a.finding_id || '').trim() || 'top finding'
    return `Investigate ${fid} (depth ${a.depth ?? 2})`
  }
  if (name === AI_TOOL_DETECT_ANOMALIES) {
    return `Detect anomalies (limit ${a.limit ?? 10})`
  }
  if (name === AI_TOOL_CORRELATE_EVENTS) {
    return `Correlate events for ${String(a.task || '?').trim() || '?'}`
  }
  if (name === AI_TOOL_FIND_CRITICAL_PATH) {
    const task = String(a.task || '?').trim() || '?'
    const ts = a.timestamp
    if (ts != null && Number.isFinite(Number(ts))) {
      const n = Number(ts)
      const label = Number.isInteger(n) ? String(Math.trunc(n)) : String(n)
      return `Find critical path for ${task} @ ${label}`
    }
    return `Find critical path for ${task}`
  }
  if (name === AI_TOOL_COMPARE_PERFORMANCE) {
    return 'Compare performance (A vs B)'
  }
  if (name === AI_TOOL_GENERATE_REPORT) {
    return `Generate ${String(a.report_type || 'performance')} report`
  }
  if (name === AI_TOOL_CHECK_BUDGET) {
    const n = Array.isArray(a.tasks) ? a.tasks.length : 0
    return n ? `Check budget (${n} task row(s))` : 'Check budget'
  }
  if (name === AI_TOOL_OPTIMIZE) {
    return `Optimize (limit ${a.limit ?? 5})`
  }
  if (name === AI_TOOL_REGRESSION_EXPLAIN) {
    return 'Explain regression (A vs B)'
  }
  if (name === AI_TOOL_BOOKMARK_FINDING) {
    const kind = String(a.kind || 'evidence').trim() || 'evidence'
    const t = Number(a.time)
    if (Number.isFinite(t)) return `Bookmark ${kind} at ${fmtTraceNum(t)}`
    return `Bookmark ${kind}`
  }
  if (name === AI_TOOL_INVESTIGATION_REPLAY) {
    const fid = String(a.finding_id || '').trim() || 'top finding'
    return `Investigation replay (${fid})`
  }
  if (name === AI_TOOL_WHAT_IF) {
    const change = String(a.change || '').trim()
    const shown = change.length <= 40 ? change : `${change.slice(0, 37)}…`
    return shown ? `What-if: ${shown}` : 'What-if'
  }
  if (name === AI_TOOL_OPTIMIZE_EXPERIMENT) {
    const task = String(a.task || '').trim()
    return `Optimize experiment (${task || 'auto'}, limit ${a.limit ?? 5})`
  }
  if (name === AI_TOOL_ANALYZE_TRACES) return 'Analyze loaded traces'
  if (name === AI_TOOL_BASELINE_SCORE) {
    const task = String(a.task || '').trim()
    return `Baseline score (${task || 'all tasks'})`
  }
  if (name === AI_TOOL_RECOMMEND_EXPERIMENTS) {
    const fid = String(a.finding_id || '').trim()
    const task = String(a.task || '').trim()
    const label = fid || task || 'top finding'
    return `Recommend experiments (${label})`
  }
  if (name === AI_TOOL_EXPORT_INVESTIGATION) return 'Export investigation (JSON)'
  if (name === AI_TOOL_DETECT_PRIORITY_INVERSION) {
    const task = String(a.task || '').trim()
    return `Detect priority inversion (${task || 'all tasks'})`
  }
  if (name === AI_TOOL_FIND_RELATED_FINDINGS) {
    const fid = String(a.finding_id || '').trim()
    const task = String(a.task || '').trim()
    const metric = String(a.metric || '').trim()
    const label = fid || task || metric || 'top finding'
    return `Find related findings (${label})`
  }
  if (name === AI_TOOL_COMPARE_TASKS) {
    const aTask = String(a.task_a || '?').trim() || '?'
    const bTask = String(a.task_b || '?').trim() || '?'
    return `Compare tasks ${aTask} vs ${bTask}`
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

const CORE_NUM_RE = /^(?:core[\s_-]*)?(\d+)$/i
const CORE_SHORT_RE = /^c(\d+)$/i

function coreMatchAliases(raw) {
  const text = String(raw || '').trim()
  if (!text) return []
  const aliases = [text]
  const compact = text.replace(/[\s_-]+/g, '_')
  if (!aliases.includes(compact)) aliases.push(compact)
  const spaced = text.replace(/_/g, ' ')
  if (!aliases.includes(spaced)) aliases.push(spaced)
  const m = CORE_NUM_RE.exec(text) || CORE_SHORT_RE.exec(text)
  if (m) {
    const n = String(Number(m[1]))
    aliases.push(n, `Core_${n}`, `core_${n}`, `Core ${n}`, `c${n}`, `C${n}`)
  }
  return [...new Set(aliases.filter(Boolean))]
}

export function resolveCoreKey(coreNameOrId, candidates) {
  const want = String(coreNameOrId || '').trim()
  if (!want) return null
  const names = (candidates || []).map(c => String(c || '')).filter(Boolean)
  if (!names.length) return null
  if (names.includes(want)) return want
  const lower = new Map(names.map(n => [n.toLowerCase(), n]))
  if (lower.has(want.toLowerCase())) return lower.get(want.toLowerCase())
  const byAlias = new Map()
  for (const name of names) {
    for (const alias of coreMatchAliases(name)) {
      const key = alias.toLowerCase()
      const list = byAlias.get(key) || []
      if (!list.includes(name)) list.push(name)
      byAlias.set(key, list)
    }
  }
  const hits = []
  for (const alias of coreMatchAliases(want)) {
    for (const orig of byAlias.get(alias.toLowerCase()) || []) {
      if (!hits.includes(orig)) hits.push(orig)
    }
  }
  return hits.length ? hits[0] : null
}

export function normalizeTaskLookupQuery(taskNameOrId) {
  let text = String(taskNameOrId || '').trim()
  if (!text) return ''
  text = text.replace(/\s*\((?:core\s*)?\d+\)\s*$/i, '').trim() || text
  const m = /([A-Za-z_][\w]*\[\d+\])/.exec(text)
  return m ? m[1] : text
}

export function resolveTaskKey(taskNameOrId, candidates) {
  const raw = String(taskNameOrId || '').trim()
  if (!raw) return null
  const names = (candidates || []).map(c => String(c || '')).filter(Boolean)
  if (!names.length) return null
  const queries = [raw]
  const norm = normalizeTaskLookupQuery(raw)
  if (norm && !queries.includes(norm)) queries.push(norm)

  const lower = new Map(names.map(n => [n.toLowerCase(), n]))
  const byAlias = new Map()
  for (const name of names) {
    for (const alias of taskMatchAliases(name)) {
      const key = alias.toLowerCase()
      const list = byAlias.get(key) || []
      if (!list.includes(name)) list.push(name)
      byAlias.set(key, list)
    }
  }
  const uniq = arr => [...new Set(arr)]
  for (const want of queries) {
    if (names.includes(want)) return want
    if (lower.has(want.toLowerCase())) return lower.get(want.toLowerCase())
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
    const prefixU = uniq(prefix)
    if (prefixU.length === 1) return prefixU[0]
    const containsU = uniq(contains)
    if (containsU.length === 1) return containsU[0]
  }
  return null
}

export function normalizeRawMetric(name) {
  const want = String(name || '').trim().toLowerCase().replace(/[-\s]/g, '_')
  return RAW_METRIC_ALIASES[want] || ''
}

export function isQueryTool(name) {
  return [
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_SEARCH_TIMELINE,
    AI_TOOL_TRIGGER_COMPARE,
    AI_TOOL_INVESTIGATE,
    AI_TOOL_DETECT_ANOMALIES,
    AI_TOOL_CORRELATE_EVENTS,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_COMPARE_PERFORMANCE,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_CHECK_BUDGET,
    AI_TOOL_OPTIMIZE,
    AI_TOOL_REGRESSION_EXPLAIN,
    AI_TOOL_INVESTIGATION_REPLAY,
    AI_TOOL_WHAT_IF,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_TOOL_ANALYZE_TRACES,
    AI_TOOL_BASELINE_SCORE,
    AI_TOOL_RECOMMEND_EXPERIMENTS,
    AI_TOOL_DETECT_PRIORITY_INVERSION,
    AI_TOOL_FIND_RELATED_FINDINGS,
    AI_TOOL_COMPARE_TASKS,
  ].includes(String(name || ''))
}

export function isExportTool(name) {
  return String(name || '') === AI_TOOL_EXPORT_REPORT || String(name || '') === AI_TOOL_EXPORT_INVESTIGATION
}

export function toolMutatesGui(name) {
  return [
    AI_TOOL_SET_CURSORS,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_OPEN_CORRIDOR,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_BOOKMARK_FINDING,
    AI_TOOL_CLEAR_MARKS,
    AI_TOOL_RESET_VIEW,
  ].includes(String(name || ''))
}

export function toolBatchAutoRuns(tools) {
  const names = (tools || []).map(t => String(t?.name || ''))
  return names.length > 0 && names.every(isQueryTool)
}

function csvEscape(value) {
  const s = value == null ? '' : String(value)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export function buildAiReportCsv({
  meta = {}, gui = {}, findings = '', annotations = [], conversation = '',
} = {}) {
  const rows = [['section', 'key', 'value']]
  for (const [k, v] of Object.entries(meta || {})) rows.push(['meta', k, v])
  const guiD = { ...(gui || {}) }
  const cursors = guiD.cursors
  delete guiD.cursors
  delete guiD.annotations
  if (cursors != null) {
    rows.push(['gui', 'cursors', Array.isArray(cursors) ? cursors.join(';') : String(cursors)])
  }
  for (const [k, v] of Object.entries(guiD)) rows.push(['gui', k, v])
  let anns = Array.isArray(annotations) ? annotations : []
  if (!anns.length && Array.isArray(gui?.annotations)) anns = gui.annotations
  for (const ann of anns) {
    if (!ann || typeof ann !== 'object') continue
    rows.push(['annotation', ann.time ?? '', ann.note ?? ''])
  }
  String(findings || '').split('\n').forEach((line, i) => {
    if (line.trim()) rows.push(['finding', String(i + 1), line])
  })
  String(conversation || '').split('\n').forEach((line, i) => {
    rows.push(['conversation', String(i + 1), line])
  })
  return `${rows.map(r => r.map(csvEscape).join(',')).join('\n')}\n`
}

function htmlEscape(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function buildAiReportHtml({
  meta = {}, gui = {}, findings = '', annotations = [], conversationHtml = '',
} = {}) {
  const stamp = (() => {
    const d = new Date()
    const p = n => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
      + ` ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  })()
  const metaRows = Object.entries(meta || {}).map(
    ([k, v]) => `<tr><th>${htmlEscape(k)}</th><td>${htmlEscape(v)}</td></tr>`,
  ).join('')
  const guiD = { ...(gui || {}) }
  let anns = Array.isArray(annotations) ? annotations : []
  if (!anns.length && Array.isArray(guiD.annotations)) anns = guiD.annotations
  delete guiD.annotations
  const guiRows = Object.entries(guiD).map(([k, v]) => {
    let val = v
    if (k === 'cursors' && Array.isArray(v)) val = v.join(', ')
    return `<tr><th>${htmlEscape(k)}</th><td>${htmlEscape(val)}</td></tr>`
  }).join('')
  const annRows = anns.filter(a => a && typeof a === 'object').map(
    a => `<tr><td>${htmlEscape(a.time ?? '')}</td><td>${htmlEscape(a.note ?? '')}</td></tr>`,
  ).join('') || '<tr><td colspan="2">None</td></tr>'
  const findingsBody = String(findings || '').trim()
    ? `<pre>${htmlEscape(findings)}</pre>`
    : '<p>No findings for the current scope.</p>'
  const conv = String(conversationHtml || '').trim()
  const body = (
    `<section class="report-card">
<h2>Report metadata</h2>
<table class="meta-table">${metaRows || '<tr><td>None</td></tr>'}</table>
</section>
<section class="report-card">
<h2>GUI state</h2>
<table class="gui-table">${guiRows || '<tr><td>None</td></tr>'}</table>
</section>
<section class="report-card">
<h2>Annotations</h2>
<table class="ann-table"><tr><th>Time</th><th>Note</th></tr>${annRows}</table>
</section>
<section class="report-card">
<h2>Analysis Findings</h2>
${findingsBody}
</section>
<section class="report-card">
<h2>Conversation</h2>
${conv}
</section>
`
  )
  return btfHtmlReportDocument('AI Diagnostic Report', body, {
    subtitle: `Saved ${stamp}`,
    docTitle: 'BTFViewer — AI Report',
  })
}

function inTimeRange(t, lo, hi) {
  if (lo == null || hi == null) return true
  const v = Number(t)
  return Number.isFinite(v) && v >= lo && v <= hi
}

function overlapsRange(start, stop, lo, hi) {
  if (lo == null || hi == null) return true
  const a = Number(start)
  const b = Number(stop)
  return Number.isFinite(a) && Number.isFinite(b) && b > lo && a < hi
}

function mapGet(mapLike, key) {
  if (!mapLike) return undefined
  if (typeof mapLike.get === 'function') return mapLike.get(key)
  return mapLike[key]
}

function mapKeys(mapLike) {
  if (!mapLike) return []
  if (typeof mapLike.keys === 'function') return [...mapLike.keys()]
  return Object.keys(mapLike)
}

function taskCandidatesFromTrace(trace) {
  const names = [...(trace?.tasks || [])].map(String)
  for (const k of mapKeys(trace?.segByMergeKey)) names.push(String(k))
  const repr = trace?.taskRepr
  if (repr && typeof repr.forEach === 'function') {
    repr.forEach((v, k) => {
      if (v) names.push(String(v))
      names.push(String(k))
    })
  } else if (repr && typeof repr === 'object') {
    for (const [k, v] of Object.entries(repr)) {
      if (v) names.push(String(v))
      names.push(String(k))
    }
  }
  return names
}

function segsForMk(trace, mk) {
  return [...(mapGet(trace?.segByMergeKey, mk) || [])]
}

function mediumLabels(ep) {
  const list = ep?.mediumTasks || ep?.medium_tasks || []
  return list.map((item) => {
    if (typeof item === 'string') return item
    if (item && typeof item === 'object') return String(item.label || item.mk || '')
    return ''
  }).filter(Boolean)
}

function lookupAliases(task) {
  const out = []
  for (const alias of taskMatchAliases(String(task || ''))) {
    if (alias && !out.includes(alias)) out.push(alias)
    const low = alias.toLowerCase()
    if (low && !out.includes(low)) out.push(low)
  }
  return out
}

export function searchTimelineHits(trace, query, mode = 'contains', annotations = []) {
  const q = String(query || '').trim()
  if (!q) return { ok: false, message: 'query must be a non-empty string' }
  if (!trace) return { ok: false, message: 'No trace loaded' }
  let findMode = String(mode || 'contains').toLowerCase()
  if (findMode === 'tags' || findMode === 'tag' || findMode === 'sti') findMode = 'sti'
  const { hits, error } = computeFindHits(trace, q, findMode, annotations || [])
  if (error) return { ok: false, message: error }
  const times = [...(hits || [])]
  return {
    ok: true,
    message: `${times.length} match(es) for ${JSON.stringify(q)} (${findMode})`,
    data: {
      times: times.slice(0, MAX_SEARCH_HITS),
      count: times.length,
      mode: findMode,
      truncated: times.length > MAX_SEARCH_HITS,
    },
  }
}

export function queryRawMetric(trace, task, metric, {
  lo = null, hi = null, findingsText = '',
} = {}) {
  if (!trace) return { ok: false, message: 'No trace loaded' }
  const metricId = normalizeRawMetric(metric)
  if (!metricId) {
    return {
      ok: false,
      message: `metric must be one of: ${AI_RAW_METRIC_NAMES.join(', ')}`,
    }
  }
  const resolved = resolveTaskKey(String(task || '').trim(), taskCandidatesFromTrace(trace))
  if (!resolved) return { ok: false, message: `Unknown task ${JSON.stringify(task)}` }
  const mk = taskMergeKey(resolved)
  let label = ''
  const repr = trace.taskRepr
  if (repr && typeof repr.get === 'function') label = String(repr.get(mk) || repr.get(resolved) || '')
  else if (repr && typeof repr === 'object') label = String(repr[mk] || repr[resolved] || '')
  if (!label) label = String(resolved)
  const scope = lo != null && hi != null ? { lo, hi } : null
  const data = { task: label, task_key: mk, metric: metricId, scope }

  if (metricId === AI_RAW_METRIC_FINDINGS) {
    const aliases = [...lookupAliases(task), ...lookupAliases(label), label, String(resolved)].filter(Boolean)
    const hits = String(findingsText || '').split('\n').filter((line) => {
      const low = line.toLowerCase()
      return aliases.some(a => low.includes(String(a).toLowerCase()))
    })
    data.rows = hits.slice(0, MAX_RAW_METRIC_ROWS)
    data.count = hits.length
    data.truncated = hits.length > MAX_RAW_METRIC_ROWS
    return { ok: true, message: `${hits.length} finding line(s) mentioning ${label}`, data }
  }

  if (metricId === AI_RAW_METRIC_PRIORITY) {
    let eps = [...(mapGet(trace.priorityEpisodesByMk, mk) || [])]
    if (!eps.length) {
      for (const ep of trace.priorityEpisodes || []) {
        if ((ep.mk || '') === mk) eps.push(ep)
      }
    }
    const rows = []
    for (const ep of eps) {
      const start = ep.startNs ?? ep.start_ns
      const stop = ep.stopNs ?? ep.stop_ns
      if (!overlapsRange(start, stop, lo, hi)) continue
      rows.push({
        start,
        stop,
        duration: start != null && stop != null ? Number(stop) - Number(start) : null,
        base_pri: ep.basePri ?? ep.base_pri,
        peak_pri: ep.peakPri ?? ep.peak_pri,
        inherited: Boolean(ep.inherited),
        inversion_suspect: Boolean(ep.inversionSuspect ?? ep.inversion_suspect),
        medium_tasks: mediumLabels(ep),
        pattern: ep.pattern || '',
      })
    }
    data.episodes = rows.slice(0, MAX_RAW_METRIC_ROWS)
    data.count = rows.length
    data.truncated = rows.length > MAX_RAW_METRIC_ROWS
    return { ok: true, message: `${rows.length} priority inheritance episode(s) for ${label}`, data }
  }

  if (metricId === AI_RAW_METRIC_EXECUTION) {
    const segs = segsForMk(trace, mk)
    const samples = []
    let total = 0
    let maxDur = 0
    let maxAt = null
    for (const seg of segs) {
      const start = seg.start
      const end = seg.end
      if (!overlapsRange(start, end, lo, hi)) continue
      let dur = Number(end) - Number(start)
      if (lo != null && hi != null) {
        dur = Math.max(0, Math.min(Number(end), Number(hi)) - Math.max(Number(start), Number(lo)))
      }
      total += dur
      if (dur >= maxDur) {
        maxDur = dur
        maxAt = start
      }
      samples.push({ start, stop: end, duration: dur, core: seg.core || '' })
    }
    data.count = samples.length
    data.total = total
    data.max = maxDur
    data.max_at = maxAt
    data.mean = samples.length ? total / samples.length : 0
    data.slices = samples.slice(0, MAX_RAW_METRIC_ROWS)
    data.truncated = samples.length > MAX_RAW_METRIC_ROWS
    return { ok: true, message: `${samples.length} execution slice(s) for ${label}`, data }
  }

  if (metricId === AI_RAW_METRIC_MIGRATIONS) {
    let migs = [...(mapGet(trace.migrationsByMk, mk) || [])]
    if (!migs.length) {
      for (const m of trace.migrations || []) {
        if ((m.mergeKey || m.merge_key) === mk) migs.push(m)
      }
    }
    const rows = []
    for (const m of migs) {
      const ns = m.ns
      if (!inTimeRange(ns, lo, hi)) continue
      rows.push({
        time: ns,
        from: m.fromCore || m.from_core || '',
        to: m.toCore || m.to_core || '',
      })
    }
    data.events = rows.slice(0, MAX_RAW_METRIC_ROWS)
    data.count = rows.length
    data.truncated = rows.length > MAX_RAW_METRIC_ROWS
    return { ok: true, message: `${rows.length} migration(s) for ${label}`, data }
  }

  if (metricId === AI_RAW_METRIC_BLOCKING) {
    const segs = [...segsForMk(trace, mk)].sort((a, b) => a.start - b.start)
    const gaps = []
    for (let i = 1; i < segs.length; i++) {
      const prev = segs[i - 1]
      const nxt = segs[i]
      const gap = Number(nxt.start) - Number(prev.end)
      if (gap <= 0 || !inTimeRange(nxt.start, lo, hi)) continue
      gaps.push({ time: nxt.start, gap })
    }
    data.count = gaps.length
    data.max = gaps.reduce((m, g) => Math.max(m, g.gap), 0)
    data.total = gaps.reduce((s, g) => s + g.gap, 0)
    data.gaps = gaps.slice(0, MAX_RAW_METRIC_ROWS)
    data.truncated = gaps.length > MAX_RAW_METRIC_ROWS
    return { ok: true, message: `${gaps.length} blocking gap(s) for ${label}`, data }
  }

  const aliases = [...lookupAliases(task), ...lookupAliases(label)].map(a => String(a).toLowerCase())
  const rows = []
  for (const ev of trace.stiEvents || []) {
    if (!inTimeRange(ev.time, lo, hi)) continue
    const blob = `${ev.note || ''} ${ev.target || ''} ${ev.event || ''}`.toLowerCase()
    if (!aliases.some(a => blob.includes(a))) continue
    rows.push({
      time: ev.time,
      core: ev.core || '',
      target: ev.target || '',
      event: ev.event || '',
      note: ev.note || '',
    })
  }
  data.events = rows.slice(0, MAX_RAW_METRIC_ROWS)
  data.count = rows.length
  data.truncated = rows.length > MAX_RAW_METRIC_ROWS
  return { ok: true, message: `${rows.length} sync STI event(s) for ${label}`, data }
}

export function maxToolRounds(templateId = '') {
  return maxToolRoundsForTemplate(templateId, 4)
}

export function investigateFinding(findings, findingId = '', { depth = 2 } = {}) {
  const ctx = buildInvestigateContext(findings, findingId, { depth })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

function eventsFromMetricPayload(payload, metric, task) {
  const data = payload && typeof payload === 'object' ? payload.data : null
  if (!data || typeof data !== 'object') return []
  const out = []
  if (metric === AI_RAW_METRIC_PRIORITY) {
    for (const ep of data.episodes || []) {
      const t = ep.start
      if (t == null) continue
      let detail = `PI base=${ep.base_pri} peak=${ep.peak_pri}`
      if (ep.inversion_suspect) detail += ' inversion_suspect'
      out.push({ time: t, kind: 'priority', detail, task })
    }
  } else if (metric === AI_RAW_METRIC_EXECUTION) {
    for (const sl of data.slices || []) {
      const t = sl.start
      if (t == null) continue
      out.push({
        time: t,
        kind: 'execution',
        detail: `dur=${sl.duration} core=${sl.core}`,
        task,
        core: sl.core || '',
      })
    }
  } else if (metric === AI_RAW_METRIC_MIGRATIONS) {
    for (const row of data.events || data.migrations || []) {
      const t = row.time
      if (t == null) continue
      out.push({
        time: t,
        kind: 'migration',
        detail: `${row.from}→${row.to}`,
        task,
      })
    }
  } else if (metric === AI_RAW_METRIC_BLOCKING) {
    for (const row of data.gaps || []) {
      const t = row.start ?? row.time
      if (t == null) continue
      out.push({
        time: t,
        kind: 'blocking',
        detail: String(row.duration ?? row.gap ?? 'block'),
        task,
      })
    }
  } else if (metric === AI_RAW_METRIC_SYNC) {
    for (const row of data.events || []) {
      const t = row.time
      if (t == null) continue
      out.push({
        time: t,
        kind: 'sync',
        detail: `${row.event || ''} ${row.target || ''} ${row.note || ''}`.trim(),
        task,
        core: row.core || '',
      })
    }
  }
  return out
}

export function correlateTaskEvents(trace, task, {
  aroundTime = null,
  window = 0,
  lo = null,
  hi = null,
  findingsText = '',
  annotations = [],
} = {}) {
  if (!trace) return { ok: false, message: 'No trace loaded' }
  const taskName = String(task || '').trim()
  if (!taskName) return { ok: false, message: 'task is required' }
  const events = []
  for (const metric of [
    AI_RAW_METRIC_BLOCKING,
    AI_RAW_METRIC_EXECUTION,
    AI_RAW_METRIC_MIGRATIONS,
    AI_RAW_METRIC_SYNC,
    AI_RAW_METRIC_PRIORITY,
  ]) {
    const payload = queryRawMetric(trace, taskName, metric, {
      lo, hi, findingsText,
    })
    if (payload.ok) events.push(...eventsFromMetricPayload(payload, metric, taskName))
  }
  const search = searchTimelineHits(trace, taskName, 'contains', annotations)
  if (search.ok) {
    for (const t of search.data?.times || []) {
      const n = Number(t)
      if (!Number.isFinite(n)) continue
      events.push({ time: n, kind: 'search', detail: taskName, task: taskName })
    }
  }
  const ctx = buildCorrelationTimeline(events, {
    task: taskName,
    aroundTime,
    window: Number(window) || 0,
  })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function findCriticalPathTask(trace, task, {
  timestamp = null,
  window = 2000,
  annotations = [],
} = {}) {
  if (!trace) return { ok: false, message: 'No trace loaded' }
  const taskName = String(task || '').trim()
  if (!taskName) return { ok: false, message: 'task is required' }
  const corr = correlateTaskEvents(trace, taskName, {
    aroundTime: timestamp,
    window: Number(window) || 2000,
    annotations,
  })
  if (!corr.ok) return corr
  const data = corr.data && typeof corr.data === 'object' ? corr.data : {}
  const ctx = buildCriticalPath(data.events || [], {
    task: taskName,
    timestamp,
  })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const out = { ...ctx }
  delete out.ok
  delete out.message
  out.correlation = data.correlation
  return { ok, message, data: out }
}

export function detectAnomaliesFinding(findings, { limit = 10 } = {}) {
  const ctx = detectAnomalies(findings, { limit })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function generateReportFinding(findings, {
  reportType = 'performance', findingId = '', compare = null,
} = {}) {
  const ctx = generateStructuredReport(findings, {
    reportType, focusId: findingId, compare,
  })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function comparePerformanceTabs(candidateSummary, baselineSummary, {
  labelA = 'A', labelB = 'B',
} = {}) {
  const snapA = snapshotFromSummary(candidateSummary || {}, { name: labelA })
  const snapB = snapshotFromSummary(baselineSummary || {}, { name: labelB })
  const ctx = comparePerformanceMetrics(snapA, snapB, { labelA, labelB })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function budgetTaskRowsFromFindings(findings) {
  const rows = []
  const seen = new Set()
  for (const a of (detectAnomalies(findings || [], { limit: 40 }).anomalies || [])) {
    const task = String(a.task || '').trim()
    if (!task || seen.has(task)) continue
    seen.add(task)
    rows.push({ task })
  }
  return rows
}

export function checkBudgetFinding(tasks = null, budgets = null, { findings = null } = {}) {
  let rows = Array.isArray(tasks) ? [...tasks] : []
  if (!rows.length) rows = budgetTaskRowsFromFindings(findings || [])
  const ctx = checkTaskBudgets(rows, budgets)
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function optimizeFinding(findings, { limit = 5 } = {}) {
  const ctx = buildOptimizationAdvice(findings, { limit })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function explainRegressionFromCompare(compare, findings = null) {
  const ctx = explainRegression(compare, findings)
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export { formatBookmarkLabel }

export function investigationReplayFinding(findings, findingId = '', {
  conclusion = '', toolsRun = null, evidenceTimes = null, plan = null,
} = {}) {
  const finding = (findings?.length || findingId)
    ? resolveFinding(findings || [], findingId)
    : null
  const ctx = buildInvestigationReplay({
    finding,
    plan,
    toolsRun,
    conclusion,
    evidenceTimes,
  })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function gatherSimulationInputs(trace, task, {
  lo = null, hi = null, findingsText = '',
} = {}) {
  let slices = []
  let migrations = []
  let blockingGaps = []
  let label = String(task || '').trim()
  if (label && trace) {
    const exec = queryRawMetric(trace, label, 'execution', { lo, hi, findingsText })
    if (exec.ok && exec.data) {
      slices = [...(exec.data.slices || [])]
      label = String(exec.data.task || label)
    }
    const mig = queryRawMetric(trace, label, 'migrations', { lo, hi, findingsText })
    if (mig.ok && mig.data) migrations = [...(mig.data.events || [])]
    const blk = queryRawMetric(trace, label, 'blocking', { lo, hi, findingsText })
    if (blk.ok && blk.data) blockingGaps = [...(blk.data.gaps || [])]
  }
  let coreUtils = []
  if (trace) {
    try {
      coreUtils = coreUtilPctRows(trace, lo, hi).map(r => [r.core, r.pct])
    } catch (_) {
      coreUtils = []
    }
  }
  return { task: label, slices, migrations, blockingGaps, coreUtils }
}

export function whatIfEstimate(change, {
  task = '', findings = null, baselineMetrics = null,
  slices = null, migrations = null, blockingGaps = null, coreUtils = null,
} = {}) {
  const hasMetrics = !!(
    (slices && slices.length)
    || (migrations && migrations.length)
    || (blockingGaps && blockingGaps.length)
    || (coreUtils && coreUtils.length)
  )
  const ctx = hasMetrics
    ? simulateWhatIf({
      change, task, slices, migrations, blockingGaps, coreUtils, findings,
    })
    : estimateWhatIf({ change, task, findings, baselineMetrics })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function optimizeExperimentFinding({
  task = '', findings = null,
  slices = null, migrations = null, blockingGaps = null, coreUtils = null,
  limit = 5,
} = {}) {
  const ctx = runOptimizationExperiments({
    task, slices, migrations, blockingGaps, coreUtils, findings, limit,
  })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function analyzeTracesSnapshots(snapshots) {
  const ctx = analyzeMultiTraces(snapshots)
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function baselineScoreFinding(snapshot, { profile = null, task = '' } = {}) {
  let scoped = snapshot
  const taskS = String(task || '').trim()
  if (taskS) {
    const tasks = (snapshot && typeof snapshot === 'object' && snapshot.tasks
      && typeof snapshot.tasks === 'object') ? snapshot.tasks : {}
    scoped = { tasks: Object.fromEntries(Object.entries(tasks).filter(([k]) => k === taskS)) }
  }
  const ctx = scoreAgainstBaseline(profile, scoped)
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function recommendExperimentsFinding(findings, { findingId = '', task = '', limit = 5 } = {}) {
  const ctx = recommendValidationExperiments(findings, { findingId, task, limit })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

function mediumLabelsFromEpisode(ep) {
  const list = ep?.medium_tasks || ep?.mediumTasks || []
  return list.map((item) => {
    if (typeof item === 'string') return item
    if (item && typeof item === 'object') return String(item.label || item.mk || '')
    return ''
  }).filter(Boolean)
}

function gatherPriorityEpisodes(trace, { task = '', lo = null, hi = null } = {}) {
  const out = []
  if (!trace) return out
  const taskS = String(task || '').trim()
  let mkFilter = null
  if (taskS) {
    const resolved = resolveTaskKey(taskS, taskCandidatesFromTrace(trace))
    if (!resolved) return out
    mkFilter = taskMergeKey(resolved)
  }
  const allEps = trace.priorityEpisodes || []
  const reprMap = trace.taskRepr
  for (const ep of allEps) {
    const mk = ep?.mk
    if (mkFilter != null && mk !== mkFilter) continue
    const start = ep.startNs ?? ep.start_ns
    const stop = ep.stopNs ?? ep.stop_ns
    if (!overlapsRange(start, stop, lo, hi)) continue
    let label = ''
    if (reprMap && typeof reprMap.get === 'function') label = String(reprMap.get(mk) || '')
    else if (reprMap && typeof reprMap === 'object') label = String(reprMap[mk] || '')
    if (!label) label = String(mk || '')
    out.push({
      task: label,
      start,
      stop,
      duration: (start == null || stop == null) ? null : Number(stop) - Number(start),
      base_pri: ep.basePri ?? ep.base_pri,
      peak_pri: ep.peakPri ?? ep.peak_pri,
      inherited: Boolean(ep.inherited),
      inversion_suspect: Boolean(ep.inversionSuspect ?? ep.inversion_suspect),
      medium_tasks: mediumLabelsFromEpisode(ep),
      pattern: ep.pattern || '',
    })
  }
  return out
}

export function detectPriorityInversionHost(trace, findings = null, {
  task = '', window = null, lo = null, hi = null,
} = {}) {
  if (!trace) return { ok: false, message: 'No trace loaded' }
  const episodes = gatherPriorityEpisodes(trace, { task, lo, hi })
  const ctx = detectPriorityInversion(episodes, findings, { task, window })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function findRelatedFindingsFinding(findings, {
  findingId = '', task = '', metric = '', window = null, limit = 10,
} = {}) {
  const ctx = findRelatedFindings(findings, { findingId, task, metric, window, limit })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

const COMPARE_TASKS_METRICS = [
  AI_RAW_METRIC_EXECUTION, AI_RAW_METRIC_BLOCKING, AI_RAW_METRIC_MIGRATIONS, AI_RAW_METRIC_PRIORITY,
]

export function compareTasksHost(trace, taskA, taskB, {
  metrics = null, lo = null, hi = null, findingsText = '',
} = {}) {
  if (!trace) return { ok: false, message: 'No trace loaded' }
  const aTask = String(taskA || '').trim()
  const bTask = String(taskB || '').trim()
  if (!aTask || !bTask) return { ok: false, message: 'task_a and task_b must be non-empty strings' }
  let wanted = (metrics || []).map(m => normalizeRawMetric(m)).filter(m => COMPARE_TASKS_METRICS.includes(m))
  if (!wanted.length) wanted = [...COMPARE_TASKS_METRICS]
  let labelA = aTask
  let labelB = bTask
  const dataA = {}
  const dataB = {}
  for (const metric of wanted) {
    const resA = queryRawMetric(trace, aTask, metric, { lo, hi, findingsText })
    if (resA.ok) {
      const d = (resA.data && typeof resA.data === 'object') ? resA.data : {}
      dataA[metric] = d
      labelA = String(d.task || labelA)
    }
    const resB = queryRawMetric(trace, bTask, metric, { lo, hi, findingsText })
    if (resB.ok) {
      const d = (resB.data && typeof resB.data === 'object') ? resB.data : {}
      dataB[metric] = d
      labelB = String(d.task || labelB)
    }
  }
  const ctx = compareTasksMetrics(labelA, labelB, dataA, dataB, { metrics: wanted })
  const ok = !!ctx.ok
  const message = String(ctx.message || (ok ? 'ok' : 'failed'))
  const data = { ...ctx }
  delete data.ok
  delete data.message
  return { ok, message, data }
}

export function exportInvestigationPackage({
  traceName = '', scope = '', finding = null, plan = null, toolsRun = null,
  queries = null, evidence = null, conclusion = '', confidence = '',
  alternatives = null, evidenceTimes = null, timestamp = '',
} = {}) {
  return buildInvestigationPackage({
    traceName, scope, finding, plan, toolsRun, queries, evidence,
    conclusion, confidence, alternatives, evidenceTimes, timestamp,
  })
}
