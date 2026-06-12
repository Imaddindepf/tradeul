import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type {
    IChartApi,
    ISeriesApi,
    CandlestickData,
    BarData,
    LineData,
    HistogramData,
    UTCTimestamp,
    LogicalRange,
    WhitespaceData,
} from 'lightweight-charts';
import { CHART_COLORS, INTERVAL_SECONDS, WHITESPACE_BAR_COUNT, type ChartBar, type Interval } from '../constants';
import { computeHeikinAshi } from '../utils/heikinAshi';
import type { ChartCandleStyle } from '@/stores/useUserPreferencesStore';

/** Build future whitespace entries so the time axis shows upcoming dates. */
export function buildWhitespace(lastTime: number, gap: number, count: number): WhitespaceData[] {
    const ws: WhitespaceData[] = [];
    for (let i = 1; i <= count; i++) {
        ws.push({ time: (lastTime + gap * i) as UTCTimestamp });
    }
    return ws;
}

/**
 * Build the data array shape required by the active candle series.
 *  - Candlestick / Bar: full OHLC
 *  - Line / Area: { time, value: close }
 *  - Heikin-Ashi: candlestick shape with HA-transformed OHLC
 */
function buildSeriesData(bars: ChartBar[], style: ChartCandleStyle): any[] {
    if (style === 'line' || style === 'area') {
        const out: LineData[] = bars.map(bar => ({
            time: bar.time as UTCTimestamp,
            value: bar.close,
        }));
        return out;
    }
    const source = style === 'heikin-ashi' ? computeHeikinAshi(bars) : bars;
    if (style === 'bars') {
        const out: BarData[] = source.map(bar => ({
            time: bar.time as UTCTimestamp,
            open: bar.open, high: bar.high, low: bar.low, close: bar.close,
        }));
        return out;
    }
    const out: CandlestickData[] = source.map(bar => ({
        time: bar.time as UTCTimestamp,
        open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    }));
    return out;
}

/**
 * Manages chart data updates: setData for candles/volume, scroll-position
 * preservation during loadMore, and auto-load on scroll.
 */
