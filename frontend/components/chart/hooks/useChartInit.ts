import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import {
    createChart,
    TickMarkType,
    ColorType,
    CrosshairMode,
    CandlestickSeries,
    BarSeries,
    AreaSeries,
    HistogramSeries,
    LineSeries,
    LineStyle,
    PriceScaleMode,
    type IChartApi,
    type ISeriesApi,
    type CandlestickData,
    type HistogramData,
    type UTCTimestamp,
    type LogicalRange,
} from 'lightweight-charts';
import { getUserTimezone, getTimezoneAbbrev } from '@/lib/date-utils';
import { getChartColors, INTERVAL_SECONDS, RIGHT_OFFSET_BARS, type ChartBar, type Interval } from '../constants';
import type { ChartCandleStyle } from '@/stores/useUserPreferencesStore';
import { createHoveredBarStore, findBarIndexByTime, type HoveredBarStore } from '../hoveredBarStore';

interface UseChartInitOptions {
    candleStyle?: ChartCandleStyle;
    /**
     * Ref to the raw OHLC data array. Used by the crosshair handler so that we
     * always resolve OHLC from source data instead of from the visible series
     * (line/area series only have `{time, value}` and would otherwise produce
     * `undefined` OHLC fields when the user switches chart style).
     */
    dataRef?: MutableRefObject<ChartBar[]>;
}

/** Visual series kind for a given candle style ('heikin-ashi' reuses candlestick). */
function seriesKindForStyle(style: ChartCandleStyle): 'bars' | 'line' | 'area' | 'candlestick' {
    if (style === 'bars' || style === 'line' || style === 'area') return style;
    return 'candlestick';
}

/** Create the main price series for the given style. */
function createMainSeries(
    chart: IChartApi,
    style: ChartCandleStyle,
    colors: ReturnType<typeof getChartColors>,
): ISeriesApi<any> {
    const priceLineOpts = {
        priceLineVisible: true,
        priceLineWidth: 1 as const,
        priceLineColor: colors.crosshair,
        priceLineStyle: LineStyle.Dotted,
        lastValueVisible: false,
    };
    const kind = seriesKindForStyle(style);
    if (kind === 'bars') {
        return chart.addSeries(BarSeries, {
            upColor: colors.upColor,
            downColor: colors.downColor,
            ...priceLineOpts,
        });
    }
    if (kind === 'line') {
        return chart.addSeries(LineSeries, {
            color: colors.crosshair,
            lineWidth: 2,
            ...priceLineOpts,
        });
    }
    if (kind === 'area') {
        return chart.addSeries(AreaSeries, {
            lineColor: colors.crosshair,
            topColor: colors.volumeUp,
            bottomColor: 'rgba(37, 99, 235, 0.04)',
            lineWidth: 2,
            ...priceLineOpts,
        });
    }
    // 'candles' and 'heikin-ashi' both use Candlestick; HA transforms data upstream.
    return chart.addSeries(CandlestickSeries, {
        upColor: colors.upColor,
        downColor: colors.downColor,
        wickUpColor: colors.upColor,
        wickDownColor: colors.downColor,
        borderVisible: false,
        ...priceLineOpts,
    });
}

