'use client';

import { useChartContext } from './ChartContext';
import { RadioIcon } from './icons';

/**
 * Tiny pulsating dot + label that surfaces realtime connectivity. Sits in the
 * OHLC overlay row so it doesn't compete with the price label or markers.
 *
 *  - Visible only when (isLive && market is open) AND not in replay.
 *  - Tooltip-less; the pulse + word "LIVE" is self-explanatory.
 */
export function ChartLiveBadge() {
    const ctx = useChartContext();
    if (!ctx.showLiveIndicator || ctx.isReplayActive) return null;
    return (
        <span className="flex items-center gap-1 pointer-events-none">
            <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-[color:var(--color-success)] animate-live-pulse" />
            <span className="text-[9.5px] font-bold uppercase tracking-wider text-[color:var(--color-success)]">live</span>
        </span>
    );
}

/**
 * "Realtime" anchor button. Shown at bottom-right when the user has scrolled
 * away from the live edge in non-replay mode. Clicking jumps the time scale
 * back to the most recent bar.
 */
export function ChartRealtimeJump() {
    const ctx = useChartContext();
    if (ctx.isReplayActive) return null;
    if (!ctx.isScrolledAway || !ctx.isLive) return null;
    return (
        <button
            onClick={() => ctx.chartRef.current?.timeScale().scrollToRealTime()}
            className="absolute bottom-3 right-14 z-20 flex items-center gap-1 px-2 py-1 bg-[color:var(--color-primary)] text-white text-[10px] font-medium rounded shadow-lg hover:bg-[color:var(--color-primary-hover)] transition-colors"
        >
            <RadioIcon className="w-2.5 h-2.5" /> Realtime
        </button>
    );
}
