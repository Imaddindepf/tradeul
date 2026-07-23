/**
 * useChartNews
 *
 * Loads news articles for the current ticker and exposes them as:
 *  1. `newsEvents`: a stream consumed by useEventMarkers to render N circles in
 *     the time-axis (consistent with earnings markers).
 *  2. `newsPriceLinesRef`: horizontal price lines anchored to each article
 *     (kept on the chart pane — visually distinct from the time-axis markers).
 *  3. `newsTimeMap`: lookup so click handlers on the chart can open the news
 *     popup for a given timestamp.
 *
 * Previously this hook drew chart-pane markers via `setMarkers()` while
 * earnings used a time-axis primitive — visually inconsistent. The new flow
 * keeps both kinds of markers in the same primitive while preserving the
 * existing click → open-popup behavior.
 */
import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import { useTranslation } from 'react-i18next';
import { useArticlesByTicker } from '@/stores/useNewsStore';
import { getUserTimezone } from '@/lib/date-utils';
import { roundToInterval } from '../formatters';
import { ChartNewsPopup } from '../ChartNewsPopup';
import type { ChartEvent } from '../primitives/EventMarkerPrimitive';
import type { ChartBar, Interval } from '../constants';

interface NewsArticle {
    id?: string;
    benzinga_id?: number;
    published?: string;
    tickerPrices?: Record<string, number>;
    [key: string]: unknown;
}

/** Stable dedup key for a news article. */
function newsKey(a: NewsArticle): string {
    const raw = a.benzinga_id ?? a.id;
    if (raw != null) return String(raw);
    return `${a.published ?? ''}|${(a.title as string) ?? ''}`;
}

interface OpenWindowFn {
    (opts: any): void;
}

/** Resolve a CSS custom property to a concrete color string (canvas-safe). */
function resolveCssColor(varName: string, fallback: string): string {
    if (typeof document === 'undefined') return fallback;
    const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return v || fallback;
}

