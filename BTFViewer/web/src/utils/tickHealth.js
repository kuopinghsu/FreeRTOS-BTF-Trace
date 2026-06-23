/**
 * Tick-gap / trace-health analysis from STI TICK timestamps.
 */

export const DEFAULT_TICK_PERIOD = 1000
export const TICK_GAP_THRESHOLD = 2.0
/**
 * Coefficient-of-variation threshold for tickless-mode detection.
 * CV = stddev / mean. A value above this indicates that tick intervals
 * vary significantly (tickless idle is suppressing ticks during idle periods).
 */
export const TICKLESS_CV_THRESHOLD = 0.05

/**
 * @param {number[]} tickTimes  Sorted STI TICK timestamps.
 * @param {number} [expectedPeriod=1000]
 * @param {number} [gapFactor=2]
 */
export function analyzeTickHealth(tickTimes, expectedPeriod = DEFAULT_TICK_PERIOD, gapFactor = TICK_GAP_THRESHOLD) {
  if (!tickTimes?.length) {
    return {
      tickCount: 0,
      expectedPeriod,
      avgPeriod: 0,
      maxGap: 0,
      largeGaps: [],
      missedTicksEstimate: 0,
      health: 'unknown',
      isTickless: false,
      tickDeltas: [],
      tickCv: 0,
    }
  }

  const threshold = expectedPeriod * gapFactor
  const largeGaps = []
  const tickDeltas = []
  let sumDelta = 0
  let maxGap = 0
  let missedTotal = 0

  for (let i = 1; i < tickTimes.length; i++) {
    const delta = tickTimes[i] - tickTimes[i - 1]
    tickDeltas.push(delta)
    sumDelta += delta
    if (delta > maxGap) maxGap = delta
    if (delta > threshold) {
      const missed = Math.max(0, Math.round(delta / expectedPeriod) - 1)
      missedTotal += missed
      largeGaps.push({
        start: tickTimes[i - 1],
        end: tickTimes[i],
        duration: delta,
        missedTicks: missed,
      })
    }
  }

  const n = tickDeltas.length
  const avgPeriod = n > 0 ? sumDelta / n : expectedPeriod

  // Tickless-mode detection: compute coefficient of variation of tick intervals.
  // In tick mode all intervals are tightly clustered; in tickless mode idle periods
  // cause the CPU to skip ticks, so the interval distribution widens noticeably.
  let tickCv = 0
  if (n > 1 && avgPeriod > 0) {
    const variance = tickDeltas.reduce((acc, d) => acc + (d - avgPeriod) ** 2, 0) / n
    tickCv = Math.sqrt(variance) / avgPeriod
  }
  const isTickless = tickCv > TICKLESS_CV_THRESHOLD

  let health = 'good'
  if (largeGaps.length > 0) {
    const worst = maxGap / expectedPeriod
    health = worst > 10 ? 'critical' : 'warning'
  }

  return {
    tickCount: tickTimes.length,
    expectedPeriod,
    avgPeriod: Math.round(avgPeriod),
    maxGap,
    largeGaps,
    missedTicksEstimate: missedTotal,
    health,
    isTickless,
    tickDeltas,
    tickCv,
  }
}

/** Scoped tick health (respects cursor range). */
export function tickHealthReport(trace, lo = null, hi = null) {
  if (!trace) return analyzeTickHealth([])
  let times = trace.tickStiTimes || []
  if (lo != null && hi != null) {
    times = times.filter(t => t >= lo && t <= hi)
  }
  return analyzeTickHealth(times)
}
