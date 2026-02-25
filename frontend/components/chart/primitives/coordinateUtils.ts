/**
 * Cross-timeframe coordinate utilities for drawing primitives.
 *
 * Gap-aware positioning: detects market gaps (overnight, weekends, holidays)
 * and snaps to the nearest bar instead of linearly interpolating in time.
 * This ensures drawings render at correct visual positions across timeframe changes.
 *
 * Clamped extrapolation: limits how far beyond the data range a drawing can
 * be rendered, preventing drawings from flying off-screen when the data
 * doesn't cover the drawing's timeframe. Returns null when too far out
 * so the auto-loadMore mechanism can fetch more data.
 *
 * For normal bar spacing (same timeframe), uses proportional interpolation —
 * behavior is identical to before.
 */
import type { ITimeScaleApi, Time } from 'lightweight-charts';

// ── Constants ───────────────────────────────────────────────────────────────
// Maximum number of bars to extrapolate beyond the data edge.
// Beyond this, timeToPixelX returns null → triggers auto-loadMore.
const MAX_EXTRAPOLATION_BARS = 20;

// ── Median gap cache ────────────────────────────────────────────────────────
let _cacheKey = '';
let _cachedMedianGap = 0;

/**
 * Compute the median gap between consecutive bars.
 * Represents the "typical" bar interval for the current timeframe.
 * Uses sampling (up to 200 gaps) for performance on large datasets.
 */
function getMedianGap(dataTimes: number[]): number {
  const n = dataTimes.length;
  if (n < 2) return 86400;

  const key = `${n}:${dataTimes[0]}:${dataTimes[n - 1]}`;
  if (key === _cacheKey && _cachedMedianGap > 0) return _cachedMedianGap;

  const gaps: number[] = [];
  const step = Math.max(1, Math.floor((n - 1) / 200));
  for (let i = 0; i < n - 1; i += step) {
    const g = dataTimes[i + 1] - dataTimes[i];
    if (g > 0) gaps.push(g);
  }

  if (gaps.length === 0) {
    _cacheKey = key;
    _cachedMedianGap = 86400;
    return 86400;
  }

  gaps.sort((a, b) => a - b);
  _cachedMedianGap = gaps[Math.floor(gaps.length / 2)];
  _cacheKey = key;
  return _cachedMedianGap;
}

// ── Main coordinate conversion ──────────────────────────────────────────────

/**
 * Convert a Unix timestamp (seconds) to a pixel X coordinate.
 *
 * Strategy:
 *   1. Exact match via timeToCoordinate (same timeframe — fastest)
 *   2. Binary search for surrounding bars:
 *      - Normal gap (≤ 1.5× median): proportional interpolation
 *      - Market gap (> 1.5× median): snap to nearest bar
 *   3. Clamped extrapolation beyond data edges:
 *      - Within MAX_EXTRAPOLATION_BARS: extrapolate using median gap
 *      - Beyond: return null (drawing invisible → triggers auto-loadMore)
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

  const medianGap = getMedianGap(dataTimes);
  const gapThreshold = medianGap * 1.5;

  // ── Before first bar ──────────────────────────────────────────────────
  if (timestamp <= dataTimes[0]) {
    const barsBack = medianGap > 0 ? (dataTimes[0] - timestamp) / medianGap : Infinity;

    // Beyond clamp limit → return null (auto-loadMore will fetch more data)
    if (barsBack > MAX_EXTRAPOLATION_BARS) return null;

    const x0 = pxAt(0);
    if (x0 === null) return null;
    if (n < 2) return x0;
    const x1 = pxAt(1);
    if (x1 === null) return null;
    const barPx = x1 - x0;
    return x0 - barsBack * barPx;
  }

  // ── After last bar (no clamp — user must be able to draw/drag freely) ──
  if (timestamp >= dataTimes[n - 1]) {
    const xLast = pxAt(n - 1);
    if (xLast === null) return null;
    if (n < 2) return xLast;
    const xPrev = pxAt(n - 2);
    if (xPrev === null) return null;
    const barPx = xLast - xPrev;
    if (medianGap <= 0) return xLast;
    const barsForward = (timestamp - dataTimes[n - 1]) / medianGap;
    return xLast + barsForward * barPx;
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

  const actualGap = dataTimes[hi] - dataTimes[lo];
  if (actualGap <= 0) return xLo;

  const timeFraction = (timestamp - dataTimes[lo]) / actualGap;

  // ── Gap-aware positioning ─────────────────────────────────────────────
  if (actualGap > gapThreshold) {
    return timeFraction < 0.5 ? xLo : xHi;
  }

  // Normal spacing: proportional interpolation (unchanged behavior)
  return xLo + timeFraction * (xHi - xLo);
}