export function useChartNews(
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    data: ChartBar[],
    selectedInterval: Interval,
    currentTicker: string,
    showNewsMarkers: boolean,
    openWindow: OpenWindowFn,
) {
    const { t } = useTranslation();
    // Live articles already in the global store (real-time WS updates).
    const storeNews = useArticlesByTicker(currentTicker);
    // Ticker-scoped history fetched on demand. The global store only holds the
    // ~200 most recent *global* articles, so a ticker with no very recent news
    // (e.g. CDT) would otherwise show nothing on the chart. We fetch the
    // ticker's own news directly, mirroring how earnings markers self-fetch.
    const [fetchedNews, setFetchedNews] = useState<NewsArticle[]>([]);
    const newsPriceLinesRef = useRef<any[]>([]);
    const newsTimeMapRef = useRef<Map<number, NewsArticle[]>>(new Map());

    useEffect(() => {
        if (!showNewsMarkers || !currentTicker) {
            setFetchedNews([]);
            return;
        }
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const controller = new AbortController();
        fetch(
            `${apiUrl}/news/api/v1/news?ticker=${encodeURIComponent(currentTicker.toUpperCase())}&limit=200`,
            { signal: controller.signal },
        )
            .then(res => (res.ok ? res.json() : null))
            .then(d => {
                if (d?.results && Array.isArray(d.results)) setFetchedNews(d.results);
                else setFetchedNews([]);
            })
            .catch(err => {
                if (err.name !== 'AbortError') setFetchedNews([]);
            });
        return () => controller.abort();
    }, [currentTicker, showNewsMarkers]);

    // Merge store (live) + fetched (history), de-duplicated by stable key.
    const tickerNews = useMemo<NewsArticle[]>(() => {
        const byKey = new Map<string, NewsArticle>();
        for (const a of storeNews as unknown as NewsArticle[]) byKey.set(newsKey(a), a);
        for (const a of fetchedNews) {
            const k = newsKey(a);
            if (!byKey.has(k)) byKey.set(k, a);
        }
        return Array.from(byKey.values());
    }, [storeNews, fetchedNews]);

    /**
     * Build the time map (timestamp → list of articles) for click-to-open.
     * Always populated when news are visible; the map is also used to know
     * which dates to emit as event markers.
     */
    const newsEvents = useMemo<ChartEvent[]>(() => {
        newsTimeMapRef.current = new Map();
        if (!showNewsMarkers || tickerNews.length === 0 || data.length === 0) return [];

        const candleDataMap = new Map<number, ChartBar>();
        for (const bar of data) {
            const roundedTime = roundToInterval(bar.time, selectedInterval);
            candleDataMap.set(roundedTime, bar);
        }

        const eventsByDate = new Map<string, ChartEvent>();
        for (const news of tickerNews as unknown as NewsArticle[]) {
            if (!news.published) continue;
            const newsDate = new Date(news.published);
            const newsTimestamp = Math.floor(newsDate.getTime() / 1000);
            const roundedNewsTime = roundToInterval(newsTimestamp, selectedInterval);
            const candleMatch = candleDataMap.get(roundedNewsTime);
            if (!candleMatch) continue;

            // Track timestamp → articles for click handler.
            const bucket = newsTimeMapRef.current.get(candleMatch.time) ?? [];
            bucket.push(news);
            newsTimeMapRef.current.set(candleMatch.time, bucket);

            // One marker per calendar date (no clustering of dozens of N's).
            // IMPORTANT: must use market timezone (America/New_York) to match
            // EventMarkerPrimitive's _dateIndex keys, otherwise non-ET users
            // never get a candle match and the "N" badge silently disappears.
            const dateStr = new Date(candleMatch.time * 1000).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
            if (!eventsByDate.has(dateStr)) {
                eventsByDate.set(dateStr, {
                    date: dateStr,
                    kind: 'news',
                    label: news.published,
                    payload: { ticker: currentTicker, articleTimestamp: candleMatch.time },
                });
            }
        }

        return Array.from(eventsByDate.values());
    }, [showNewsMarkers, tickerNews, data, selectedInterval, currentTicker]);

    /**
     * Maintain horizontal price lines on the chart pane, one per article that
     * matches a candle. These are visually distinct from the markers and serve
     * to highlight the price level at which the news happened.
     */
    useEffect(() => {
        const series = candleSeriesRef.current;
        if (!series) return;

        for (const line of newsPriceLinesRef.current) {
            try { series.removePriceLine(line); } catch { /* */ }
        }
        newsPriceLinesRef.current = [];

        if (!showNewsMarkers || tickerNews.length === 0 || data.length === 0) return;

        const tz = getUserTimezone();
        // lightweight-charts draws price lines on a canvas and does NOT resolve
        // CSS variables, so we must resolve the news marker color to a concrete
        // value here (falling back to the amber default) or the lines render invalid.
        const newsLineColor = resolveCssColor('--color-chart-marker-news', '#f59e0b');
        const candleDataMap = new Map<number, ChartBar>();
        for (const bar of data) {
            const roundedTime = roundToInterval(bar.time, selectedInterval);
            candleDataMap.set(roundedTime, bar);
        }

        const seenPrices = new Set<number>();
        for (const news of tickerNews as unknown as NewsArticle[]) {
            if (!news.published) continue;
            const newsDate = new Date(news.published);
            const newsTimestamp = Math.floor(newsDate.getTime() / 1000);
            const roundedNewsTime = roundToInterval(newsTimestamp, selectedInterval);
            const candleMatch = candleDataMap.get(roundedNewsTime);
            if (!candleMatch) continue;

            const tickerUpper = currentTicker.toUpperCase();
            let newsPrice: number;
            if (news.tickerPrices && news.tickerPrices[tickerUpper]) {
                newsPrice = news.tickerPrices[tickerUpper];
            } else {
                const secondsInMinute = newsDate.getSeconds();
                const ratio = secondsInMinute / 60;
                newsPrice = candleMatch.open + (candleMatch.close - candleMatch.open) * ratio;
            }

            // Avoid creating duplicate price lines for the same exact level.
            const rounded = Math.round(newsPrice * 100);
            if (seenPrices.has(rounded)) continue;
            seenPrices.add(rounded);

            const timeLabel = newsDate.toLocaleTimeString('en-US', {
                timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false,
            });
            const priceLine = series.createPriceLine({
                price: newsPrice,
                color: newsLineColor,
                lineWidth: 2,
                lineStyle: 2,
                axisLabelVisible: true,
                title: timeLabel,
            });
            newsPriceLinesRef.current.push(priceLine);
        }

        return () => {
            for (const line of newsPriceLinesRef.current) {
                try { series.removePriceLine(line); } catch { /* */ }
            }
            newsPriceLinesRef.current = [];
        };
    }, [showNewsMarkers, tickerNews, data, selectedInterval, currentTicker]);

    const handleNewsMarkerClick = useCallback((time: number) => {
        const newsAtTime = newsTimeMapRef.current.get(time);
        if (newsAtTime && newsAtTime.length > 0) {
            openWindow({
                title: t('chart.newsTitle', { ticker: currentTicker }),
                content: <ChartNewsPopup ticker={currentTicker} articles={newsAtTime as any} />,
                width: 400, height: 300, x: 300, y: 150,
                minWidth: 320, minHeight: 200,
            });
        }
    }, [currentTicker, openWindow, t]);

    const showNewsMarkersRef = useRef(showNewsMarkers);
    showNewsMarkersRef.current = showNewsMarkers;
    const handleNewsMarkerClickRef = useRef(handleNewsMarkerClick);
    handleNewsMarkerClickRef.current = handleNewsMarkerClick;

    return {
        tickerNews,
        newsEvents,
        newsPriceLinesRef,
        newsTimeMapRef,
        showNewsMarkersRef,
        handleNewsMarkerClickRef,
        handleNewsMarkerClick,
    };
}
