'use client';

import { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react';
import {
    createChart,
    ColorType,
    CrosshairMode,
    CandlestickSeries,
    LineSeries,
    HistogramSeries,
    createSeriesMarkers,
    createTextWatermark,
    LineStyle,
    PriceScaleMode,
    type IChartApi,
    type ISeriesApi,
    type CandlestickData,
    type HistogramData,
    type Time,
    type UTCTimestamp,
    type SeriesMarker,
} from 'lightweight-charts';
import { RefreshCw, Maximize2, Minimize2, BarChart3, ZoomIn, ZoomOut, Radio, Minus, Trash2, MousePointer, Newspaper, ExternalLink, ChevronDown, Activity, LineChart, TrendingUp, Waves, Target, X, Sparkles, Bot } from 'lucide-react';
import { useLiveChartData, type ChartBar as HookChartBar } from '@/hooks/useLiveChartData';
import { useChartDrawings } from '@/hooks/useChartDrawings';
import { useIndicatorWorker, type IndicatorType, PANEL_INDICATORS } from '@/hooks/useIndicatorWorker';
import type { IndicatorDataPoint, MACDData, StochData, ADXData, SqueezeData } from '@/hooks/useIndicatorWorker';
import { ChartNewsPopup } from './ChartNewsPopup';
import { useArticlesByTicker } from '@/stores/useNewsStore';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { getUserTimezone, getTimezoneAbbrev } from '@/lib/date-utils';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';

import {
    CHART_COLORS,
    INDICATOR_COLORS,
    INTERVALS,
    TIME_RANGES,
    INTERVAL_SECONDS,
    type ChartBar,
    type TradingChartProps,
    type Interval,
    type TimeRange,
    type ChartWindowState,
} from './constants';
import { formatPrice, formatVolume, roundToInterval } from './formatters';
import { calculateSMA, calculateEMA } from './indicators';
import type { ChartContext, ChartSnapshot } from '@/components/ai-agent/types';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { Drawing } from '@/hooks/useChartDrawings';

// ============================================================================
// Chart AI Snapshot Builder
// ============================================================================

function buildChartSnapshot(
    data: ChartBar[],
    indicatorResults: IndicatorResults | null,
    drawings: Drawing[],
    activeOverlays: string[],
    activePanels: string[],
    showMA: boolean,
    showEMA: boolean,
    chartApi: IChartApi | null,
): ChartSnapshot {
    const visibleRange = chartApi?.timeScale().getVisibleLogicalRange();
    const fromIdx = Math.max(0, Math.floor(visibleRange?.from ?? 0));
    const toIdx = Math.min(data.length - 1, Math.ceil(visibleRange?.to ?? data.length - 1));

    const visibleBars = data.slice(fromIdx, toIdx + 1);
    const recentBars = visibleBars;

    const rightEdge = toIdx;
    const rightTime = data[rightEdge]?.time;

    const findValue = (arr?: { time: number; value: number }[]) => {
        if (!arr || !rightTime) return undefined;
        const pt = arr.find(p => p.time === rightTime);
        return pt?.value;
    };

    const trajectory = (arr?: { time: number; value: number }[], count = 5) => {
        if (!arr || !rightTime) return undefined;
        return arr.filter(p => p.time <= rightTime).slice(-count).map(d => d.value);
    };

    const indicators: ChartSnapshot['indicators'] = {};

    if (indicatorResults) {
        const { overlays, panels } = indicatorResults;

        // Capture ALL available indicators regardless of UI visibility
        if (overlays.sma20) indicators.sma20 = findValue(overlays.sma20);
        if (overlays.sma50) indicators.sma50 = findValue(overlays.sma50);
        if (overlays.sma200) indicators.sma200 = findValue(overlays.sma200);
        if (overlays.ema12) indicators.ema12 = findValue(overlays.ema12);
        if (overlays.ema26) indicators.ema26 = findValue(overlays.ema26);
        if (overlays.vwap) indicators.vwap = findValue(overlays.vwap);
        if (overlays.bb) {
            indicators.bb_upper = findValue(overlays.bb.upper);
            indicators.bb_mid = findValue(overlays.bb.middle);
            indicators.bb_lower = findValue(overlays.bb.lower);
        }
        if (panels.rsi) {
            indicators.rsi = findValue(panels.rsi.data);
            indicators.rsi_trajectory = trajectory(panels.rsi.data);
        }
        if (panels.macd) {
            indicators.macd_line = findValue(panels.macd.data.macd);
            indicators.macd_signal = findValue(panels.macd.data.signal);
            indicators.macd_histogram = findValue(panels.macd.data.histogram);
            indicators.macd_hist_trajectory = trajectory(panels.macd.data.histogram);
        }
        if (panels.stoch) {
            indicators.stoch_k = findValue(panels.stoch.data.k);
            indicators.stoch_d = findValue(panels.stoch.data.d);
        }
        if (panels.adx) {
            indicators.adx = findValue(panels.adx.data.adx);
            indicators.adx_pdi = findValue(panels.adx.data.pdi);
            indicators.adx_mdi = findValue(panels.adx.data.mdi);
        }
        if (panels.atr) indicators.atr = findValue(panels.atr.data);
    }

    // Fallback: calculate all key indicators from visible bars when worker didn't provide them
    const closePrices = visibleBars.map(b => b.close);
    const r2 = (v: number) => Math.round(v * 100) / 100;

    const calcSMA = (prices: number[], period: number) =>
        r2(prices.slice(-period).reduce((s, c) => s + c, 0) / period);

    const calcEMA = (prices: number[], period: number) => {
        const k = 2 / (period + 1);
        let ema = prices.slice(0, period).reduce((s, c) => s + c, 0) / period;
        for (let i = period; i < prices.length; i++) ema = prices[i] * k + ema * (1 - k);
        return r2(ema);
    };

    if (!indicators.sma20 && closePrices.length >= 20) indicators.sma20 = calcSMA(closePrices, 20);
    if (!indicators.sma50 && closePrices.length >= 50) indicators.sma50 = calcSMA(closePrices, 50);

    if (!indicators.ema12 && closePrices.length >= 12) indicators.ema12 = calcEMA(closePrices, 12);
    if (!indicators.ema26 && closePrices.length >= 26) indicators.ema26 = calcEMA(closePrices, 26);

    // MACD
    if (!indicators.macd_line && closePrices.length >= 26) {
        const allEma12: number[] = [];
        const allEma26: number[] = [];
        const k12 = 2 / 13, k26 = 2 / 27;
        let e12 = closePrices.slice(0, 12).reduce((s, c) => s + c, 0) / 12;
        let e26 = closePrices.slice(0, 26).reduce((s, c) => s + c, 0) / 26;
        for (let i = 0; i < closePrices.length; i++) {
            if (i >= 12) e12 = closePrices[i] * k12 + e12 * (1 - k12);
            if (i >= 26) e26 = closePrices[i] * k26 + e26 * (1 - k26);
            if (i >= 26) { allEma12.push(e12); allEma26.push(e26); }
        }
        const macdLine = allEma12.map((v, i) => v - allEma26[i]);
        if (macdLine.length >= 9) {
            const k9 = 2 / 10;
            let sig = macdLine.slice(0, 9).reduce((s, c) => s + c, 0) / 9;
            for (let i = 9; i < macdLine.length; i++) sig = macdLine[i] * k9 + sig * (1 - k9);
            indicators.macd_line = r2(macdLine[macdLine.length - 1]);
            indicators.macd_signal = r2(sig);
            indicators.macd_histogram = r2(macdLine[macdLine.length - 1] - sig);
            indicators.macd_hist_trajectory = macdLine.slice(-5).map((v, i, arr) => {
                const sigArr = macdLine.slice(0, -5 + i + 1);
                let s = sigArr.slice(0, 9).reduce((sum, c) => sum + c, 0) / 9;
                for (let j = 9; j < sigArr.length; j++) s = sigArr[j] * k9 + s * (1 - k9);
                return r2(v - s);
            });
        }
    }

    // Bollinger Bands (SMA20 ± 2 * stddev)
    if (!indicators.bb_upper && closePrices.length >= 20) {
        const sma = indicators.sma20 ?? calcSMA(closePrices, 20);
        const last20 = closePrices.slice(-20);
        const variance = last20.reduce((s, c) => s + Math.pow(c - sma, 2), 0) / 20;
        const stddev = Math.sqrt(variance);
        indicators.bb_upper = r2(sma + 2 * stddev);
        indicators.bb_mid = r2(sma);
        indicators.bb_lower = r2(sma - 2 * stddev);
    }

    // RSI(14)
    if (!indicators.rsi && closePrices.length >= 15) {
        const period = 14;
        const changes = closePrices.slice(-period - 1).map((c, i, arr) => i > 0 ? c - arr[i - 1] : 0).slice(1);
        const avgGain = changes.filter(c => c > 0).reduce((s, c) => s + c, 0) / period;
        const avgLoss = changes.filter(c => c < 0).reduce((s, c) => s + Math.abs(c), 0) / period;
        indicators.rsi = avgLoss === 0 ? 100 : r2(100 - 100 / (1 + avgGain / avgLoss));
    }

    // ATR(14)
    if (!indicators.atr && visibleBars.length >= 15) {
        const last15 = visibleBars.slice(-15);
        const trs = last15.slice(1).map((b, i) => Math.max(b.high - b.low, Math.abs(b.high - last15[i].close), Math.abs(b.low - last15[i].close)));
        indicators.atr = r2(trs.reduce((s, t) => s + t, 0) / trs.length);
    }

    const levels = drawings
        .filter((d): d is Drawing & { type: 'horizontal_line' } => d.type === 'horizontal_line')
        .map(d => ({ price: d.price, label: d.label }));

    const isHistorical = toIdx < data.length - 3;

    return {
        recentBars: recentBars.map(b => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })),
        indicators,
        levels,
        visibleDateRange: {
            from: data[fromIdx]?.time ?? 0,
            to: rightTime ?? 0,
        },
        isHistorical,
    };
}

