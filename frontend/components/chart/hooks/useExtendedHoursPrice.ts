import { useEffect, useRef, useCallback } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi, IPriceLine } from 'lightweight-charts';
import { LineStyle } from 'lightweight-charts';
import { INTERVAL_SECONDS, type Interval } from '../constants';

interface ExtendedHoursPriceOptions {
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>;
    priceOverlayRef: MutableRefObject<HTMLDivElement | null>;
    selectedInterval: Interval;
    currentSession: string | null;
    ticker: string;
    isReplayActive: boolean;
    registerExtendedHoursHandler: (handler: ((price: number) => void) | null) => void;
}

const EH_COLORS = {
    PRE_MARKET: '#f97316',
    POST_MARKET: '#3b82f6',
} as const;

const EH_LABELS: Record<string, string> = {
    PRE_MARKET: 'Pre',
    POST_MARKET: 'Post',
};

/**
 * Real-time extended-hours price line on daily+ charts.
 *
 * Primary source: per-second WebSocket aggregates that useLiveChartData
 * discards for daily candles outside regular hours (9:30-16:00 ET).
 * Those discarded prices are forwarded here via registerExtendedHoursHandler.
 *
 * Seed: Polygon snapshot fetched once on mount to show a price immediately
 * before the first WS aggregate arrives.
 */
export function useExtendedHoursPrice({
    candleSeriesRef,
    priceOverlayRef,
    selectedInterval,
    currentSession,
    ticker,
    isReplayActive,
    registerExtendedHoursHandler,
}: ExtendedHoursPriceOptions) {
    const priceLineRef = useRef<IPriceLine | null>(null);
    const ehOverlayRef = useRef<HTMLDivElement | null>(null);
    const lastPriceRef = useRef<number>(0);
    const overlayTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const activeRef = useRef(false);
    const colorRef = useRef('');
    const labelRef = useRef('');

    const updatePriceLine = useCallback((price: number) => {
        if (!activeRef.current || price <= 0) return;
        const series = candleSeriesRef.current;
        if (!series) return;

        lastPriceRef.current = price;

        if (priceLineRef.current) {
            try { series.removePriceLine(priceLineRef.current); } catch {}
        }

        priceLineRef.current = series.createPriceLine({
            price,
            color: colorRef.current,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: '',
        });
    }, [candleSeriesRef]);

    const updateOverlayPosition = useCallback(() => {
        const series = candleSeriesRef.current;
        const price = lastPriceRef.current;
        if (!activeRef.current || !series || price <= 0) {
            if (ehOverlayRef.current) ehOverlayRef.current.style.display = 'none';
            return;
        }

        const parentEl = priceOverlayRef.current?.parentElement;
        if (!parentEl) return;

        if (!ehOverlayRef.current) {
            const el = document.createElement('div');
            el.style.cssText = [
                'position:absolute', 'right:0', 'display:none', 'flex-direction:column',
                'align-items:center', 'color:white', 'padding:1px 4px', 'border-radius:2px',
                'text-align:center', 'z-index:19', 'pointer-events:none', 'min-width:50px',
                'font-size:11px', 'font-weight:600', 'line-height:1.2',
            ].join(';');
            parentEl.appendChild(el);
            ehOverlayRef.current = el;
        }

        const overlay = ehOverlayRef.current;
        const y = series.priceToCoordinate(price);
        if (y === null) {
            overlay.style.display = 'none';
            return;
        }

        overlay.style.display = 'flex';
        overlay.style.top = `${y - 10}px`;
        overlay.style.backgroundColor = colorRef.current;
        overlay.textContent = `${labelRef.current} ${price.toFixed(2)}`;
    }, [candleSeriesRef, priceOverlayRef]);

    useEffect(() => {
        const cleanup = () => {
            activeRef.current = false;
            registerExtendedHoursHandler(null);

            if (overlayTimerRef.current) {
                clearInterval(overlayTimerRef.current);
                overlayTimerRef.current = null;
            }
            if (priceLineRef.current && candleSeriesRef.current) {
                try { candleSeriesRef.current.removePriceLine(priceLineRef.current); } catch {}
                priceLineRef.current = null;
            }
            if (ehOverlayRef.current) {
                try { ehOverlayRef.current.remove(); } catch {}
                ehOverlayRef.current = null;
            }
            lastPriceRef.current = 0;
        };

        const intervalSec = INTERVAL_SECONDS[selectedInterval] || 86400;
        const isDailyOrAbove = intervalSec >= 86400;
        const isExtendedSession = currentSession === 'PRE_MARKET' || currentSession === 'POST_MARKET';

        if (!isDailyOrAbove || !isExtendedSession || isReplayActive || !ticker) {
            cleanup();
            return cleanup;
        }

        const session = currentSession as 'PRE_MARKET' | 'POST_MARKET';
        colorRef.current = EH_COLORS[session];
        labelRef.current = EH_LABELS[session];
        activeRef.current = true;

        // Register for real-time WS aggregate prices (per-second)
        registerExtendedHoursHandler((price: number) => {
            updatePriceLine(price);
        });

        // Overlay position timer (re-positions on zoom/scroll, 500ms)
        overlayTimerRef.current = setInterval(updateOverlayPosition, 500);

        // Seed: fetch snapshot once for immediate display before first WS tick
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${apiUrl}/api/v1/ticker/${ticker.toUpperCase()}/snapshot`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (!activeRef.current) return;
                const price = data?.ticker?.lastTrade?.p;
                if (price && price > 0 && lastPriceRef.current === 0) {
                    updatePriceLine(price);
                    updateOverlayPosition();
                }
            })
            .catch(() => {});

        return cleanup;
    }, [selectedInterval, currentSession, ticker, isReplayActive, registerExtendedHoursHandler, updatePriceLine, updateOverlayPosition]);
}
