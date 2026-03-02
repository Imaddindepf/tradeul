import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import {
    createChart,
    TickMarkType,
    ColorType,
    CrosshairMode,
    CandlestickSeries,
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
import { CHART_COLORS, INTERVAL_SECONDS, RIGHT_OFFSET_BARS, type ChartBar, type Interval } from '../constants';

export function useChartInit(
    containerRef: MutableRefObject<HTMLDivElement | null>,
    currentTicker: string,
    selectedInterval: Interval,
    fontFamily: string,
    priceOverlayRef: MutableRefObject<HTMLDivElement | null>,
) {
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const sessionBgSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const whitespaceSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const watermarkRef = useRef<any>(null);
    const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const lastPriceInfoRef = useRef<{ close: number; open: number }>({ close: 0, open: 0 });
    const beforeDestroyCallbackRef = useRef<(() => void) | null>(null);
    const [chartVersion, setChartVersion] = useState(0);
    const [hoveredBar, setHoveredBar] = useState<ChartBar | null>(null);

    useEffect(() => {
        if (!containerRef.current) return;

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

        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: CHART_COLORS.upColor, downColor: CHART_COLORS.downColor,
            wickUpColor: CHART_COLORS.upColor, wickDownColor: CHART_COLORS.downColor,
            borderVisible: false, priceLineVisible: true, priceLineWidth: 1,
            priceLineColor: CHART_COLORS.crosshair, priceLineStyle: LineStyle.Dotted, lastValueVisible: false,
        });
        candleSeriesRef.current = candleSeries;

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
            if (!param.time || !param.seriesData) { setHoveredBar(null); return; }
            const candleData = param.seriesData.get(candleSeries) as CandlestickData | undefined;
            const volumeData = param.seriesData.get(volumeSeries) as HistogramData | undefined;
            if (candleData && volumeData) {
                setHoveredBar({
                    time: param.time as number, open: candleData.open as number,
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
        };
    }, [currentTicker, fontFamily, selectedInterval]);

    // Update watermark when ticker changes
    useEffect(() => {
        if (chartRef.current && watermarkRef.current) {
            try {
                watermarkRef.current.applyOptions({ lines: [{ text: currentTicker, color: CHART_COLORS.watermark, fontSize: 72 }] });
            } catch { /* */ }
        }
    }, [currentTicker]);

    return {
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef,
        whitespaceSeriesRef, watermarkRef, lastPriceInfoRef, beforeDestroyCallbackRef,
        chartVersion, setChartVersion, hoveredBar, setHoveredBar,
    };
}