// ============================================================================
// Chart Context Menu Component
// ============================================================================

interface ContextMenuState {
    visible: boolean;
    x: number;
    y: number;
    candle: ChartBar | null;
}

function ChartContextMenu({
    state, ticker, interval, range, data, indicatorResults, drawings, activeOverlays, activePanels, showMA, showEMA, chartApi, onClose,
}: {
    state: ContextMenuState;
    ticker: string;
    interval: string;
    range: string;
    data: ChartBar[];
    indicatorResults: IndicatorResults | null;
    drawings: Drawing[];
    activeOverlays: string[];
    activePanels: string[];
    showMA: boolean;
    showEMA: boolean;
    chartApi: IChartApi | null;
    onClose: () => void;
}) {
    if (!state.visible) return null;

    const dispatchChartAsk = (prompt: string) => {
        const snapshot = buildChartSnapshot(data, indicatorResults, drawings, activeOverlays, activePanels, showMA, showEMA, chartApi);
        const activeIndicatorNames: string[] = [];
        if (showMA) activeIndicatorNames.push('SMA20', 'SMA50');
        if (showEMA) activeIndicatorNames.push('EMA12', 'EMA26');
        activeOverlays.forEach(o => activeIndicatorNames.push(o.toUpperCase()));
        activePanels.forEach(p => activeIndicatorNames.push(p.toUpperCase()));

        const chartCtx: ChartContext = {
            ticker,
            interval,
            range,
            activeIndicators: activeIndicatorNames,
            currentPrice: data.length > 0 ? data[data.length - 1].close : null,
            snapshot,
            targetCandle: state.candle ? {
                date: state.candle.time,
                open: state.candle.open,
                high: state.candle.high,
                low: state.candle.low,
                close: state.candle.close,
                volume: state.candle.volume,
            } : null,
        };

        window.dispatchEvent(new CustomEvent('agent:chart-ask', { detail: { chartContext: chartCtx, prompt } }));
        onClose();
    };

    const items = state.candle
        ? [
            { label: 'Analyze this candle', prompt: `Analyze the candle at ${new Date(state.candle.time * 1000).toLocaleDateString()} for ${ticker}` },
            { label: 'Why did this move?', prompt: `Why did ${ticker} move like this on ${new Date(state.candle.time * 1000).toLocaleDateString()}?` },
            { label: 'Full technical analysis', prompt: `Full technical analysis of ${ticker} chart` },
            { label: 'Support & resistance levels', prompt: `Identify support and resistance levels for ${ticker}` },
        ]
        : [
            { label: 'Full technical analysis', prompt: `Full technical analysis of ${ticker} chart` },
            { label: 'Support & resistance levels', prompt: `Identify support and resistance levels for ${ticker}` },
            { label: 'Trend direction', prompt: `What is the current trend for ${ticker}?` },
            { label: 'Entry/exit points', prompt: `Suggest entry and exit points for ${ticker}` },
        ];

    return (
        <>
            <div className="fixed inset-0 z-[9998]" onClick={onClose} />
            <div
                className="absolute z-[9999] bg-white rounded-lg shadow-xl border border-slate-200 py-1 min-w-[200px]"
                style={{ left: state.x, top: state.y }}
            >
                <div className="px-3 py-1.5 flex items-center gap-1.5 border-b border-slate-100">
                    <Bot className="w-3.5 h-3.5 text-blue-500" />
                    <span className="text-[10px] font-semibold text-slate-600">AI Chart Analysis</span>
                </div>
                {items.map((item, i) => (
                    <button
                        key={i}
                        onClick={() => dispatchChartAsk(item.prompt)}
                        className="w-full text-left px-3 py-1.5 text-[11px] text-slate-700 hover:bg-blue-50 hover:text-blue-700 flex items-center gap-2"
                    >
                        <Sparkles className="w-3 h-3 text-blue-400 flex-shrink-0" />
                        {item.label}
                    </button>
                ))}
                <div className="border-t border-slate-100 px-3 py-1.5">
                    <input
                        type="text"
                        placeholder="Ask anything about this chart..."
                        className="w-full text-[11px] text-slate-700 bg-slate-50 border border-slate-200 rounded px-2 py-1 focus:outline-none focus:border-blue-400"
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && (e.target as HTMLInputElement).value.trim()) {
                                dispatchChartAsk((e.target as HTMLInputElement).value.trim());
                            }
                        }}
                        autoFocus
                    />
                </div>
            </div>
        </>
    );
}

// ============================================================================
// Component
// ============================================================================

