/**
 * Heikin-Ashi transformation.
 *
 * Heikin-Ashi candles are computed from regular OHLC data with these formulas:
 *   HA_close = (O + H + L + C) / 4
 *   HA_open  = (prev_HA_open + prev_HA_close) / 2  (first bar uses (O+C)/2)
 *   HA_high  = max(H, HA_open, HA_close)
 *   HA_low   = min(L, HA_open, HA_close)
 *
 * IMPORTANT: This is a display transformation only. Volume, indicator
 * calculations, hover OHLC display, and trade logic should always use the
 * underlying real OHLC bars — Heikin-Ashi values are intentionally smoothed
 * and would mislead any consumer that expects real prices.
 */
import type { ChartBar } from '../constants';

export function computeHeikinAshi(bars: ChartBar[]): ChartBar[] {
    if (bars.length === 0) return bars;
    const out: ChartBar[] = new Array(bars.length);
    let prevHaOpen = (bars[0].open + bars[0].close) / 2;
    let prevHaClose = (bars[0].open + bars[0].high + bars[0].low + bars[0].close) / 4;
    out[0] = {
        time: bars[0].time,
        open: prevHaOpen,
        close: prevHaClose,
        high: Math.max(bars[0].high, prevHaOpen, prevHaClose),
        low: Math.min(bars[0].low, prevHaOpen, prevHaClose),
        volume: bars[0].volume,
    };
    for (let i = 1; i < bars.length; i++) {
        const bar = bars[i];
        const haClose = (bar.open + bar.high + bar.low + bar.close) / 4;
        const haOpen = (prevHaOpen + prevHaClose) / 2;
        out[i] = {
            time: bar.time,
            open: haOpen,
            close: haClose,
            high: Math.max(bar.high, haOpen, haClose),
            low: Math.min(bar.low, haOpen, haClose),
            volume: bar.volume,
        };
        prevHaOpen = haOpen;
        prevHaClose = haClose;
    }
    return out;
}
