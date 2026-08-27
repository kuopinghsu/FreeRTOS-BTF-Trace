/**
 * Statistics symptom landing cards.
 * Keep in sync with btf_viewer_pkg/stats_symptom_landing.py.
 */

export const SYMPTOM_CARDS = [
  { id: 'unknown', title: 'Unknown issue', first_section: 'overview', path: ['Analysis Findings', 'Timeline Anomalies'] },
  { id: 'late', title: 'Task is sometimes late', first_section: 'response_time', path: ['Response Time', 'Execution', 'Dispatch', 'Blocking', 'Preemption'] },
  { id: 'spike', title: 'Execution spike / long slice', first_section: 'execution', path: ['Execution', 'Worst Events', 'Preemption Matrix'] },
  { id: 'dispatch', title: 'Dispatch delay', first_section: 'dispatch', path: ['Dispatch latency', 'Execution', 'Core Utilization'] },
  { id: 'blocking', title: 'Blocking / off-CPU wait', first_section: 'blocking', path: ['Blocking Time', 'Mutex Blocking', 'Waiter × Owner'] },
  { id: 'jitter', title: 'Period / jitter', first_section: 'period_jitter', path: ['Period / Jitter', 'Unified Jitter', 'Recurring Patterns'] },
  { id: 'load', title: 'Load imbalance', first_section: 'load_balance', path: ['Load Balance', 'Task × Core', 'Core Utilization'] },
  { id: 'migration', title: 'Migration / thrash', first_section: 'migrations', path: ['Core Migrations', 'Load Balance', 'Task × Core'] },
  { id: 'sync', title: 'Synchronization', first_section: 'mutex_blocking', path: ['Mutex Blocking', 'Waiter × Owner', 'Sync Issues'], requires_sti: true },
  { id: 'deadline', title: 'Deadline miss', first_section: 'deadline', path: ['Deadline / CPU Budget', 'Response Time', 'Execution'] },
]

export function symptomCard(cardId) {
  const want = String(cardId || '').trim().toLowerCase()
  const hit = SYMPTOM_CARDS.find(c => c.id === want)
  return hit ? { ...hit } : null
}

export function recommendSymptomFromFinding(finding) {
  if (!finding || typeof finding !== 'object') return null
  const blob = `${finding.title || ''} ${finding.text || ''}`.toLowerCase()
  if (/deadline|budget|miss/.test(blob)) return 'deadline'
  if (/migrat|thrash|bounce|affinity/.test(blob)) return 'migration'
  if (/block|mutex|semaphore|wait/.test(blob)) return 'blocking'
  if (/jitter|period|interval/.test(blob)) return 'jitter'
  if (/dispatch|latency|ready/.test(blob)) return 'dispatch'
  if (/wcet|execution|cpu|slice/.test(blob)) return 'spike'
  if (/load|balance|gini/.test(blob)) return 'load'
  if (/response|late|slow/.test(blob)) return 'late'
  return 'unknown'
}

export function availableSymptomCards({ hasSti = true, singleCore = false } = {}) {
  return SYMPTOM_CARDS.map(card => {
    const item = { ...card }
    const reasons = []
    if (card.requires_sti && !hasSti) {
      item.disabled = true
      reasons.push('STI instrumentation unavailable')
    }
    if (card.id === 'migration' && singleCore) {
      item.disabled = true
      reasons.push('Single-core trace')
    }
    if (reasons.length) item.disabled_reason = reasons.join('; ')
    return item
  })
}

/** Desktop/Web section ids used by StatisticsPanel scroll targets. */
export const SYMPTOM_SECTION_MAP = {
  overview: 'anomalies',
  response_time: 'response',
  execution: 'exec',
  dispatch: 'dispatch',
  blocking: 'block',
  period_jitter: 'period',
  load_balance: 'cores',
  migrations: 'migrations',
  mutex_blocking: 'mutex_block',
  deadline: 'deadline',
}

export function symptomSectionId(card) {
  if (!card || typeof card !== 'object') return 'anomalies'
  return SYMPTOM_SECTION_MAP[String(card.first_section || '').trim()] || 'anomalies'
}
