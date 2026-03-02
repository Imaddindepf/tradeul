import { useEffect, useRef, useCallback } from 'react';
import type { MutableRefObject } from 'react';
import {
    createSeriesMarkers,
    type ISeriesApi,
    type SeriesMarker,
    type Time,
    type UTCTimestamp,
} from 'lightweight-charts';
import { useArticlesByTicker } from '@/stores/useNewsStore';
import { getUserTimezone } from '@/lib/date-utils';
import { roundToInterval } from '../formatters';
import { ChartNewsPopup } from '../ChartNewsPopup';
import type { ChartBar, Interval } from '../constants';

export function useChartNews(
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    data: ChartBar[],
    selectedInterval: Interval,
    currentTicker: string,
    showNewsMarkers: boolean,
    openWindow: (opts: any) => void,
) {
    const tickerNews = useArticlesByTicker(currentTicker);

    const newsMarkersRef = useRef<any>(null);
    const newsPriceLinesRef = useRef<any[]>([]);
    const newsTimeMapRef = useRef<Map<number, any[]>>(new Map());

    useEffect(() => {
        if (!candleSeriesRef.current || !data || data.length === 0) return;

        for (const line of newsPriceLinesRef.current) {
            try { candleSeriesRef.current.removePriceLine(line); } catch { /* */ }
        }
        newsPriceLinesRef.current = [];
        newsTimeMapRef.current.clear();

        if (newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers([]);
        }

        if (!showNewsMarkers || tickerNews.length === 0) return;

        const newsMarkers: SeriesMarker<Time>[] = [];

        const candleDataMap = new Map<number, { time: number; open: number; high: number; low: number; close: number }>();
        for (const bar of data) {
            const roundedTime = roundToInterval(bar.time, selectedInterval);
            candleDataMap.set(roundedTime, { time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
        }

        for (const news of tickerNews) {
            if (!news.published) continue;

            const newsDate = new Date(news.published);
            const newsTimestamp = Math.floor(newsDate.getTime() / 1000);
            const roundedNewsTime = roundToInterval(newsTimestamp, selectedInterval);
            const candleMatch = candleDataMap.get(roundedNewsTime);

            if (candleMatch) {
                if (!newsTimeMapRef.current.has(candleMatch.time)) {
                    newsTimeMapRef.current.set(candleMatch.time, []);
                }
                newsTimeMapRef.current.get(candleMatch.time)!.push(news);

                let newsPrice: number;
                const tickerUpper = currentTicker.toUpperCase();

                if (news.tickerPrices && news.tickerPrices[tickerUpper]) {
                    newsPrice = news.tickerPrices[tickerUpper];
                } else {
                    const secondsInMinute = newsDate.getSeconds();
                    const ratio = secondsInMinute / 60;
                    newsPrice = candleMatch.open + (candleMatch.close - candleMatch.open) * ratio;
                }

                newsMarkers.push({
                    time: candleMatch.time as UTCTimestamp,
                    position: 'aboveBar',
                    color: '#f59e0b',
                    shape: 'arrowDown',
                    text: '📰',
                    size: 2,
                });

                const priceLine = candleSeriesRef.current!.createPriceLine({
                    price: newsPrice,
                    color: '#f59e0b',
                    lineWidth: 2,
                    lineStyle: 2,
                    axisLabelVisible: true,
                    title: `📰 ${newsDate.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', hour12: false })}`,
                });
                newsPriceLinesRef.current.push(priceLine);
            }
        }

        newsMarkers.sort((a, b) => (a.time as number) - (b.time as number));
        const uniqueMarkers = newsMarkers.filter((marker, index, self) =>
            index === self.findIndex(m => m.time === marker.time)
        );

        if (newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers(uniqueMarkers);
        } else if (candleSeriesRef.current && uniqueMarkers.length > 0) {
            newsMarkersRef.current = createSeriesMarkers(candleSeriesRef.current, uniqueMarkers);
        }
        return () => {
            newsMarkersRef.current = null;
            newsPriceLinesRef.current = [];
            newsTimeMapRef.current.clear();
        };
    }, [showNewsMarkers, tickerNews, data, selectedInterval, currentTicker]);

    const handleNewsMarkerClick = useCallback((time: number) => {
        const newsAtTime = newsTimeMapRef.current.get(time);
        if (newsAtTime && newsAtTime.length > 0) {
            openWindow({
                title: `📰 News: ${currentTicker}`,
                content: <ChartNewsPopup ticker={currentTicker} articles={newsAtTime} />,
                width: 400,
                height: 300,
                x: 300,
                y: 150,
                minWidth: 320,
                minHeight: 200,
            });
        }
    }, [currentTicker, openWindow]);

    const showNewsMarkersRef = useRef(showNewsMarkers);
    showNewsMarkersRef.current = showNewsMarkers;
    const handleNewsMarkerClickRef = useRef(handleNewsMarkerClick);
    handleNewsMarkerClickRef.current = handleNewsMarkerClick;

    return {
        tickerNews,
        newsMarkersRef,
        newsPriceLinesRef,
        newsTimeMapRef,
        showNewsMarkersRef,
        handleNewsMarkerClickRef,
    };
}
