import { Sparkles, Bot } from 'lucide-react';
import type { IChartApi } from 'lightweight-charts';
import { buildChartSnapshot } from './buildChartSnapshot';
import { INDICATOR_TYPE_DEFAULTS, type ChartBar, type IndicatorInstance } from './constants';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { Drawing } from '@/hooks/useChartDrawings';
import type { ChartContext } from '@/components/ai-agent/types';

export interface ContextMenuState {
    visible: boolean;
    x: number;
    y: number;
    candle: ChartBar | null;
}

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
    if (!state.visible) return null;

    const dispatchChartAsk = (prompt: string) => {
        const snapshot = buildChartSnapshot(data, indicatorResults, drawings, activeIndicators, chartApi);
        const activeIndicatorNames: string[] = activeIndicators.map(i => {
            const defaults = INDICATOR_TYPE_DEFAULTS[i.type];
            return defaults ? `${defaults.name}${i.params.length ? ' ' + i.params.length : ''}` : i.type.toUpperCase();
        });

        const chartCtx: ChartContext = {
            ticker, interval, range,
            activeIndicators: activeIndicatorNames,
            currentPrice: data.length > 0 ? data[data.length - 1].close : null,
            snapshot,
            targetCandle: state.candle ? {
                date: state.candle.time, open: state.candle.open, high: state.candle.high,
                low: state.candle.low, close: state.candle.close, volume: state.candle.volume,
            } : null,
        };

        window.dispatchEvent(new CustomEvent('agent:chart-ask', { detail: { chartContext: chartCtx, prompt } }));
        onClose();
    };

    const candleDateISO = state.candle
        ? new Date(state.candle.time * 1000).toISOString().slice(0, 10)
        : '';

    const items = state.candle
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

    return (
        <>
            <div className="fixed inset-0 z-[9998]" onClick={onClose} />
            <div
                className="absolute z-[9999] bg-surface rounded-lg shadow-xl border border-border py-1 min-w-[200px]"
                style={{ left: state.x, top: state.y }}
            >
                <div className="px-3 py-1.5 flex items-center gap-1.5 border-b border-border-subtle">
                    <Bot className="w-3.5 h-3.5 text-blue-500" />
                    <span className="text-[10px] font-semibold text-foreground/80">AI Chart Analysis</span>
                </div>
                {items.map((item, i) => (
                    <button
                        key={i}
                        onClick={() => dispatchChartAsk(item.prompt)}
                        className="w-full text-left px-3 py-1.5 text-[11px] text-foreground hover:bg-primary/10 hover:text-primary flex items-center gap-2"
                    >
                        <Sparkles className="w-3 h-3 text-blue-400 flex-shrink-0" />
                        {item.label}
                    </button>
                ))}
                <div className="border-t border-border-subtle px-3 py-1.5">
                    <input
                        type="text"
                        placeholder="Ask anything about this chart..."
                        className="w-full text-[11px] text-foreground bg-surface-hover border border-border rounded px-2 py-1 focus:outline-none focus:border-primary"
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
