'use client';

import { useChartContext } from './ChartContext';
import { ReplayIcon } from './icons';

/**
 * Floating REPLAY badge shown over the chart pane while in replay mode (not
 * during initial selection). Anchored top-right to avoid the OHLC overlay.
 */
export function ChartReplayOverlay() {
    const ctx = useChartContext();
    const mode = ctx.replayState.mode;
    if (mode === 'idle' || mode === 'selecting') return null;
    return (
        <div className="absolute top-2 right-14 z-20 flex items-center gap-1.5 px-2 py-1 bg-[color:var(--color-chart-replay)]/90 text-white text-[10px] font-bold rounded shadow-lg tracking-wider uppercase pointer-events-none">
            <ReplayIcon className="w-3 h-3" />
            Replay
        </div>
    );
}
