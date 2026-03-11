/**
 * bisect.js – Binary search helpers (mirrors Python's bisect module).
 */

/**
 * Return the leftmost index i such that arr[i] >= value.
 * arr must be sorted ascending. Returns arr.length if all values < value.
 */
export function bisectLeft(arr, value) {
  let lo = 0, hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (arr[mid] < value) lo = mid + 1
    else hi = mid
  }
  return lo
}

/**
 * Return the rightmost index i such that arr[i] <= value.
 * arr must be sorted ascending. Returns 0 if all values > value.
 */
export function bisectRight(arr, value) {
  let lo = 0, hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (arr[mid] <= value) lo = mid + 1
    else hi = mid
  }
  return lo
}
