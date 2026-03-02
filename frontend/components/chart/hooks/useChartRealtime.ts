import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi, UTCTimestamp, LogicalRange } from 'lightweight-charts';
import type { ChartBar as HookChartBar } from '@/hooks/useLiveChartData';
import { CHART_COLORS, INTERVAL_SECONDS, WHITESPACE_BAR_COUNT, type ChartBar, type Interval } from '../constants';
import { getSessionColor } from './useSessionBackground';
import { buildWhitespace } from './useChartData';
import { IncrementalIndicatorEngine } from '../IncrementalIndicatorEngine';
import type { IndicatorInstance } from '../constants';

export function useChartRealtime(
    chartRef: MutableRefObject<IChartApi | null>,
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    volumeSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    sessionBgSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    whitespaceSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    indicatorSeriesRef: MutableRefObject<Map<string, Map<string, ISeriesApi<any>>>>,
    lastPriceInfoRef: MutableRefObject<{ close: number; open: number }>,
    data: ChartBar[],
    selectedInterval: Interval,
    indicators: IndicatorInstance[],
    registerUpdateHandler: (handler: ((bar: HookChartBar, isNewBar: boolean) => void) | null) => void,
    isReplayActive = false,
) {
    const engineRef = useRef<IncrementalIndicatorEngine | null>(null);
    const isReplayActiveRef = useRef(isReplayActive);
    isReplayActiveRef.current = isReplayActive;

    // Initialize incremental indicator engine
    useEffect(() => {
        if (data.length === 0) return;
        const activeInsts = indicators.filter(i => i.visible);
        if (activeInsts.length === 0) {
            engineRef.current = null;
            return;
        }
        const engine = new IncrementalIndicatorEngine();
        const configs = activeInsts.map(i => ({ id: i.id, type: i.type, params: i.params }));
        engine.initialize(data, configs);
        engineRef.current = engine;
        return () => { engineRef.current = null; };
    }, [data, indicators]);

    // Register real-time update handler
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) {
            registerUpdateHandler(null);
            return;
        }

        const handleRealtimeUpdate = (bar: HookChartBar, isNewBar: boolean) => {
            if (isReplayActiveRef.current) return;
            const candleSeries = candleSeriesRef.current;
            const volumeSeries = volumeSeriesRef.current;
            if (!candleSeries || !volumeSeries) return;

            try {
                candleSeries.update({
                    time: bar.time as UTCTimestamp,
                    open: bar.open,
                    high: bar.high,
                    low: bar.low,
                    close: bar.close,
                });

                lastPriceInfoRef.current = { close: bar.close, open: bar.open };

                const volumeColor = bar.close >= bar.open
                    ? CHART_COLORS.volumeUp
                    : CHART_COLORS.volumeDown;

                volumeSeries.update({
                    time: bar.time as UTCTimestamp,
                    value: bar.volume,
                    color: volumeColor,
                });

                const sessionBg = sessionBgSeriesRef.current;
                if (sessionBg) {
                    sessionBg.update({
                        time: bar.time as UTCTimestamp,
                        value: 1,
                        color: getSessionColor(bar.time),
                    });
                }
            } catch {
                return;
            }

            if (isNewBar) {
                if (whitespaceSeriesRef.current) {
                    const gap = INTERVAL_SECONDS[selectedInterval] || 3600;
                    const count = WHITESPACE_BAR_COUNT[selectedInterval] || 60;
                    whitespaceSeriesRef.current.setData(buildWhitespace(bar.time, gap, count));
                }
                if (chartRef.current) {
                    const timeScale = chartRef.current.timeScale();
                    const logicalRange = timeScale.getVisibleLogicalRange();
                    if (logicalRange && logicalRange.to >= data.length - 5) {
                        timeScale.scrollToRealTime();
                    }
                }
            }

            // Real-time indicator updates
            if (engineRef.current) {
                const resultsMap = engineRef.current.update(
                    { time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume },
                    isNewBar,
                );
                const time = bar.time as UTCTimestamp;

                for (const [instanceId, val] of resultsMap) {
                    const seriesMap = indicatorSeriesRef.current.get(instanceId);
                    if (!seriesMap) continue;

                    if (typeof val === 'number') {
                        seriesMap.get('main')?.update({ time, value: val });
                    } else if (val && 'upper' in val && 'middle' in val && 'lower' in val) {
                        seriesMap.get('upper')?.update({ time, value: (val as any).upper });
                        seriesMap.get('middle')?.update({ time, value: (val as any).middle });
                        seriesMap.get('lower')?.update({ time, value: (val as any).lower });
                    } else if (val && 'macd' in val) {
                        const m = val as { macd: number; signal: number; histogram: number };
                        seriesMap.get('macd')?.update({ time, value: m.macd });
                        seriesMap.get('signal')?.update({ time, value: m.signal });
                        const hc = m.histogram >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)';
                        seriesMap.get('histogram')?.update({ time, value: m.histogram, color: hc });
                    } else if (val && 'k' in val) {
                        const st = val as { k: number; d: number };
                        seriesMap.get('k')?.update({ time, value: st.k });
                        seriesMap.get('d')?.update({ time, value: st.d });
                    } else if (val && 'adx' in val) {
                        const a = val as { adx: number; pdi: number; mdi: number };
                        seriesMap.get('adx')?.update({ time, value: a.adx });
                        seriesMap.get('pdi')?.update({ time, value: a.pdi });
                        seriesMap.get('mdi')?.update({ time, value: a.mdi });
                    } else if (val && 'isOn' in val) {
                        const sq = val as { value: number; isOn: boolean };
                        const sqc = sq.isOn ? '#ef4444' : '#10b981';
                        seriesMap.get('main')?.update({ time, value: sq.value, color: sqc });
                    }
                }
            }
        };

        registerUpdateHandler(handleRealtimeUpdate);
        return () => { registerUpdateHandler(null); };
    }, [registerUpdateHandler, data.length]);

    // Auto-load more data when scrolling left + detect if scrolled away from realtime
    const [isScrolledAway, setIsScrolledAway] = useState(false);

    return { engineRef, isScrolledAway, setIsScrolledAway };
}
