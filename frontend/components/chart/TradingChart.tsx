'use client';

import { useEffect, useRef, useState, useCallback, memo } from 'react';
import {
    createChart,
    ColorType,
    CrosshairMode,
    IChartApi,
    ISeriesApi,
    CandlestickData,
    HistogramData,
    Time,
    UTCTimestamp,
    LineStyle,
    PriceScaleMode,
    SeriesMarker
} from 'lightweight-charts';
import { RefreshCw, Maximize2, Minimize2, BarChart3, Search, ZoomIn, ZoomOut, Radio, Minus, Trash2, MousePointer, Newspaper, ExternalLink } from 'lucide-react';
import { useLiveChartData, type ChartInterval, type ChartBar as HookChartBar } from '@/hooks/useLiveChartData';
import { useChartDrawings, type Drawing, type DrawingTool } from '@/hooks/useChartDrawings';
import { useNewsStore } from '@/stores/useNewsStore';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

// ============================================================================
// Types
// ============================================================================

interface ChartBar {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface TradingChartProps {
    ticker: string;
    exchange?: string;
    onTickerChange?: (ticker: string) => void;
}

// Interval type is now ChartInterval from useLiveChartData
type Interval = ChartInterval;
type TimeRange = '1M' | '3M' | '6M' | '1Y' | '2Y' | '5Y' | 'ALL';

interface IntervalConfig {
    label: string;
    shortLabel: string;
    interval: Interval;
}

// ============================================================================
// Constants
// ============================================================================

const INTERVALS: IntervalConfig[] = [
    { label: '1 Minute', shortLabel: '1m', interval: '1min' },
    { label: '5 Minutes', shortLabel: '5m', interval: '5min' },
    { label: '15 Minutes', shortLabel: '15m', interval: '15min' },
    { label: '30 Minutes', shortLabel: '30m', interval: '30min' },
    { label: '1 Hour', shortLabel: '1H', interval: '1hour' },
    { label: '4 Hours', shortLabel: '4H', interval: '4hour' },
    { label: '1 Day', shortLabel: '1D', interval: '1day' },
];

// Time ranges in days
const TIME_RANGES: { id: TimeRange; label: string; days: number }[] = [
    { id: '1M', label: '1M', days: 30 },
    { id: '3M', label: '3M', days: 90 },
    { id: '6M', label: '6M', days: 180 },
    { id: '1Y', label: '1Y', days: 365 },
    { id: '2Y', label: '2Y', days: 730 },
    { id: '5Y', label: '5Y', days: 1825 },
    { id: 'ALL', label: 'ALL', days: 0 },
];

// Light theme matching app design (slate/white)
const CHART_COLORS = {
    background: '#ffffff',
    gridColor: '#f1f5f9',           // slate-100
    borderColor: '#e2e8f0',          // slate-200
    textColor: '#64748b',            // slate-500
    textStrong: '#334155',           // slate-700
    upColor: '#10b981',              // emerald-500
    downColor: '#ef4444',            // red-500
    upColorLight: '#d1fae5',         // emerald-100
    downColorLight: '#fee2e2',       // red-100
    volumeUp: 'rgba(16, 185, 129, 0.3)',
    volumeDown: 'rgba(239, 68, 68, 0.3)',
    crosshair: '#3b82f6',            // blue-500
    ma20: '#f59e0b',                 // amber-500
    ma50: '#6366f1',                 // indigo-500
    ema12: '#ec4899',                // pink-500
    ema26: '#8b5cf6',                // violet-500
    watermark: 'rgba(100, 116, 139, 0.07)',  // slate-500 muy tenue
};

// API Gateway URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Hook useChartData movido a @/hooks/useLiveChartData con soporte real-time

// ============================================================================
// Moving Average Calculators
// ============================================================================

function calculateSMA(data: ChartBar[], period: number): { time: Time; value: number }[] {
    const result: { time: Time; value: number }[] = [];

    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j].close;
        }
        result.push({
            time: data[i].time as UTCTimestamp,
            value: sum / period
        });
    }

    return result;
}

function calculateEMA(data: ChartBar[], period: number): { time: Time; value: number }[] {
    const result: { time: Time; value: number }[] = [];
    const multiplier = 2 / (period + 1);

    // Start with SMA for first value
    let sum = 0;
    for (let i = 0; i < period && i < data.length; i++) {
        sum += data[i].close;
    }

    if (data.length < period) return result;

    let ema = sum / period;
    result.push({ time: data[period - 1].time as UTCTimestamp, value: ema });

    for (let i = period; i < data.length; i++) {
        ema = (data[i].close - ema) * multiplier + ema;
        result.push({ time: data[i].time as UTCTimestamp, value: ema });
    }

    return result;
}

// ============================================================================
// Format helpers
// ============================================================================

function formatVolume(vol: number): string {
    if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(2)}B`;
    if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(2)}M`;
    if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
    return vol.toString();
}

function formatPrice(price: number): string {
    if (price >= 1000) return price.toFixed(0);
    if (price >= 100) return price.toFixed(1);
    if (price >= 1) return price.toFixed(2);
    return price.toFixed(4);
}

// ============================================================================
// News Popup Component (for chart markers)
// ============================================================================

interface NewsArticle {
    benzinga_id?: string;
    id?: string;
    title: string;
    url: string;
    published: string;
    author?: string;
}

