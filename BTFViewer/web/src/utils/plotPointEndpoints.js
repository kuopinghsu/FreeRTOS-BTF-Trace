/**
 * Outliers whose jump marks both ends — parity with desktop `_plot_point_endpoints`.
 * @returns {{ startNs: number, stopNs: number } | null}
 */
export function plotPointEndpoints(kind, payload) {
  if ((kind === 'priority' || kind === 'sync_hold') && payload?.startNs != null && payload?.stopNs != null) {
    return { startNs: payload.startNs, stopNs: payload.stopNs }
  }
  return null
}

export function plotPointEndpointNotes(note) {
  return [`${note} — start`, `${note} — end`]
}
