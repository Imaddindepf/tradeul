import { useEffect, useRef, useMemo } from 'react';
import type { MutableRefObject } from 'react';
import {
    LineSeries,
    HistogramSeries,
    LineStyle,
    type IChartApi,
    type ISeriesApi,
    type UTCTimestamp,
} from 'lightweight-charts';
import type { WorkerIndicatorConfig, IndicatorResults } from '@/hooks/useIndicatorWorker';
import { INDICATOR_TYPE_DEFAULTS, type IndicatorInstance, type ChartBar, type Interval, type TimeRange } from '../constants';

/**
 * Manages creating/destroying indicator series on the chart
 * and syncing worker results to them.
 */
export function useIndicatorSeries(
    chartRef: MutableRefObject<IChartApi | null>,
    indicatorSeriesRef: MutableRefObject<Map<string, Map<string, ISeriesApi<any>>>>,
    panelPaneIndexRef: MutableRefObject<Map<string, number>>,
    indicators: IndicatorInstance[],
    indicatorResults: IndicatorResults | null,
    data: ChartBar[],
    currentTicker: string,
    selectedInterval: Interval,
    selectedRange: TimeRange,
    workerReady: boolean,
    calculate: (...args: any[]) => void,
    clearCache: (ticker: string) => void,
    volumeSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    showVolume: boolean,
    chartVersion: number,
    isReplayActive: boolean,
) {
    // Dynamic indicator series creation/destruction
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const activeIds = new Set(indicators.filter(i => i.visible).map(i => i.id));

        for (const [id, seriesMap] of indicatorSeriesRef.current) {
            if (!activeIds.has(id)) {
                const paneIdx = panelPaneIndexRef.current.get(id);
                if (paneIdx !== undefined) {
                    try { chart.removePane(paneIdx); } catch {}
                    panelPaneIndexRef.current.delete(id);
                }
                for (const [, series] of seriesMap) {
                    try { chart.removeSeries(series); } catch {}
                }
                indicatorSeriesRef.current.delete(id);
            }
        }

        let nextPaneIndex = 1;
        const usedPanes = new Set(panelPaneIndexRef.current.values());
        while (usedPanes.has(nextPaneIndex)) nextPaneIndex++;

        for (const inst of indicators) {
            if (!inst.visible) continue;
            if (indicatorSeriesRef.current.has(inst.id)) continue;

            const seriesMap = new Map<string, ISeriesApi<any>>();
            const config = INDICATOR_TYPE_DEFAULTS[inst.type];
            if (!config) continue;

            try {
                if (config.category === 'overlay') {
                    if (inst.type === 'sma' || inst.type === 'ema' || inst.type === 'vwap') {
                        const s = chart.addSeries(LineSeries, {
                            color: (inst.styles.color as string) || config.defaultStyles.color as string,
                            lineWidth: ((inst.styles.lineWidth as number) || config.defaultStyles.lineWidth as number) as 1 | 2 | 3 | 4,
                            priceLineVisible: false, lastValueVisible: true,
                            crosshairMarkerVisible: true, crosshairMarkerRadius: 3,
                        });
                        seriesMap.set('main', s);
                    } else if (inst.type === 'bb' || inst.type === 'keltner') {
                        const uc = (inst.styles.upperColor as string) || config.defaultStyles.upperColor as string;
                        const mc = (inst.styles.middleColor as string) || config.defaultStyles.middleColor as string;
                        const lc = (inst.styles.lowerColor as string) || config.defaultStyles.lowerColor as string;
                        const lw = ((inst.styles.lineWidth as number) || config.defaultStyles.lineWidth as number) as 1 | 2 | 3 | 4;
                        seriesMap.set('upper', chart.addSeries(LineSeries, { color: uc, lineWidth: lw, priceLineVisible: false, lastValueVisible: false }));
                        seriesMap.set('middle', chart.addSeries(LineSeries, { color: mc, lineWidth: lw, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true }));
                        seriesMap.set('lower', chart.addSeries(LineSeries, { color: lc, lineWidth: lw, priceLineVisible: false, lastValueVisible: false }));
                    }
                } else {
                    while (usedPanes.has(nextPaneIndex)) nextPaneIndex++;
                    switch (inst.type) {
                        case 'rsi': {
                            const s = chart.addSeries(LineSeries, { color: (inst.styles.color as string) || '#8b5cf6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex);
                            s.createPriceLine({ price: 70, color: 'rgba(239,68,68,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            s.createPriceLine({ price: 30, color: 'rgba(16,185,129,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            seriesMap.set('main', s);
                            break;
                        }
                        case 'macd': {
                            const psId = `macd_${nextPaneIndex}`;
                            seriesMap.set('histogram', chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false, priceScaleId: psId }, nextPaneIndex));
                            seriesMap.set('macd', chart.addSeries(LineSeries, { color: (inst.styles.macdColor as string) || '#3b82f6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true, priceScaleId: psId }, nextPaneIndex));
                            seriesMap.set('signal', chart.addSeries(LineSeries, { color: (inst.styles.signalColor as string) || '#f97316', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false, priceScaleId: psId }, nextPaneIndex));
                            break;
                        }
                        case 'stoch': {
                            const kS = chart.addSeries(LineSeries, { color: (inst.styles.kColor as string) || '#3b82f6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex);
                            const dS = chart.addSeries(LineSeries, { color: (inst.styles.dColor as string) || '#f97316', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex);
                            kS.createPriceLine({ price: 80, color: 'rgba(239,68,68,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            kS.createPriceLine({ price: 20, color: 'rgba(16,185,129,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            seriesMap.set('k', kS); seriesMap.set('d', dS); seriesMap.set('main', kS);
                            break;
                        }
                        case 'adx': {
                            seriesMap.set('adx', chart.addSeries(LineSeries, { color: (inst.styles.adxColor as string) || '#8b5cf6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            seriesMap.set('pdi', chart.addSeries(LineSeries, { color: (inst.styles.pdiColor as string) || '#10b981', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex));
                            seriesMap.set('mdi', chart.addSeries(LineSeries, { color: (inst.styles.mdiColor as string) || '#ef4444', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex));
                            seriesMap.set('main', seriesMap.get('adx')!);
                            break;
                        }
                        case 'atr': case 'obv': {
                            seriesMap.set('main', chart.addSeries(LineSeries, { color: (inst.styles.color as string) || config.defaultStyles.color as string, lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            break;
                        }
                        case 'squeeze': case 'rvol': {
                            seriesMap.set('main', chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            break;
                        }
                    }
                    panelPaneIndexRef.current.set(inst.id, nextPaneIndex);
                    usedPanes.add(nextPaneIndex);
                    try { const pane = chart.panes()[nextPaneIndex]; if (pane) pane.setHeight(100); } catch {}
                    nextPaneIndex++;
                }
                indicatorSeriesRef.current.set(inst.id, seriesMap);
            } catch (err) {
                console.warn('[TradingChart] Failed to create indicator', inst.id, err);
            }
        }
    }, [indicators, chartVersion]);

    // Toggle volume visibility
    useEffect(() => {
        if (volumeSeriesRef.current) {
            volumeSeriesRef.current.applyOptions({ visible: showVolume });
        }
    }, [showVolume]);

    // Worker configs
    const workerConfigs = useMemo((): WorkerIndicatorConfig[] => {
        return indicators.filter(i => i.visible).map(i => ({ id: i.id, type: i.type, params: i.params }));
    }, [indicators]);

    // Calculate indicators in worker
    const lastBarCountRef = useRef(0);
    const lastIntervalRef = useRef(selectedInterval);
    const lastRangeRef = useRef(selectedRange);

    useEffect(() => {
        const intervalChanged = lastIntervalRef.current !== selectedInterval;
        const rangeChanged = lastRangeRef.current !== selectedRange;
        if (intervalChanged || rangeChanged) {
            clearCache(currentTicker);
            lastIntervalRef.current = selectedInterval;
            lastRangeRef.current = selectedRange;
            lastBarCountRef.current = 0;
        }
        if (!workerReady || !data.length || workerConfigs.length === 0) return;
        calculate(currentTicker, data, workerConfigs, selectedInterval);
        lastBarCountRef.current = data.length;
    }, [workerReady, data, data.length, workerConfigs, currentTicker, selectedInterval, selectedRange, calculate, clearCache]);

    // Update indicator series from worker results
    // During replay, syncIndicators in useBarReplay handles filtered data — skip here.
    useEffect(() => {
        if (!indicatorResults || !chartRef.current || isReplayActive) return;
        for (const inst of indicators) {
            if (!inst.visible) continue;
            const result = (indicatorResults as any)[inst.id];
            if (!result) continue;
            const seriesMap = indicatorSeriesRef.current.get(inst.id);
            if (!seriesMap) continue;
            const { type, data: rData } = result as any;
            try {
                if (type === 'sma' || type === 'ema' || type === 'vwap' || type === 'rsi' || type === 'atr' || type === 'obv') {
                    const main = seriesMap.get('main');
                    if (main && Array.isArray(rData)) main.setData(rData.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'bb' || type === 'keltner') {
                    if (rData?.upper) seriesMap.get('upper')?.setData(rData.upper.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.middle) seriesMap.get('middle')?.setData(rData.middle.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.lower) seriesMap.get('lower')?.setData(rData.lower.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'macd') {
                    if (rData?.histogram) seriesMap.get('histogram')?.setData(rData.histogram.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value, color: d.color || (d.value >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)') })));
                    if (rData?.macd) seriesMap.get('macd')?.setData(rData.macd.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.signal) seriesMap.get('signal')?.setData(rData.signal.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'stoch') {
                    if (rData?.k) seriesMap.get('k')?.setData(rData.k.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.d) seriesMap.get('d')?.setData(rData.d.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'adx') {
                    if (rData?.adx) seriesMap.get('adx')?.setData(rData.adx.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.pdi) seriesMap.get('pdi')?.setData(rData.pdi.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.mdi) seriesMap.get('mdi')?.setData(rData.mdi.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'squeeze' || type === 'rvol') {
                    const main = seriesMap.get('main');
                    if (main && Array.isArray(rData)) main.setData(rData.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value, color: d.color })));
                }
            } catch (err) {
                console.warn('[TradingChart] Error setting data for', inst.id, err);
            }
        }
    }, [indicatorResults, indicators, isReplayActive]);

}
