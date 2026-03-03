import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi, CandlestickData, HistogramData, UTCTimestamp, LogicalRange, WhitespaceData } from 'lightweight-charts';
import { CHART_COLORS, INTERVAL_SECONDS, WHITESPACE_BAR_COUNT, type ChartBar, type Interval } from '../constants';

/** Build future whitespace entries so the time axis shows upcoming dates. */
export function buildWhitespace(lastTime: number, gap: number, count: number): WhitespaceData[] {
    const ws: WhitespaceData[] = [];
    for (let i = 1; i <= count; i++) {
        ws.push({ time: (lastTime + gap * i) as UTCTimestamp });
    }
    return ws;
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
    newsMarkersRef: MutableRefObject<any>,
    data: ChartBar[],
    currentTicker: string,
    selectedInterval: Interval,
    showNewsMarkers: boolean,
    hasMore: boolean,
    loadingMore: boolean,
    loadMore: () => Promise<any>,
    replayControlsDataRef?: MutableRefObject<boolean>,
    chartVersion?: number,
) {
    const prevDataLengthRef = useRef(0);
    const prevTickerRef = useRef(currentTicker);
    const [isScrolledAway, setIsScrolledAway] = useState(false);

    // Update chart data
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
        if (!data || data.length === 0) return;
        if (replayControlsDataRef?.current) return;

        const tickerChanged = prevTickerRef.current !== currentTicker;
        if (tickerChanged) {
            prevDataLengthRef.current = 0;
            prevTickerRef.current = currentTicker;
        }
        const isPrepend = !tickerChanged && prevDataLengthRef.current > 0 && data.length > prevDataLengthRef.current;
        const prependedBars = isPrepend ? data.length - prevDataLengthRef.current : 0;

        const timeScale = chartRef.current?.timeScale();
        let savedLogicalRange: LogicalRange | null = null;
        if (isPrepend && timeScale) {
            savedLogicalRange = timeScale.getVisibleLogicalRange();
        }

        const candleData: CandlestickData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
        }));
        const volumeData: HistogramData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp, value: bar.volume,
            color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        }));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volumeData);

        if (whitespaceSeriesRef.current) {
            const lastBar = data[data.length - 1];
            const gap = INTERVAL_SECONDS[selectedInterval] || 3600;
            const count = WHITESPACE_BAR_COUNT[selectedInterval] || 60;
            whitespaceSeriesRef.current.setData(buildWhitespace(lastBar.time, gap, count));
        }

        if (data.length > 0) {
            const lastBar = data[data.length - 1];
            lastPriceInfoRef.current = { close: lastBar.close, open: lastBar.open };
        }

        if (savedLogicalRange && timeScale && prependedBars > 0) {
            timeScale.setVisibleLogicalRange({
                from: savedLogicalRange.from + prependedBars,
                to: savedLogicalRange.to + prependedBars,
            });
        }

        prevDataLengthRef.current = data.length;

        if (!showNewsMarkers && newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers([]);
        }
    }, [data, currentTicker, showNewsMarkers]);

    // Auto-load more on scroll + detect scrolled away
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
