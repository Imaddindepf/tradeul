'use client';

import { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react';
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
import { RefreshCw, Maximize2, Minimize2, BarChart3, ZoomIn, ZoomOut, Radio, Minus, Trash2, MousePointer, Newspaper, ExternalLink, ChevronDown, Activity, LineChart, TrendingUp, Waves, Target } from 'lucide-react';
import { useLiveChartData, type ChartInterval, type ChartBar as HookChartBar } from '@/hooks/useLiveChartData';
import { useChartDrawings, type Drawing, type DrawingTool } from '@/hooks/useChartDrawings';
import { useIndicatorWorker, type IndicatorType, OVERLAY_INDICATORS, PANEL_INDICATORS } from '@/hooks/useIndicatorWorker';
import { IndicatorPanel } from './IndicatorPanel';
import { useNewsStore } from '@/stores/useNewsStore';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { getUserTimezone, getTimezoneAbbrev } from '@/lib/date-utils';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';

// Window state for persistence
interface ChartWindowState {
    ticker?: string;
    interval?: Interval;
    range?: TimeRange;
    showMA?: boolean;
    showEMA?: boolean;
    showVolume?: boolean;
    activeOverlays?: string[];
    activePanels?: string[];
    [key: string]: unknown;
}

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
    /** Modo minimal: oculta toolbar, indicadores, intervalos. Para uso en Description. */
    minimal?: boolean;
    /** Callbacks para botones externos (solo en modo minimal) */
    onOpenChart?: () => void;
    onOpenNews?: () => void;
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

// Grouped intervals for dropdown
const INTERVAL_GROUPS = {
    intraday: [
        { label: '1m', interval: '1min' as Interval },
        { label: '5m', interval: '5min' as Interval },
        { label: '15m', interval: '15min' as Interval },
        { label: '30m', interval: '30min' as Interval },
    ],
    hourly: [
        { label: '1H', interval: '1hour' as Interval },
        { label: '4H', interval: '4hour' as Interval },
    ],
    daily: [
        { label: '1D', interval: '1day' as Interval },
    ],
};

// Interval in seconds for news marker matching
const INTERVAL_SECONDS: Record<Interval, number> = {
    '1min': 60,
    '5min': 300,
    '15min': 900,
    '30min': 1800,
    '1hour': 3600,
    '4hour': 14400,
    '1day': 86400,
};

// Helper to round timestamp to interval
function roundToInterval(timestamp: number, interval: Interval): number {
    const seconds = INTERVAL_SECONDS[interval];
    return Math.floor(timestamp / seconds) * seconds;
}

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
    // Format time in user's preferred timezone
    const formatTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            const tz = getUserTimezone();
            return d.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
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

function TradingChartComponent({
    ticker: initialTicker = 'AAPL',
    exchange,
    onTickerChange,
    minimal = false,
    onOpenChart,
    onOpenNews
}: TradingChartProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
    const ma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ma50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ema12SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const ema26SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);

    // User preferences
    const font = useUserPreferencesStore(selectFont);

    // Market session for LIVE indicator
    const ws = useWebSocket();
    const [marketSession, setMarketSession] = useState<MarketSession | null>(null);

    // Persist window state
    const { state: windowState, updateState: updateWindowState } = useWindowState<ChartWindowState>();

    // Use persisted state or props/defaults
    const [currentTicker, setCurrentTicker] = useState(windowState.ticker || initialTicker);
    const [selectedInterval, setSelectedInterval] = useState<Interval>(windowState.interval || '1day');
    const [selectedRange, setSelectedRange] = useState<TimeRange>(windowState.range || '1Y');
    const [inputValue, setInputValue] = useState(windowState.ticker || initialTicker);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [showMA, setShowMA] = useState(windowState.showMA ?? true);
    const [showEMA, setShowEMA] = useState(windowState.showEMA ?? false);
    const [showVolume, setShowVolume] = useState(windowState.showVolume ?? true);
    const [showNewsMarkers, setShowNewsMarkers] = useState(false);
    const [hoveredBar, setHoveredBar] = useState<ChartBar | null>(null);

    // === INDICADORES AVANZADOS (Worker-based) ===
    const { calculate, clearCache, results: indicatorResults, isCalculating: indicatorsLoading, isReady: workerReady } = useIndicatorWorker();

    // Overlays activos (sobre el precio): sma200, bb, keltner, vwap
    const [activeOverlays, setActiveOverlays] = useState<string[]>(windowState.activeOverlays || []);

    // Paneles activos (debajo del chart): rsi, macd, stoch, adx, atr, squeeze
    const [activePanels, setActivePanels] = useState<string[]>(windowState.activePanels || []);

    // Refs para series de overlays calculados por worker
    const sma200SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const bbUpperSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const bbMiddleSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const bbLowerSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const keltnerUpperSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const keltnerMiddleSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const keltnerLowerSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

    // Toggle helpers para overlays y paneles
    const toggleOverlay = useCallback((id: string) => {
        setActiveOverlays(prev =>
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        );
    }, []);

    const togglePanel = useCallback((id: string) => {
        setActivePanels(prev =>
            prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
        );
    }, []);

    const removePanel = useCallback((id: string) => {
        setActivePanels(prev => prev.filter(x => x !== id));
    }, []);

    // Dropdown states
    const [showIntervalDropdown, setShowIntervalDropdown] = useState(false);
    const [showIndicatorDropdown, setShowIndicatorDropdown] = useState(false);
    const [showToolsDropdown, setShowToolsDropdown] = useState(false);

    // Persist state changes
    useEffect(() => {
        updateWindowState({
            ticker: currentTicker,
            interval: selectedInterval,
            range: selectedRange,
            showMA,
            showEMA,
            showVolume,
            activeOverlays,
            activePanels,
        });
    }, [currentTicker, selectedInterval, selectedRange, showMA, showEMA, showVolume, activeOverlays, activePanels, updateWindowState]);

    const { data, loading, loadingMore, error, hasMore, isLive, refetch, loadMore, registerUpdateHandler } = useLiveChartData(currentTicker, selectedInterval);

    // Fetch market session and subscribe to updates
    useEffect(() => {
        // Initial fetch
        getMarketSession().then(setMarketSession).catch(() => { });

        // Subscribe to WebSocket updates
        const subscription = ws.messages$.subscribe((message: any) => {
            if (message.type === 'market_session_change' && message.data) {
                setMarketSession({
                    current_session: message.data.current_session,
                    trading_date: message.data.trading_date,
                    timestamp: message.data.timestamp,
                } as MarketSession);
            }
        });

        return () => subscription.unsubscribe();
    }, [ws.messages$]);

    // Check if market is actually open (not just WebSocket connected)
    const isMarketOpen = marketSession?.current_session === 'MARKET_OPEN' ||
        marketSession?.current_session === 'PRE_MARKET' ||
        marketSession?.current_session === 'POST_MARKET';
    const showLiveIndicator = isLive && isMarketOpen;

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
                tickMarkFormatter: (time: number) => {
                    // Format time in user's preferred timezone
                    const tz = getUserTimezone();
                    const date = new Date(time * 1000);
                    return date.toLocaleTimeString('en-US', {
                        timeZone: tz,
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false,
                    });
                },
            },
            localization: {
                timeFormatter: (time: number) => {
                    // Format time in user's timezone for tooltips/crosshair
                    const tz = getUserTimezone();
                    const abbrev = getTimezoneAbbrev(tz);
                    const date = new Date(time * 1000);
                    return date.toLocaleString('en-US', {
                        timeZone: tz,
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false,
                    }) + ` ${abbrev}`;
                },
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

        // === SERIES CALCULADAS POR WORKER ===

        // SMA 200 (red, importante para tendencia)
        const sma200Series = chart.addLineSeries({
            color: '#ef4444',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false, // Se activa cuando el usuario lo selecciona
        });
        sma200SeriesRef.current = sma200Series;

        // Bollinger Bands (blue)
        const bbUpperSeries = chart.addLineSeries({
            color: 'rgba(59, 130, 246, 0.6)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        bbUpperSeriesRef.current = bbUpperSeries;

        const bbMiddleSeries = chart.addLineSeries({
            color: 'rgba(59, 130, 246, 0.4)',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        bbMiddleSeriesRef.current = bbMiddleSeries;

        const bbLowerSeries = chart.addLineSeries({
            color: 'rgba(59, 130, 246, 0.6)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        bbLowerSeriesRef.current = bbLowerSeries;

        // Keltner Channels (teal)
        const keltnerUpperSeries = chart.addLineSeries({
            color: 'rgba(20, 184, 166, 0.6)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        keltnerUpperSeriesRef.current = keltnerUpperSeries;

        const keltnerMiddleSeries = chart.addLineSeries({
            color: 'rgba(20, 184, 166, 0.4)',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        keltnerMiddleSeriesRef.current = keltnerMiddleSeries;

        const keltnerLowerSeries = chart.addLineSeries({
            color: 'rgba(20, 184, 166, 0.6)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        keltnerLowerSeriesRef.current = keltnerLowerSeries;

        // VWAP (orange)
        const vwapSeries = chart.addLineSeries({
            color: '#f97316',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            visible: false,
        });
        vwapSeriesRef.current = vwapSeries;

        // Crosshair move handler for tooltip
        // IMPORTANTE: Verificar param.point para evitar loop infinito
        // setMarkers() dispara crosshairMove internamente pero sin point
        chart.subscribeCrosshairMove((param) => {
            // Solo procesar si hay un punto real del cursor (no eventos programáticos)
            if (!param.point) {
                // Sin punto = evento programático de setMarkers, no actualizar estado
                return;
            }

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
    }, [data, currentTicker, showNewsMarkers]);

    // Apply time range only on initial load or ticker change (not on every data update)
    const lastAppliedTickerRef = useRef<string>('');
    useEffect(() => {
        if (!data || data.length === 0 || !candleSeriesRef.current) return;

        // Only apply when ticker changes (new chart loaded)
        if (lastAppliedTickerRef.current !== currentTicker) {
            lastAppliedTickerRef.current = currentTicker;
            setTimeout(() => applyTimeRange(selectedRange), 50);
        }
    }, [data, currentTicker, selectedRange, applyTimeRange]);

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

        // Create a map of candle data for quick lookup - rounded to current interval
        const candleDataMap = new Map<number, { time: number; open: number; high: number; low: number; close: number }>();
        for (const bar of data) {
            // Round to current interval for matching (not just 1 minute)
            const roundedTime = roundToInterval(bar.time, selectedInterval);
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
            // Round to current interval (5m, 15m, 1H, etc.)
            const roundedNewsTime = roundToInterval(newsTimestamp, selectedInterval);

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
                    title: `📰 ${newsDate.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', hour12: false })}`,
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
    }, [showNewsMarkers, tickerNews, data, selectedInterval, currentTicker]);

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

    // ============================================================================
    // CALCULAR INDICADORES EN WORKER (no bloqueante)
    // ============================================================================

    // Combinar indicadores activos para enviar al worker
    const allActiveIndicators = useMemo(() => {
        const indicators: IndicatorType[] = [];

        // Overlays calculados por worker
        if (activeOverlays.includes('sma200')) indicators.push('sma200');
        if (activeOverlays.includes('bb')) indicators.push('bb');
        if (activeOverlays.includes('keltner')) indicators.push('keltner');
        if (activeOverlays.includes('vwap')) indicators.push('vwap');

        // Paneles (oscillators)
        activePanels.forEach(panel => {
            if (['rsi', 'macd', 'stoch', 'adx', 'atr', 'bbWidth', 'squeeze', 'obv', 'rvol'].includes(panel)) {
                indicators.push(panel as IndicatorType);
            }
        });

        return indicators;
    }, [activeOverlays, activePanels]);

    // Calcular indicadores cuando cambian los datos o los indicadores activos
    // También recalcula cuando llegan más barras (lazy loading), cambia el intervalo o el rango
    const lastBarCountRef = useRef(0);
    const lastIntervalRef = useRef(selectedInterval);
    const lastRangeRef = useRef(selectedRange);

    useEffect(() => {
        // Limpiar cache si cambió el intervalo o el rango (nuevos datos = nuevo cálculo)
        const intervalChanged = lastIntervalRef.current !== selectedInterval;
        const rangeChanged = lastRangeRef.current !== selectedRange;

        if (intervalChanged || rangeChanged) {
            console.log('[TradingChart] Settings changed, clearing cache:', {
                interval: intervalChanged ? `${lastIntervalRef.current} -> ${selectedInterval}` : 'same',
                range: rangeChanged ? `${lastRangeRef.current} -> ${selectedRange}` : 'same'
            });
            clearCache(currentTicker);
            lastIntervalRef.current = selectedInterval;
            lastRangeRef.current = selectedRange;
            lastBarCountRef.current = 0; // Forzar recálculo
        }

        if (!workerReady || !data.length || allActiveIndicators.length === 0) return;

        calculate(currentTicker, data, allActiveIndicators, selectedInterval);
        lastBarCountRef.current = data.length;
    }, [workerReady, data, data.length, allActiveIndicators, currentTicker, selectedInterval, selectedRange, calculate, clearCache]);

    // ============================================================================
    // ACTUALIZAR SERIES DE OVERLAYS cuando llegan resultados del worker
    // ============================================================================

    useEffect(() => {
        console.log('[TradingChart] indicatorResults changed:', {
            hasOverlays: !!indicatorResults?.overlays,
            overlayKeys: Object.keys(indicatorResults?.overlays || {}),
            panelKeys: Object.keys(indicatorResults?.panels || {}),
            chartReady: !!chartRef.current
        });

        if (!indicatorResults?.overlays || !chartRef.current) return;

        const { overlays } = indicatorResults;

        // SMA 200
        if (sma200SeriesRef.current && overlays.sma200) {
            sma200SeriesRef.current.setData(overlays.sma200.map(d => ({
                time: d.time as UTCTimestamp,
                value: d.value,
            })));
            sma200SeriesRef.current.applyOptions({ visible: activeOverlays.includes('sma200') });
        }

        // Bollinger Bands
        if (overlays.bb) {
            if (bbUpperSeriesRef.current) {
                bbUpperSeriesRef.current.setData(overlays.bb.upper.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                bbUpperSeriesRef.current.applyOptions({ visible: activeOverlays.includes('bb') });
            }
            if (bbMiddleSeriesRef.current) {
                bbMiddleSeriesRef.current.setData(overlays.bb.middle.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                bbMiddleSeriesRef.current.applyOptions({ visible: activeOverlays.includes('bb') });
            }
            if (bbLowerSeriesRef.current) {
                bbLowerSeriesRef.current.setData(overlays.bb.lower.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                bbLowerSeriesRef.current.applyOptions({ visible: activeOverlays.includes('bb') });
            }
        }

        // Keltner Channels
        if (overlays.keltner) {
            if (keltnerUpperSeriesRef.current) {
                keltnerUpperSeriesRef.current.setData(overlays.keltner.upper.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                keltnerUpperSeriesRef.current.applyOptions({ visible: activeOverlays.includes('keltner') });
            }
            if (keltnerMiddleSeriesRef.current) {
                keltnerMiddleSeriesRef.current.setData(overlays.keltner.middle.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                keltnerMiddleSeriesRef.current.applyOptions({ visible: activeOverlays.includes('keltner') });
            }
            if (keltnerLowerSeriesRef.current) {
                keltnerLowerSeriesRef.current.setData(overlays.keltner.lower.map(d => ({
                    time: d.time as UTCTimestamp,
                    value: d.value,
                })));
                keltnerLowerSeriesRef.current.applyOptions({ visible: activeOverlays.includes('keltner') });
            }
        }

        // VWAP
        if (vwapSeriesRef.current && overlays.vwap) {
            vwapSeriesRef.current.setData(overlays.vwap.map(d => ({
                time: d.time as UTCTimestamp,
                value: d.value,
            })));
            vwapSeriesRef.current.applyOptions({ visible: activeOverlays.includes('vwap') });
        }
    }, [indicatorResults, activeOverlays]);

    const handleTickerChange = (e: React.FormEvent) => {
        e.preventDefault();
        const newTicker = inputValue.trim().toUpperCase();
        if (newTicker && newTicker !== currentTicker) {
            setCurrentTicker(newTicker);
            onTickerChange?.(newTicker);
        }
        tickerSearchRef.current?.close();
    };

    const handleTickerSelect = useCallback((selected: { symbol: string }) => {
        const newTicker = selected.symbol.toUpperCase();
        setInputValue(newTicker);
        if (newTicker !== currentTicker) {
            setCurrentTicker(newTicker);
            onTickerChange?.(newTicker);
        }
        tickerSearchRef.current?.close();
    }, [currentTicker, onTickerChange]);

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
        <div className="h-full flex flex-col bg-white border border-slate-200 rounded-lg">
            {/* Minimal Header (for Description) */}
            {minimal ? (
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-600 tracking-wide">PRICE CHART</span>
                        <span className="text-[10px] text-slate-400">1 Year</span>
                        <span className="text-[10px] text-slate-400">Intraday</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* Open full Chart window */}
                        {onOpenChart && (
                            <button
                                onClick={onOpenChart}
                                className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors"
                                title="Open Chart Window"
                            >
                                G <span className="font-normal">&gt;</span>
                            </button>
                        )}
                        {/* Open News window */}
                        {onOpenNews && (
                            <button
                                onClick={onOpenNews}
                                className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors"
                                title="Open News Window"
                            >
                                N <span className="font-normal">&gt;</span>
                            </button>
                        )}
                        {/* Open Chat window - placeholder for future */}
                        <button
                            className="text-xs font-bold text-blue-600 opacity-50 cursor-not-allowed"
                            title="Chat (coming soon)"
                            disabled
                        >
                            CHAT <span className="font-normal">&gt;</span>
                        </button>
                    </div>
                </div>
            ) : (
                <>
                    {/* Compact Header - Single Row */}
                    <div className="flex items-center justify-between px-2 py-1 border-b border-slate-200 bg-slate-50 text-[11px]" style={{ fontFamily: `var(--font-${font})` }}>
                        {/* Left: Ticker + Price */}
                        <div className="flex items-center gap-2">
                            {/* Compact Ticker Search */}
                            <form onSubmit={handleTickerChange} className="flex items-center">
                                <TickerSearch
                                    ref={tickerSearchRef}
                                    value={inputValue}
                                    onChange={setInputValue}
                                    onSelect={handleTickerSelect}
                                    placeholder="Ticker"
                                    className="w-20"
                                    autoFocus={false}
                                />
                                <button
                                    type="submit"
                                    className="px-2 py-1 bg-blue-600 text-white rounded-r text-[10px] font-medium hover:bg-blue-700"
                                >
                                    Go
                                </button>
                            </form>

                            {/* Price info compact */}
                            {displayBar && (
                                <div className="flex items-center gap-1.5">
                                    <span className="font-bold text-slate-800 text-sm">
                                        ${formatPrice(displayBar.close)}
                                    </span>
                                    <span className={`text-[10px] font-medium px-1 rounded ${isPositive ? 'text-emerald-600 bg-emerald-50' : 'text-red-600 bg-red-50'}`}>
                                        {isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%
                                    </span>
                                    {/* Live indicator - only when market is open */}
                                    {showLiveIndicator && (
                                        <span className="flex items-center gap-0.5 text-[9px] font-medium text-red-500 animate-pulse">
                                            <Radio className="w-2.5 h-2.5" />
                                            LIVE
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Center: Interval Dropdown */}
                        <div className="flex items-center gap-1">
                            {/* Quick intervals */}
                            {['1m', '5m', '15m', '1H', '1D'].map((label) => {
                                const int = INTERVALS.find(i => i.shortLabel === label);
                                if (!int) return null;
                                return (
                                    <button
                                        key={int.interval}
                                        onClick={() => setSelectedInterval(int.interval)}
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-all ${selectedInterval === int.interval
                                            ? 'bg-blue-600 text-white'
                                            : 'text-slate-500 hover:bg-slate-100'
                                            }`}
                                    >
                                        {label}
                                    </button>
                                );
                            })}

                            {/* More intervals dropdown */}
                            <div className="relative">
                                <button
                                    onClick={() => setShowIntervalDropdown(!showIntervalDropdown)}
                                    className="px-1 py-0.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100"
                                >
                                    <ChevronDown className="w-3 h-3" />
                                </button>
                                {showIntervalDropdown && (
                                    <>
                                        <div className="fixed inset-0 z-40" onClick={() => setShowIntervalDropdown(false)} />
                                        <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded shadow-lg z-50 min-w-[80px]">
                                            {INTERVALS.map((int) => (
                                                <button
                                                    key={int.interval}
                                                    onClick={() => { setSelectedInterval(int.interval); setShowIntervalDropdown(false); }}
                                                    className={`w-full px-2 py-1 text-left text-[10px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600' : 'text-slate-600'}`}
                                                >
                                                    {int.label}
                                                </button>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </div>

                            <div className="w-px h-4 bg-slate-200 mx-0.5" />

                            {/* Range */}
                            {['1M', '3M', '1Y', 'ALL'].map((r) => {
                                const range = TIME_RANGES.find(tr => tr.id === r);
                                if (!range) return null;
                                return (
                                    <button
                                        key={range.id}
                                        onClick={() => handleRangeChange(range.id)}
                                        className={`px-1 py-0.5 rounded text-[9px] font-medium ${selectedRange === range.id
                                            ? 'bg-slate-700 text-white'
                                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                                            }`}
                                    >
                                        {range.label}
                                    </button>
                                );
                            })}
                        </div>

                        {/* Right: Actions only (Indicators & Tools in sidebar) */}
                        <div className="flex items-center gap-0.5">
                            {/* Refresh */}
                            <button onClick={refetch} disabled={loading} className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 disabled:opacity-50" title="Refresh">
                                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                            </button>

                            {/* Fullscreen */}
                            <button onClick={toggleFullscreen} className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100" title="Fullscreen">
                                {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                            </button>
                        </div>
                    </div>

                    {/* Legend row - only when indicators active */}
                    {(showMA || showEMA) && (
                        <div className="flex items-center justify-end px-2 py-0.5 border-b border-slate-50 bg-white">
                            <div className="flex items-center gap-2 text-[9px]">
                                {showMA && (
                                    <>
                                        <span className="flex items-center gap-1">
                                            <span className="w-3 h-0.5 rounded" style={{ background: CHART_COLORS.ma20 }}></span>
                                            <span className="text-slate-400">MA20</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <span className="w-3 h-0.5 rounded" style={{ background: CHART_COLORS.ma50 }}></span>
                                            <span className="text-slate-400">MA50</span>
                                        </span>
                                    </>
                                )}
                                {showEMA && (
                                    <>
                                        <span className="flex items-center gap-1">
                                            <span className="w-3 h-0.5 rounded" style={{ background: CHART_COLORS.ema12 }}></span>
                                            <span className="text-slate-400">EMA12</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <span className="w-3 h-0.5 rounded" style={{ background: CHART_COLORS.ema26 }}></span>
                                            <span className="text-slate-400">EMA26</span>
                                        </span>
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Chart container with sidebar - min-h-0 permite que flex-1 funcione correctamente */}
            <div className="flex-1 min-h-0 flex bg-white">
                {/* Left Sidebar: Expandable sections */}
                <div className="w-9 flex-shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col py-1 text-[8px] relative">

                    {/* INDICATORS Section - Expandable */}
                    <div className="relative">
                        <button
                            onClick={() => setShowIndicatorDropdown(!showIndicatorDropdown)}
                            className={`w-full h-8 flex flex-col items-center justify-center gap-0.5 transition-colors ${(showMA || showEMA || showVolume || showNewsMarkers) ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:bg-white/50'}`}
                            title="Indicators"
                        >
                            <Activity className="w-4 h-4" />
                            <span className="text-[7px] font-medium">IND</span>
                        </button>

                        {/* Indicator Dropdown - Expandido con todas las categorías */}
                        {showIndicatorDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIndicatorDropdown(false)} />
                                <div className="absolute left-full top-0 ml-0.5 bg-white border border-slate-200 rounded shadow-lg z-50 min-w-[140px] max-h-[400px] overflow-y-auto">

                                    {/* === OVERLAYS === */}
                                    <div className="px-1.5 py-0.5 text-[8px] font-semibold text-slate-400 bg-slate-50 border-b border-slate-100 sticky top-0 flex items-center gap-1">
                                        <TrendingUp className="w-2.5 h-2.5" />
                                        OVERLAYS
                                    </div>

                                    <button onClick={() => setShowMA(!showMA)} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${showMA ? 'text-amber-600 bg-amber-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0" style={{ background: CHART_COLORS.ma20 }}></span>
                                        <span className="flex-1 text-left">SMA 20/50</span>
                                        {showMA && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => toggleOverlay('sma200')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeOverlays.includes('sma200') ? 'text-red-600 bg-red-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-red-500"></span>
                                        <span className="flex-1 text-left">SMA 200</span>
                                        {activeOverlays.includes('sma200') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => setShowEMA(!showEMA)} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${showEMA ? 'text-pink-600 bg-pink-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0" style={{ background: CHART_COLORS.ema12 }}></span>
                                        <span className="flex-1 text-left">EMA 12/26</span>
                                        {showEMA && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => toggleOverlay('bb')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeOverlays.includes('bb') ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <Waves className="w-2.5 h-2.5 text-blue-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">Bollinger</span>
                                        {activeOverlays.includes('bb') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => toggleOverlay('keltner')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeOverlays.includes('keltner') ? 'text-teal-600 bg-teal-50/50' : 'text-slate-600'}`}>
                                        <Waves className="w-2.5 h-2.5 text-teal-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">Keltner</span>
                                        {activeOverlays.includes('keltner') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => toggleOverlay('vwap')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeOverlays.includes('vwap') ? 'text-orange-600 bg-orange-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-orange-500"></span>
                                        <span className="flex-1 text-left">VWAP</span>
                                        {activeOverlays.includes('vwap') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    {/* === OSCILLATORS (Paneles separados) === */}
                                    <div className="px-1.5 py-0.5 text-[8px] font-semibold text-slate-400 bg-slate-50 border-y border-slate-100 mt-1 flex items-center gap-1">
                                        <Target className="w-2.5 h-2.5" />
                                        OSCILLATORS
                                    </div>

                                    <button onClick={() => togglePanel('rsi')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('rsi') ? 'text-violet-600 bg-violet-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-violet-500"></span>
                                        <span className="flex-1 text-left">RSI (14)</span>
                                        {activePanels.includes('rsi') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('macd')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('macd') ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <BarChart3 className="w-2.5 h-2.5 text-blue-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">MACD</span>
                                        {activePanels.includes('macd') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('stoch')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('stoch') ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-blue-500"></span>
                                        <span className="flex-1 text-left">Stochastic</span>
                                        {activePanels.includes('stoch') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('adx')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('adx') ? 'text-violet-600 bg-violet-50/50' : 'text-slate-600'}`}>
                                        <TrendingUp className="w-2.5 h-2.5 text-violet-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">ADX/DMI</span>
                                        {activePanels.includes('adx') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    {/* === VOLATILITY === */}
                                    <div className="px-1.5 py-0.5 text-[8px] font-semibold text-slate-400 bg-slate-50 border-y border-slate-100 mt-1 flex items-center gap-1">
                                        <Activity className="w-2.5 h-2.5" />
                                        VOLATILITY
                                    </div>

                                    <button onClick={() => togglePanel('atr')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('atr') ? 'text-indigo-600 bg-indigo-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-indigo-500"></span>
                                        <span className="flex-1 text-left">ATR (14)</span>
                                        {activePanels.includes('atr') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('squeeze')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('squeeze') ? 'text-red-600 bg-red-50/50' : 'text-slate-600'}`}>
                                        <Target className="w-2.5 h-2.5 text-red-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">TTM Squeeze</span>
                                        {activePanels.includes('squeeze') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    {/* === VOLUME === */}
                                    <div className="px-1.5 py-0.5 text-[8px] font-semibold text-slate-400 bg-slate-50 border-y border-slate-100 mt-1 flex items-center gap-1">
                                        <BarChart3 className="w-2.5 h-2.5" />
                                        VOLUME
                                    </div>

                                    <button onClick={() => setShowVolume(!showVolume)} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${showVolume ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <BarChart3 className="w-2.5 h-2.5 flex-shrink-0" />
                                        <span className="flex-1 text-left">Volume</span>
                                        {showVolume && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('obv')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('obv') ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <span className="w-2 h-0.5 rounded flex-shrink-0 bg-blue-500"></span>
                                        <span className="flex-1 text-left">OBV</span>
                                        {activePanels.includes('obv') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    <button onClick={() => togglePanel('rvol')} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activePanels.includes('rvol') ? 'text-emerald-600 bg-emerald-50/50' : 'text-slate-600'}`}>
                                        <BarChart3 className="w-2.5 h-2.5 text-emerald-500 flex-shrink-0" />
                                        <span className="flex-1 text-left">RVOL</span>
                                        {selectedInterval && ['1minute', '5minute', '15minute', '30minute'].includes(selectedInterval) && (
                                            <span className="text-[7px] text-emerald-400">⚡</span>
                                        )}
                                        {activePanels.includes('rvol') && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    {/* === OTHER === */}
                                    <div className="border-t border-slate-100 my-0.5" />

                                    <button onClick={() => setShowNewsMarkers(!showNewsMarkers)} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${showNewsMarkers ? 'text-amber-600 bg-amber-50/50' : 'text-slate-600'}`}>
                                        <Newspaper className="w-2.5 h-2.5 flex-shrink-0" />
                                        <span className="flex-1 text-left">News</span>
                                        {tickerNews.length > 0 && <span className="text-[7px] text-slate-400">{tickerNews.length}</span>}
                                        {showNewsMarkers && <span className="text-[8px] text-emerald-500">✓</span>}
                                    </button>

                                    {/* Indicador de cálculo */}
                                    {indicatorsLoading && (
                                        <div className="px-1.5 py-1 text-[8px] text-blue-500 bg-blue-50 border-t border-slate-100 flex items-center gap-1">
                                            <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                                            Calculating...
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="w-6 h-px bg-slate-200 mx-auto my-0.5" />

                    {/* TOOLS Section - Expandable */}
                    <div className="relative">
                        <button
                            onClick={() => setShowToolsDropdown(!showToolsDropdown)}
                            className={`w-full h-8 flex flex-col items-center justify-center gap-0.5 transition-colors ${activeTool !== 'none' ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:bg-white/50'}`}
                            title="Drawing Tools"
                        >
                            <LineChart className="w-4 h-4" />
                            <span className="text-[7px] font-medium">TOOLS</span>
                        </button>

                        {/* Tools Dropdown - Compact flyout */}
                        {showToolsDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowToolsDropdown(false)} />
                                <div className="absolute left-full top-0 ml-0.5 bg-white border border-slate-200 rounded shadow-lg z-50 min-w-[110px] max-h-[300px] overflow-y-auto">
                                    <div className="px-1.5 py-0.5 text-[8px] font-semibold text-slate-400 bg-slate-50 border-b border-slate-100 sticky top-0">TOOLS</div>

                                    <button onClick={() => { setActiveTool('none'); setShowToolsDropdown(false); }} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeTool === 'none' ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <MousePointer className="w-2.5 h-2.5 flex-shrink-0" />
                                        <span className="flex-1 text-left">Select</span>
                                        <span className="text-[7px] text-slate-400">Esc</span>
                                    </button>

                                    <button onClick={() => { setActiveTool('horizontal_line'); setShowToolsDropdown(false); }} className={`w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] hover:bg-slate-50 ${activeTool === 'horizontal_line' ? 'text-blue-600 bg-blue-50/50' : 'text-slate-600'}`}>
                                        <Minus className="w-2.5 h-2.5 flex-shrink-0" />
                                        <span className="flex-1 text-left">H-Line</span>
                                        <span className="text-[7px] text-slate-400">H</span>
                                    </button>

                                    {drawings.length > 0 && (
                                        <>
                                            <div className="border-t border-slate-100 my-0.5" />
                                            <button onClick={() => { clearAllDrawings(); setShowToolsDropdown(false); }} className="w-full flex items-center gap-1.5 px-1.5 py-[3px] text-[9px] text-red-600 hover:bg-red-50">
                                                <Trash2 className="w-2.5 h-2.5 flex-shrink-0" />
                                                <span className="flex-1 text-left">Clear</span>
                                                <span className="text-[7px]">{drawings.length}</span>
                                            </button>
                                        </>
                                    )}
                                </div>
                            </>
                        )}
                    </div>

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Quick actions at bottom */}
                    <div className="w-6 h-px bg-slate-200 mx-auto my-0.5" />

                    <button onClick={zoomIn} className="w-full h-7 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-white/50" title="Zoom In (+)">
                        <ZoomIn className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={zoomOut} className="w-full h-7 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-white/50" title="Zoom Out (-)">
                        <ZoomOut className="w-3.5 h-3.5" />
                    </button>
                </div>

                {/* Content area: main chart + indicator panels */}
                <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
                    {/* Chart area - calcula altura dinámicamente basada en paneles activos */}
                    <div
                        className="min-w-0 relative"
                        style={{
                            height: activePanels.length > 0
                                ? `calc(100% - ${activePanels.length * 100}px)`
                                : '100%',
                            minHeight: '200px',
                            cursor: hoveredDrawingId && activeTool === 'none'
                                ? 'ns-resize'
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

                    {/* === INDICATOR PANELS (debajo del chart principal) === */}
                    {activePanels.length > 0 && indicatorResults?.panels && (
                        <div className="flex-shrink-0 flex flex-col">
                            {activePanels.map(panelId => {
                                const panelData = indicatorResults.panels[panelId as keyof typeof indicatorResults.panels];
                                if (!panelData) return null;

                                return (
                                    <IndicatorPanel
                                        key={panelId}
                                        type={panelId}
                                        data={panelData.data}
                                        mainChart={chartRef.current}
                                        height={100}
                                        onClose={() => removePanel(panelId)}
                                    />
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* Footer with OHLCV data - Compact */}
            {displayBar && !minimal && (
                <div className="flex items-center justify-between px-2 py-1 border-t border-slate-200 bg-slate-50 text-[9px]" style={{ fontFamily: `var(--font-${font})` }}>
                    <div className="flex items-center gap-2 font-mono">
                        <span className="text-slate-400">O:<span className="text-slate-600">${formatPrice(displayBar.open)}</span></span>
                        <span className="text-slate-400">H:<span className="text-emerald-600">${formatPrice(displayBar.high)}</span></span>
                        <span className="text-slate-400">L:<span className="text-red-600">${formatPrice(displayBar.low)}</span></span>
                        <span className="text-slate-400">C:<span className="text-slate-600">${formatPrice(displayBar.close)}</span></span>
                        <span className="text-slate-400">V:<span className="text-slate-600">{formatVolume(displayBar.volume)}</span></span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                        {loadingMore && <RefreshCw className="w-2.5 h-2.5 animate-spin text-blue-500" />}
                        <span>{data.length.toLocaleString()} bars</span>
                        {hasMore && !loadingMore && <span>← more</span>}
                    </div>
                </div>
            )}
        </div>
    );
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