export function useChartInit(
    containerRef: MutableRefObject<HTMLDivElement | null>,
    currentTicker: string,
    selectedInterval: Interval,
    fontFamily: string,
    priceOverlayRef: MutableRefObject<HTMLDivElement | null>,
    options: UseChartInitOptions = {},
) {
    const candleStyle: ChartCandleStyle = options.candleStyle ?? 'candles';
    const dataRef = options.dataRef;
    // The main effect reads the style via ref so style changes do NOT recreate
    // the chart — a dedicated effect below hot-swaps just the price series.
    const candleStyleRef = useRef(candleStyle);
    candleStyleRef.current = candleStyle;
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const sessionBgSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const whitespaceSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const watermarkRef = useRef<any>(null);
    const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const lastPriceInfoRef = useRef<{ close: number; open: number }>({ close: 0, open: 0 });
    const beforeDestroyCallbackRef = useRef<(() => void) | null>(null);
    /**
     * Called right before the main price series is hot-swapped (candle style
     * change). The owner must detach any primitives attached to the old series
     * (drawings, tentative) WITHOUT clearing indicator series refs — those
     * live on the chart, which survives the swap.
     */
    const beforeSeriesSwapCallbackRef = useRef<(() => void) | null>(null);
    const [chartVersion, setChartVersion] = useState(0);
    // Hovered bar lives in an external store (NOT React state): the crosshair
    // fires per pixel and routing it through state re-rendered the whole chart
    // tree. Display components subscribe via useDisplayBar().
    const hoveredBarStoreRef = useRef<HoveredBarStore | null>(null);
    if (!hoveredBarStoreRef.current) hoveredBarStoreRef.current = createHoveredBarStore();
    const hoveredBarStore = hoveredBarStoreRef.current;
    // Tracks which series kind is currently mounted, so the style-swap effect
    // only acts on real kind changes (candles ↔ heikin-ashi share a kind).
    const renderedSeriesKindRef = useRef<ReturnType<typeof seriesKindForStyle> | null>(null);

    useEffect(() => {
        if (!containerRef.current) return;

        const CHART_COLORS = getChartColors();
        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: CHART_COLORS.background },
                textColor: CHART_COLORS.textColor,
                fontFamily,
                fontSize: 11,
                attributionLogo: false,
                panes: {
                    separatorColor: CHART_COLORS.borderColor,
                    separatorHoverColor: CHART_COLORS.crosshair,
                    enableResize: true,
                },
            },
            grid: {
                vertLines: { color: CHART_COLORS.gridColor, style: LineStyle.Solid },
                horzLines: { color: CHART_COLORS.gridColor, style: LineStyle.Solid },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { color: CHART_COLORS.crosshair, width: 1, style: LineStyle.Dashed, labelBackgroundColor: CHART_COLORS.crosshair },
                horzLine: { color: CHART_COLORS.crosshair, width: 1, style: LineStyle.Dashed, labelBackgroundColor: CHART_COLORS.crosshair },
                doNotSnapToHiddenSeriesIndices: true,
            },
            rightPriceScale: {
                borderColor: CHART_COLORS.borderColor,
                scaleMargins: { top: 0.1, bottom: 0.2 },
                mode: PriceScaleMode.Normal,
                autoScale: true,
            },
            timeScale: {
                borderColor: CHART_COLORS.borderColor,
                timeVisible: true,
                secondsVisible: false,
                rightOffset: RIGHT_OFFSET_BARS,
                barSpacing: 8,
                minBarSpacing: 0.5,
                fixLeftEdge: false,
                fixRightEdge: false,
                allowShiftVisibleRangeOnWhitespaceReplacement: true,
                ticksVisible: true,
                uniformDistribution: true,
                enableConflation: true,
                tickMarkFormatter: (time: number, tickMarkType: TickMarkType) => {
                    const tz = getUserTimezone();
                    const d = new Date(time * 1000);
                    const sec = INTERVAL_SECONDS[selectedInterval] || 86400;
                    const intraday = sec < 86400;
                    switch (tickMarkType) {
                        case TickMarkType.Year:
                            return d.toLocaleDateString('en-US', { timeZone: tz, year: 'numeric' });
                        case TickMarkType.Month:
                            return d.toLocaleDateString('en-US', { timeZone: tz, month: 'short', year: intraday ? undefined : '2-digit' });
                        case TickMarkType.DayOfMonth:
                            return intraday
                                ? d.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short', day: 'numeric' })
                                : d.toLocaleDateString('en-US', { timeZone: tz, day: 'numeric', month: 'short' });
                        case TickMarkType.Time:
                            return d.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
                        case TickMarkType.TimeWithSeconds:
                            return d.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                        default:
                            return null;
                    }
                },
            },
            localization: {
                timeFormatter: (time: number) => {
                    const tz = getUserTimezone();
                    const abbrev = getTimezoneAbbrev(tz);
                    const d = new Date(time * 1000);
                    const sec = INTERVAL_SECONDS[selectedInterval] || 86400;
                    if (sec < 86400) {
                        return d.toLocaleString('en-US', { timeZone: tz, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) + ` ${abbrev}`;
                    }
                    if (sec >= 2592000) {
                        return d.toLocaleDateString('en-US', { timeZone: tz, month: 'long', year: 'numeric' });
                    }
                    return d.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
                },
            },
            handleScale: { axisPressedMouseMove: { time: true, price: true }, mouseWheel: true, pinch: true },
            handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
            kineticScroll: { mouse: true, touch: true },
            autoSize: false,
        });

        chartRef.current = chart;
        setChartVersion(v => v + 1);
        watermarkRef.current = null;

        const intSec = INTERVAL_SECONDS[selectedInterval] || 86400;
        const isIntraday = intSec < 86400;
        if (isIntraday) {
            const sessionBgSeries = chart.addSeries(HistogramSeries, {
                priceScaleId: 'session_bg', priceLineVisible: false, lastValueVisible: false, priceFormat: { type: 'price' },
            });
            chart.priceScale('session_bg').applyOptions({ visible: false, scaleMargins: { top: 0, bottom: 0 } });
            sessionBgSeriesRef.current = sessionBgSeries;
        } else {
            sessionBgSeriesRef.current = null;
        }

        const candleSeries = createMainSeries(chart, candleStyleRef.current, CHART_COLORS);
        candleSeriesRef.current = candleSeries;
        renderedSeriesKindRef.current = seriesKindForStyle(candleStyleRef.current);

        // Price overlay timer (countdown for intraday, price-only for daily+)
        if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
        const intervalSec = INTERVAL_SECONDS[selectedInterval] || 0;
        const showCountdown = intervalSec > 0 && intervalSec < 86400;
        {
            const intervalMs = showCountdown ? intervalSec * 1000 : 0;
            countdownIntervalRef.current = setInterval(() => {
                const overlay = priceOverlayRef.current;
                const series = candleSeriesRef.current;
                if (!overlay || !series) return;
                const { close, open } = lastPriceInfoRef.current;
                if (close <= 0) { overlay.style.display = 'none'; return; }
                const y = series.priceToCoordinate(close);
                if (y === null) { overlay.style.display = 'none'; return; }
                const bgColor = close >= open ? CHART_COLORS.upColor : CHART_COLORS.downColor;
                overlay.style.display = 'flex';
                overlay.style.top = `${y - 15}px`;
                overlay.style.backgroundColor = bgColor;
                let priceEl = overlay.querySelector('.p-val') as HTMLElement;
                let cdEl = overlay.querySelector('.p-cd') as HTMLElement;
                if (!priceEl) {
                    priceEl = document.createElement('div');
                    priceEl.className = 'p-val';
                    priceEl.style.cssText = 'font-size:11px;font-weight:600;line-height:1.2';
                    overlay.appendChild(priceEl);
                }
                priceEl.textContent = close.toFixed(2);
                if (showCountdown) {
                    if (!cdEl) {
                        cdEl = document.createElement('div');
                        cdEl.className = 'p-cd';
                        cdEl.style.cssText = 'font-size:9px;opacity:0.85;line-height:1.2';
                        overlay.appendChild(cdEl);
                    }
                    const now = Date.now();
                    const candleEnd = Math.ceil(now / intervalMs) * intervalMs;
                    const remaining = Math.max(0, candleEnd - now);
                    const totalSec = Math.floor(remaining / 1000);
                    let countdown: string;
                    if (intervalSec >= 3600) {
                        const hrs = Math.floor(totalSec / 3600);
                        const mins = Math.floor((totalSec % 3600) / 60);
                        const secs = totalSec % 60;
                        countdown = `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
                    } else {
                        const mins = Math.floor(totalSec / 60);
                        const secs = totalSec % 60;
                        countdown = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
                    }
                    cdEl.textContent = countdown;
                } else if (cdEl) {
                    cdEl.remove();
                }
            }, 500);
        }

        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: CHART_COLORS.volumeUp, priceFormat: { type: 'volume' }, priceScaleId: 'volume',
        });
        volumeSeriesRef.current = volumeSeries;
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

        const whitespaceSeries = chart.addSeries(LineSeries, {
            priceScaleId: 'whitespace_hidden',
            lineWidth: 1,
            pointMarkersVisible: false,
            crosshairMarkerVisible: false,
            lastValueVisible: false,
            priceLineVisible: false,
            visible: false,
        });
        chart.priceScale('whitespace_hidden').applyOptions({ visible: false });
        whitespaceSeriesRef.current = whitespaceSeries;

        chart.subscribeCrosshairMove((param) => {
            if (!param.point) return;
            if (!param.time || !param.seriesData) { hoveredBarStore.set(null); return; }
            const time = param.time as number;
            // Always resolve OHLC from the source data array so we work regardless
            // of which candleStyle is active (line/area series only carry `value`).
            const source = dataRef?.current;
            if (source && source.length > 0) {
                const idx = findBarIndexByTime(source, time);
                if (idx !== -1) {
                    hoveredBarStore.set(source[idx]);
                    return;
                }
            }
            // Fallback for candles/bars/heikin-ashi when no dataRef is wired.
            // Resolved via refs so the handler keeps working after a series hot-swap.
            if (hoveredBarStore.get()?.time === time) return;
            const activeCandleSeries = candleSeriesRef.current;
            if (!activeCandleSeries) return;
            const candleData = param.seriesData.get(activeCandleSeries) as CandlestickData | undefined;
            const volumeData = param.seriesData.get(volumeSeries) as HistogramData | undefined;
            if (candleData && typeof candleData.open === 'number' && volumeData) {
                hoveredBarStore.set({
                    time, open: candleData.open as number,
                    high: candleData.high as number, low: candleData.low as number,
                    close: candleData.close as number, volume: volumeData.value as number,
                });
            }
        });

        let resizeTimeout: NodeJS.Timeout | null = null;
        let lastWidth = 0;
        let lastHeight = 0;
        const applyResize = (width: number, height: number) => {
            if (!chartRef.current || width <= 0 || height <= 0) return;
            if (width === lastWidth && height === lastHeight) return;
            lastWidth = width; lastHeight = height;
            chartRef.current.applyOptions({ width, height });
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (chartRef.current) {
                    const ts = chartRef.current.timeScale();
                    const vr = ts.getVisibleLogicalRange();
                    ts.applyOptions({ rightOffset: RIGHT_OFFSET_BARS, barSpacing: 8 });
                    if (vr) ts.setVisibleLogicalRange(vr);
                }
            }, 150);
        };
        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                requestAnimationFrame(() => applyResize(width, height));
            }
        });
        resizeObserver.observe(containerRef.current);
        if (containerRef.current) applyResize(containerRef.current.clientWidth, containerRef.current.clientHeight);

        return () => {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeObserver.disconnect();
            lastPriceInfoRef.current = { close: 0, open: 0 };
            if (countdownIntervalRef.current) { clearInterval(countdownIntervalRef.current); countdownIntervalRef.current = null; }
            try { beforeDestroyCallbackRef.current?.(); } catch {}
            watermarkRef.current = null;
            sessionBgSeriesRef.current = null;
            whitespaceSeriesRef.current = null;
            chart.remove();
            chartRef.current = null;
            candleSeriesRef.current = null;
            volumeSeriesRef.current = null;
            hoveredBarStore.set(null);
        };
    }, [currentTicker, fontFamily, selectedInterval]);

    // ── Hot-swap the price series when the candle style changes ─────────
    // Recreating the whole chart for a style change (the old behaviour) tears
    // down primitives, indicator panes and listeners. Instead we replace just
    // the main series and bump chartVersion so dependents re-bind. Note:
    // candles ↔ heikin-ashi share the Candlestick series, so only the data
    // transform changes (handled by useChartData via its candleStyle dep).
    useEffect(() => {
        const chart = chartRef.current;
        const oldSeries = candleSeriesRef.current;
        if (!chart || !oldSeries) return;

        const nextKind = seriesKindForStyle(candleStyle);
        if (renderedSeriesKindRef.current === nextKind) return;

        // Let the owner detach series-bound primitives (drawings/tentative).
        try { beforeSeriesSwapCallbackRef.current?.(); } catch { /* */ }

        let savedOrder: number | null = null;
        try { savedOrder = oldSeries.seriesOrder(); } catch { /* */ }
        try { chart.removeSeries(oldSeries); } catch { /* */ }

        const newSeries = createMainSeries(chart, candleStyle, getChartColors());
        if (savedOrder !== null) {
            try { newSeries.setSeriesOrder(savedOrder); } catch { /* */ }
        }
        candleSeriesRef.current = newSeries;
        renderedSeriesKindRef.current = nextKind;

        // Re-bind everything that holds the old series (primitives, handlers,
        // multichart bridge). useChartData re-sets the data in this same commit
        // via its own candleStyle dependency.
        setChartVersion(v => v + 1);
    }, [candleStyle]);

    // Update watermark when ticker changes
    useEffect(() => {
        if (chartRef.current && watermarkRef.current) {
            try {
                watermarkRef.current.applyOptions({ lines: [{ text: currentTicker, color: getChartColors().watermark, fontSize: 72 }] });
            } catch { /* */ }
        }
    }, [currentTicker]);

    // Re-apply chart colors when theme changes (dark ↔ light)
    useEffect(() => {
        const observer = new MutationObserver(() => {
            const chart = chartRef.current;
            if (!chart) return;
            const c = getChartColors();
            chart.applyOptions({
                layout: {
                    background: { type: ColorType.Solid, color: c.background },
                    textColor: c.textColor,
                    panes: { separatorColor: c.borderColor, separatorHoverColor: c.crosshair },
                },
                grid: {
                    vertLines: { color: c.gridColor },
                    horzLines: { color: c.gridColor },
                },
                rightPriceScale: { borderColor: c.borderColor },
                timeScale: { borderColor: c.borderColor },
            });
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, []);

    return {
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef,
        whitespaceSeriesRef, watermarkRef, lastPriceInfoRef, beforeDestroyCallbackRef,
        beforeSeriesSwapCallbackRef,
        chartVersion, setChartVersion, hoveredBarStore,
    };
}