export function useChartData(
    chartRef: MutableRefObject<IChartApi | null>,
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    volumeSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    whitespaceSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    lastPriceInfoRef: MutableRefObject<{ close: number; open: number }>,
    data: ChartBar[],
    currentTicker: string,
    selectedInterval: Interval,
    hasMore: boolean,
    loadingMore: boolean,
    loadMore: () => Promise<any>,
    replayControlsDataRef?: MutableRefObject<boolean>,
    chartVersion?: number,
    candleStyle: ChartCandleStyle = 'candles',
) {
    const prevDataLengthRef = useRef(0);
    const prevTickerRef = useRef(currentTicker);
    // First/last bar times of the last applied dataset — used to classify the
    // change as append / prepend / reset without diffing the whole array.
    const prevFirstTimeRef = useRef(0);
    const prevLastTimeRef = useRef(0);
    const prevStyleRef = useRef(candleStyle);
    const prevChartVersionRef = useRef(chartVersion);
    const [isScrolledAway, setIsScrolledAway] = useState(false);

    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
        if (!data || data.length === 0) return;
        if (replayControlsDataRef?.current) return;

        const tickerChanged = prevTickerRef.current !== currentTicker;
        const styleChanged = prevStyleRef.current !== candleStyle;
        const chartChanged = prevChartVersionRef.current !== chartVersion;
        if (tickerChanged) {
            prevDataLengthRef.current = 0;
            prevTickerRef.current = currentTicker;
        }
        prevStyleRef.current = candleStyle;
        prevChartVersionRef.current = chartVersion;

        const prevLen = prevDataLengthRef.current;
        const firstTime = data[0].time;
        const lastTime = data[data.length - 1].time;

        const volumeBar = (bar: ChartBar): HistogramData => ({
            time: bar.time as UTCTimestamp,
            value: bar.volume,
            color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        });

        const finish = (rebuildWhitespace: boolean) => {
            const lastBar = data[data.length - 1];
            lastPriceInfoRef.current = { close: lastBar.close, open: lastBar.open };
            if (whitespaceSeriesRef.current && rebuildWhitespace) {
                const gap = INTERVAL_SECONDS[selectedInterval] || 3600;
                const count = WHITESPACE_BAR_COUNT[selectedInterval] || 60;
                whitespaceSeriesRef.current.setData(buildWhitespace(lastBar.time, gap, count));
            }
            prevDataLengthRef.current = data.length;
            prevFirstTimeRef.current = firstTime;
            prevLastTimeRef.current = lastTime;
        };

        const sameEpoch = !tickerChanged && !styleChanged && !chartChanged && prevLen > 0;

        // ── Append (loadForward / live bar promotion): update() per new bar.
        // setData() re-layouts every bar; with 10k+ candles that's a visible
        // hitch — update() touches only the right edge.
        if (
            sameEpoch && firstTime === prevFirstTimeRef.current &&
            data.length >= prevLen && lastTime >= prevLastTimeRef.current
        ) {
            // Re-emit from the bar that was previously last (its values may
            // have changed: e.g. a partial candle closing) plus all new bars.
            const fromIdx = Math.max(0, prevLen - 1);
            // Heikin-Ashi bars depend on the previous HA bar, so the transform
            // runs over the full array but only the tail gets pushed.
            const seriesTail = buildSeriesData(data, candleStyle).slice(fromIdx);
            const series = candleSeriesRef.current;
            const volume = volumeSeriesRef.current;
            try {
                for (const item of seriesTail) series.update(item);
                for (let i = fromIdx; i < data.length; i++) volume.update(volumeBar(data[i]));
                finish(lastTime !== prevLastTimeRef.current);
                return;
            } catch {
                // La serie puede contener una vela live más nueva que `data`
                // (carrera ws/refetch tras recargar): update() rechaza tiempos
                // antiguos ("Cannot update oldest data"). Caemos al setData
                // completo, que resetea la serie de forma segura.
            }
        }

        // ── Prepend (loadMore) or cold load: full setData ─────────────────
        const isPrepend =
            sameEpoch && data.length > prevLen &&
            lastTime === prevLastTimeRef.current && firstTime < prevFirstTimeRef.current;
        const prependedBars = isPrepend ? data.length - prevLen : 0;

        const timeScale = chartRef.current?.timeScale();
        let savedLogicalRange: LogicalRange | null = null;
        if (isPrepend && timeScale) {
            savedLogicalRange = timeScale.getVisibleLogicalRange();
        }

        candleSeriesRef.current.setData(buildSeriesData(data, candleStyle));
        volumeSeriesRef.current.setData(data.map(volumeBar));

        if (savedLogicalRange && timeScale && prependedBars > 0) {
            timeScale.setVisibleLogicalRange({
                from: savedLogicalRange.from + prependedBars,
                to: savedLogicalRange.to + prependedBars,
            });
        }

        finish(true);
    }, [data, currentTicker, candleStyle, chartVersion]);

    const loadMorePendingRef = useRef(false);
    const hasMoreRef = useRef(hasMore);
    hasMoreRef.current = hasMore;
    const dataLengthRef = useRef(data.length);
    dataLengthRef.current = data.length;
    const loadMoreRef = useRef(loadMore);
    loadMoreRef.current = loadMore;

    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;
        const timeScale = chart.timeScale();

        const handleVisibleRangeChange = () => {
            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) return;

            if (!replayControlsDataRef?.current) {
                const totalBars = dataLengthRef.current;
                const isNearRealtime = logicalRange.to >= totalBars - 3;
                setIsScrolledAway(!isNearRealtime && totalBars > 0);
            }

            if (!hasMoreRef.current || loadMorePendingRef.current || !candleSeriesRef.current) return;

            const barsInfo = candleSeriesRef.current.barsInLogicalRange(logicalRange);
            if (barsInfo !== null && barsInfo.barsBefore < 50) {
                loadMorePendingRef.current = true;
                loadMoreRef.current().finally(() => {
                    loadMorePendingRef.current = false;
                });
            }
        };

        timeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        return () => { timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange); };
    }, [chartVersion]);

    return { isScrolledAway };
}
