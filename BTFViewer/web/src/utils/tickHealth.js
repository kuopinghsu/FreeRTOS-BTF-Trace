/**
 * Tick-gap / trace-health analysis from STI TICK timestamps.
 */

export const DEFAULT_TICK_PERIOD = 1000
export const TICK_GAP_THRESHOLD = 2.0

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
    }
  }

  const threshold = expectedPeriod * gapFactor
  const largeGaps = []
  let sumDelta = 0
  let maxGap = 0
  let missedTotal = 0

  for (let i = 1; i < tickTimes.length; i++) {
    const delta = tickTimes[i] - tickTimes[i - 1]
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

  const avgPeriod = tickTimes.length > 1 ? sumDelta / (tickTimes.length - 1) : expectedPeriod
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