function ChartNewsPopup({ ticker, articles }: { ticker: string; articles: NewsArticle[] }) {
    const formatTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        } catch {
            return '—';
        }
    };

    if (articles.length === 0) {
        return (
            <div className="flex items-center justify-center h-full bg-white p-4">
                <p className="text-slate-500 text-sm">No news for {ticker}</p>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full bg-white">
            <div className="px-3 py-2 bg-slate-50 border-b border-slate-200">
                <span className="text-sm font-bold text-blue-600">{ticker}</span>
                <span className="text-xs text-slate-500 ml-2">
                    {articles.length} article{articles.length !== 1 ? 's' : ''}
                </span>
            </div>
            <div className="flex-1 overflow-auto divide-y divide-slate-100">
                {articles.map((article, i) => (
                    <a
                        key={article.benzinga_id || article.id || i}
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block px-3 py-2 hover:bg-slate-50 group"
                    >
                        <div className="flex items-start gap-2">
                            <span className="text-xs text-slate-800 flex-1 leading-snug">{article.title}</span>
                            <ExternalLink className="w-3 h-3 text-slate-400 group-hover:text-blue-500 flex-shrink-0" />
                        </div>
                        <div className="text-xs text-slate-400 mt-1">
                            {formatTime(article.published)} · {article.author || 'Benzinga'}
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
}

// ============================================================================
// Component
// ============================================================================

function TradingChartComponent({ ticker: initialTicker = 'AAPL', exchange, onTickerChange }: TradingChartProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
    const ma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ma50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ema12SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ema26SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

    const [currentTicker, setCurrentTicker] = useState(initialTicker);
    const [selectedInterval, setSelectedInterval] = useState<Interval>('1day');
    const [selectedRange, setSelectedRange] = useState<TimeRange>('1Y');
    const [inputValue, setInputValue] = useState(initialTicker);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [showMA, setShowMA] = useState(true);
    const [showEMA, setShowEMA] = useState(false);
    const [showVolume, setShowVolume] = useState(true);
    const [showNewsMarkers, setShowNewsMarkers] = useState(false);
    const [hoveredBar, setHoveredBar] = useState<ChartBar | null>(null);

    const { data, loading, loadingMore, error, hasMore, isLive, refetch, loadMore, registerUpdateHandler } = useLiveChartData(currentTicker, selectedInterval);

    // News for markers
    const allNews = useNewsStore((state) => state.articles);
    const tickerNews = allNews.filter(article => 
        article.tickers?.some(t => t.toUpperCase() === currentTicker.toUpperCase())
    );
    
    // Floating window for news popup
    const { openWindow } = useFloatingWindow();

    // Drawing tools
    const {
        drawings,
        activeTool,
        isDrawing,
        selectedDrawingId,
        hoveredDrawingId,
        setActiveTool,
        cancelDrawing,
        handleChartClick,
        removeDrawing,
        clearAllDrawings,
        selectDrawing,
        updateHorizontalLinePrice,
        updateDrawingLineWidth,
        updateDrawingColor,
        startDragging,
        stopDragging,
        findDrawingNearPrice,
        setHoveredDrawing,
        colors: drawingColors,
    } = useChartDrawings(currentTicker);

    // Estado para popup de edición de línea
    const [editPopup, setEditPopup] = useState<{
        visible: boolean;
        drawingId: string | null;
        x: number;
        y: number;
    }>({ visible: false, drawingId: null, x: 0, y: 0 });

    // Obtener la línea que se está editando
    const editingDrawing = editPopup.drawingId
        ? drawings.find(d => d.id === editPopup.drawingId)
        : null;

    // Abrir popup de edición
    const openEditPopup = useCallback((drawingId: string, x: number, y: number) => {
        setEditPopup({ visible: true, drawingId, x, y });
        selectDrawing(drawingId);
    }, [selectDrawing]);

    // Cerrar popup
    const closeEditPopup = useCallback(() => {
        setEditPopup({ visible: false, drawingId: null, x: 0, y: 0 });
    }, []);

    // Cambiar color de la línea en edición
    const handleEditColor = useCallback((color: string) => {
        if (editPopup.drawingId) {
            updateDrawingColor(editPopup.drawingId, color);
        }
    }, [editPopup.drawingId, updateDrawingColor]);

    // Cambiar grosor de la línea en edición
    const handleEditLineWidth = useCallback((width: number) => {
        if (editPopup.drawingId) {
            updateDrawingLineWidth(editPopup.drawingId, width);
        }
    }, [editPopup.drawingId, updateDrawingLineWidth]);

    // Eliminar línea en edición
    const handleEditDelete = useCallback(() => {
        if (editPopup.drawingId) {
            removeDrawing(editPopup.drawingId);
            closeEditPopup();
        }
    }, [editPopup.drawingId, removeDrawing, closeEditPopup]);

    // Refs para price lines
    const priceLinesRef = useRef<Map<string, any>>(new Map());

    // Update when external ticker changes
    useEffect(() => {
        setCurrentTicker(initialTicker);
        setInputValue(initialTicker);
    }, [initialTicker]);

    // Apply time range to chart
    const applyTimeRange = useCallback((range: TimeRange) => {
        if (!chartRef.current || data.length === 0) return;

        const timeScale = chartRef.current.timeScale();
        const rangeConfig = TIME_RANGES.find(r => r.id === range);

        if (!rangeConfig) return;

        if (range === 'ALL' || rangeConfig.days === 0) {
            // Show all data
            timeScale.fitContent();
        } else {
            // Calculate how many bars to show based on days
            const barsToShow = Math.min(rangeConfig.days, data.length);
            const fromIndex = Math.max(0, data.length - barsToShow);

            if (data[fromIndex] && data[data.length - 1]) {
                timeScale.setVisibleRange({
                    from: data[fromIndex].time as UTCTimestamp,
                    to: data[data.length - 1].time as UTCTimestamp,
                });
            }
        }
    }, [data]);

    // Zoom functions
    const zoomIn = useCallback(() => {
        if (!chartRef.current) return;
        const timeScale = chartRef.current.timeScale();
        const currentBarSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.min(currentBarSpacing * 1.5, 50) });
    }, []);

    const zoomOut = useCallback(() => {
        if (!chartRef.current) return;
        const timeScale = chartRef.current.timeScale();
        const currentBarSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.max(currentBarSpacing / 1.5, 1) });
    }, []);

    // Reset zoom to fit all visible
    const resetZoom = useCallback(() => {
        if (!chartRef.current) return;
        chartRef.current.timeScale().fitContent();
    }, []);

    // Initialize chart
    useEffect(() => {
        if (!containerRef.current) return;

        // Create chart with light theme
        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: CHART_COLORS.background },
                textColor: CHART_COLORS.textColor,
                fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: CHART_COLORS.gridColor, style: LineStyle.Solid },
                horzLines: { color: CHART_COLORS.gridColor, style: LineStyle.Solid },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: {
                    color: CHART_COLORS.crosshair,
                    width: 1,
                    style: LineStyle.Dashed,
                    labelBackgroundColor: CHART_COLORS.crosshair,
                },
                horzLine: {
                    color: CHART_COLORS.crosshair,
                    width: 1,
                    style: LineStyle.Dashed,
                    labelBackgroundColor: CHART_COLORS.crosshair,
                },
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
                rightOffset: 5,
                barSpacing: 6,        // Smaller default for more bars
                minBarSpacing: 0.5,   // Allow very small bars
                fixLeftEdge: false,
                fixRightEdge: false,
            },
            handleScale: {
                axisPressedMouseMove: { time: true, price: true },
                mouseWheel: true,
                pinch: true,
            },
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: false,
            },
            watermark: {
                visible: true,
                fontSize: 72,
                horzAlign: 'center',
                vertAlign: 'center',
                color: CHART_COLORS.watermark,
                text: currentTicker,
            },
        });

        chartRef.current = chart;

        // Candlestick series with wicks
        const candleSeries = chart.addCandlestickSeries({
            upColor: CHART_COLORS.upColor,
            downColor: CHART_COLORS.downColor,
            borderUpColor: CHART_COLORS.upColor,
            borderDownColor: CHART_COLORS.downColor,
            wickUpColor: CHART_COLORS.upColor,
            wickDownColor: CHART_COLORS.downColor,
            priceLineVisible: true,
            priceLineWidth: 1,
            priceLineColor: CHART_COLORS.crosshair,
            priceLineStyle: LineStyle.Dotted,
            lastValueVisible: true,
        });
        candleSeriesRef.current = candleSeries;

        // Volume series
        const volumeSeries = chart.addHistogramSeries({
            color: CHART_COLORS.volumeUp,
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });
        volumeSeriesRef.current = volumeSeries;

        chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.85, bottom: 0 },
        });

        // MA20 line
        const ma20Series = chart.addLineSeries({
            color: CHART_COLORS.ma20,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 4,
        });
        ma20SeriesRef.current = ma20Series;

        // MA50 line
        const ma50Series = chart.addLineSeries({
            color: CHART_COLORS.ma50,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 4,
        });
        ma50SeriesRef.current = ma50Series;

        // EMA12 line
        const ema12Series = chart.addLineSeries({
            color: CHART_COLORS.ema12,
            lineWidth: 1,
            lineStyle: LineStyle.Solid,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 3,
        });
        ema12SeriesRef.current = ema12Series;

        // EMA26 line
        const ema26Series = chart.addLineSeries({
            color: CHART_COLORS.ema26,
            lineWidth: 1,
            lineStyle: LineStyle.Solid,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 3,
        });
        ema26SeriesRef.current = ema26Series;

        // Crosshair move handler for tooltip
        chart.subscribeCrosshairMove((param) => {
            if (!param.time || !param.seriesData) {
                setHoveredBar(null);
                return;
            }

            const candleData = param.seriesData.get(candleSeries) as CandlestickData | undefined;
            const volumeData = param.seriesData.get(volumeSeries) as HistogramData | undefined;

            if (candleData && volumeData) {
                setHoveredBar({
                    time: param.time as number,
                    open: candleData.open as number,
                    high: candleData.high as number,
                    low: candleData.low as number,
                    close: candleData.close as number,
                    volume: volumeData.value as number,
                });
            }
        });

        // Handle resize with proper size detection from ResizeObserver entries
        let resizeTimeout: NodeJS.Timeout | null = null;
        let lastWidth = 0;
        let lastHeight = 0;

        const applyResize = (width: number, height: number) => {
            if (!chartRef.current || width <= 0 || height <= 0) return;
            if (width === lastWidth && height === lastHeight) return;

            lastWidth = width;
            lastHeight = height;

            // Apply new dimensions immediately
            chartRef.current.applyOptions({ width, height });

            // After resize completes, force timeScale to recalculate labels
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (chartRef.current) {
                    const timeScale = chartRef.current.timeScale();
                    // Get current visible range before reset
                    const visibleRange = timeScale.getVisibleLogicalRange();
                    // Force complete recalculation
                    timeScale.applyOptions({
                        rightOffset: 5,
                        barSpacing: 6,
                    });
                    // Restore visible range if it was set
                    if (visibleRange) {
                        timeScale.setVisibleLogicalRange(visibleRange);
                    }
                }
            }, 150);
        };

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                // Use contentRect for accurate dimensions
                const { width, height } = entry.contentRect;
                requestAnimationFrame(() => applyResize(width, height));
            }
        });
        resizeObserver.observe(containerRef.current);

        // Initial size
        if (containerRef.current) {
            applyResize(containerRef.current.clientWidth, containerRef.current.clientHeight);
        }

        return () => {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeObserver.disconnect();
            chart.remove();
            chartRef.current = null;
        };
    }, [currentTicker]);

    // Auto-load more data when scrolling to the left edge (TradingView style)
    useEffect(() => {
        if (!chartRef.current || !hasMore || loadingMore) return;

        const chart = chartRef.current;
        const timeScale = chart.timeScale();

        const handleVisibleRangeChange = () => {
            if (loadingMore || !hasMore) return;

            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) return;

            // If user scrolled to show index < 50 (near the left edge), load more
            if (logicalRange.from < 50) {
                loadMore();
            }
        };

        // Subscribe to visible range changes
        timeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);

        return () => {
            timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        };
    }, [hasMore, loadingMore, loadMore]);

    // Update watermark when ticker changes
    useEffect(() => {
        if (chartRef.current) {
            chartRef.current.applyOptions({
                watermark: {
                    visible: true,
                    fontSize: 72,
                    horzAlign: 'center',
                    vertAlign: 'center',
                    color: CHART_COLORS.watermark,
                    text: currentTicker,
                },
            });
        }
    }, [currentTicker]);

    // Update chart data
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
        if (!data || data.length === 0) return;

        // Transform data for candlestick
        const candleData: CandlestickData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
        }));

        // Transform data for volume with colors
        const volumeData: HistogramData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            value: bar.volume,
            color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        }));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volumeData);

        // Clear markers if news markers disabled
        if (!showNewsMarkers) {
            candleSeriesRef.current.setMarkers([]);
        }

        // Calculate and set MAs
        if (ma20SeriesRef.current && ma50SeriesRef.current) {
            const ma20Data = calculateSMA(data, 20);
            const ma50Data = calculateSMA(data, 50);
            ma20SeriesRef.current.setData(ma20Data);
            ma50SeriesRef.current.setData(ma50Data);
        }

        // Calculate and set EMAs
        if (ema12SeriesRef.current && ema26SeriesRef.current) {
            const ema12Data = calculateEMA(data, 12);
            const ema26Data = calculateEMA(data, 26);
            ema12SeriesRef.current.setData(ema12Data);
            ema26SeriesRef.current.setData(ema26Data);
        }

        // Apply selected time range
        setTimeout(() => applyTimeRange(selectedRange), 50);
    }, [data, selectedRange, applyTimeRange, currentTicker, showNewsMarkers]);

    // ============================================================================
    // News markers effect - positioned at exact price with click support
    // ============================================================================
    const newsPriceLinesRef = useRef<any[]>([]);
    const newsTimeMapRef = useRef<Map<number, any[]>>(new Map()); // Map candle time -> news articles
    
    useEffect(() => {
        if (!candleSeriesRef.current || !data || data.length === 0) return;
        
        // Clear previous price lines
        for (const line of newsPriceLinesRef.current) {
            try {
                candleSeriesRef.current.removePriceLine(line);
            } catch (e) {
                // Ignore if already removed
            }
        }
        newsPriceLinesRef.current = [];
        newsTimeMapRef.current.clear();
        
        // Clear markers too
        candleSeriesRef.current.setMarkers([]);
        
        if (!showNewsMarkers || tickerNews.length === 0) {
            return;
        }

        const newsMarkers: SeriesMarker<Time>[] = [];
        
        // Create a map of candle data for quick lookup
        const candleDataMap = new Map<number, { time: number; open: number; high: number; low: number; close: number }>();
        for (const bar of data) {
            // Round to minute for matching
            const roundedTime = Math.floor(bar.time / 60) * 60;
            candleDataMap.set(roundedTime, {
                time: bar.time,
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close
            });
        }

        // For each news, find the matching candle and create marker at price
        for (const news of tickerNews) {
            if (!news.published) continue;
            
            // Parse news published time
            const newsDate = new Date(news.published);
            const newsTimestamp = Math.floor(newsDate.getTime() / 1000);
            const roundedNewsTime = Math.floor(newsTimestamp / 60) * 60;
            
            // Find matching candle
            const candleData = candleDataMap.get(roundedNewsTime);
            
            if (candleData) {
                // Store the news for this candle time (for click handling)
                if (!newsTimeMapRef.current.has(candleData.time)) {
                    newsTimeMapRef.current.set(candleData.time, []);
                }
                newsTimeMapRef.current.get(candleData.time)!.push(news);
                
                // Get the exact price if available, otherwise interpolate
                let newsPrice: number;
                const tickerUpper = currentTicker.toUpperCase();
                
                if (news.tickerPrices && news.tickerPrices[tickerUpper]) {
                    // Use exact captured price
                    newsPrice = news.tickerPrices[tickerUpper];
                } else {
                    // Fallback: Interpolate price based on seconds within the minute
                    const secondsInMinute = newsDate.getSeconds();
                    const ratio = secondsInMinute / 60; // 0 to 1
                    newsPrice = candleData.open + (candleData.close - candleData.open) * ratio;
                }
                
                // Add marker at the candle - arrowDown pointing to the price
                newsMarkers.push({
                    time: candleData.time as UTCTimestamp,
                    position: 'aboveBar',
                    color: '#f59e0b', // amber/gold color
                    shape: 'arrowDown',
                    text: '📰',
                    size: 2,
                });
                
                // Add a small price line annotation at that price
                const priceLine = candleSeriesRef.current.createPriceLine({
                    price: newsPrice,
                    color: '#f59e0b',
                    lineWidth: 2,
                    lineStyle: 2, // Dashed
                    axisLabelVisible: true,
                    title: `📰 ${newsDate.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}`,
                });
                newsPriceLinesRef.current.push(priceLine);
            }
        }

        // Sort markers by time (required by lightweight-charts)
        newsMarkers.sort((a, b) => (a.time as number) - (b.time as number));
        
        // Remove duplicates (same time) - keep first occurrence
        const uniqueMarkers = newsMarkers.filter((marker, index, self) => 
            index === self.findIndex(m => m.time === marker.time)
        );

        candleSeriesRef.current.setMarkers(uniqueMarkers);
        
        if (uniqueMarkers.length > 0) {
            console.log('[Chart] News markers added:', uniqueMarkers.length, 'with price lines');
        }
    }, [showNewsMarkers, tickerNews, data]);
    
    // Handler for clicking on news markers
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

    // ============================================================================
    // Register real-time update handler (uses series.update() - NO re-render)
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) {
            registerUpdateHandler(null);
            return;
        }

        const candleSeries = candleSeriesRef.current;
        const volumeSeries = volumeSeriesRef.current;

        // Handler que recibe updates del WebSocket sin causar re-render
        const handleRealtimeUpdate = (bar: HookChartBar, isNewBar: boolean) => {
            // Actualizar vela (series.update actualiza in-place sin re-render)
            candleSeries.update({
                time: bar.time as UTCTimestamp,
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
            });

            // Actualizar volumen
            const prevBar = data.length > 0 ? data[data.length - 1] : null;
            const volumeColor = bar.close >= bar.open
                ? CHART_COLORS.volumeUp
                : CHART_COLORS.volumeDown;

            volumeSeries.update({
                time: bar.time as UTCTimestamp,
                value: bar.volume,
                color: volumeColor,
            });

            // Si es nueva barra, scroll suave al final (solo si user está mirando el final)
            if (isNewBar && chartRef.current) {
                const timeScale = chartRef.current.timeScale();
                const logicalRange = timeScale.getVisibleLogicalRange();

                // Solo auto-scroll si user está cerca del final
                if (logicalRange && logicalRange.to >= data.length - 5) {
                    timeScale.scrollToPosition(0, true);
                }
            }
        };

        // Registrar handler
        registerUpdateHandler(handleRealtimeUpdate);

        return () => {
            registerUpdateHandler(null);
        };
    }, [registerUpdateHandler, data.length]);

    // ============================================================================
    // Renderizar dibujos (líneas horizontales) con hover y selección
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current) return;

        const candleSeries = candleSeriesRef.current;
        const currentLines = priceLinesRef.current;

        // Eliminar líneas que ya no existen
        currentLines.forEach((priceLine, id) => {
            if (!drawings.find(d => d.id === id)) {
                candleSeries.removePriceLine(priceLine);
                currentLines.delete(id);
            }
        });

        // Añadir/actualizar líneas
        drawings.forEach(drawing => {
            if (drawing.type === 'horizontal_line') {
                const existingLine = currentLines.get(drawing.id);
                const isSelected = selectedDrawingId === drawing.id;
                const isHovered = hoveredDrawingId === drawing.id;

                // Grosor visual: seleccionado > hover > normal
                const visualWidth = isSelected ? Math.max(drawing.lineWidth + 1, 3)
                    : isHovered ? Math.max(drawing.lineWidth, 2)
                        : drawing.lineWidth;

                if (existingLine) {
                    // Actualizar línea existente
                    existingLine.applyOptions({
                        price: drawing.price,
                        color: drawing.color,
                        lineWidth: visualWidth as 1 | 2 | 3 | 4,
                        lineStyle: isSelected || isHovered ? LineStyle.Solid :
                            drawing.lineStyle === 'dashed' ? LineStyle.Dashed :
                                drawing.lineStyle === 'dotted' ? LineStyle.Dotted : LineStyle.Solid,
                    });
                } else {
                    // Crear nueva línea
                    const lineStyle = drawing.lineStyle === 'dashed'
                        ? LineStyle.Dashed
                        : drawing.lineStyle === 'dotted'
                            ? LineStyle.Dotted
                            : LineStyle.Solid;

                    const priceLine = candleSeries.createPriceLine({
                        price: drawing.price,
                        color: drawing.color,
                        lineWidth: drawing.lineWidth as 1 | 2 | 3 | 4,
                        lineStyle,
                        axisLabelVisible: true,
                        title: drawing.label || '',
                    });

                    currentLines.set(drawing.id, priceLine);
                }
            }
        });
    }, [drawings, selectedDrawingId, hoveredDrawingId]);


    // ============================================================================
    // Estado local para drag overlay
    // ============================================================================
    const [dragState, setDragState] = useState<{
        active: boolean;
        drawingId: string | null;
        drawingType: 'horizontal_line' | null;
        originalPrice: number;
        startMouseY: number;
    }>({
        active: false,
        drawingId: null,
        drawingType: null,
        originalPrice: 0,
        startMouseY: 0,
    });

    // ============================================================================
    // Manejar clicks para dibujo/selección
    // ============================================================================
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;

        const chart = chartRef.current;
        const candleSeries = candleSeriesRef.current;

        const handleClick = (param: any) => {
            if (!param.point) return;

            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) return;

            // Check if clicked on a news marker
            if (showNewsMarkers && param.time && newsTimeMapRef.current.has(param.time as number)) {
                handleNewsMarkerClick(param.time as number);
                return;
            }

            if (activeTool === 'horizontal_line') {
                // Modo dibujo: crear línea horizontal
                handleChartClick(price);
            } else {
                // Modo normal: seleccionar/deseleccionar líneas
                const nearDrawing = findDrawingNearPrice(price, 0.5);
                if (nearDrawing) {
                    selectDrawing(nearDrawing.id);
                } else {
                    selectDrawing(null);
                }
            }
        };

        const handleDoubleClick = (param: any) => {
            if (!param.point || activeTool !== 'none') return;

            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) return;

            const nearDrawing = findDrawingNearPrice(price, 1.5);
            if (nearDrawing) {
                openEditPopup(nearDrawing.id, param.point.x + 20, param.point.y);
            }
        };

        chart.subscribeClick(handleClick);
        chart.subscribeDblClick(handleDoubleClick);

        return () => {
            chart.unsubscribeClick(handleClick);
            chart.unsubscribeDblClick(handleDoubleClick);
        };
    }, [activeTool, handleChartClick, findDrawingNearPrice, selectDrawing, openEditPopup, showNewsMarkers, handleNewsMarkerClick]);

    // ============================================================================
    // Hover detection para selección de líneas (solo cuando no estamos dibujando)
    // ============================================================================
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;
        if (dragState.active || activeTool !== 'none') return;

        const chart = chartRef.current;
        const candleSeries = candleSeriesRef.current;

        const handleCrosshairMove = (param: any) => {
            if (!param.point) {
                setHoveredDrawing(null);
                return;
            }

            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) {
                setHoveredDrawing(null);
                return;
            }

            const nearDrawing = findDrawingNearPrice(price, 1.5);
            setHoveredDrawing(nearDrawing?.id || null);
        };

        chart.subscribeCrosshairMove(handleCrosshairMove);

        return () => {
            chart.unsubscribeCrosshairMove(handleCrosshairMove);
        };
    }, [findDrawingNearPrice, setHoveredDrawing, dragState.active, activeTool]);

    // ============================================================================
    // Iniciar drag de línea horizontal
    // ============================================================================
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if (activeTool !== 'none' || !candleSeriesRef.current || !containerRef.current) return;
        if (editPopup.visible) return;

        const rect = containerRef.current.getBoundingClientRect();
        const mouseY = e.clientY - rect.top;
        const price = candleSeriesRef.current.coordinateToPrice(mouseY);
        if (price === null) return;

        const nearDrawing = findDrawingNearPrice(price, 1.0);
        if (!nearDrawing) return;

        e.preventDefault();
        e.stopPropagation();

        setDragState({
            active: true,
            drawingId: nearDrawing.id,
            drawingType: 'horizontal_line',
            originalPrice: nearDrawing.price,
            startMouseY: mouseY,
        });

        selectDrawing(nearDrawing.id);
        startDragging();
    }, [activeTool, findDrawingNearPrice, selectDrawing, startDragging, editPopup.visible]);

    // ============================================================================
    // Mover línea durante drag
    // ============================================================================
    const handleDragMove = useCallback((e: React.MouseEvent) => {
        if (!dragState.active || !dragState.drawingId || !candleSeriesRef.current || !containerRef.current) return;

        const container = containerRef.current;
        const rect = container.getBoundingClientRect();
        const mouseY = e.clientY - rect.top;

        const candleSeries = candleSeriesRef.current;

        // Calcular nuevo precio basado en posición actual del mouse
        const newPrice = candleSeries.coordinateToPrice(mouseY);
        if (newPrice !== null && newPrice > 0) {
            updateHorizontalLinePrice(dragState.drawingId, newPrice);
        }
    }, [dragState, updateHorizontalLinePrice]);

    // ============================================================================
    // Terminar drag
    // ============================================================================
    const handleDragEnd = useCallback(() => {
        if (dragState.active) {
            setDragState({
                active: false,
                drawingId: null,
                drawingType: null,
                originalPrice: 0,
                startMouseY: 0,
            });
            stopDragging();
            // Deseleccionar después de drag para evitar que el siguiente click mueva la línea
            setTimeout(() => selectDrawing(null), 50);
        }
    }, [dragState.active, stopDragging, selectDrawing]);

    // ============================================================================
    // Desactivar scroll del chart durante drag
    // ============================================================================
    useEffect(() => {
        if (!chartRef.current) return;

        chartRef.current.applyOptions({
            handleScroll: {
                mouseWheel: !dragState.active,
                pressedMouseMove: !dragState.active,
                horzTouchDrag: !dragState.active,
                vertTouchDrag: false,
            },
        });
    }, [dragState.active]);

    // ============================================================================
    // Atajos de teclado
    // ============================================================================
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ignorar si estamos en un input
            if ((e.target as HTMLElement).tagName === 'INPUT') return;

            switch (e.key) {
                case 'Escape':
                    cancelDrawing();
                    selectDrawing(null);
                    break;
                case 'h':
                case 'H':
                    setActiveTool(activeTool === 'horizontal_line' ? 'none' : 'horizontal_line');
                    break;
                case 'Delete':
                case 'Backspace':
                    if (selectedDrawingId) {
                        removeDrawing(selectedDrawingId);
                    }
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [activeTool, selectedDrawingId, cancelDrawing, selectDrawing, setActiveTool, removeDrawing]);

    // Cambiar cursor cuando hay herramienta activa
    useEffect(() => {
        if (!containerRef.current) return;
        containerRef.current.style.cursor = isDrawing ? 'crosshair' : 'default';
    }, [isDrawing]);

    // Handle range change
    const handleRangeChange = useCallback((range: TimeRange) => {
        setSelectedRange(range);
        applyTimeRange(range);
    }, [applyTimeRange]);

    // Toggle MA visibility
    useEffect(() => {
        if (ma20SeriesRef.current) {
            ma20SeriesRef.current.applyOptions({ visible: showMA });
        }
        if (ma50SeriesRef.current) {
            ma50SeriesRef.current.applyOptions({ visible: showMA });
        }
    }, [showMA]);

    // Toggle EMA visibility
    useEffect(() => {
        if (ema12SeriesRef.current) {
            ema12SeriesRef.current.applyOptions({ visible: showEMA });
        }
        if (ema26SeriesRef.current) {
            ema26SeriesRef.current.applyOptions({ visible: showEMA });
        }
    }, [showEMA]);

    // Toggle volume visibility
    useEffect(() => {
        if (volumeSeriesRef.current) {
            volumeSeriesRef.current.applyOptions({ visible: showVolume });
        }
    }, [showVolume]);

    const handleTickerChange = (e: React.FormEvent) => {
        e.preventDefault();
        const newTicker = inputValue.trim().toUpperCase();
        if (newTicker && newTicker !== currentTicker) {
            setCurrentTicker(newTicker);
            onTickerChange?.(newTicker);
        }
    };

    const toggleFullscreen = () => {
        const container = containerRef.current?.parentElement?.parentElement;
        if (!container) return;

        if (!document.fullscreenElement) {
            container.requestFullscreen();
            setIsFullscreen(true);
        } else {
            document.exitFullscreen();
            setIsFullscreen(false);
        }
    };

    // Listen for fullscreen changes and force chart resize
    useEffect(() => {
        const forceChartResize = () => {
            if (chartRef.current && containerRef.current) {
                const width = containerRef.current.clientWidth;
                const height = containerRef.current.clientHeight;

                if (width > 0 && height > 0) {
                    chartRef.current.applyOptions({ width, height });
                    // Recalculate time scale labels
                    chartRef.current.timeScale().applyOptions({
                        rightOffset: 5,
                        barSpacing: 6,
                    });
                }
            }
        };

        const handleFullscreenChange = () => {
            const isNowFullscreen = !!document.fullscreenElement;
            setIsFullscreen(isNowFullscreen);

            // Force multiple resize attempts to ensure DOM has settled
            // First attempt after short delay
            setTimeout(forceChartResize, 50);
            // Second attempt after DOM animation completes
            setTimeout(forceChartResize, 200);
            // Final attempt to catch any stragglers
            setTimeout(forceChartResize, 500);
        };

        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
    }, []);

    // Get display data (hovered or last bar)
    const displayBar = hoveredBar || (data.length > 0 ? data[data.length - 1] : null);
    const prevBar = data.length > 1 ? data[data.length - 2] : null;
    const priceChange = displayBar && prevBar ? displayBar.close - prevBar.close : 0;
    const priceChangePercent = displayBar && prevBar && prevBar.close !== 0
        ? ((priceChange / prevBar.close) * 100)
        : 0;
    const isPositive = priceChange >= 0;

    return (
        <div className="h-full flex flex-col bg-white border border-slate-200 rounded-lg overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50">
                <div className="flex items-center gap-4">
                    {/* Ticker search */}
                    <form onSubmit={handleTickerChange} className="flex items-center">
                        <div className="relative">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                            <input
                                type="text"
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value.toUpperCase())}
                                placeholder="TICKER"
                                className="w-24 pl-7 pr-2 py-1.5 text-xs font-semibold tracking-wide
                                         bg-white border border-slate-300 rounded-l-md
                                         focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                                         text-slate-800 placeholder-slate-400"
                            />
                        </div>
                        <button
                            type="submit"
                            className="px-3 py-1.5 bg-blue-600 text-white rounded-r-md hover:bg-blue-700 
                                     text-xs font-semibold transition-colors border border-blue-600"
                        >
                            Go
                        </button>
                    </form>

                    {/* Price info */}
                    {displayBar && (
                        <div className="flex items-center gap-3">
                            <span className="text-lg font-bold text-slate-800">
                                ${formatPrice(displayBar.close)}
                            </span>
                            <span className={`flex items-center gap-1 text-sm font-semibold px-2 py-0.5 rounded ${isPositive
                                ? 'text-emerald-700 bg-emerald-50'
                                : 'text-red-700 bg-red-50'
                                }`}>
                                {isPositive ? '▲' : '▼'}
                                {formatPrice(Math.abs(priceChange))} ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
                            </span>
                            {/* Live indicator */}
                            {isLive && (
                                <span className="flex items-center gap-1 text-xs font-medium text-red-500 animate-pulse">
                                    <Radio className="w-3 h-3" />
                                    LIVE
                                </span>
                            )}
                        </div>
                    )}
                </div>

                {/* Right controls */}
                <div className="flex items-center gap-1">
                    {/* SMA toggle */}
                    <button
                        onClick={() => setShowMA(!showMA)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${showMA
                            ? 'bg-amber-100 text-amber-700 border border-amber-300'
                            : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100 border border-transparent'
                            }`}
                        title="SMA (20, 50)"
                    >
                        SMA
                    </button>

                    {/* EMA toggle */}
                    <button
                        onClick={() => setShowEMA(!showEMA)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${showEMA
                            ? 'bg-pink-100 text-pink-700 border border-pink-300'
                            : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100 border border-transparent'
                            }`}
                        title="EMA (12, 26)"
                    >
                        EMA
                    </button>

                    {/* Volume toggle */}
                    <button
                        onClick={() => setShowVolume(!showVolume)}
                        className={`p-1.5 rounded transition-colors ${showVolume
                            ? 'bg-blue-100 text-blue-600'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                            }`}
                        title="Volume"
                    >
                        <BarChart3 className="w-4 h-4" />
                    </button>

                    {/* News markers toggle */}
                    <button
                        onClick={() => setShowNewsMarkers(!showNewsMarkers)}
                        className={`p-1.5 rounded transition-colors ${showNewsMarkers
                            ? 'bg-blue-100 text-blue-600'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                            }`}
                        title={`News Markers (${tickerNews.length})`}
                    >
                        <Newspaper className="w-4 h-4" />
                    </button>

                    <div className="w-px h-5 bg-slate-200 mx-1" />

                    {/* Zoom controls */}
                    <button
                        onClick={zoomIn}
                        className="p-1.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 transition-colors"
                        title="Zoom In"
                    >
                        <ZoomIn className="w-4 h-4" />
                    </button>
                    <button
                        onClick={zoomOut}
                        className="p-1.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 transition-colors"
                        title="Zoom Out"
                    >
                        <ZoomOut className="w-4 h-4" />
                    </button>

                    <div className="w-px h-5 bg-slate-200 mx-1" />

                    {/* Refresh */}
                    <button
                        onClick={refetch}
                        disabled={loading}
                        className="p-1.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 
                                 disabled:opacity-50 transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>

                    {/* Fullscreen */}
                    <button
                        onClick={toggleFullscreen}
                        className="p-1.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 transition-colors"
                        title="Fullscreen"
                    >
                        {isFullscreen ? (
                            <Minimize2 className="w-4 h-4" />
                        ) : (
                            <Maximize2 className="w-4 h-4" />
                        )}
                    </button>
                </div>
            </div>

            {/* Interval + Range selector */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-100 bg-white">
                {/* Interval buttons */}
                <div className="flex items-center gap-1">
                    {INTERVALS.map((int) => (
                        <button
                            key={int.interval}
                            onClick={() => setSelectedInterval(int.interval)}
                            className={`px-2 py-1 text-xs font-medium rounded transition-all ${selectedInterval === int.interval
                                ? 'bg-blue-600 text-white shadow-sm'
                                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                                }`}
                        >
                            {int.shortLabel}
                        </button>
                    ))}
                </div>

                {/* Time Range buttons */}
                <div className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-400 mr-1">Range:</span>
                    {TIME_RANGES.map((range) => (
                        <button
                            key={range.id}
                            onClick={() => handleRangeChange(range.id)}
                            className={`px-2 py-0.5 text-[10px] font-medium rounded transition-all ${selectedRange === range.id
                                ? 'bg-slate-700 text-white'
                                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                                }`}
                        >
                            {range.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Legend row */}
            <div className="flex items-center justify-end px-3 py-1 border-b border-slate-50 bg-white">
                <div className="flex items-center gap-3 text-[10px]">
                    {showMA && (
                        <>
                            <span className="flex items-center gap-1.5">
                                <span className="w-4 h-0.5 rounded" style={{ background: CHART_COLORS.ma20 }}></span>
                                <span className="text-slate-500">MA20</span>
                            </span>
                            <span className="flex items-center gap-1.5">
                                <span className="w-4 h-0.5 rounded" style={{ background: CHART_COLORS.ma50 }}></span>
                                <span className="text-slate-500">MA50</span>
                            </span>
                        </>
                    )}
                    {showEMA && (
                        <>
                            <span className="flex items-center gap-1.5">
                                <span className="w-4 h-0.5 rounded" style={{ background: CHART_COLORS.ema12 }}></span>
                                <span className="text-slate-500">EMA12</span>
                            </span>
                            <span className="flex items-center gap-1.5">
                                <span className="w-4 h-0.5 rounded" style={{ background: CHART_COLORS.ema26 }}></span>
                                <span className="text-slate-500">EMA26</span>
                            </span>
                        </>
                    )}
                </div>
            </div>

            {/* Chart container with drawing toolbar */}
            <div className="flex-1 min-h-0 flex bg-white overflow-hidden">
                {/* Drawing Tools Sidebar */}
                <div className="w-10 flex-shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col items-center py-2 gap-1">
                    {/* Selection tool */}
                    <button
                        onClick={() => setActiveTool('none')}
                        className={`p-2 rounded transition-colors ${activeTool === 'none'
                            ? 'bg-white text-slate-700 shadow-sm'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                            }`}
                        title="Seleccionar (Esc)"
                    >
                        <MousePointer className="w-4 h-4" />
                    </button>

                    {/* Horizontal line */}
                    <button
                        onClick={() => setActiveTool(activeTool === 'horizontal_line' ? 'none' : 'horizontal_line')}
                        className={`p-2 rounded transition-colors ${activeTool === 'horizontal_line'
                            ? 'bg-blue-100 text-blue-600 shadow-sm'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-white/50'
                            }`}
                        title="Línea horizontal (H)"
                    >
                        <Minus className="w-4 h-4" />
                    </button>

                    <div className="w-6 h-px bg-slate-200 my-1" />

                    {/* Tip de ayuda */}
                    <div className="text-[8px] text-slate-400 text-center px-1 leading-tight">
                        Doble click<br />para editar
                    </div>

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Clear all */}
                    {drawings.length > 0 && (
                        <button
                            onClick={clearAllDrawings}
                            className="p-2 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                            title={`Borrar todos (${drawings.length})`}
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    )}
                </div>

                {/* Chart area */}
                <div
                    className="flex-1 min-w-0 relative"
                    style={{
                        cursor: hoveredDrawingId && activeTool === 'none'
                            ? 'ns-resize'  // Sobre línea = mover línea
                            : isDrawing
                                ? 'crosshair'
                                : 'default'
                    }}
                    onMouseDown={activeTool === 'none' ? handleDragStart : undefined}
                >
                    {/* Drag overlay - captura todos los eventos durante drag */}
                    {dragState.active && (
                        <div
                            className="absolute inset-0 z-50"
                            style={{ cursor: 'ns-resize' }}
                            onMouseMove={handleDragMove}
                            onMouseUp={handleDragEnd}
                            onMouseLeave={handleDragEnd}
                        />
                    )}

                    {/* Drawing mode indicator */}
                    {isDrawing && (
                        <div className="absolute top-2 left-2 z-20 flex items-center gap-2 px-2 py-1 bg-blue-500 text-white text-xs font-medium rounded shadow-lg">
                            <span>Click para añadir línea horizontal</span>
                            <button
                                onClick={cancelDrawing}
                                className="hover:bg-blue-600 rounded px-1"
                            >
                                ✕
                            </button>
                        </div>
                    )}

                    {/* Drag indicator */}
                    {dragState.active && (
                        <div className="absolute top-2 right-2 z-20 px-2 py-1 bg-blue-600 text-white text-xs font-medium rounded shadow-lg">
                            ↕ Arrastrando...
                        </div>
                    )}

                    {/* Edit popup - aparece al doble click en línea */}
                    {editPopup.visible && editingDrawing && (
                        <>
                            {/* Backdrop para cerrar */}
                            <div
                                className="absolute inset-0 z-40"
                                onClick={closeEditPopup}
                            />
                            {/* Popup */}
                            <div
                                className="absolute z-50 bg-white rounded-lg shadow-xl border border-slate-200 p-3 min-w-[160px]"
                                style={{
                                    left: Math.min(editPopup.x, (containerRef.current?.clientWidth || 300) - 180),
                                    top: Math.min(editPopup.y, (containerRef.current?.clientHeight || 200) - 150),
                                }}
                            >
                                <div className="text-xs font-semibold text-slate-700 mb-2 pb-2 border-b border-slate-100">
                                    Editar línea
                                </div>

                                {/* Colores */}
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Color</div>
                                    <div className="flex gap-1.5">
                                        {drawingColors.map(color => (
                                            <button
                                                key={color}
                                                onClick={() => handleEditColor(color)}
                                                className={`w-6 h-6 rounded-full transition-all ${editingDrawing.color === color
                                                    ? 'ring-2 ring-offset-1 ring-slate-400 scale-110'
                                                    : 'hover:scale-110'
                                                    }`}
                                                style={{ backgroundColor: color }}
                                            />
                                        ))}
                                    </div>
                                </div>

                                {/* Grosor */}
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Grosor</div>
                                    <div className="flex gap-1">
                                        {[1, 2, 3, 4].map(width => (
                                            <button
                                                key={width}
                                                onClick={() => handleEditLineWidth(width)}
                                                className={`flex-1 h-7 flex items-center justify-center rounded border transition-all ${editingDrawing.lineWidth === width
                                                    ? 'bg-blue-50 border-blue-300'
                                                    : 'border-slate-200 hover:bg-slate-50'
                                                    }`}
                                            >
                                                <div
                                                    className="rounded-full"
                                                    style={{
                                                        width: '20px',
                                                        height: `${width}px`,
                                                        backgroundColor: editingDrawing.color
                                                    }}
                                                />
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Acciones */}
                                <div className="flex gap-2 pt-2 border-t border-slate-100">
                                    <button
                                        onClick={handleEditDelete}
                                        className="flex-1 px-2 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded hover:bg-red-100 transition-colors"
                                    >
                                        Eliminar
                                    </button>
                                    <button
                                        onClick={closeEditPopup}
                                        className="flex-1 px-2 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 rounded hover:bg-slate-200 transition-colors"
                                    >
                                        Cerrar
                                    </button>
                                </div>
                            </div>
                        </>
                    )}

                    {loading && (
                        <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10">
                            <div className="flex items-center gap-2 text-slate-500">
                                <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                                <span className="text-sm">Loading {currentTicker}...</span>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10">
                            <div className="text-center">
                                <p className="text-red-500 text-sm mb-2">Failed to load chart</p>
                                <p className="text-slate-400 text-xs mb-3">{error}</p>
                                <button
                                    onClick={refetch}
                                    className="px-4 py-1.5 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700 transition-colors"
                                >
                                    Retry
                                </button>
                            </div>
                        </div>
                    )}

                    <div
                        ref={containerRef}
                        className="h-full w-full"
                    />
                </div>
            </div>

            {/* Footer with OHLCV data + Load More */}
            {displayBar && (
                <div className="flex items-center justify-between px-3 py-1.5 border-t border-slate-200 bg-slate-50 text-[10px]">
                    <div className="flex items-center gap-4 font-mono">
                        <span className="text-slate-500">
                            O: <span className="text-slate-700 font-medium">${formatPrice(displayBar.open)}</span>
                        </span>
                        <span className="text-slate-500">
                            H: <span className="text-emerald-600 font-medium">${formatPrice(displayBar.high)}</span>
                        </span>
                        <span className="text-slate-500">
                            L: <span className="text-red-600 font-medium">${formatPrice(displayBar.low)}</span>
                        </span>
                        <span className="text-slate-500">
                            C: <span className="text-slate-700 font-medium">${formatPrice(displayBar.close)}</span>
                        </span>
                        <span className="text-slate-500">
                            Vol: <span className="text-slate-700 font-medium">{formatVolume(displayBar.volume)}</span>
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        {/* Auto-loading indicator */}
                        {loadingMore && (
                            <span className="flex items-center gap-1 text-blue-500 text-[10px]">
                                <RefreshCw className="w-3 h-3 animate-spin" />
                                Loading history...
                            </span>
                        )}
                        <span className="text-slate-400">
                            {data.length.toLocaleString()} bars • {selectedInterval.toUpperCase()} • {currentTicker}
                            {hasMore && !loadingMore && ' • ← scroll for more'}
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
