/**
 * Tick-gap / trace-health analysis from STI TICK timestamps.
 */

export const DEFAULT_TICK_PERIOD = 1000
export const DEFAULT_TICK_HZ = 1000
const TICK_RATE_META_KEYS = new Set([
  'tickrate', 'tick_rate', 'tickratehz', 'tick_rate_hz',
  'configtick_rate_hz', 'tickhz', 'tick_hz',
])
const TIME_UNITS_PER_SECOND = { ps: 1e12, ns: 1e9, us: 1e6, ms: 1e3, s: 1 }

/**
 * Expected RTOS tick period in trace time units, plus its source.
 * Uses a tick-rate header (e.g. `#tickRate 1000`) when present; otherwise the
 * FreeRTOS default 1000 Hz. `core_clock` is a counter frequency, never the tick rate.
 * @returns {{ period: number, source: 'metadata'|'default' }}
 */
export function tickExpectedPeriod(trace) {
  const perS = TIME_UNITS_PER_SECOND[String(trace?.timeScale || 'ns').toLowerCase()] ?? 1e9
  const meta = trace?.meta || {}
  for (const [key, value] of Object.entries(meta)) {
    if (!TICK_RATE_META_KEYS.has(String(key).toLowerCase())) continue
    const hz = parseInt(String(value).trim().toLowerCase().replace(/hz$/, '').trim(), 10)
    if (Number.isFinite(hz) && hz > 0) return { period: perS / hz, source: 'metadata' }
  }
  return { period: perS / DEFAULT_TICK_HZ, source: 'default' }
}

export const TICK_GAP_THRESHOLD = 2.0
/**
 * Coefficient-of-variation threshold for tickless-mode detection.
 * CV = stddev / mean. A value above this indicates that tick intervals
 * vary significantly (tickless idle is suppressing ticks during idle periods).
 *
 * Caveat for a busy many-core SMP build with configUSE_TICKLESS_IDLE=0: this
 * CV can legitimately cross the threshold even though tickless idle was
 * never compiled in. On FreeRTOS SMP the tick timestamp is stamped inside
 * xTaskIncrementTick(), which the port may only call while holding the task
 * lock and the ISR lock (see Demo/port/RISC-V/port.c's xPortTimerTickHandler
 * for the concrete lock-ordering contract and measured numbers). The
 * underlying timer interrupt still fires exactly on schedule; what varies is
 * how long the tick-owning core has to wait for those two locks, since any
 * other core's critical section can be holding one when the tick lands.
 * It's inherent to FreeRTOS SMP's lock-serialized tick handling, and it gets
 * worse the more cores are contending for the same two spinlocks - measured
 * at ~0.4% CV on 1 core rising to ~23% on 8 cores for the same workload. So
 * the tick doesn't actually go tickless; SMP lock-wait jitter on a busy,
 * many-core build can just look like it did, by the same CV yardstick that
 * correctly flags genuine tickless idle elsewhere.
 */
export const TICKLESS_CV_THRESHOLD = 0.05

/**
 * @param {number[]} tickTimes  Sorted STI TICK timestamps.
 * @param {?(number|null)[]} [tickCounts]  xTickCount for each tickTimes entry, same
 *   order/length. While the scheduler is suspended, xTaskResumeAll() replays
 *   pended ticks by calling xTaskIncrementTick() again for a count already
 *   recorded, so the same xTickCount can appear at two nearby, non-periodic
 *   timestamps (see the catch-up-replay comment in FreeRTOS-Trace/btf_trace.c).
 *   Two consecutive rows sharing a count are the same logical tick, not a
 *   second timer IRQ — excluded here so a handful of catch-up replays cannot
 *   inflate the CV enough to misclassify a real tick-full trace as tickless.
 * @param {number} [expectedPeriod=1000]
 * @param {number} [gapFactor=2]
 */
export function analyzeTickHealth(tickTimes, tickCounts = null, expectedPeriod = DEFAULT_TICK_PERIOD, gapFactor = TICK_GAP_THRESHOLD) {
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
    const prevCount = tickCounts?.[i - 1]
    const curCount = tickCounts?.[i]
    if (prevCount != null && curCount != null && prevCount === curCount) {
      continue  // catch-up replay of the same tick, not a real interval
    }
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
  const { period, source } = tickExpectedPeriod(trace)
  let times = trace.tickStiTimes || []
  let counts = trace.tickStiCounts || []
  if (lo != null && hi != null) {
    const kept = []
    times.forEach((t, i) => { if (t >= lo && t <= hi) kept.push(i) })
    counts = kept.map(i => counts[i])
    times = kept.map(i => times[i])
  }
  return { ...analyzeTickHealth(times, counts, period), expectedPeriodSource: source }
}
