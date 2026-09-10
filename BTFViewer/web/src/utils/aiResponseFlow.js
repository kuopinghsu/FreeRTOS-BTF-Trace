/**
 * One clean response block per user query (AI_RESPONSE_FLOW_TODO):
 *   user → "Analysis completed · N.N s" → collapsed "Tool usage · X calls /
 *   Y tools" → final answer.
 * Pure helpers shared by the live panel, the desktop log, and the exports.
 *
 * Keep in lockstep with btf_viewer_pkg/ai_response_flow.py.
 */

import { recordToolUsage, summarizeToolUsage } from './aiToolUsage.js'

/** `28.3` — one decimal, matches the TODO's own examples. */
export function formatElapsedSeconds(s) {
  const n = Math.max(0, Number(s) || 0)
  return (Math.round(n * 10) / 10).toFixed(1)
}

/** "Analysis completed · 28.3 s" / "分析完成 · 用時 28.3 秒". */
export function formatAnalysisStatus(elapsedS, labels = {}) {
  const done = labels.analysis_completed || 'Analysis completed'
  const timeWord = labels.time_used ? `${labels.time_used} ` : ''
  const unit = labels.seconds_unit || 's'
  return `${done} · ${timeWord}${formatElapsedSeconds(elapsedS)} ${unit}`
    .replace(/\s+/g, ' ')
    .trim()
}

/** Roll up the chat-level tool list (name + status + result string) into the
 *  same shape as summarizeToolUsage, so every count agrees. */
export function toolUsageFromChatTools(tools) {
  let u = { calls: [] }
  for (const t of tools || []) {
    if (!t || !t.name) continue
    const failed = t.status === 'failed'
    u = recordToolUsage(u, {
      name: t.name,
      result: {
        ok: !failed,
        message: t.result,
        error: failed ? (t.result || 'failed') : null,
      },
    })
  }
  return summarizeToolUsage(u)
}

/** "Tool usage · 5 calls / 5 tools" (+ " · 1 failed"). */
export function formatToolUsageSummaryLine(tools, labels = {}) {
  const s = toolUsageFromChatTools(tools)
  let out = `${labels.tool_usage || 'Tool usage'} · ${s.total} ${labels.calls || 'calls'}`
    + ` / ${s.unique} ${labels.uniq_tools || 'tools'}`
  if (s.failed) out += ` · ${s.failed} ${labels.failed_word || 'failed'}`
  return out
}

/**
 * For a completed conversation, decide how each message renders.
 * `messages` is the array of { role, content, tools, batchId, turnComplete,
 * analysisElapsedS }.
 *
 * Returns { hidden: Set<index>, meta: Map<index, {elapsedS, tools, batchIds}> }:
 * - `hidden` — interstitial narration turns and per-round tool cards for a
 *   query that has completed (still reachable via "View request context").
 * - `meta`  — the message that carries the status line + tool-usage summary
 *   (the final answer, or the last tool turn when there is no written answer).
 * A query that is still running is left untouched (nothing hidden).
 */
export function planQueryBlocks(messages) {
  const msgs = Array.isArray(messages) ? messages : []
  const hidden = new Set()
  const meta = new Map()
  let i = 0
  while (i < msgs.length) {
    if (!msgs[i] || msgs[i].role !== 'user') { i += 1; continue }
    const userIdx = i
    let j = i + 1
    const rest = []
    while (j < msgs.length && msgs[j] && msgs[j].role !== 'user') { rest.push(j); j += 1 }
    const toolIdxs = rest.filter(
      k => msgs[k].role === 'assistant' && msgs[k].tools && msgs[k].tools.length)
    const proseIdxs = rest.filter(
      k => msgs[k].role === 'assistant' && String(msgs[k].content || '').trim())
    const allTools = toolIdxs.flatMap(k => msgs[k].tools || [])
    const anyPending = allTools.some(t => (t.status || 'pending') === 'pending')
    const complete = !!msgs[userIdx].turnComplete && !anyPending
    // Per-round tool cards are never shown in the chat — a tool-only turn with
    // no written prose is hidden even while the query is still running. Only
    // the one consolidated "Tool Usage" block (below, on completion) surfaces
    // tool activity.
    for (const k of toolIdxs) {
      if (!String(msgs[k].content || '').trim()) hidden.add(k)
    }
    if (complete && (toolIdxs.length || proseIdxs.length)) {
      const answerIdx = proseIdxs.length ? proseIdxs[proseIdxs.length - 1] : null
      const host = answerIdx != null
        ? answerIdx
        : (toolIdxs.length ? toolIdxs[toolIdxs.length - 1] : null)
      if (host != null) {
        meta.set(host, {
          elapsedS: Number(msgs[userIdx].analysisElapsedS || 0),
          tools: allTools,
          batchIds: [...new Set(toolIdxs.map(k => msgs[k].batchId).filter(Boolean))],
        })
        hidden.delete(host)
        // Hide only the assistant's own turns (interstitial narration + the
        // per-round tool cards). Never hide the Evidence & Validation panel
        // (role 'evidence') or any other non-assistant entry.
        for (const k of rest) {
          if (k !== host && msgs[k].role === 'assistant') hidden.add(k)
        }
      }
    }
    i = j
  }
  return { hidden, meta }
}
