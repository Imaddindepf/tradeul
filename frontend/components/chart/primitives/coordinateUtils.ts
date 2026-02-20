/**
 * Cross-timeframe coordinate utilities for drawing primitives.
 *
 * Uses pixel-based interpolation: gets the actual pixel positions of
 * surrounding bars from the chart and interpolates between them.
 * This guarantees correct positioning regardless of timeframe.
 */
import type { ITimeScaleApi, Time } from 'lightweight-charts';

/**
 * Convert a Unix timestamp (seconds) to a pixel X coordinate.
 *
 * Strategy:
 *   1. Exact match via timeToCoordinate (same timeframe — fastest)
 *   2. Binary search for surrounding bars, get their pixel positions,
 *      interpolate in pixel space (cross-timeframe)
 *   3. Extrapolate beyond data using actual bar pixel spacing
 */
export function timeToPixelX(
  timestamp: number,
  dataTimes: number[],
  timeScale: ITimeScaleApi<Time>,
): number | null {
  const n = dataTimes.length;
  if (n === 0 || !isFinite(timestamp)) return null;

  // Fast path: exact bar match
  const exact = timeScale.timeToCoordinate(timestamp as unknown as Time);
  if (exact !== null) return exact as number;

  // Helper: get pixel position of a data bar by index
  const pxAt = (i: number): number | null =>
    timeScale.timeToCoordinate(dataTimes[i] as unknown as Time) as number | null;

  // ── Before first bar ──────────────────────────────────────────────────
  if (timestamp <= dataTimes[0]) {
    const x0 = pxAt(0);
    if (x0 === null) return null;
    if (n < 2) return x0;
    const x1 = pxAt(1);
    if (x1 === null) return null;
    const barPx = x1 - x0; // pixel width of one bar
    const timeGap = dataTimes[1] - dataTimes[0];
    if (timeGap <= 0) return x0;
    return x0 + ((timestamp - dataTimes[0]) / timeGap) * barPx;
  }

  // ── After last bar ────────────────────────────────────────────────────
  if (timestamp >= dataTimes[n - 1]) {
    const xLast = pxAt(n - 1);
    if (xLast === null) return null;
    if (n < 2) return xLast;
    const xPrev = pxAt(n - 2);
    if (xPrev === null) return null;
    const barPx = xLast - xPrev;
    const timeGap = dataTimes[n - 1] - dataTimes[n - 2];
    if (timeGap <= 0) return xLast;
    return xLast + ((timestamp - dataTimes[n - 1]) / timeGap) * barPx;
  }

  // ── Within data range: binary search ──────────────────────────────────
  let lo = 0, hi = n - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (dataTimes[mid] <= timestamp) lo = mid;
    else hi = mid;
  }

  const xLo = pxAt(lo);
  const xHi = pxAt(hi);
  if (xLo === null || xHi === null) return null;

  const tGap = dataTimes[hi] - dataTimes[lo];
  if (tGap <= 0) return xLo;
  const fraction = (timestamp - dataTimes[lo]) / tGap;
  return xLo + fraction * (xHi - xLo);
}
