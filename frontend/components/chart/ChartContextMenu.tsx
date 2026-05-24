import { Sparkles, Bot, Maximize2, Minimize2, Settings, RotateCcw } from 'lucide-react';
import type { IChartApi } from 'lightweight-charts';
import { buildChartSnapshot } from './buildChartSnapshot';
import { INDICATOR_TYPE_DEFAULTS, type ChartBar, type IndicatorInstance } from './constants';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { Drawing } from '@/hooks/useChartDrawings';
import type { ChartContext } from '@/components/ai-agent/types';
import { useChartContext } from './ChartContext';

export interface ContextMenuState {
    visible: boolean;
    x: number;
    y: number;
    candle: ChartBar | null;
}

/**
 * Right-click menu organised into sections:
 *   1. Chart actions   — reset zoom, settings, fullscreen
 *   2. AI analysis     — quick prompts about the current candle / chart
 *   3. Free-text input — ask anything
 */
export function ChartContextMenu({
    state, ticker, interval, range, data, indicatorResults, drawings, activeIndicators, chartApi, onClose,
}: {
    state: ContextMenuState;
    ticker: string;
    interval: string;
    range: string;
    data: ChartBar[];
    indicatorResults: IndicatorResults | null;
    drawings: Drawing[];
    activeIndicators: IndicatorInstance[];
    chartApi: IChartApi | null;
    onClose: () => void;
}) {
    const chartCtx = useChartContext();
    if (!state.visible) return null;

    const dispatchChartAsk = (prompt: string) => {
        const snapshot = buildChartSnapshot(data, indicatorResults, drawings, activeIndicators, chartApi);
        const activeIndicatorNames: string[] = activeIndicators.map(i => {
            const defaults = INDICATOR_TYPE_DEFAULTS[i.type];
            return defaults ? `${defaults.name}${i.params.length ? ' ' + i.params.length : ''}` : i.type.toUpperCase();
        });

        const ctx: ChartContext = {
            ticker, interval, range,
            activeIndicators: activeIndicatorNames,
            currentPrice: data.length > 0 ? data[data.length - 1].close : null,
            snapshot,
            targetCandle: state.candle ? {
                date: state.candle.time, open: state.candle.open, high: state.candle.high,
                low: state.candle.low, close: state.candle.close, volume: state.candle.volume,
            } : null,
        };

        window.dispatchEvent(new CustomEvent('agent:chart-ask', { detail: { chartContext: ctx, prompt } }));
        onClose();
    };

    const candleDateISO = state.candle
        ? new Date(state.candle.time * 1000).toISOString().slice(0, 10)
        : '';

    const aiItems = state.candle
        ? [
            { label: 'Analyze this candle', prompt: `Analyze the candle at ${candleDateISO} for ${ticker}` },
            { label: 'Why did this move?', prompt: `Why did ${ticker} move like this on ${candleDateISO}?` },
            { label: 'Full technical analysis', prompt: `Full technical analysis of ${ticker} chart` },
            { label: 'Support & resistance levels', prompt: `Identify support and resistance levels for ${ticker}` },
        ]
        : [
            { label: 'Full technical analysis', prompt: `Full technical analysis of ${ticker} chart` },
            { label: 'Support & resistance levels', prompt: `Identify support and resistance levels for ${ticker}` },
            { label: 'Trend direction', prompt: `What is the current trend for ${ticker}?` },
            { label: 'Entry/exit points', prompt: `Suggest entry and exit points for ${ticker}` },
        ];

    const handleResetZoom = () => {
        chartApi?.timeScale().fitContent();
        onClose();
    };
    const handleSettings = () => {
        chartCtx.openSettings();
        onClose();
    };
    const handleFullscreen = () => {
        chartCtx.toggleFullscreen();
        onClose();
    };

    const sectionLabel = 'px-3 py-1 text-[9px] uppercase tracking-wider text-[color:var(--color-muted-fg)]/70 font-semibold';
    const itemClass = 'w-full text-left px-3 py-1.5 text-[11px] text-[color:var(--color-fg)] hover:bg-[color:var(--color-primary)]/10 hover:text-[color:var(--color-primary)] flex items-center gap-2';

    return (
        <>
            <div className="fixed inset-0 z-[9998]" onClick={onClose} />
            <div
                className="absolute z-[9999] bg-[color:var(--color-surface)] rounded-lg shadow-xl border border-[color:var(--color-border)] py-1 min-w-[220px]"
                style={{ left: state.x, top: state.y }}
            >
                {/* Section 1 — Chart actions */}
                <div className={sectionLabel}>Chart</div>
                <button onClick={handleResetZoom} className={itemClass}>
                    <RotateCcw className="w-3 h-3 text-[color:var(--color-muted-fg)] flex-shrink-0" />
                    Reset zoom
                </button>
                <button onClick={handleSettings} className={itemClass}>
                    <Settings className="w-3 h-3 text-[color:var(--color-muted-fg)] flex-shrink-0" />
                    Chart settings…
                </button>
                <button onClick={handleFullscreen} className={itemClass}>
                    {chartCtx.isFullscreen
                        ? <Minimize2 className="w-3 h-3 text-[color:var(--color-muted-fg)] flex-shrink-0" />
                        : <Maximize2 className="w-3 h-3 text-[color:var(--color-muted-fg)] flex-shrink-0" />}
                    {chartCtx.isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                </button>

                {/* Section 2 — AI Analysis */}
                <div className="border-t border-[color:var(--color-border-subtle)] mt-1 pt-1">
                    <div className="px-3 py-1 flex items-center gap-1.5">
                        <Bot className="w-3 h-3 text-blue-500" />
                        <span className="text-[9px] uppercase tracking-wider text-[color:var(--color-muted-fg)]/70 font-semibold">AI Analysis</span>
                    </div>
                    {aiItems.map((item, i) => (
                        <button key={i} onClick={() => dispatchChartAsk(item.prompt)} className={itemClass}>
                            <Sparkles className="w-3 h-3 text-blue-400 flex-shrink-0" />
                            {item.label}
                        </button>
                    ))}
                </div>

                {/* Section 3 — Free-text prompt */}
                <div className="border-t border-[color:var(--color-border-subtle)] mt-1 px-3 py-1.5">
                    <input
                        type="text"
                        placeholder="Ask anything about this chart…"
                        className="w-full text-[11px] text-[color:var(--color-fg)] bg-[color:var(--color-surface-hover)] border border-[color:var(--color-border)] rounded px-2 py-1 focus:outline-none focus:border-[color:var(--color-primary)]"
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                                dispatchChartAsk((e.target as HTMLInputElement).value.trim());
                            }
                        }}
                        autoFocus
                    />
                </div>
            </div>
        </>
    );
}