function TradingChartComponent({
    ticker: initialTicker = 'AAPL',
    onTickerChange,
    minimal = false,
    onOpenChart,
    onOpenNews
}: TradingChartProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const sessionBgSeriesRef = useRef<ISeriesApi<any> | null>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);

    // User preferences
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    // Market session for LIVE indicator
    const ws = useWebSocket();
    const [marketSession, setMarketSession] = useState<MarketSession | null>(null);

    // Persist window state
    const { state: windowState, updateState: updateWindowState } = useWindowState<ChartWindowState>();

    const [currentTicker, setCurrentTicker] = useState(windowState.ticker || initialTicker);
    const [selectedInterval, setSelectedInterval] = useState<Interval>(windowState.interval || '1day');
    const [selectedRange, setSelectedRange] = useState<TimeRange>(windowState.range || '1Y');
    const [inputValue, setInputValue] = useState(windowState.ticker || initialTicker);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [isScrolledAway, setIsScrolledAway] = useState(false);
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

    // On-demand overlay series refs (created when activated)
    const overlaySeriesRef = useRef<Map<string, ISeriesApi<any>>>(new Map());

    // On-demand MA/EMA series refs
    const maSeriesRef = useRef<{ ma20: ISeriesApi<any> | null; ma50: ISeriesApi<any> | null }>({ ma20: null, ma50: null });
    const emaSeriesRef = useRef<{ ema12: ISeriesApi<any> | null; ema26: ISeriesApi<any> | null }>({ ema12: null, ema26: null });

    // Panel indicator series refs (pane-based)
    const panelSeriesRef = useRef<Map<string, Map<string, ISeriesApi<any>>>>(new Map());
    const panelPaneIndexRef = useRef<Map<string, number>>(new Map());

    // Watermark ref for updates
    const watermarkRef = useRef<any>(null);

    // Markers primitive ref (v5)
    const newsMarkersRef = useRef<any>(null);

    // Toggle helpers
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
        getMarketSession().then(setMarketSession).catch(() => { });
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

    const isMarketOpen = marketSession?.current_session === 'MARKET_OPEN' ||
        marketSession?.current_session === 'PRE_MARKET' ||
        marketSession?.current_session === 'POST_MARKET';
    const showLiveIndicator = isLive && isMarketOpen;

    // News for markers
    const tickerNews = useArticlesByTicker(currentTicker);

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

    // Edit popup state
    const [editPopup, setEditPopup] = useState<{
        visible: boolean;
        drawingId: string | null;
        x: number;
        y: number;
    }>({ visible: false, drawingId: null, x: 0, y: 0 });

    const editingDrawing = editPopup.drawingId
        ? drawings.find(d => d.id === editPopup.drawingId)
        : null;

    // AI chart context menu
    const [ctxMenu, setCtxMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, candle: null });

    const handleChartContextMenu = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        const x = Math.min(e.clientX - rect.left, rect.width - 220);
        const y = Math.min(e.clientY - rect.top, rect.height - 200);
        setCtxMenu({ visible: true, x, y, candle: hoveredBar });
    }, [hoveredBar]);

    const openEditPopup = useCallback((drawingId: string, x: number, y: number) => {
        setEditPopup({ visible: true, drawingId, x, y });
        selectDrawing(drawingId);
    }, [selectDrawing]);

    const closeEditPopup = useCallback(() => {
        setEditPopup({ visible: false, drawingId: null, x: 0, y: 0 });
    }, []);

    const handleEditColor = useCallback((color: string) => {
        if (editPopup.drawingId) updateDrawingColor(editPopup.drawingId, color);
    }, [editPopup.drawingId, updateDrawingColor]);

    const handleEditLineWidth = useCallback((width: number) => {
        if (editPopup.drawingId) updateDrawingLineWidth(editPopup.drawingId, width);
    }, [editPopup.drawingId, updateDrawingLineWidth]);

    const handleEditDelete = useCallback(() => {
        if (editPopup.drawingId) {
            removeDrawing(editPopup.drawingId);
            closeEditPopup();
        }
    }, [editPopup.drawingId, removeDrawing, closeEditPopup]);

    // Refs para price lines (drawings)
    const priceLinesRef = useRef<Map<string, any>>(new Map());

    // Update when external ticker changes
    useEffect(() => {
        setCurrentTicker(initialTicker);
        setInputValue(initialTicker);
    }, [initialTicker]);

    // Apply time range to chart — uses real timestamps, not bar count
    const applyTimeRange = useCallback((range: TimeRange) => {
        if (!chartRef.current || data.length === 0) return;
        const timeScale = chartRef.current.timeScale();
        const rangeConfig = TIME_RANGES.find(r => r.id === range);
        if (!rangeConfig) return;

        if (range === 'ALL' || rangeConfig.days === 0) {
            timeScale.fitContent();
            return;
        }

        const lastBar = data[data.length - 1];
        const fromTimestamp = lastBar.time - (rangeConfig.days * 86400);

        // Find the first bar that falls within the range
        let fromIndex = 0;
        for (let i = 0; i < data.length; i++) {
            if (data[i].time >= fromTimestamp) {
                fromIndex = i;
                break;
            }
        }

        // If all data is within range, just fitContent
        if (fromIndex === 0 && data[0].time > fromTimestamp) {
            timeScale.fitContent();
            return;
        }

        timeScale.setVisibleRange({
            from: data[fromIndex].time as UTCTimestamp,
            to: lastBar.time as UTCTimestamp,
        });
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

    // ============================================================================
    // Initialize chart (v5 API)
    // ============================================================================
    useEffect(() => {
        if (!containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: CHART_COLORS.background },
                textColor: CHART_COLORS.textColor,
                fontFamily: fontFamily,
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
                barSpacing: 8,
                minBarSpacing: 0.5,
                fixLeftEdge: false,
                fixRightEdge: false,
                tickMarkFormatter: (time: number) => {
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
            autoSize: false,
        });

        chartRef.current = chart;

        // Watermark disabled for testing
        watermarkRef.current = null;

        // Session background series (pre/post market highlighting)
        // Created BEFORE candle series so it renders behind
        const isIntraday = selectedInterval !== '1day';
        if (isIntraday) {
            const sessionBgSeries = chart.addSeries(HistogramSeries, {
                priceScaleId: 'session_bg',
                priceLineVisible: false,
                lastValueVisible: false,
                priceFormat: { type: 'price' },
            });
            chart.priceScale('session_bg').applyOptions({
                visible: false,
                scaleMargins: { top: 0, bottom: 0 },
            });
            sessionBgSeriesRef.current = sessionBgSeries;
        } else {
            sessionBgSeriesRef.current = null;
        }

        // Candlestick series (v5 API — borderVisible: false for clean modern look)
        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: CHART_COLORS.upColor,
            downColor: CHART_COLORS.downColor,
            wickUpColor: CHART_COLORS.upColor,
            wickDownColor: CHART_COLORS.downColor,
            borderVisible: false,
            priceLineVisible: true,
            priceLineWidth: 1,
            priceLineColor: CHART_COLORS.crosshair,
            priceLineStyle: LineStyle.Dotted,
            lastValueVisible: true,
        });
        candleSeriesRef.current = candleSeries;

        // Volume series (v5 API)
        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: CHART_COLORS.volumeUp,
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });
        volumeSeriesRef.current = volumeSeries;

        chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.85, bottom: 0 },
        });

        // Crosshair move handler
        chart.subscribeCrosshairMove((param) => {
            if (!param.point) return;
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

        // Resize observer
        let resizeTimeout: NodeJS.Timeout | null = null;
        let lastWidth = 0;
        let lastHeight = 0;

        const applyResize = (width: number, height: number) => {
            if (!chartRef.current || width <= 0 || height <= 0) return;
            if (width === lastWidth && height === lastHeight) return;

            lastWidth = width;
            lastHeight = height;
            chartRef.current.applyOptions({ width, height });

            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (chartRef.current) {
                    const timeScale = chartRef.current.timeScale();
                    const visibleRange = timeScale.getVisibleLogicalRange();
                    timeScale.applyOptions({ rightOffset: 5, barSpacing: 8 });
                    if (visibleRange) timeScale.setVisibleLogicalRange(visibleRange);
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

        if (containerRef.current) {
            applyResize(containerRef.current.clientWidth, containerRef.current.clientHeight);
        }

        return () => {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeObserver.disconnect();
            // Clean up refs
            overlaySeriesRef.current.clear();
            maSeriesRef.current = { ma20: null, ma50: null };
            emaSeriesRef.current = { ema12: null, ema26: null };
            panelSeriesRef.current.clear();
            panelPaneIndexRef.current.clear();
            newsMarkersRef.current = null;
            watermarkRef.current = null;
            sessionBgSeriesRef.current = null;
            chart.remove();
            chartRef.current = null;
        };
    }, [currentTicker, fontFamily, selectedInterval]);

    // Auto-load more data when scrolling left + detect if scrolled away from realtime
    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;
        const timeScale = chart.timeScale();

        const handleVisibleRangeChange = () => {
            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) return;

            // Lazy-load older data
            if (!loadingMore && hasMore && logicalRange.from < 50) loadMore();

            // Detect if user scrolled away from the right edge (latest bars)
            const totalBars = data.length;
            const isNearRealtime = logicalRange.to >= totalBars - 3;
            setIsScrolledAway(!isNearRealtime && totalBars > 0);
        };

        timeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        return () => {
            timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        };
    }, [hasMore, loadingMore, loadMore, data.length]);

    // Update watermark when ticker changes (v5 – recreate watermark)
    useEffect(() => {
        if (chartRef.current && watermarkRef.current) {
            try {
                watermarkRef.current.applyOptions({
                    lines: [{
                        text: currentTicker,
                        color: CHART_COLORS.watermark,
                        fontSize: 72,
                    }],
                });
            } catch {
                // Watermark not critical
            }
        }
    }, [currentTicker]);

    // ============================================================================
    // On-demand MA/EMA series creation
    // ============================================================================

    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        if (showMA) {
            if (!maSeriesRef.current.ma20) {
                maSeriesRef.current.ma20 = chart.addSeries(LineSeries, {
                    color: CHART_COLORS.ma20,
                    lineWidth: 2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: true,
                    crosshairMarkerRadius: 4,
                });
            }
            if (!maSeriesRef.current.ma50) {
                maSeriesRef.current.ma50 = chart.addSeries(LineSeries, {
                    color: CHART_COLORS.ma50,
                    lineWidth: 2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: true,
                    crosshairMarkerRadius: 4,
                });
            }
            maSeriesRef.current.ma20.applyOptions({ visible: true });
            maSeriesRef.current.ma50.applyOptions({ visible: true });
        } else {
            if (maSeriesRef.current.ma20) maSeriesRef.current.ma20.applyOptions({ visible: false });
            if (maSeriesRef.current.ma50) maSeriesRef.current.ma50.applyOptions({ visible: false });
        }
    }, [showMA]);

    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        if (showEMA) {
            if (!emaSeriesRef.current.ema12) {
                emaSeriesRef.current.ema12 = chart.addSeries(LineSeries, {
                    color: CHART_COLORS.ema12,
                    lineWidth: 1,
                    lineStyle: LineStyle.Solid,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: true,
                    crosshairMarkerRadius: 3,
                });
            }
            if (!emaSeriesRef.current.ema26) {
                emaSeriesRef.current.ema26 = chart.addSeries(LineSeries, {
                    color: CHART_COLORS.ema26,
                    lineWidth: 1,
                    lineStyle: LineStyle.Solid,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: true,
                    crosshairMarkerRadius: 3,
                });
            }
            emaSeriesRef.current.ema12.applyOptions({ visible: true });
            emaSeriesRef.current.ema26.applyOptions({ visible: true });
        } else {
            if (emaSeriesRef.current.ema12) emaSeriesRef.current.ema12.applyOptions({ visible: false });
            if (emaSeriesRef.current.ema26) emaSeriesRef.current.ema26.applyOptions({ visible: false });
        }
    }, [showEMA]);

    // Toggle volume visibility
    useEffect(() => {
        if (volumeSeriesRef.current) {
            volumeSeriesRef.current.applyOptions({ visible: showVolume });
        }
    }, [showVolume]);

    // ============================================================================
    // On-demand overlay series (sma200, bb, keltner, vwap)
    // ============================================================================

    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const overlayConfigs: Record<string, { keys: string[]; configs: Record<string, { color: string; lineWidth: number; lineStyle?: number }> }> = {
            sma200: {
                keys: ['sma200'],
                configs: { sma200: { color: '#ef4444', lineWidth: 2 } }
            },
            bb: {
                keys: ['bb_upper', 'bb_middle', 'bb_lower'],
                configs: {
                    bb_upper: { color: 'rgba(59, 130, 246, 0.6)', lineWidth: 1 },
                    bb_middle: { color: 'rgba(59, 130, 246, 0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed },
                    bb_lower: { color: 'rgba(59, 130, 246, 0.6)', lineWidth: 1 },
                }
            },
            keltner: {
                keys: ['keltner_upper', 'keltner_middle', 'keltner_lower'],
                configs: {
                    keltner_upper: { color: 'rgba(20, 184, 166, 0.6)', lineWidth: 1 },
                    keltner_middle: { color: 'rgba(20, 184, 166, 0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed },
                    keltner_lower: { color: 'rgba(20, 184, 166, 0.6)', lineWidth: 1 },
                }
            },
            vwap: {
                keys: ['vwap'],
                configs: { vwap: { color: '#f97316', lineWidth: 2 } }
            },
        };

        for (const [overlayId, config] of Object.entries(overlayConfigs)) {
            const isActive = activeOverlays.includes(overlayId);

            for (const key of config.keys) {
                let series = overlaySeriesRef.current.get(key);

                if (isActive && !series) {
                    const seriesConfig = config.configs[key];
                    series = chart.addSeries(LineSeries, {
                        color: seriesConfig.color,
                        lineWidth: seriesConfig.lineWidth as 1 | 2 | 3 | 4,
                        lineStyle: seriesConfig.lineStyle ?? LineStyle.Solid,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    overlaySeriesRef.current.set(key, series);
                }

                if (series) {
                    series.applyOptions({ visible: isActive });
                }
            }
        }
    }, [activeOverlays]);

    // ============================================================================
    // Multi-pane indicator panels (v5 native panes)
    // ============================================================================

    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        // Remove panes for deactivated panels
        const currentPanelIds = new Set(activePanels);
        for (const [panelId, paneIndex] of panelPaneIndexRef.current.entries()) {
            if (!currentPanelIds.has(panelId)) {
                try {
                    chart.removePane(paneIndex);
                } catch {
                    // Pane may already be removed
                }
                panelSeriesRef.current.delete(panelId);
                panelPaneIndexRef.current.delete(panelId);
            }
        }

        // Reassign pane indices (pane 0 = main, pane 1+ = panels)
        let nextPaneIndex = 1;
        for (const panelId of activePanels) {
            if (!panelPaneIndexRef.current.has(panelId)) {
                // Find next available pane index
                const usedIndices = new Set(panelPaneIndexRef.current.values());
                while (usedIndices.has(nextPaneIndex)) nextPaneIndex++;

                const seriesMap = new Map<string, ISeriesApi<any>>();

                try {
                    switch (panelId) {
                        case 'rsi': {
                            const rsiSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.rsi,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            seriesMap.set('main', rsiSeries);

                            // Reference lines
                            rsiSeries.createPriceLine({ price: 70, color: 'rgba(239, 68, 68, 0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            rsiSeries.createPriceLine({ price: 30, color: 'rgba(16, 185, 129, 0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            break;
                        }
                        case 'macd': {
                            const histSeries = chart.addSeries(HistogramSeries, {
                                priceLineVisible: false,
                                lastValueVisible: false,
                                priceScaleId: `macd_${nextPaneIndex}`,
                            }, nextPaneIndex);
                            const macdLine = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.macdLine,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                                priceScaleId: `macd_${nextPaneIndex}`,
                            }, nextPaneIndex);
                            const sigLine = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.macdSignal,
                                lineWidth: 1,
                                priceLineVisible: false,
                                lastValueVisible: false,
                                priceScaleId: `macd_${nextPaneIndex}`,
                            }, nextPaneIndex);
                            seriesMap.set('histogram', histSeries);
                            seriesMap.set('macd', macdLine);
                            seriesMap.set('signal', sigLine);
                            break;
                        }
                        case 'stoch': {
                            const kSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.stochK,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            const dSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.stochD,
                                lineWidth: 1,
                                priceLineVisible: false,
                                lastValueVisible: false,
                            }, nextPaneIndex);
                            seriesMap.set('k', kSeries);
                            seriesMap.set('d', dSeries);
                            seriesMap.set('main', kSeries);

                            kSeries.createPriceLine({ price: 80, color: 'rgba(239, 68, 68, 0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            kSeries.createPriceLine({ price: 20, color: 'rgba(16, 185, 129, 0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            break;
                        }
                        case 'adx': {
                            const adxSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.adxLine,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            const pdiSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.pdiLine,
                                lineWidth: 1,
                                priceLineVisible: false,
                                lastValueVisible: false,
                            }, nextPaneIndex);
                            const mdiSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.mdiLine,
                                lineWidth: 1,
                                priceLineVisible: false,
                                lastValueVisible: false,
                            }, nextPaneIndex);
                            seriesMap.set('adx', adxSeries);
                            seriesMap.set('pdi', pdiSeries);
                            seriesMap.set('mdi', mdiSeries);
                            seriesMap.set('main', adxSeries);
                            break;
                        }
                        case 'atr': {
                            const atrSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.atr,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            seriesMap.set('main', atrSeries);
                            break;
                        }
                        case 'squeeze': {
                            const sqSeries = chart.addSeries(HistogramSeries, {
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            seriesMap.set('main', sqSeries);
                            break;
                        }
                        case 'obv': {
                            const obvSeries = chart.addSeries(LineSeries, {
                                color: INDICATOR_COLORS.obv,
                                lineWidth: 2,
                                priceLineVisible: false,
                                lastValueVisible: true,
                            }, nextPaneIndex);
                            seriesMap.set('main', obvSeries);
                            break;
                        }
                        case 'rvol': {
                            const rvolSeries = chart.addSeries(HistogramSeries, {
                                priceLineVisible: false,
                                lastValueVisible: true,
                                priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
                            }, nextPaneIndex);
                            seriesMap.set('main', rvolSeries);
                            break;
                        }
                    }

                    panelSeriesRef.current.set(panelId, seriesMap);
                    panelPaneIndexRef.current.set(panelId, nextPaneIndex);

                    // Set pane height
                    try {
                        const pane = chart.panes()[nextPaneIndex];
                        if (pane) pane.setHeight(100);
                    } catch {
                        // Pane height not critical
                    }

                    nextPaneIndex++;
                } catch (err) {
                    console.warn(`[TradingChart] Failed to create panel ${panelId}:`, err);
                }
            }
        }
    }, [activePanels]);

    // ============================================================================
    // Update chart data
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
        if (!data || data.length === 0) return;

        const candleData: CandlestickData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
        }));

        const volumeData: HistogramData[] = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            value: bar.volume,
            color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        }));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volumeData);

        // Clear markers if disabled (v5)
        if (!showNewsMarkers && newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers([]);
        }

        // Calculate and set MAs (if series exist)
        if (maSeriesRef.current.ma20 && maSeriesRef.current.ma50) {
            maSeriesRef.current.ma20.setData(calculateSMA(data, 20));
            maSeriesRef.current.ma50.setData(calculateSMA(data, 50));
        }

        // Calculate and set EMAs (if series exist)
        if (emaSeriesRef.current.ema12 && emaSeriesRef.current.ema26) {
            emaSeriesRef.current.ema12.setData(calculateEMA(data, 12));
            emaSeriesRef.current.ema26.setData(calculateEMA(data, 26));
        }
    }, [data, currentTicker, showNewsMarkers]);

    // ============================================================================
    // Session background (pre-market / post-market highlighting)
    // ============================================================================
    useEffect(() => {
        if (!sessionBgSeriesRef.current || !data || data.length === 0) return;

        const SESSION_COLORS = {
            preMarket: 'rgba(59, 130, 246, 0.06)',   // light blue
            postMarket: 'rgba(139, 92, 246, 0.06)',   // light violet
            regular: 'rgba(0, 0, 0, 0)',               // transparent
        };

        const sessionData = data.map(bar => {
            const date = new Date(bar.time * 1000);
            // Get hours/minutes in US Eastern Time
            const etParts = date.toLocaleString('en-US', {
                timeZone: 'America/New_York',
                hour: 'numeric',
                minute: 'numeric',
                hour12: false,
            });
            const [hStr, mStr] = etParts.split(':');
            const totalMinutes = parseInt(hStr) * 60 + parseInt(mStr);

            // Pre-market:  4:00 AM - 9:30 AM ET  (240 - 570)
            // Regular:     9:30 AM - 4:00 PM ET  (570 - 960)
            // Post-market: 4:00 PM - 8:00 PM ET  (960 - 1200)
            let color = SESSION_COLORS.regular;
            if (totalMinutes >= 240 && totalMinutes < 570) {
                color = SESSION_COLORS.preMarket;
            } else if (totalMinutes >= 960 && totalMinutes < 1200) {
                color = SESSION_COLORS.postMarket;
            }

            return {
                time: bar.time as UTCTimestamp,
                value: 1,
                color,
            };
        });

        sessionBgSeriesRef.current.setData(sessionData);
    }, [data, selectedInterval]);

    // Apply time range when data loads (ticker change or interval change)
    const lastAppliedKeyRef = useRef<string>('');
    useEffect(() => {
        if (!data || data.length === 0 || !candleSeriesRef.current) return;
        const key = `${currentTicker}-${selectedInterval}-${data.length}`;
        if (lastAppliedKeyRef.current !== key) {
            lastAppliedKeyRef.current = key;
            setTimeout(() => applyTimeRange(selectedRange), 50);
        }
    }, [data, currentTicker, selectedInterval, selectedRange, applyTimeRange]);

    // ============================================================================
    // News markers (v5 API - createSeriesMarkers)
    // ============================================================================
    const newsPriceLinesRef = useRef<any[]>([]);
    const newsTimeMapRef = useRef<Map<number, any[]>>(new Map());

    useEffect(() => {
        if (!candleSeriesRef.current || !data || data.length === 0) return;

        // Clear previous price lines
        for (const line of newsPriceLinesRef.current) {
            try { candleSeriesRef.current.removePriceLine(line); } catch { /* */ }
        }
        newsPriceLinesRef.current = [];
        newsTimeMapRef.current.clear();

        // Clear previous markers (v5)
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

                const priceLine = candleSeriesRef.current.createPriceLine({
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

        // v5: Use createSeriesMarkers
        if (newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers(uniqueMarkers);
        } else if (candleSeriesRef.current && uniqueMarkers.length > 0) {
            newsMarkersRef.current = createSeriesMarkers(candleSeriesRef.current, uniqueMarkers);
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
    // Register real-time update handler
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) {
            registerUpdateHandler(null);
            return;
        }

        const candleSeries = candleSeriesRef.current;
        const volumeSeries = volumeSeriesRef.current;

        const handleRealtimeUpdate = (bar: HookChartBar, isNewBar: boolean) => {
            candleSeries.update({
                time: bar.time as UTCTimestamp,
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
            });

            const volumeColor = bar.close >= bar.open
                ? CHART_COLORS.volumeUp
                : CHART_COLORS.volumeDown;

            volumeSeries.update({
                time: bar.time as UTCTimestamp,
                value: bar.volume,
                color: volumeColor,
            });

            // Auto-scroll to latest bar if user is near the right edge (v5 scrollToRealtime)
            if (isNewBar && chartRef.current) {
                const timeScale = chartRef.current.timeScale();
                const logicalRange = timeScale.getVisibleLogicalRange();
                if (logicalRange && logicalRange.to >= data.length - 5) {
                    timeScale.scrollToRealTime();
                }
            }
        };

        registerUpdateHandler(handleRealtimeUpdate);
        return () => { registerUpdateHandler(null); };
    }, [registerUpdateHandler, data.length]);

    // ============================================================================
    // Render drawings (horizontal lines) with hover and selection
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current) return;

        const candleSeries = candleSeriesRef.current;
        const currentLines = priceLinesRef.current;

        currentLines.forEach((priceLine, id) => {
            if (!drawings.find(d => d.id === id)) {
                candleSeries.removePriceLine(priceLine);
                currentLines.delete(id);
            }
        });

        drawings.forEach(drawing => {
            if (drawing.type === 'horizontal_line') {
                const existingLine = currentLines.get(drawing.id);
                const isSelected = selectedDrawingId === drawing.id;
                const isHovered = hoveredDrawingId === drawing.id;

                const visualWidth = isSelected ? Math.max(drawing.lineWidth + 1, 3)
                    : isHovered ? Math.max(drawing.lineWidth, 2)
                        : drawing.lineWidth;

                if (existingLine) {
                    existingLine.applyOptions({
                        price: drawing.price,
                        color: drawing.color,
                        lineWidth: visualWidth as 1 | 2 | 3 | 4,
                        lineStyle: isSelected || isHovered ? LineStyle.Solid :
                            drawing.lineStyle === 'dashed' ? LineStyle.Dashed :
                                drawing.lineStyle === 'dotted' ? LineStyle.Dotted : LineStyle.Solid,
                    });
                } else {
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

    // Drag state
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

    // Click handler for drawing/selection
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;

        const chart = chartRef.current;
        const candleSeries = candleSeriesRef.current;

        const handleClick = (param: any) => {
            if (!param.point) return;
            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) return;

            if (showNewsMarkers && param.time && newsTimeMapRef.current.has(param.time as number)) {
                handleNewsMarkerClick(param.time as number);
                return;
            }

            if (activeTool === 'horizontal_line') {
                handleChartClick(price);
            } else {
                const nearDrawing = findDrawingNearPrice(price, 0.5);
                selectDrawing(nearDrawing ? nearDrawing.id : null);
            }
        };

        const handleDoubleClick = (param: any) => {
            if (!param.point || activeTool !== 'none') return;
            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) return;

            const nearDrawing = findDrawingNearPrice(price, 1.5);
            if (nearDrawing) openEditPopup(nearDrawing.id, param.point.x + 20, param.point.y);
        };

        chart.subscribeClick(handleClick);
        chart.subscribeDblClick(handleDoubleClick);

        return () => {
            chart.unsubscribeClick(handleClick);
            chart.unsubscribeDblClick(handleDoubleClick);
        };
    }, [activeTool, handleChartClick, findDrawingNearPrice, selectDrawing, openEditPopup, showNewsMarkers, handleNewsMarkerClick]);

    // Hover detection
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;
        if (dragState.active || activeTool !== 'none') return;

        const chart = chartRef.current;
        const candleSeries = candleSeriesRef.current;

        const handleCrosshairMove = (param: any) => {
            if (!param.point) { setHoveredDrawing(null); return; }
            const price = candleSeries.coordinateToPrice(param.point.y);
            if (price === null) { setHoveredDrawing(null); return; }
            const nearDrawing = findDrawingNearPrice(price, 1.5);
            setHoveredDrawing(nearDrawing?.id || null);
        };

        chart.subscribeCrosshairMove(handleCrosshairMove);
        return () => { chart.unsubscribeCrosshairMove(handleCrosshairMove); };
    }, [findDrawingNearPrice, setHoveredDrawing, dragState.active, activeTool]);

    // Drag handlers
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
        setDragState({ active: true, drawingId: nearDrawing.id, drawingType: 'horizontal_line', originalPrice: nearDrawing.price, startMouseY: mouseY });
        selectDrawing(nearDrawing.id);
        startDragging();
    }, [activeTool, findDrawingNearPrice, selectDrawing, startDragging, editPopup.visible]);

    const handleDragMove = useCallback((e: React.MouseEvent) => {
        if (!dragState.active || !dragState.drawingId || !candleSeriesRef.current || !containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseY = e.clientY - rect.top;
        const newPrice = candleSeriesRef.current.coordinateToPrice(mouseY);
        if (newPrice !== null && newPrice > 0) updateHorizontalLinePrice(dragState.drawingId, newPrice);
    }, [dragState, updateHorizontalLinePrice]);

    const handleDragEnd = useCallback(() => {
        if (dragState.active) {
            setDragState({ active: false, drawingId: null, drawingType: null, originalPrice: 0, startMouseY: 0 });
            stopDragging();
            setTimeout(() => selectDrawing(null), 50);
        }
    }, [dragState.active, stopDragging, selectDrawing]);

    // Disable scroll during drag
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

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
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
                    if (selectedDrawingId) removeDrawing(selectedDrawingId);
                    break;
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [activeTool, selectedDrawingId, cancelDrawing, selectDrawing, setActiveTool, removeDrawing]);

    // Drawing cursor
    useEffect(() => {
        if (!containerRef.current) return;
        containerRef.current.style.cursor = isDrawing ? 'crosshair' : 'default';
    }, [isDrawing]);

    // Range change — auto-switch interval for long ranges (like TradingView)
    const handleRangeChange = useCallback((range: TimeRange) => {
        setSelectedRange(range);

        // Auto-switch to daily interval for ranges >= 6M to avoid excessive bar counts
        const rangeConfig = TIME_RANGES.find(r => r.id === range);
        if (rangeConfig && rangeConfig.days >= 180 && selectedInterval !== '1day') {
            setSelectedInterval('1day');
            return; // Data will reload, applyTimeRange runs after new data arrives
        }

        // Auto-switch to hourly for 1M-3M if currently on minute intervals
        if (rangeConfig && rangeConfig.days >= 30 && ['1min', '5min', '15min', '30min'].includes(selectedInterval)) {
            setSelectedInterval('1hour');
            return;
        }

        applyTimeRange(range);
    }, [applyTimeRange, selectedInterval]);

    // ============================================================================
    // Calculate indicators in worker
    // ============================================================================

    const allActiveIndicators = useMemo(() => {
        const indicators: IndicatorType[] = [];
        if (activeOverlays.includes('sma200')) indicators.push('sma200');
        if (activeOverlays.includes('bb')) indicators.push('bb');
        if (activeOverlays.includes('keltner')) indicators.push('keltner');
        if (activeOverlays.includes('vwap')) indicators.push('vwap');
        activePanels.forEach(panel => {
            if (['rsi', 'macd', 'stoch', 'adx', 'atr', 'bbWidth', 'squeeze', 'obv', 'rvol'].includes(panel)) {
                indicators.push(panel as IndicatorType);
            }
        });
        return indicators;
    }, [activeOverlays, activePanels]);

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

        if (!workerReady || !data.length || allActiveIndicators.length === 0) return;
        calculate(currentTicker, data, allActiveIndicators, selectedInterval);
        lastBarCountRef.current = data.length;
    }, [workerReady, data, data.length, allActiveIndicators, currentTicker, selectedInterval, selectedRange, calculate, clearCache]);

    // ============================================================================
    // Update overlay series from worker results
    // ============================================================================

    useEffect(() => {
        if (!indicatorResults?.overlays || !chartRef.current) return;

        const { overlays } = indicatorResults;

        // SMA 200
        const sma200Series = overlaySeriesRef.current.get('sma200');
        if (sma200Series && overlays.sma200) {
            sma200Series.setData(overlays.sma200.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
        }

        // Bollinger Bands
        if (overlays.bb) {
            const bbUpper = overlaySeriesRef.current.get('bb_upper');
            const bbMiddle = overlaySeriesRef.current.get('bb_middle');
            const bbLower = overlaySeriesRef.current.get('bb_lower');
            if (bbUpper) bbUpper.setData(overlays.bb.upper.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
            if (bbMiddle) bbMiddle.setData(overlays.bb.middle.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
            if (bbLower) bbLower.setData(overlays.bb.lower.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
        }

        // Keltner Channels
        if (overlays.keltner) {
            const kU = overlaySeriesRef.current.get('keltner_upper');
            const kM = overlaySeriesRef.current.get('keltner_middle');
            const kL = overlaySeriesRef.current.get('keltner_lower');
            if (kU) kU.setData(overlays.keltner.upper.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
            if (kM) kM.setData(overlays.keltner.middle.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
            if (kL) kL.setData(overlays.keltner.lower.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
        }

        // VWAP
        const vwapSeries = overlaySeriesRef.current.get('vwap');
        if (vwapSeries && overlays.vwap) {
            vwapSeries.setData(overlays.vwap.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
        }
    }, [indicatorResults, activeOverlays]);

    // ============================================================================
    // Update panel indicator data from worker results
    // ============================================================================

    useEffect(() => {
        if (!indicatorResults?.panels || !chartRef.current) return;

        const { panels } = indicatorResults;

        for (const panelId of activePanels) {
            const panelData = panels[panelId as keyof typeof panels];
            if (!panelData) continue;

            const seriesMap = panelSeriesRef.current.get(panelId);
            if (!seriesMap) continue;

            switch (panelId) {
                case 'rsi':
                case 'atr':
                case 'bbWidth':
                case 'obv': {
                    const mainSeries = seriesMap.get('main');
                    if (mainSeries && Array.isArray(panelData.data)) {
                        mainSeries.setData(panelData.data.map((d: IndicatorDataPoint) => ({
                            time: d.time as UTCTimestamp,
                            value: d.value,
                        })));
                    }
                    break;
                }
                case 'macd': {
                    const macdData = panelData.data as MACDData;
                    if (macdData) {
                        const histSeries = seriesMap.get('histogram');
                        const macdLine = seriesMap.get('macd');
                        const sigLine = seriesMap.get('signal');
                        if (histSeries && macdData.histogram) {
                            histSeries.setData(macdData.histogram.map(d => ({
                                time: d.time as UTCTimestamp,
                                value: d.value,
                                color: d.color || (d.value >= 0 ? INDICATOR_COLORS.macdHistogramUp : INDICATOR_COLORS.macdHistogramDown),
                            })));
                        }
                        if (macdLine && macdData.macd) {
                            macdLine.setData(macdData.macd.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                        }
                        if (sigLine && macdData.signal) {
                            sigLine.setData(macdData.signal.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                        }
                    }
                    break;
                }
                case 'stoch': {
                    const stochData = panelData.data as StochData;
                    if (stochData) {
                        const kSeries = seriesMap.get('k');
                        const dSeries = seriesMap.get('d');
                        if (kSeries && stochData.k) kSeries.setData(stochData.k.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                        if (dSeries && stochData.d) dSeries.setData(stochData.d.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                    }
                    break;
                }
                case 'adx': {
                    const adxData = panelData.data as ADXData;
                    if (adxData) {
                        const adxS = seriesMap.get('adx');
                        const pdiS = seriesMap.get('pdi');
                        const mdiS = seriesMap.get('mdi');
                        if (adxS && adxData.adx) adxS.setData(adxData.adx.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                        if (pdiS && adxData.pdi) pdiS.setData(adxData.pdi.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                        if (mdiS && adxData.mdi) mdiS.setData(adxData.mdi.map(d => ({ time: d.time as UTCTimestamp, value: d.value })));
                    }
                    break;
                }
                case 'squeeze': {
                    const sqSeries = seriesMap.get('main');
                    if (sqSeries && Array.isArray(panelData.data)) {
                        const squeezeArr = panelData.data as unknown as SqueezeData[];
                        sqSeries.setData(squeezeArr.map(d => ({
                            time: d.time as UTCTimestamp,
                            value: d.value,
                            color: d.color || (d.squeezeOn ? INDICATOR_COLORS.squeezeOn : INDICATOR_COLORS.squeezeOff),
                        })));
                    }
                    break;
                }
                case 'rvol': {
                    const rvolSeries = seriesMap.get('main');
                    if (rvolSeries && Array.isArray(panelData.data)) {
                        rvolSeries.setData(panelData.data.map((d: IndicatorDataPoint) => ({
                            time: d.time as UTCTimestamp,
                            value: d.value,
                            color: d.color,
                        })));
                    }
                    break;
                }
            }
        }
    }, [indicatorResults, activePanels]);

    // ============================================================================
    // Ticker change handlers
    // ============================================================================

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

    // Fullscreen resize
    useEffect(() => {
        const forceChartResize = () => {
            if (chartRef.current && containerRef.current) {
                const width = containerRef.current.clientWidth;
                const height = containerRef.current.clientHeight;
                if (width > 0 && height > 0) {
                    chartRef.current.applyOptions({ width, height });
                    chartRef.current.timeScale().applyOptions({ rightOffset: 5, barSpacing: 8 });
                }
            }
        };

        const handleFullscreenChange = () => {
            const isNowFullscreen = !!document.fullscreenElement;
            setIsFullscreen(isNowFullscreen);
            setTimeout(forceChartResize, 50);
            setTimeout(forceChartResize, 200);
            setTimeout(forceChartResize, 500);
        };

        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
    }, []);

    // Display data
    const displayBar = hoveredBar || (data.length > 0 ? data[data.length - 1] : null);
    const prevBar = data.length > 1 ? data[data.length - 2] : null;
    const priceChange = displayBar && prevBar ? displayBar.close - prevBar.close : 0;
    const priceChangePercent = displayBar && prevBar && prevBar.close !== 0
        ? ((priceChange / prevBar.close) * 100)
        : 0;
    const isPositive = priceChange >= 0;

    // Active indicator count for badge
    const activeIndicatorCount = (showMA ? 1 : 0) + (showEMA ? 1 : 0) + activeOverlays.length + activePanels.length + (showVolume ? 1 : 0) + (showNewsMarkers ? 1 : 0);

    // ============================================================================
    // RENDER
    // ============================================================================

    return (
        <div className="h-full flex flex-col bg-white border border-slate-200 rounded-lg overflow-hidden">
            {/* Minimal Header (for Description) */}
            {minimal ? (
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-600 tracking-wide">PRICE CHART</span>
                        <span className="text-[10px] text-slate-400">1 Year</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {onOpenChart && (
                            <button onClick={onOpenChart} className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors" title="Open Chart Window">
                                G <span className="font-normal">&gt;</span>
                            </button>
                        )}
                        {onOpenNews && (
                            <button onClick={onOpenNews} className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors" title="Open News Window">
                                N <span className="font-normal">&gt;</span>
                            </button>
                        )}
                    </div>
                </div>
            ) : (
                /* ===== TradingView-style Header ===== */
                <div className="flex items-center gap-1 px-1.5 py-[3px] border-b border-slate-200 bg-slate-50/80 text-[11px]" style={{ fontFamily }}>
                    {/* Ticker */}
                    <form onSubmit={handleTickerChange} className="flex items-center">
                        <TickerSearch
                            ref={tickerSearchRef}
                            value={inputValue}
                            onChange={setInputValue}
                            onSelect={handleTickerSelect}
                            placeholder="Ticker"
                            className="w-16"
                            autoFocus={false}
                        />
                    </form>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Intervals */}
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
                    <div className="relative">
                        <button onClick={() => setShowIntervalDropdown(!showIntervalDropdown)} className="px-0.5 py-0.5 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100">
                            <ChevronDown className="w-3 h-3" />
                        </button>
                        {showIntervalDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIntervalDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded shadow-lg z-50 min-w-[80px]">
                                    {INTERVALS.map((int) => (
                                        <button key={int.interval} onClick={() => { setSelectedInterval(int.interval); setShowIntervalDropdown(false); }}
                                            className={`w-full px-2 py-1 text-left text-[10px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600 font-medium' : 'text-slate-600'}`}>
                                            {int.label}
                                        </button>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Indicators button (opens dropdown) */}
                    <div className="relative">
                        <button
                            onClick={() => setShowIndicatorDropdown(!showIndicatorDropdown)}
                            className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium transition-all ${showIndicatorDropdown ? 'bg-blue-50 text-blue-600' : activeIndicatorCount > 0 ? 'text-blue-600 hover:bg-blue-50' : 'text-slate-500 hover:bg-slate-100'}`}
                        >
                            <Activity className="w-3 h-3" />
                            <span>Indicators</span>
                            {activeIndicatorCount > 0 && (
                                <span className="text-[8px] bg-blue-600 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center">{activeIndicatorCount}</span>
                            )}
                        </button>

                        {showIndicatorDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIndicatorDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-xl z-50 min-w-[180px] max-h-[420px] overflow-y-auto">

                                    <div className="px-2 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-b border-slate-100 sticky top-0">Overlays</div>

                                    <button onClick={() => setShowMA(!showMA)} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${showMA ? 'text-amber-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0" style={{ background: CHART_COLORS.ma20 }}></span>
                                        <span className="flex-1 text-left">SMA 20 / 50</span>
                                        {showMA && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>
                                    <button onClick={() => toggleOverlay('sma200')} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${activeOverlays.includes('sma200') ? 'text-red-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0 bg-red-500"></span>
                                        <span className="flex-1 text-left">SMA 200</span>
                                        {activeOverlays.includes('sma200') && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>
                                    <button onClick={() => setShowEMA(!showEMA)} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${showEMA ? 'text-pink-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0" style={{ background: CHART_COLORS.ema12 }}></span>
                                        <span className="flex-1 text-left">EMA 12 / 26</span>
                                        {showEMA && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>
                                    <button onClick={() => toggleOverlay('bb')} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${activeOverlays.includes('bb') ? 'text-blue-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0 bg-blue-500"></span>
                                        <span className="flex-1 text-left">Bollinger Bands</span>
                                        {activeOverlays.includes('bb') && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>
                                    <button onClick={() => toggleOverlay('keltner')} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${activeOverlays.includes('keltner') ? 'text-teal-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0 bg-teal-500"></span>
                                        <span className="flex-1 text-left">Keltner Channels</span>
                                        {activeOverlays.includes('keltner') && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>
                                    <button onClick={() => toggleOverlay('vwap')} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${activeOverlays.includes('vwap') ? 'text-orange-600' : 'text-slate-600'}`}>
                                        <span className="w-2.5 h-0.5 rounded flex-shrink-0 bg-orange-500"></span>
                                        <span className="flex-1 text-left">VWAP</span>
                                        {activeOverlays.includes('vwap') && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>

                                    <div className="px-2 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Oscillators</div>

                                    {[
                                        { id: 'rsi', label: 'RSI (14)', color: 'bg-violet-500' },
                                        { id: 'macd', label: 'MACD', color: 'bg-blue-500' },
                                        { id: 'stoch', label: 'Stochastic', color: 'bg-blue-400' },
                                        { id: 'adx', label: 'ADX / DMI', color: 'bg-violet-400' },
                                    ].map(p => (
                                        <button key={p.id} onClick={() => togglePanel(p.id)} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${activePanels.includes(p.id) ? 'text-blue-600' : 'text-slate-600'}`}>
                                            <span className={`w-2.5 h-0.5 rounded flex-shrink-0 ${p.color}`}></span>
                                            <span className="flex-1 text-left">{p.label}</span>
                                            {activePanels.includes(p.id) && <span className="text-emerald-500 text-[9px]">✓</span>}
                                        </button>
                                    ))}

                                    <div className="px-2 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Volatility & Volume</div>

                                    {[
                                        { id: 'atr', label: 'ATR (14)', color: 'bg-indigo-500', toggle: () => togglePanel('atr'), active: activePanels.includes('atr') },
                                        { id: 'squeeze', label: 'TTM Squeeze', color: 'bg-red-500', toggle: () => togglePanel('squeeze'), active: activePanels.includes('squeeze') },
                                        { id: 'volume', label: 'Volume', color: 'bg-emerald-500', toggle: () => setShowVolume(!showVolume), active: showVolume },
                                        { id: 'obv', label: 'OBV', color: 'bg-blue-500', toggle: () => togglePanel('obv'), active: activePanels.includes('obv') },
                                        { id: 'rvol', label: 'RVOL', color: 'bg-emerald-400', toggle: () => togglePanel('rvol'), active: activePanels.includes('rvol') },
                                    ].map(p => (
                                        <button key={p.id} onClick={p.toggle} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${p.active ? 'text-blue-600' : 'text-slate-600'}`}>
                                            <span className={`w-2.5 h-0.5 rounded flex-shrink-0 ${p.color}`}></span>
                                            <span className="flex-1 text-left">{p.label}</span>
                                            {p.active && <span className="text-emerald-500 text-[9px]">✓</span>}
                                        </button>
                                    ))}

                                    <div className="border-t border-slate-100" />
                                    <button onClick={() => setShowNewsMarkers(!showNewsMarkers)} className={`w-full flex items-center gap-2 px-2 py-1.5 text-[10px] hover:bg-slate-50 ${showNewsMarkers ? 'text-amber-600' : 'text-slate-600'}`}>
                                        <Newspaper className="w-3 h-3 flex-shrink-0" />
                                        <span className="flex-1 text-left">News Markers</span>
                                        {tickerNews.length > 0 && <span className="text-[8px] text-slate-400">{tickerNews.length}</span>}
                                        {showNewsMarkers && <span className="text-emerald-500 text-[9px]">✓</span>}
                                    </button>

                                    {indicatorsLoading && (
                                        <div className="px-2 py-1.5 text-[9px] text-blue-500 bg-blue-50/50 border-t border-slate-100 flex items-center gap-1">
                                            <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                                            Calculating...
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Range buttons */}
                    {['1M', '3M', '1Y', 'ALL'].map((r) => {
                        const range = TIME_RANGES.find(tr => tr.id === r);
                        if (!range) return null;
                        return (
                            <button key={range.id} onClick={() => handleRangeChange(range.id)}
                                className={`px-1 py-0.5 rounded text-[9px] font-medium ${selectedRange === range.id ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}>
                                {range.label}
                            </button>
                        );
                    })}

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Price display */}
                    {displayBar && (
                        <div className="flex items-center gap-1.5 mr-1">
                            <span className="font-bold text-slate-800 text-sm">${formatPrice(displayBar.close)}</span>
                            <span className={`text-[10px] font-medium px-1 rounded ${isPositive ? 'text-emerald-600 bg-emerald-50' : 'text-red-600 bg-red-50'}`}>
                                {isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%
                            </span>
                            {showLiveIndicator && (
                                <span className="flex items-center gap-0.5 text-[9px] font-medium text-red-500 animate-pulse">
                                    <Radio className="w-2.5 h-2.5" />
                                    LIVE
                                </span>
                            )}
                        </div>
                    )}

                    {/* Actions */}
                    <button onClick={refetch} disabled={loading} className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 disabled:opacity-50" title="Refresh">
                        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                    <button onClick={toggleFullscreen} className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100" title="Fullscreen">
                        {isFullscreen ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
                    </button>
                </div>
            )}

            {/* ===== Main area: Left Toolbar + Chart ===== */}
            <div className="flex-1 min-h-0 flex bg-white">
                {/* Left Toolbar — slim, icon-only, TradingView-style */}
                {!minimal && (
                    <div className="w-[30px] flex-shrink-0 border-r border-slate-100 flex flex-col items-center py-1 gap-0.5">
                        {/* Cursor / Select */}
                        <button
                            onClick={() => setActiveTool('none')}
                            className={`w-6 h-6 flex items-center justify-center rounded transition-colors ${activeTool === 'none' ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                            title="Select (Esc)"
                        >
                            <MousePointer className="w-3.5 h-3.5" />
                        </button>

                        {/* Horizontal Line */}
                        <button
                            onClick={() => setActiveTool(activeTool === 'horizontal_line' ? 'none' : 'horizontal_line')}
                            className={`w-6 h-6 flex items-center justify-center rounded transition-colors ${activeTool === 'horizontal_line' ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                            title="Horizontal Line (H)"
                        >
                            <Minus className="w-3.5 h-3.5" />
                        </button>

                        {/* Clear drawings */}
                        {drawings.length > 0 && (
                            <button
                                onClick={clearAllDrawings}
                                className="w-6 h-6 flex items-center justify-center rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                                title={`Clear all (${drawings.length})`}
                            >
                                <Trash2 className="w-3 h-3" />
                            </button>
                        )}

                        <div className="flex-1" />

                        {/* Zoom controls at bottom */}
                        <button onClick={zoomIn} className="w-6 h-6 flex items-center justify-center rounded text-slate-400 hover:text-slate-600 hover:bg-slate-50" title="Zoom In">
                            <ZoomIn className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={zoomOut} className="w-6 h-6 flex items-center justify-center rounded text-slate-400 hover:text-slate-600 hover:bg-slate-50" title="Zoom Out">
                            <ZoomOut className="w-3.5 h-3.5" />
                        </button>
                    </div>
                )}

                {/* Chart area — takes ALL remaining space */}
                <div className="flex-1 min-w-0 min-h-0 overflow-hidden relative">
                    {/* Indicator legend overlay (top-left, over the chart like TV) */}
                    {!minimal && (showMA || showEMA || activeOverlays.length > 0) && (
                        <div className="absolute top-1 left-1 z-10 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] pointer-events-none opacity-70">
                            {showMA && (
                                <>
                                    <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded" style={{ background: CHART_COLORS.ma20 }}></span><span className="text-slate-500">MA20</span></span>
                                    <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded" style={{ background: CHART_COLORS.ma50 }}></span><span className="text-slate-500">MA50</span></span>
                                </>
                            )}
                            {showEMA && (
                                <>
                                    <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded" style={{ background: CHART_COLORS.ema12 }}></span><span className="text-slate-500">EMA12</span></span>
                                    <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded" style={{ background: CHART_COLORS.ema26 }}></span><span className="text-slate-500">EMA26</span></span>
                                </>
                            )}
                            {activeOverlays.includes('sma200') && <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded bg-red-500"></span><span className="text-slate-500">SMA200</span></span>}
                            {activeOverlays.includes('bb') && <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded bg-blue-500"></span><span className="text-slate-500">BB</span></span>}
                            {activeOverlays.includes('keltner') && <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded bg-teal-500"></span><span className="text-slate-500">KC</span></span>}
                            {activeOverlays.includes('vwap') && <span className="flex items-center gap-0.5"><span className="w-2.5 h-[2px] rounded bg-orange-500"></span><span className="text-slate-500">VWAP</span></span>}
                        </div>
                    )}

                    {/* "Go to realtime" button — shown when user scrolls away */}
                    {isScrolledAway && isLive && (
                        <button
                            onClick={() => chartRef.current?.timeScale().scrollToRealTime()}
                            className="absolute bottom-3 right-14 z-20 flex items-center gap-1 px-2 py-1 bg-blue-600 text-white text-[10px] font-medium rounded shadow-lg hover:bg-blue-700 transition-colors"
                        >
                            <Radio className="w-2.5 h-2.5" />
                            Realtime
                        </button>
                    )}

                    {/* Drag overlay */}
                    {dragState.active && (
                        <div className="absolute inset-0 z-50" style={{ cursor: 'ns-resize' }} onMouseMove={handleDragMove} onMouseUp={handleDragEnd} onMouseLeave={handleDragEnd} />
                    )}

                    {/* Drawing mode indicator */}
                    {isDrawing && (
                        <div className="absolute top-1 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-2 py-1 bg-blue-500 text-white text-[10px] font-medium rounded shadow-lg">
                            <span>Click to place line</span>
                            <button onClick={cancelDrawing} className="hover:bg-blue-600 rounded px-1">✕</button>
                        </div>
                    )}

                    {/* Edit popup */}
                    {editPopup.visible && editingDrawing && (
                        <>
                            <div className="absolute inset-0 z-40" onClick={closeEditPopup} />
                            <div
                                className="absolute z-50 bg-white rounded-lg shadow-xl border border-slate-200 p-3 min-w-[160px]"
                                style={{
                                    left: Math.min(editPopup.x, (containerRef.current?.clientWidth || 300) - 180),
                                    top: Math.min(editPopup.y, (containerRef.current?.clientHeight || 200) - 150),
                                }}
                            >
                                <div className="text-xs font-semibold text-slate-700 mb-2 pb-2 border-b border-slate-100">Edit line</div>
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Color</div>
                                    <div className="flex gap-1.5">
                                        {drawingColors.map(color => (
                                            <button key={color} onClick={() => handleEditColor(color)}
                                                className={`w-5 h-5 rounded-full transition-all ${editingDrawing.color === color ? 'ring-2 ring-offset-1 ring-slate-400 scale-110' : 'hover:scale-110'}`}
                                                style={{ backgroundColor: color }} />
                                        ))}
                                    </div>
                                </div>
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Width</div>
                                    <div className="flex gap-1">
                                        {[1, 2, 3, 4].map(width => (
                                            <button key={width} onClick={() => handleEditLineWidth(width)}
                                                className={`flex-1 h-6 flex items-center justify-center rounded border transition-all ${editingDrawing.lineWidth === width ? 'bg-blue-50 border-blue-300' : 'border-slate-200 hover:bg-slate-50'}`}>
                                                <div className="rounded-full" style={{ width: '16px', height: `${width}px`, backgroundColor: editingDrawing.color }} />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex gap-2 pt-2 border-t border-slate-100">
                                    <button onClick={handleEditDelete} className="flex-1 px-2 py-1 text-[10px] font-medium text-red-600 bg-red-50 rounded hover:bg-red-100">Delete</button>
                                    <button onClick={closeEditPopup} className="flex-1 px-2 py-1 text-[10px] font-medium text-slate-600 bg-slate-100 rounded hover:bg-slate-200">Close</button>
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
                                <button onClick={refetch} className="px-4 py-1.5 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700 transition-colors">Retry</button>
                            </div>
                        </div>
                    )}

                    <div
                        ref={containerRef}
                        className="h-full w-full"
                        onMouseDown={activeTool === 'none' && !minimal ? handleDragStart : undefined}
                        onContextMenu={!minimal ? handleChartContextMenu : undefined}
                        style={{
                            cursor: hoveredDrawingId && activeTool === 'none' ? 'ns-resize' : isDrawing ? 'crosshair' : 'default'
                        }}
                    />
                    {ctxMenu.visible && (
                        <ChartContextMenu
                            state={ctxMenu}
                            ticker={currentTicker}
                            interval={selectedInterval}
                            range={selectedRange}
                            data={data}
                            indicatorResults={indicatorResults}
                            drawings={drawings}
                            activeOverlays={activeOverlays}
                            activePanels={activePanels}
                            showMA={showMA}
                            showEMA={showEMA}
                            chartApi={chartRef.current}
                            onClose={() => setCtxMenu(prev => ({ ...prev, visible: false }))}
                        />
                    )}
                </div>
            </div>

            {/* Footer — compact OHLCV */}
            {displayBar && !minimal && (
                <div className="flex items-center justify-between px-2 py-0.5 border-t border-slate-100 text-[9px]" style={{ fontFamily }}>
                    <div className="flex items-center gap-2 font-mono text-slate-500">
                        <span>O:<span className="text-slate-700">{formatPrice(displayBar.open)}</span></span>
                        <span>H:<span className="text-emerald-600">{formatPrice(displayBar.high)}</span></span>
                        <span>L:<span className="text-red-500">{formatPrice(displayBar.low)}</span></span>
                        <span>C:<span className="text-slate-700">{formatPrice(displayBar.close)}</span></span>
                        <span>V:<span className="text-slate-700">{formatVolume(displayBar.volume)}</span></span>
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
