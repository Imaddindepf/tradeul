'use client';

import { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
    createChart,
    TickMarkType,
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
    type LogicalRange,
} from 'lightweight-charts';
import { RefreshCw, Maximize2, Minimize2, BarChart3, Radio, Newspaper, ExternalLink, ChevronDown, LineChart, Waves, X, Sparkles, Bot } from 'lucide-react';
import { useLiveChartData, type ChartBar as HookChartBar } from '@/hooks/useLiveChartData';
import { useChartDrawings } from '@/hooks/useChartDrawings';
import { useLinkGroupSubscription } from '@/hooks/useLinkGroup';
import type { Drawing as DrawingType } from '@/hooks/useChartDrawings';
import { TrendlinePrimitive } from './primitives/TrendlinePrimitive';
import { HorizontalLinePrimitive } from './primitives/HorizontalLinePrimitive';
import { VerticalLinePrimitive } from './primitives/VerticalLinePrimitive';
import { RayPrimitive } from './primitives/RayPrimitive';
import { ExtendedLinePrimitive } from './primitives/ExtendedLinePrimitive';
import { ParallelChannelPrimitive } from './primitives/ParallelChannelPrimitive';
import { FibonacciPrimitive } from './primitives/FibonacciPrimitive';
import { RectanglePrimitive } from './primitives/RectanglePrimitive';
import { CirclePrimitive } from './primitives/CirclePrimitive';
import { TrianglePrimitive } from './primitives/TrianglePrimitive';
import { MeasurePrimitive } from './primitives/MeasurePrimitive';
import { TentativePrimitive } from './primitives/TentativePrimitive';
import { timeToPixelX } from './primitives/coordinateUtils';
import { EarningsMarkerPrimitive } from './primitives/EarningsMarkerPrimitive';
import type { ISeriesPrimitive } from 'lightweight-charts';
import { useIndicatorWorker } from '@/hooks/useIndicatorWorker';
import { ChartToolbar, HeaderDrawingTools, IndicatorsIcon } from './ChartToolbar';
import { IndicatorSettingsDialog } from './IndicatorSettingsDialog';
import { getSettingsForIndicator, INDICATOR_TYPE_DEFAULTS, OVERLAY_TYPES, PANEL_TYPES, getNextColor, getInstanceLabel, migrateOldIndicatorState, type IndicatorInstance } from './constants';
import type { IndicatorDataPoint, WorkerIndicatorConfig, IndicatorResults } from '@/hooks/useIndicatorWorker';
import { ChartNewsPopup } from './ChartNewsPopup';
import { useArticlesByTicker } from '@/stores/useNewsStore';
import { useFloatingWindow, useWindowState, useCurrentWindowId } from '@/contexts/FloatingWindowContext';
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
import { IncrementalIndicatorEngine, type IndicatorValue } from './IncrementalIndicatorEngine';
import type { ChartContext, ChartSnapshot } from '@/components/ai-agent/types';
// IndicatorResults imported above
import type { Drawing } from '@/hooks/useChartDrawings';

// ============================================================================
// Session Background Colors (pre-market / post-market)
// ============================================================================

const SESSION_COLORS = {
    preMarket: 'rgba(255, 247, 235, 0.85)',   // warm amber #fff7eb
    postMarket: 'rgba(238, 243, 255, 0.85)',   // cool blue #eef3ff
    regular: 'rgba(0, 0, 0, 0)',               // transparent
};

function getSessionColor(barTimeSeconds: number): string {
    const date = new Date(barTimeSeconds * 1000);
    const etParts = date.toLocaleString('en-US', {
        timeZone: 'America/New_York',
        hour: 'numeric',
        minute: 'numeric',
        hour12: false,
    });
    const [hStr, mStr] = etParts.split(':');
    const totalMinutes = parseInt(hStr) * 60 + parseInt(mStr);

    if (totalMinutes >= 240 && totalMinutes < 570) return SESSION_COLORS.preMarket;
    if (totalMinutes >= 960 && totalMinutes < 1200) return SESSION_COLORS.postMarket;
    return SESSION_COLORS.regular;
}

// ============================================================================
// Chart AI Snapshot Builder
// ============================================================================

function buildChartSnapshot(
    data: ChartBar[],
    indicatorResults: IndicatorResults | null,
    drawings: Drawing[],
    activeIndicators: IndicatorInstance[],
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
        if (!arr?.length || !rightTime) return undefined;
        const pt = arr.find(p => p.time === rightTime);
        if (pt) return pt.value;
        // Fallback: use the last computed value (closest to right edge)
        return arr[arr.length - 1]?.value;
    };

    const trajectory = (arr?: { time: number; value: number }[], count = 5) => {
        if (!arr || !rightTime) return undefined;
        return arr.filter(p => p.time <= rightTime).slice(-count).map(d => d.value);
    };

    const indicators: ChartSnapshot['indicators'] = {};

    if (indicatorResults) {
        // Dynamic instance-based extraction
        for (const [instId, result] of Object.entries(indicatorResults)) {
            const { type, data: rData } = result as any;
            const label = instId; // e.g. 'sma_1', 'rsi_2'
            if (type === 'sma' || type === 'ema' || type === 'vwap' || type === 'atr' || type === 'obv') {
                if (Array.isArray(rData)) indicators[label] = findValue(rData);
            } else if (type === 'bb' || type === 'keltner') {
                if (rData?.upper) indicators[label + '_upper'] = findValue(rData.upper);
                if (rData?.middle) indicators[label + '_mid'] = findValue(rData.middle);
                if (rData?.lower) indicators[label + '_lower'] = findValue(rData.lower);
            } else if (type === 'rsi') {
                if (Array.isArray(rData)) {
                    indicators[label] = findValue(rData);
                    indicators[label + '_trajectory'] = trajectory(rData);
                }
            } else if (type === 'macd') {
                if (rData?.macd) indicators[label + '_line'] = findValue(rData.macd);
                if (rData?.signal) indicators[label + '_signal'] = findValue(rData.signal);
                if (rData?.histogram) {
                    indicators[label + '_histogram'] = findValue(rData.histogram);
                    indicators[label + '_hist_trajectory'] = trajectory(rData.histogram);
                }
            } else if (type === 'stoch') {
                if (rData?.k) indicators[label + '_k'] = findValue(rData.k);
                if (rData?.d) indicators[label + '_d'] = findValue(rData.d);
            } else if (type === 'adx') {
                if (rData?.adx) indicators[label + '_adx'] = findValue(rData.adx);
                if (rData?.pdi) indicators[label + '_pdi'] = findValue(rData.pdi);
                if (rData?.mdi) indicators[label + '_mdi'] = findValue(rData.mdi);
            }
        }
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

    // Strip undefined/NaN values so JSON.stringify preserves all computed indicators
    const cleanIndicators: ChartSnapshot['indicators'] = {};
    for (const [k, v] of Object.entries(indicators)) {
        if (v !== undefined && v !== null && (typeof v !== 'number' || !isNaN(v))) {
            (cleanIndicators as Record<string, unknown>)[k] = v;
        }
    }

    const levels = drawings
        .filter((d): d is Drawing & { type: 'horizontal_line' } => d.type === 'horizontal_line')
        .map(d => ({ price: d.price, label: d.label }));

    const isHistorical = toIdx < data.length - 3;

    return {
        recentBars: recentBars.map(b => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })),
        indicators: cleanIndicators,
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
    state, ticker, interval, range, data, indicatorResults, drawings, activeIndicators, chartApi, onClose,
}: {
    state: ContextMenuState;
    ticker: string;
    interval: string;
    range: string;
    data: ChartBar[];
    indicatorResults: IndicatorResults | null;
    drawings: Drawing[];
    activeIndicators: IndicatorInstance[];
    chartApi: IChartApi | null;
    onClose: () => void;
}) {
    if (!state.visible) return null;

    const dispatchChartAsk = (prompt: string) => {
        const snapshot = buildChartSnapshot(data, indicatorResults, drawings, activeIndicators, chartApi);
        const activeIndicatorNames: string[] = activeIndicators.map(i => {
            const defaults = INDICATOR_TYPE_DEFAULTS[i.type];
            return defaults ? `${defaults.name}${i.params.length ? ' ' + i.params.length : ''}` : i.type.toUpperCase();
        });

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

    const candleDateISO = state.candle
        ? new Date(state.candle.time * 1000).toISOString().slice(0, 10)
        : '';

    const items = state.candle
        ? [
            { label: 'Analyze this candle', prompt: `Analyze the candle at ${candleDateISO} for ${ticker}` },
            { label: 'Why did this move?', prompt: `Why did ${ticker} move like this on ${candleDateISO}?` },
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

    // Portal: render TickerSearch in the floating window header instead of chart header
    const windowId = useCurrentWindowId?.();
    const [headerPortalTarget, setHeaderPortalTarget] = useState<HTMLElement | null>(null);

    useEffect(() => {
        if (windowId && !minimal) {
            const el = document.getElementById(`window-header-extra-${windowId}`);
            if (el) {
                setHeaderPortalTarget(el);
            }
        }
    }, [windowId, minimal]);

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
    // Dynamic indicator instances
    const [indicators, setIndicators] = useState<IndicatorInstance[]>(() => {
        if (windowState.indicators && windowState.indicators.length > 0) return windowState.indicators;
        if (windowState.showMA || windowState.showEMA || windowState.activeOverlays?.length || windowState.activePanels?.length) {
            return migrateOldIndicatorState(windowState);
        }
        return [];
    });
    const nextInstanceIdRef = useRef(windowState.nextInstanceId || 1);
    const [showVolume, setShowVolume] = useState(windowState.showVolume ?? true);
    const [showNewsMarkers, setShowNewsMarkers] = useState(false);
    const [showEarningsMarkers, setShowEarningsMarkers] = useState(true);
    const [earningsDates, setEarningsDates] = useState<{date: string; time_slot: string}[]>([]);
    const [tickerMeta, setTickerMeta] = useState<{ company_name: string; exchange: string; icon_url: string } | null>(null);
    const [legendExpanded, setLegendExpanded] = useState(true);
    const [hoveredBar, setHoveredBar] = useState<ChartBar | null>(null);

    // === INDICADORES AVANZADOS (Worker-based) ===
    const { calculate, clearCache, results: indicatorResults, isCalculating: indicatorsLoading, isReady: workerReady } = useIndicatorWorker();

    // Derived overlay/panel lists from indicators
    const overlayInstances = useMemo(() => indicators.filter(i => i.visible && OVERLAY_TYPES.has(i.type)), [indicators]);
    const panelInstances = useMemo(() => indicators.filter(i => i.visible && PANEL_TYPES.has(i.type)), [indicators]);

    // Unified indicator series ref: Map<instanceId, Map<subKey, ISeriesApi>>
    const indicatorSeriesRef = useRef<Map<string, Map<string, ISeriesApi<any>>>>(new Map());
    const panelPaneIndexRef = useRef<Map<string, number>>(new Map());
    // Keep overlaySeriesRef as alias for backward compat in context menu etc
    const overlaySeriesRef = indicatorSeriesRef;
    const panelSeriesRef = indicatorSeriesRef;

    // Incremental indicator engine for real-time updates
    const engineRef = useRef<IncrementalIndicatorEngine | null>(null);

    // Watermark ref for updates
    const watermarkRef = useRef<any>(null);

    // Markers primitive ref (v5)
    const newsMarkersRef = useRef<any>(null);

    // Price overlay with countdown timer (TradingView-style)
    const priceOverlayRef = useRef<HTMLDivElement>(null);
    const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const lastPriceInfoRef = useRef<{ close: number; open: number }>({ close: 0, open: 0 });

    // Add a new indicator instance
    const addIndicator = useCallback((type: string) => {
        const id = `${type}_${nextInstanceIdRef.current++}`;
        const config = INDICATOR_TYPE_DEFAULTS[type];
        if (!config) return;
        const color = getNextColor(indicators);
        const newInst: IndicatorInstance = {
            id, type,
            params: { ...config.defaultParams },
            styles: { ...config.defaultStyles, color },
            visible: true,
        };
        setIndicators(prev => [...prev, newInst]);
        setShowIndicatorDropdown(false);
    }, [indicators]);

    // Dropdown states
    const [showIntervalDropdown, setShowIntervalDropdown] = useState(false);
    const [showIndicatorDropdown, setShowIndicatorDropdown] = useState(false);
    const indicatorDropdownRef = useRef<HTMLDivElement>(null);

    // Close indicator dropdown on click outside
    useEffect(() => {
        if (!showIndicatorDropdown) return;
        const handleClick = (e: MouseEvent) => {
            if (indicatorDropdownRef.current && !indicatorDropdownRef.current.contains(e.target as Node)) {
                setShowIndicatorDropdown(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [showIndicatorDropdown]);
    const [indicatorSettingsOpen, setIndicatorSettingsOpen] = useState<string | null>(null);
    const [indicatorSettingsPos, setIndicatorSettingsPos] = useState<{ x: number; y: number } | undefined>();
    const [selectedIndicator, setSelectedIndicator] = useState<string | null>(null);
    const [showToolsDropdown, setShowToolsDropdown] = useState(false);

    const openIndicatorSettings = useCallback((indicatorId: string, event?: React.MouseEvent) => {
        const pos = event ? { x: Math.min(event.clientX, window.innerWidth - 340), y: Math.min(event.clientY, window.innerHeight - 460) } : undefined;
        setIndicatorSettingsPos(pos);
        setIndicatorSettingsOpen(indicatorId);
    }, []);

    const removeIndicator = useCallback((instanceId: string) => {
        if (instanceId === 'volume') { setShowVolume(false); return; }
        setIndicators(prev => prev.filter(i => i.id !== instanceId));
        setSelectedIndicator(null);
    }, []);

    const onApplyIndicatorSettings = useCallback((id: string, settings: { inputs: Record<string, number | string>; styles: Record<string, string | number>; visibility: string[] }) => {
        const { styles, inputs } = settings;
        // Update the instance params/styles in state
        setIndicators(prev => prev.map(inst => {
            if (inst.id !== id) return inst;
            return { ...inst, params: { ...inst.params, ...inputs }, styles: { ...inst.styles, ...styles } };
        }));
        // Apply visual changes immediately to series
        const seriesMap = indicatorSeriesRef.current.get(id);
        if (!seriesMap) return;
        const inst = indicators.find(i => i.id === id);
        if (!inst) return;
        const color = styles.color as string;
        const lw = styles.lineWidth as number;
        const apply = (s: any, c?: string, w?: number) => {
            if (!s) return;
            const opts: any = {};
            if (c) opts.color = c;
            if (w) opts.lineWidth = w;
            try { s.applyOptions(opts); } catch {}
        };
        if (['sma', 'ema', 'vwap', 'atr', 'rsi', 'obv'].includes(inst.type)) {
            apply(seriesMap.get('main'), color, lw);
        } else if (inst.type === 'bb' || inst.type === 'keltner') {
            apply(seriesMap.get('upper'), styles.upperColor as string, lw);
            apply(seriesMap.get('middle'), styles.middleColor as string, lw);
            apply(seriesMap.get('lower'), styles.lowerColor as string, lw);
        } else if (inst.type === 'macd') {
            apply(seriesMap.get('macd'), styles.macdColor as string);
            apply(seriesMap.get('signal'), styles.signalColor as string);
        } else if (inst.type === 'stoch') {
            apply(seriesMap.get('k'), styles.kColor as string);
            apply(seriesMap.get('d'), styles.dColor as string);
        } else if (inst.type === 'adx') {
            apply(seriesMap.get('adx'), styles.adxColor as string);
            apply(seriesMap.get('pdi'), styles.pdiColor as string);
            apply(seriesMap.get('mdi'), styles.mdiColor as string);
        }
    }, [indicators]);

    // Persist state changes
    useEffect(() => {
        updateWindowState({
            ticker: currentTicker,
            interval: selectedInterval,
            range: selectedRange,
            showVolume,
            indicators,
            nextInstanceId: nextInstanceIdRef.current,
        });
    }, [currentTicker, selectedInterval, selectedRange, showVolume, indicators, updateWindowState]);

    const { data, loading, loadingMore, error, hasMore, isLive, refetch, loadMore, registerUpdateHandler } = useLiveChartData(currentTicker, selectedInterval);

    // Refs for scroll-position preservation during loadMore
    const prevDataLengthRef = useRef(0);
    const prevTickerRef = useRef(currentTicker);

    // Stable refs for scroll handler (avoids re-subscribing on every data change)
    const hasMoreRef = useRef(hasMore);
    const loadMoreRef = useRef(loadMore);
    const dataLengthRef = useRef(data.length);
    useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);
    useEffect(() => { loadMoreRef.current = loadMore; }, [loadMore]);
    useEffect(() => { dataLengthRef.current = data.length; }, [data.length]);

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

    // Earnings dates for chart markers
    useEffect(() => {
        if (!currentTicker) return;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${apiUrl}/api/v1/earnings/ticker/${currentTicker.toUpperCase()}/dates?limit=100`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data?.dates) setEarningsDates(data.dates);
            })
            .catch(() => setEarningsDates([]));
    }, [currentTicker]);

    // Fetch ticker metadata (company name, exchange, logo)
    useEffect(() => {
        if (!currentTicker) return;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${apiUrl}/api/v1/ticker/${currentTicker.toUpperCase()}/metadata`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data) {
                    const MIC: Record<string, string> = {
                        XNAS: 'NASDAQ', XNYS: 'NYSE', XASE: 'AMEX',
                        ARCX: 'NYSE ARCA', BATS: 'CBOE', IEXG: 'IEX',
                        XNMS: 'NASDAQ', XNGS: 'NASDAQ', XNCM: 'NASDAQ',
                        OTC: 'OTC', OTCM: 'OTC', OOTC: 'OTC',
                    };
                    setTickerMeta({
                        company_name: data.company_name || currentTicker,
                        exchange: MIC[data.exchange] || data.exchange || '',
                        icon_url: data.icon_url || '',
                    });
                }
            })
            .catch(() => setTickerMeta(null));
    }, [currentTicker]);

    // Floating window for news popup
    const { openWindow, updateWindow } = useFloatingWindow();

    // Update floating window title with current ticker
    // Title is just "Chart" — ticker is already visible in the legend (logo + company name)
    // Ticker is persisted via componentState (useWindowState) for restore on reload
    useEffect(() => {
        if (windowId) {
            updateWindow(windowId, { title: "Chart" });
        }
    }, [windowId, updateWindow]);

    // Drawing tools
    const {
        drawings,
        activeTool,
        isDrawing,
        selectedDrawingId,
        hoveredDrawingId,
        pendingDrawing,
        tentativeEndpoint,
        setActiveTool,
        cancelDrawing,
        handleChartClick,
        updateTentativeEndpoint,
        removeDrawing,
        clearAllDrawings,
        selectDrawing,
        updateHorizontalLinePrice,
        updateVerticalLineTime,
        updateDrawingPoints,
        updateDrawingLineWidth,
        updateDrawingColor,
        startDragging,
        stopDragging,
        findDrawingNearPrice,
        setHoveredDrawing,
        colors: drawingColors,
    } = useChartDrawings(currentTicker);

    // Drawings visibility toggle
    const [drawingsVisible, setDrawingsVisible] = useState(true);
    const toggleDrawingsVisibility = useCallback(() => {
        setDrawingsVisible(prev => !prev);
    }, []);

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

    // Broadcast active chart state so AI agent can auto-include context
    useEffect(() => {
        if (!data || data.length === 0 || !currentTicker) return;
        const detail = {
            ticker: currentTicker,
            interval: selectedInterval,
            range: selectedRange,
            barCount: data.length,
        };
        window.dispatchEvent(new CustomEvent('agent:chart-active', { detail }));
        return () => {
            window.dispatchEvent(new CustomEvent('agent:chart-active', { detail: null }));
        };
    }, [currentTicker, selectedInterval, selectedRange, data?.length]);

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

    // Refs for drawing primitives
    const drawingPrimitivesRef = useRef<Map<string, ISeriesPrimitive<Time>>>(new Map());
    const tentativePrimitiveRef = useRef<TentativePrimitive | null>(null);
    const [chartVersion, setChartVersion] = useState(0);

    // Sorted timestamps for cross-timeframe coordinate interpolation
    const dataTimes = useMemo(() => data.map(d => d.time), [data]);
    const dataTimesRef = useRef(dataTimes);
    dataTimesRef.current = dataTimes;

    // Stable refs — prevents stale closures in LWC event handlers
    const activeToolRef = useRef(activeTool);
    activeToolRef.current = activeTool;
    const handleChartClickRef = useRef(handleChartClick);
    handleChartClickRef.current = handleChartClick;
    const selectDrawingRef = useRef(selectDrawing);
    selectDrawingRef.current = selectDrawing;
    const pendingDrawingRef = useRef(pendingDrawing);
    pendingDrawingRef.current = pendingDrawing;
    const updateTentativeEndpointRef = useRef(updateTentativeEndpoint);
    updateTentativeEndpointRef.current = updateTentativeEndpoint;
    const openEditPopupRef = useRef(openEditPopup);
    openEditPopupRef.current = openEditPopup;
    const findDrawingNearPriceRef = useRef(findDrawingNearPrice);
    findDrawingNearPriceRef.current = findDrawingNearPrice;

    // Sync when windowState.ticker arrives late (store hydration race condition)
    const hasAppliedWindowState = useRef(!!windowState.ticker);
    useEffect(() => {
        if (windowState.ticker && windowState.ticker !== currentTicker && !hasAppliedWindowState.current) {
            hasAppliedWindowState.current = true;
            setCurrentTicker(windowState.ticker);
            setInputValue(windowState.ticker);
        } else if (windowState.ticker) {
            hasAppliedWindowState.current = true;
        }
    }, [windowState.ticker]);

    // Update when external ticker prop changes (e.g. link group, command palette)
    useEffect(() => {
        if (hasAppliedWindowState.current) {
            hasAppliedWindowState.current = false;
            return;
        }
        setCurrentTicker(initialTicker);
        setInputValue(initialTicker);
    }, [initialTicker]);

    // IBKR-style link group: subscribe to ticker broadcasts
    const linkBroadcast = useLinkGroupSubscription();
    useEffect(() => {
        if (linkBroadcast?.ticker) {
            tickerSearchRef.current?.suppressSearch();
            setCurrentTicker(linkBroadcast.ticker.toUpperCase());
            setInputValue(linkBroadcast.ticker.toUpperCase());
        }
    }, [linkBroadcast]);

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
                tickMarkFormatter: (time: number, tickMarkType: TickMarkType) => {
                    const tz = getUserTimezone();
                    const d = new Date(time * 1000);
                    const intraday = selectedInterval !== '1day';

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
                    const intraday = selectedInterval !== '1day';
                    if (intraday) {
                        return d.toLocaleString('en-US', {
                            timeZone: tz, month: 'short', day: 'numeric',
                            hour: '2-digit', minute: '2-digit', hour12: false,
                        }) + ` ${abbrev}`;
                    }
                    return d.toLocaleDateString('en-US', {
                        timeZone: tz, weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
                    });
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
        setChartVersion(v => v + 1);

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
            lastValueVisible: false,
        });
        candleSeriesRef.current = candleSeries;

        // Start countdown timer for candle close (updates HTML overlay)
        if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
        const intervalSec = INTERVAL_SECONDS[selectedInterval] || 0;
        if (intervalSec > 0 && selectedInterval !== '1day') {
            const intervalMs = intervalSec * 1000;
            countdownIntervalRef.current = setInterval(() => {
                const overlay = priceOverlayRef.current;
                const series = candleSeriesRef.current;
                if (!overlay || !series) return;

                const { close, open } = lastPriceInfoRef.current;
                if (close <= 0) { overlay.style.display = 'none'; return; }

                const y = series.priceToCoordinate(close);
                if (y === null) { overlay.style.display = 'none'; return; }

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

                const bgColor = close >= open ? CHART_COLORS.upColor : CHART_COLORS.downColor;
                overlay.style.display = 'flex';
                overlay.style.top = `${y - 15}px`;
                overlay.style.backgroundColor = bgColor;
                // Create child elements once, then just update text
                let priceEl = overlay.querySelector('.p-val') as HTMLElement;
                let cdEl = overlay.querySelector('.p-cd') as HTMLElement;
                if (!priceEl) {
                    priceEl = document.createElement('div');
                    priceEl.className = 'p-val';
                    priceEl.style.cssText = 'font-size:11px;font-weight:600;line-height:1.2';
                    overlay.appendChild(priceEl);
                }
                if (!cdEl) {
                    cdEl = document.createElement('div');
                    cdEl.className = 'p-cd';
                    cdEl.style.cssText = 'font-size:9px;opacity:0.85;line-height:1.2';
                    overlay.appendChild(cdEl);
                }
                priceEl.textContent = close.toFixed(2);
                cdEl.textContent = countdown;
            }, 500);
        }

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
            drawingPrimitivesRef.current.clear();
            tentativePrimitiveRef.current = null;
            indicatorSeriesRef.current.clear();
            panelPaneIndexRef.current.clear();
            newsMarkersRef.current = null;
            lastPriceInfoRef.current = { close: 0, open: 0 };
            if (countdownIntervalRef.current) {
                clearInterval(countdownIntervalRef.current);
                countdownIntervalRef.current = null;
            }
            watermarkRef.current = null;
            sessionBgSeriesRef.current = null;
            earningsPrimitiveRef.current = null;
            chart.remove();
            chartRef.current = null;
            candleSeriesRef.current = null;
            volumeSeriesRef.current = null;
            newsPriceLinesRef.current = [];
            newsTimeMapRef.current.clear();
        };
    }, [currentTicker, fontFamily, selectedInterval]);

    // Auto-load more data when scrolling left + detect if scrolled away from realtime.
    // Subscribed once per chart instance — accesses mutable state via refs to avoid
    // re-subscribing on every data/loadMore change (which caused infinite load loops).
    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;
        const timeScale = chart.timeScale();

        let throttleTimer: ReturnType<typeof setTimeout> | null = null;
        const THROTTLE_MS = 100;

        const handleVisibleRangeChange = () => {
            if (throttleTimer) return;
            throttleTimer = setTimeout(() => {
                throttleTimer = null;

                const logicalRange = timeScale.getVisibleLogicalRange();
                if (!logicalRange) return;

                if (hasMoreRef.current && candleSeriesRef.current) {
                    const barsInfo = candleSeriesRef.current.barsInLogicalRange(logicalRange);
                    if (barsInfo !== null && barsInfo.barsBefore < 10) {
                        loadMoreRef.current();
                    }
                }

                const totalBars = dataLengthRef.current;
                const isNearRealtime = logicalRange.to >= totalBars - 3;
                setIsScrolledAway(!isNearRealtime && totalBars > 0);
            }, THROTTLE_MS);
        };

        timeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        return () => {
            if (throttleTimer) clearTimeout(throttleTimer);
            timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
        };
    }, [currentTicker, selectedInterval]);

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
    // Dynamic indicator series creation/destruction
    // ============================================================================

    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        const activeIds = new Set(indicators.filter(i => i.visible).map(i => i.id));

        // Remove series for deleted/hidden instances
        for (const [id, seriesMap] of indicatorSeriesRef.current) {
            if (!activeIds.has(id)) {
                // Check if it's a panel — remove pane
                const paneIdx = panelPaneIndexRef.current.get(id);
                if (paneIdx !== undefined) {
                    try { chart.removePane(paneIdx); } catch {}
                    panelPaneIndexRef.current.delete(id);
                }
                // Remove series from chart
                for (const [, series] of seriesMap) {
                    try { chart.removeSeries(series); } catch {}
                }
                indicatorSeriesRef.current.delete(id);
            }
        }

        // Create series for new instances
        let nextPaneIndex = 1;
        const usedPanes = new Set(panelPaneIndexRef.current.values());
        while (usedPanes.has(nextPaneIndex)) nextPaneIndex++;

        for (const inst of indicators) {
            if (!inst.visible) continue;
            if (indicatorSeriesRef.current.has(inst.id)) continue;

            const seriesMap = new Map<string, ISeriesApi<any>>();
            const config = INDICATOR_TYPE_DEFAULTS[inst.type];
            if (!config) continue;

            try {
                if (config.category === 'overlay') {
                    // Overlay types → LineSeries on main chart
                    if (inst.type === 'sma' || inst.type === 'ema' || inst.type === 'vwap') {
                        const s = chart.addSeries(LineSeries, {
                            color: (inst.styles.color as string) || config.defaultStyles.color as string,
                            lineWidth: ((inst.styles.lineWidth as number) || config.defaultStyles.lineWidth as number) as 1 | 2 | 3 | 4,
                            priceLineVisible: false,
                            lastValueVisible: true,
                            crosshairMarkerVisible: true,
                            crosshairMarkerRadius: 3,
                        });
                        seriesMap.set('main', s);
                    } else if (inst.type === 'bb' || inst.type === 'keltner') {
                        const uc = (inst.styles.upperColor as string) || config.defaultStyles.upperColor as string;
                        const mc = (inst.styles.middleColor as string) || config.defaultStyles.middleColor as string;
                        const lc = (inst.styles.lowerColor as string) || config.defaultStyles.lowerColor as string;
                        const lw = ((inst.styles.lineWidth as number) || config.defaultStyles.lineWidth as number) as 1 | 2 | 3 | 4;
                        seriesMap.set('upper', chart.addSeries(LineSeries, { color: uc, lineWidth: lw, priceLineVisible: false, lastValueVisible: false }));
                        seriesMap.set('middle', chart.addSeries(LineSeries, { color: mc, lineWidth: lw, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true }));
                        seriesMap.set('lower', chart.addSeries(LineSeries, { color: lc, lineWidth: lw, priceLineVisible: false, lastValueVisible: false }));
                    }
                } else {
                    // Panel types → separate pane
                    while (usedPanes.has(nextPaneIndex)) nextPaneIndex++;

                    switch (inst.type) {
                        case 'rsi': {
                            const s = chart.addSeries(LineSeries, { color: (inst.styles.color as string) || '#8b5cf6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex);
                            s.createPriceLine({ price: 70, color: 'rgba(239,68,68,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            s.createPriceLine({ price: 30, color: 'rgba(16,185,129,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            seriesMap.set('main', s);
                            break;
                        }
                        case 'macd': {
                            const psId = `macd_${nextPaneIndex}`;
                            seriesMap.set('histogram', chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false, priceScaleId: psId }, nextPaneIndex));
                            seriesMap.set('macd', chart.addSeries(LineSeries, { color: (inst.styles.macdColor as string) || '#3b82f6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true, priceScaleId: psId }, nextPaneIndex));
                            seriesMap.set('signal', chart.addSeries(LineSeries, { color: (inst.styles.signalColor as string) || '#f97316', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false, priceScaleId: psId }, nextPaneIndex));
                            break;
                        }
                        case 'stoch': {
                            const kS = chart.addSeries(LineSeries, { color: (inst.styles.kColor as string) || '#3b82f6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex);
                            const dS = chart.addSeries(LineSeries, { color: (inst.styles.dColor as string) || '#f97316', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex);
                            kS.createPriceLine({ price: 80, color: 'rgba(239,68,68,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            kS.createPriceLine({ price: 20, color: 'rgba(16,185,129,0.3)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
                            seriesMap.set('k', kS);
                            seriesMap.set('d', dS);
                            seriesMap.set('main', kS);
                            break;
                        }
                        case 'adx': {
                            seriesMap.set('adx', chart.addSeries(LineSeries, { color: (inst.styles.adxColor as string) || '#8b5cf6', lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            seriesMap.set('pdi', chart.addSeries(LineSeries, { color: (inst.styles.pdiColor as string) || '#10b981', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex));
                            seriesMap.set('mdi', chart.addSeries(LineSeries, { color: (inst.styles.mdiColor as string) || '#ef4444', lineWidth: 1 as 1|2|3|4, priceLineVisible: false, lastValueVisible: false }, nextPaneIndex));
                            seriesMap.set('main', seriesMap.get('adx')!);
                            break;
                        }
                        case 'atr':
                        case 'obv': {
                            seriesMap.set('main', chart.addSeries(LineSeries, { color: (inst.styles.color as string) || config.defaultStyles.color as string, lineWidth: 2 as 1|2|3|4, priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            break;
                        }
                        case 'squeeze':
                        case 'rvol': {
                            seriesMap.set('main', chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: true }, nextPaneIndex));
                            break;
                        }
                    }

                    panelPaneIndexRef.current.set(inst.id, nextPaneIndex);
                    usedPanes.add(nextPaneIndex);
                    try { const pane = chart.panes()[nextPaneIndex]; if (pane) pane.setHeight(100); } catch {}
                    nextPaneIndex++;
                }

                indicatorSeriesRef.current.set(inst.id, seriesMap);
            } catch (err) {
                console.warn('[TradingChart] Failed to create indicator', inst.id, err);
            }
        }
    }, [indicators]);

    // Toggle volume visibility
    useEffect(() => {
        if (volumeSeriesRef.current) {
            volumeSeriesRef.current.applyOptions({ visible: showVolume });
        }
    }, [showVolume]);

    // Overlay creation is now handled by the unified indicators effect above


    // ============================================================================
    // Update chart data
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
        if (!data || data.length === 0) return;

        // Detect if this is a loadMore prepend (not a ticker/interval change)
        const tickerChanged = prevTickerRef.current !== currentTicker;
        if (tickerChanged) {
            prevDataLengthRef.current = 0;
            prevTickerRef.current = currentTicker;
        }
        const isPrepend = !tickerChanged && prevDataLengthRef.current > 0 && data.length > prevDataLengthRef.current;
        const prependedBars = isPrepend ? data.length - prevDataLengthRef.current : 0;

        // Save viewport BEFORE setData (for loadMore compensation)
        const timeScale = chartRef.current?.timeScale();
        let savedLogicalRange: LogicalRange | null = null;
        if (isPrepend && timeScale) {
            savedLogicalRange = timeScale.getVisibleLogicalRange();
        }

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

        // Update price info for countdown timer
        if (data.length > 0) {
            const lastBar = data[data.length - 1];
            lastPriceInfoRef.current = { close: lastBar.close, open: lastBar.open };
        }

        // Restore viewport with offset: prepended bars shift logical indices
        if (savedLogicalRange && timeScale && prependedBars > 0) {
            timeScale.setVisibleLogicalRange({
                from: savedLogicalRange.from + prependedBars,
                to: savedLogicalRange.to + prependedBars,
            });
        }

        prevDataLengthRef.current = data.length;

        // Clear markers if disabled (v5)
        if (!showNewsMarkers && newsMarkersRef.current) {
            newsMarkersRef.current.setMarkers([]);
        }

        // MA/EMA data is now handled by the worker + unified indicator effects
    }, [data, currentTicker, showNewsMarkers]);

    // ============================================================================
    // Session background (pre-market / post-market highlighting)
    // ============================================================================
    useEffect(() => {
        if (!sessionBgSeriesRef.current || !data || data.length === 0) return;

        const sessionData = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            value: 1,
            color: getSessionColor(bar.time),
        }));

        sessionBgSeriesRef.current.setData(sessionData);
    }, [data, selectedInterval]);

    const lastAppliedKeyRef = useRef<string>('');
    const applyRangeTimerRef = useRef<ReturnType<typeof setTimeout>>();
    useEffect(() => {
        if (!data || data.length === 0 || !candleSeriesRef.current) return;
        // Key excludes data.length: loadMore prepend must NOT reset the viewport
        const key = `${currentTicker}-${selectedInterval}-${selectedRange}`;
        if (lastAppliedKeyRef.current !== key) {
            lastAppliedKeyRef.current = key;
            clearTimeout(applyRangeTimerRef.current);
            applyRangeTimerRef.current = setTimeout(() => applyTimeRange(selectedRange), 50);
        }
        return () => { clearTimeout(applyRangeTimerRef.current); };
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

    // ============================================================================
    // Earnings markers (E labels on time axis via custom primitive)
    // ============================================================================
    const earningsPrimitiveRef = useRef<EarningsMarkerPrimitive | null>(null);

    useEffect(() => {
        if (!candleSeriesRef.current || !data || data.length === 0) return;

        // Create primitive if needed
        if (!earningsPrimitiveRef.current) {
            earningsPrimitiveRef.current = new EarningsMarkerPrimitive();
            candleSeriesRef.current.attachPrimitive(earningsPrimitiveRef.current);
        }

        const primitive = earningsPrimitiveRef.current;
        primitive.setVisible(showEarningsMarkers);
        primitive.setInterval(selectedInterval);
        primitive.setDataTimes(data.map(b => b.time));
        primitive.setEarnings(earningsDates);
    }, [showEarningsMarkers, earningsDates, data, selectedInterval]);



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

    // Stable refs for news/edit handlers (declared after their definitions)
    const showNewsMarkersRef = useRef(showNewsMarkers);
    showNewsMarkersRef.current = showNewsMarkers;
    const handleNewsMarkerClickRef = useRef(handleNewsMarkerClick);
    handleNewsMarkerClickRef.current = handleNewsMarkerClick;

    // ============================================================================
    // Initialize incremental indicator engine (for real-time updates)
    // ============================================================================
    useEffect(() => {
        if (data.length === 0) return;
        const activeInsts = indicators.filter(i => i.visible);
        if (activeInsts.length === 0) {
            engineRef.current = null;
            return;
        }
        const engine = new IncrementalIndicatorEngine();
        const configs = activeInsts.map(i => ({ id: i.id, type: i.type, params: i.params }));
        engine.initialize(data, configs);
        engineRef.current = engine;
        return () => { engineRef.current = null; };
    }, [data, indicators]);

    // ============================================================================
    // Register real-time update handler
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) {
            registerUpdateHandler(null);
            return;
        }

        // Read from refs on each call to avoid stale closure over disposed series.
        const handleRealtimeUpdate = (bar: HookChartBar, isNewBar: boolean) => {
            const candleSeries = candleSeriesRef.current;
            const volumeSeries = volumeSeriesRef.current;
            if (!candleSeries || !volumeSeries) return;

            try {
                candleSeries.update({
                    time: bar.time as UTCTimestamp,
                    open: bar.open,
                    high: bar.high,
                    low: bar.low,
                    close: bar.close,
                });

                // Update price info for countdown timer
                lastPriceInfoRef.current = { close: bar.close, open: bar.open };

                const volumeColor = bar.close >= bar.open
                    ? CHART_COLORS.volumeUp
                    : CHART_COLORS.volumeDown;

                volumeSeries.update({
                    time: bar.time as UTCTimestamp,
                    value: bar.volume,
                    color: volumeColor,
                });

                // Update session background for real-time candle
                const sessionBg = sessionBgSeriesRef.current;
                if (sessionBg) {
                    sessionBg.update({
                        time: bar.time as UTCTimestamp,
                        value: 1,
                        color: getSessionColor(bar.time),
                    });
                }
            } catch {
                return;
            }

            if (isNewBar && chartRef.current) {
                const timeScale = chartRef.current.timeScale();
                const logicalRange = timeScale.getVisibleLogicalRange();
                if (logicalRange && logicalRange.to >= data.length - 5) {
                    timeScale.scrollToRealTime();
                }
            }

            // ── Real-time indicator updates (dynamic instances) ────────
            if (engineRef.current) {
                const resultsMap = engineRef.current.update(
                    { time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume },
                    isNewBar,
                );
                const time = bar.time as UTCTimestamp;

                for (const [instanceId, val] of resultsMap) {
                    const seriesMap = indicatorSeriesRef.current.get(instanceId);
                    if (!seriesMap) continue;

                    if (typeof val === 'number') {
                        seriesMap.get('main')?.update({ time, value: val });
                    } else if (val && 'upper' in val && 'middle' in val && 'lower' in val) {
                        seriesMap.get('upper')?.update({ time, value: (val as any).upper });
                        seriesMap.get('middle')?.update({ time, value: (val as any).middle });
                        seriesMap.get('lower')?.update({ time, value: (val as any).lower });
                    } else if (val && 'macd' in val) {
                        const m = val as { macd: number; signal: number; histogram: number };
                        seriesMap.get('macd')?.update({ time, value: m.macd });
                        seriesMap.get('signal')?.update({ time, value: m.signal });
                        const hc = m.histogram >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)';
                        seriesMap.get('histogram')?.update({ time, value: m.histogram, color: hc });
                    } else if (val && 'k' in val) {
                        const st = val as { k: number; d: number };
                        seriesMap.get('k')?.update({ time, value: st.k });
                        seriesMap.get('d')?.update({ time, value: st.d });
                    } else if (val && 'adx' in val) {
                        const a = val as { adx: number; pdi: number; mdi: number };
                        seriesMap.get('adx')?.update({ time, value: a.adx });
                        seriesMap.get('pdi')?.update({ time, value: a.pdi });
                        seriesMap.get('mdi')?.update({ time, value: a.mdi });
                    } else if (val && 'isOn' in val) {
                        const sq = val as { value: number; isOn: boolean };
                        const sqc = sq.isOn ? '#ef4444' : '#10b981';
                        seriesMap.get('main')?.update({ time, value: sq.value, color: sqc });
                    }
                }
            }
        };

        registerUpdateHandler(handleRealtimeUpdate);
        return () => { registerUpdateHandler(null); };
    }, [registerUpdateHandler, data.length]);

    // ============================================================================
    // Double-click on indicator line → open settings dialog
    // ============================================================================
    useEffect(() => {
        const chart = chartRef.current;
        const container = containerRef.current;
        if (!chart || !container) return;

        const handleDblClick = (e: MouseEvent) => {
            // Only handle double-clicks on the chart canvas itself
            const target = e.target as HTMLElement;
            if (!target.closest('canvas')) return;

            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            // Build candidates from unified indicatorSeriesRef
            const candidates: { id: string; series: any }[] = [];
            for (const [instanceId, seriesMap] of indicatorSeriesRef.current) {
                for (const [, series] of seriesMap) {
                    candidates.push({ id: instanceId, series });
                }
            }

            // Find which series line is closest to the click Y coordinate
            let bestId: string | null = null;
            let bestDist = 12; // max 12px threshold

            for (const { id, series } of candidates) {
                try {
                    // Get the coordinate of the series value at this X position
                    const timeScale = chart.timeScale();
                    const time = timeScale.coordinateToTime(x);
                    if (time == null) continue;

                    // priceToCoordinate uses the series' own price scale
                    const dataPoint = series.dataByIndex(timeScale.coordinateToLogical(x));
                    if (!dataPoint) continue;

                    const val = dataPoint.value ?? dataPoint.close;
                    if (val == null) continue;

                    const seriesY = series.priceToCoordinate(val);
                    if (seriesY == null) continue;

                    const dist = Math.abs(seriesY - y);
                    if (dist < bestDist) {
                        bestDist = dist;
                        bestId = id;
                    }
                } catch {
                    // Series may not have data at this point
                }
            }

            if (bestId) {
                e.preventDefault();
                e.stopPropagation();
                openIndicatorSettings(bestId, e as any);
            }
        };

        container.addEventListener('dblclick', handleDblClick);
        return () => container.removeEventListener('dblclick', handleDblClick);
    }, [openIndicatorSettings]);

    // Delete selected indicator with Delete/Backspace key
    useEffect(() => {
        if (!selectedIndicator) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Delete' || e.key === 'Backspace') {
                e.preventDefault();
                removeIndicator(selectedIndicator);
            }
            if (e.key === 'Escape') {
                setSelectedIndicator(null);
            }
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [selectedIndicator, removeIndicator]);

    // Click on canvas selects indicator (single click)
    useEffect(() => {
        const chart = chartRef.current;
        const container = containerRef.current;
        if (!chart || !container) return;

        const handleClick = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (!target.closest('canvas')) { setSelectedIndicator(null); return; }

            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const candidates: { id: string; series: any }[] = [];
            for (const [instanceId, seriesMap] of indicatorSeriesRef.current) {
                for (const [, series] of seriesMap) {
                    candidates.push({ id: instanceId, series });
                }
            }

            let bestId: string | null = null;
            let bestDist = 10;
            for (const { id, series } of candidates) {
                try {
                    const timeScale = chart.timeScale();
                    const dataPoint = series.dataByIndex(timeScale.coordinateToLogical(x));
                    if (!dataPoint) continue;
                    const val = dataPoint.value ?? dataPoint.close;
                    if (val == null) continue;
                    const seriesY = series.priceToCoordinate(val);
                    if (seriesY == null) continue;
                    const dist = Math.abs(seriesY - y);
                    if (dist < bestDist) { bestDist = dist; bestId = id; }
                } catch { /* */ }
            }

            setSelectedIndicator(bestId);
        };

        container.addEventListener('click', handleClick);
        return () => container.removeEventListener('click', handleClick);
    }, []);

    // ============================================================================
    // Sync drawings to primitives
    // ============================================================================
    useEffect(() => {
        if (!candleSeriesRef.current || dataTimes.length === 0) return;
        const series = candleSeriesRef.current;
        const currentPrimitives = drawingPrimitivesRef.current;

        // Remove deleted drawings
        for (const [id, primitive] of currentPrimitives) {
            if (!drawings.find(d => d.id === id)) {
                series.detachPrimitive(primitive);
                currentPrimitives.delete(id);
            }
        }

        // Add/update drawings
        for (const drawing of drawings) {
            const isSelected = selectedDrawingId === drawing.id;
            const isHovered = hoveredDrawingId === drawing.id;
            const existing = currentPrimitives.get(drawing.id);

            if (existing) {
                (existing as any).updateDrawing(drawing, isSelected, isHovered, dataTimes);
            } else {
                let primitive: ISeriesPrimitive<Time> | null = null;
                switch (drawing.type) {
                    case 'horizontal_line':
                        primitive = new HorizontalLinePrimitive(drawing);
                        break;
                    case 'vertical_line':
                        primitive = new VerticalLinePrimitive(drawing);
                        break;
                    case 'trendline':
                        primitive = new TrendlinePrimitive(drawing);
                        break;
                    case 'ray':
                        primitive = new RayPrimitive(drawing);
                        break;
                    case 'extended_line':
                        primitive = new ExtendedLinePrimitive(drawing);
                        break;
                    case 'parallel_channel':
                        primitive = new ParallelChannelPrimitive(drawing);
                        break;
                    case 'fibonacci':
                        primitive = new FibonacciPrimitive(drawing);
                        break;
                    case 'rectangle':
                        primitive = new RectanglePrimitive(drawing);
                        break;
                    case 'circle':
                        primitive = new CirclePrimitive(drawing);
                        break;
                    case 'triangle':
                        primitive = new TrianglePrimitive(drawing);
                        break;
                    case 'measure':
                        primitive = new MeasurePrimitive(drawing);
                        break;
                }
                if (primitive) {
                    series.attachPrimitive(primitive);
                    currentPrimitives.set(drawing.id, primitive);
                    (primitive as any).updateDrawing(drawing, isSelected, isHovered, dataTimes);
                }
            }
        }
    }, [drawings, selectedDrawingId, hoveredDrawingId, chartVersion, dataTimes]);

    // ============================================================================
    // Auto-loadMore: fetch older data when drawings are outside data range
    // ============================================================================
    const autoLoadTriggeredRef = useRef(false);

    // Reset auto-load guard when interval changes (new data range)
    useEffect(() => {
        autoLoadTriggeredRef.current = false;
    }, [selectedInterval]);

    useEffect(() => {
        if (!hasMore || loadingMore || dataTimes.length === 0 || drawings.length === 0) return;
        if (autoLoadTriggeredRef.current) return;

        const firstDataTime = dataTimes[0];

        // Check if any drawing has a timestamp before the first data bar
        const hasOutOfRange = drawings.some(d => {
            // Extract times based on drawing type (type-safe union handling)
            if (d.type === "horizontal_line") return false; // No time anchor
            if (d.type === "vertical_line") return (d as any).time < firstDataTime;
            // All other types have point1 + point2 (and optionally point3)
            const dd = d as any;
            if (dd.point1 && dd.point1.time < firstDataTime) return true;
            if (dd.point2 && dd.point2.time < firstDataTime) return true;
            if (dd.point3 && dd.point3.time < firstDataTime) return true;
            return false;
        });

        if (hasOutOfRange) {
            autoLoadTriggeredRef.current = true;
            loadMore().then((loaded) => {
                if (loaded) {
                    // Allow another load if still out of range (will re-check on next render)
                    autoLoadTriggeredRef.current = false;
                }
            });
        }
    }, [drawings, dataTimes, hasMore, loadingMore, loadMore]);

    // Tentative drawing primitive (preview while placing)
    useEffect(() => {
        if (!candleSeriesRef.current || dataTimes.length === 0) return;
        const series = candleSeriesRef.current;

        if (!tentativePrimitiveRef.current) {
            tentativePrimitiveRef.current = new TentativePrimitive();
            series.attachPrimitive(tentativePrimitiveRef.current);
        }

        if (pendingDrawing) {
            tentativePrimitiveRef.current.setDataTimes(dataTimes);
            tentativePrimitiveRef.current.setState({
                type: pendingDrawing.type,
                point1: pendingDrawing.point1,
                point2: pendingDrawing.point2,
                screenX: tentativeEndpoint?.x ?? -1,   // -1 = anchor-only (no endpoint yet)
                screenY: tentativeEndpoint?.y ?? -1,
                mousePrice: tentativeEndpoint?.price ?? pendingDrawing.point1.price,
                color: drawingColors[0],
            });
        } else {
            tentativePrimitiveRef.current.setState(null);
        }
    }, [pendingDrawing, tentativeEndpoint, drawingColors, chartVersion, dataTimes]);

    // Drag state
    const [dragState, setDragState] = useState<{
        active: boolean;
        drawingId: string | null;
        drawingType: string | null;
        dragMode: 'translate' | 'anchor1' | 'anchor2' | 'anchor3' | 'anchor4' | 'mid1' | 'mid2';
        startScreenX: number;
        startScreenY: number;
        p1ScreenX: number;
        p1ScreenY: number;
        p2ScreenX: number;
        p2ScreenY: number;
        p3ScreenX: number;
        p3ScreenY: number;
    }>({
        active: false,
        drawingId: null,
        drawingType: null,
        dragMode: 'translate',
        startScreenX: 0,
        startScreenY: 0,
        p1ScreenX: 0,
        p1ScreenY: 0,
        p2ScreenX: 0,
        p2ScreenY: 0,
        p3ScreenX: 0,
        p3ScreenY: 0,
    });

    // Time extrapolation for clicks/drags beyond data range.
    // Uses dataTimesRef (not dataTimes) to avoid stale closure in event handlers.
    const getTimeAtX = (x: number): { time: number; logical?: number } | null => {
        if (!chartRef.current) return null;
        const ts = chartRef.current.timeScale();
        const time = ts.coordinateToTime(x);
        if (time != null) return { time: time as number };
        // Beyond data: extrapolate using bar gap (consistent with timeToPixelX)
        const dt = dataTimesRef.current;
        const logical = ts.coordinateToLogical(x);
        if (logical == null || dt.length < 2) return null;
        const n = dt.length;
        const lastGap = dt[n - 1] - dt[n - 2];
        if (lastGap <= 0) return null;
        const offset = logical - (n - 1);
        const extrapolatedTime = Math.round(dt[n - 1] + offset * lastGap);
        if (!isFinite(extrapolatedTime)) return null;
        return { time: extrapolatedTime, logical };
    };

    // Click handler for drawing/selection (reads from refs to avoid stale closures)
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;

        const chart = chartRef.current;

        // LWC subscribeClick for selection and news markers (non-drawing mode)
        const handleClick = (param: any) => {
            if (!param.point || !candleSeriesRef.current) return;
            if (activeToolRef.current !== 'none') return; // Drawing clicks handled by DOM listener below

            const price = candleSeriesRef.current.coordinateToPrice(param.point.y);
            if (price === null) return;

            if (showNewsMarkersRef.current && param.time && newsTimeMapRef.current.has(param.time as number)) {
                handleNewsMarkerClickRef.current(param.time as number);
                return;
            }

            let hitId: string | null = null;
            for (const [id, primitive] of drawingPrimitivesRef.current) {
                const hit = (primitive as any).hitTest?.(param.point.x, param.point.y);
                if (hit) {
                    const eid = (hit.externalId ?? '') as string;
                    hitId = (eid.endsWith(':p1') || eid.endsWith(':p2') || eid.endsWith(':p3') || eid.endsWith(':p4') || eid.endsWith(':m1') || eid.endsWith(':m2')) ? eid.slice(0, -3) : eid;
                    break;
                }
            }
            selectDrawingRef.current(hitId);
        };

        const handleDoubleClick = (param: any) => {
            if (!param.point || !candleSeriesRef.current || activeToolRef.current !== 'none') return;
            const price = candleSeriesRef.current.coordinateToPrice(param.point.y);
            if (price === null) return;

            const nearDrawing = findDrawingNearPriceRef.current(price, 1.5);
            if (nearDrawing) openEditPopupRef.current(nearDrawing.id, param.point.x + 20, param.point.y);
        };

        chart.subscribeClick(handleClick);
        chart.subscribeDblClick(handleDoubleClick);

        return () => {
            chart.unsubscribeClick(handleClick);
            chart.unsubscribeDblClick(handleDoubleClick);
        };
    }, [chartVersion]);

    // Direct DOM click for drawing tools — bypasses LWC's internal click threshold
    // LWC subscribeClick can miss clicks if mouse moves even 1-2px (treated as drag).
    // A direct DOM "click" event always fires regardless of mouse movement.
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const handleDrawingClick = (e: MouseEvent) => {
            if (activeToolRef.current === 'none') return;
            if (!candleSeriesRef.current || !chartRef.current) return;

            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const price = candleSeriesRef.current.coordinateToPrice(y);
            if (price === null) return;

            const ts = chartRef.current.timeScale();
            const time = ts.coordinateToTime(x);
            const resolved = time != null ? { time: time as number } : getTimeAtX(x);
            if (!resolved) return;

            handleChartClickRef.current(resolved.time, price, resolved.logical);
        };

        container.addEventListener('click', handleDrawingClick);
        return () => container.removeEventListener('click', handleDrawingClick);
    }, [chartVersion]);

    // Hover detection (reads from refs)
    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;

        const handleCrosshairMove = (param: any) => {
            if (dragState.active || activeToolRef.current !== 'none') return;
            if (!param.point) { setHoveredDrawing(null); return; }
            let hitId: string | null = null;
            for (const [id, primitive] of drawingPrimitivesRef.current) {
                const hit = (primitive as any).hitTest?.(param.point.x, param.point.y);
                if (hit) {
                    const eid = (hit.externalId ?? '') as string;
                    hitId = eid.endsWith(':p1') || eid.endsWith(':p2') ? eid.slice(0, -3) : eid;
                    break;
                }
            }
            setHoveredDrawing(hitId);
        };

        chart.subscribeCrosshairMove(handleCrosshairMove);
        return () => { chart.unsubscribeCrosshairMove(handleCrosshairMove); };
    }, [dragState.active, setHoveredDrawing, chartVersion]);

    // Track mouse for tentative drawing preview (reads from refs)
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;
        const chart = chartRef.current;

        const handleMove = (param: any) => {
            if (!param.point || !pendingDrawingRef.current || !candleSeriesRef.current) return;
            const price = candleSeriesRef.current.coordinateToPrice(param.point.y);
            if (price === null) return;
            updateTentativeEndpointRef.current(param.point.x, param.point.y, price);
        };

        chart.subscribeCrosshairMove(handleMove);
        return () => { chart.unsubscribeCrosshairMove(handleMove); };
    }, [chartVersion]);

    // Drag handlers
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if (activeTool !== 'none' || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        if (editPopup.visible) return;

        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        let hitId: string | null = null;
        let dragMode: 'translate' | 'anchor1' | 'anchor2' | 'anchor3' | 'anchor4' | 'mid1' | 'mid2' = 'translate';
        for (const [id, primitive] of drawingPrimitivesRef.current) {
            const hit = (primitive as any).hitTest?.(mouseX, mouseY);
            if (hit) {
                const eid = (hit.externalId ?? '') as string;
                if (eid.endsWith(':p1')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'anchor1';
                } else if (eid.endsWith(':p2')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'anchor2';
                } else if (eid.endsWith(':p3')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'anchor3';
                } else if (eid.endsWith(':p4')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'anchor4';
                } else if (eid.endsWith(':m1')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'mid1';
                } else if (eid.endsWith(':m2')) {
                    hitId = eid.slice(0, -3);
                    dragMode = 'mid2';
                } else {
                    hitId = eid;
                    dragMode = 'translate';
                }
                break;
            }
        }
        if (!hitId) return;

        const drawing = drawings.find(d => d.id === hitId);
        if (!drawing) return;

        e.preventDefault();
        e.stopPropagation();

        const series = candleSeriesRef.current;
        const ts = chartRef.current.timeScale();
        let p1ScreenX = 0, p1ScreenY = 0, p2ScreenX = 0, p2ScreenY = 0, p3ScreenX = 0, p3ScreenY = 0;
        if (drawing.type === 'horizontal_line') {
            p1ScreenY = (series.priceToCoordinate(drawing.price) as number) ?? 0;
        } else if (drawing.type === 'vertical_line') {
            p1ScreenX = timeToPixelX(drawing.time, dataTimes, ts) ?? 0;
        } else if ('point1' in drawing && 'point2' in drawing) {
            const d = drawing as any;
            p1ScreenX = timeToPixelX(d.point1.time, dataTimes, ts) ?? 0;
            p1ScreenY = (series.priceToCoordinate(d.point1.price) as number) ?? 0;
            p2ScreenX = timeToPixelX(d.point2.time, dataTimes, ts) ?? 0;
            p2ScreenY = (series.priceToCoordinate(d.point2.price) as number) ?? 0;
            if ('point3' in d && d.point3) {
                p3ScreenX = timeToPixelX(d.point3.time, dataTimes, ts) ?? 0;
                p3ScreenY = (series.priceToCoordinate(d.point3.price) as number) ?? 0;
            }
        }

        setDragState({
            active: true, drawingId: hitId, drawingType: drawing.type, dragMode,
            startScreenX: mouseX, startScreenY: mouseY,
            p1ScreenX, p1ScreenY, p2ScreenX, p2ScreenY, p3ScreenX, p3ScreenY,
        });
        selectDrawing(hitId);
        startDragging();
    }, [activeTool, drawings, selectDrawing, startDragging, editPopup.visible]);

    const handleDragMove = useCallback((e: React.MouseEvent) => {
        if (!dragState.active || !dragState.drawingId || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const dx = mouseX - dragState.startScreenX;
        const dy = mouseY - dragState.startScreenY;
        const series = candleSeriesRef.current;
        const ts = chartRef.current.timeScale();

        if (dragState.drawingType === 'horizontal_line') {
            const newPrice = series.coordinateToPrice(dragState.p1ScreenY + dy);
            if (newPrice !== null && newPrice > 0) updateHorizontalLinePrice(dragState.drawingId, newPrice);
        } else if (dragState.drawingType === 'vertical_line') {
            const resolved = getTimeAtX(dragState.p1ScreenX + dx);
            if (resolved) updateVerticalLineTime(dragState.drawingId, resolved.time);
        } else if (dragState.drawingType === 'parallel_channel') {
            // 6-point parallel channel: TradingView-style drag behavior
            // Data model: point1=A, point2=B, point3=C, D=derived (C + B - A)
            if (dragState.dragMode === 'anchor2') {
                // Drag B: A,C fixed. D auto-derives.
                const resolved = getTimeAtX(mouseX);
                const newPrice = series.coordinateToPrice(mouseY);
                if (resolved && newPrice != null) {
                    updateDrawingPoints(dragState.drawingId, {
                        point2: { time: resolved.time, price: newPrice, logical: resolved.logical },
                    });
                }
            } else if (dragState.dragMode === 'anchor1') {
                // Drag A: B,D fixed. A moves, C shifts by same delta.
                const resolved = getTimeAtX(mouseX);
                const newAPrice = series.coordinateToPrice(mouseY);
                const cNewScreenY = dragState.p3ScreenY + (mouseY - dragState.p1ScreenY);
                const newCPrice = series.coordinateToPrice(cNewScreenY);
                if (resolved && newAPrice != null && newCPrice != null) {
                    updateDrawingPoints(dragState.drawingId, {
                        point1: { time: resolved.time, price: newAPrice, logical: resolved.logical },
                        point3: { time: resolved.time, price: newCPrice },
                    });
                }
            } else if (dragState.dragMode === 'anchor3') {
                // Drag C: B,D fixed. C moves, A shifts by same delta.
                const resolved = getTimeAtX(mouseX);
                const newCPrice = series.coordinateToPrice(mouseY);
                const aNewScreenY = dragState.p1ScreenY + (mouseY - dragState.p3ScreenY);
                const newAPrice = series.coordinateToPrice(aNewScreenY);
                if (resolved && newCPrice != null && newAPrice != null) {
                    updateDrawingPoints(dragState.drawingId, {
                        point1: { time: resolved.time, price: newAPrice },
                        point3: { time: resolved.time, price: newCPrice, logical: resolved.logical },
                    });
                }
            } else if (dragState.dragMode === 'anchor4') {
                // Drag D (derived): A,C fixed. Compute new B = A + (D_new - C).
                // C is displayed at A's X (p1ScreenX), so use that instead of p3ScreenX
                const bNewScreenY = dragState.p1ScreenY + (mouseY - dragState.p3ScreenY);
                const resolvedB = getTimeAtX(mouseX);
                const bPrice = series.coordinateToPrice(bNewScreenY);
                if (resolvedB && bPrice != null) {
                    updateDrawingPoints(dragState.drawingId, {
                        point2: { time: resolvedB.time, price: bPrice, logical: resolvedB.logical },
                    });
                }
            } else if (dragState.dragMode === 'mid1') {
                // Drag M1: shift top line (A,B) vertically. C fixed.
                const newAPrice = series.coordinateToPrice(dragState.p1ScreenY + dy);
                const newBPrice = series.coordinateToPrice(dragState.p2ScreenY + dy);
                const aResolved = getTimeAtX(dragState.p1ScreenX);
                const bResolved = getTimeAtX(dragState.p2ScreenX);
                if (newAPrice != null && newBPrice != null && aResolved && bResolved) {
                    updateDrawingPoints(dragState.drawingId, {
                        point1: { time: aResolved.time, price: newAPrice },
                        point2: { time: bResolved.time, price: newBPrice },
                    });
                }
            } else if (dragState.dragMode === 'mid2') {
                // Drag M2: shift bottom line (C) vertically. A,B fixed.
                const newCPrice = series.coordinateToPrice(dragState.p3ScreenY + dy);
                const cResolved = getTimeAtX(dragState.p1ScreenX);
                if (newCPrice != null && cResolved) {
                    updateDrawingPoints(dragState.drawingId, {
                        point3: { time: cResolved.time, price: newCPrice },
                    });
                }
            } else {
                // Translate: move all 3 stored points
                const r1 = getTimeAtX(dragState.p1ScreenX + dx);
                const r2 = getTimeAtX(dragState.p2ScreenX + dx);
                const r3 = getTimeAtX(dragState.p1ScreenX + dx);
                const newP1Price = series.coordinateToPrice(dragState.p1ScreenY + dy);
                const newP2Price = series.coordinateToPrice(dragState.p2ScreenY + dy);
                const newP3Price = series.coordinateToPrice(dragState.p3ScreenY + dy);
                if (r1 && r2 && r3 && newP1Price != null && newP2Price != null && newP3Price != null) {
                    updateDrawingPoints(dragState.drawingId, {
                        point1: { time: r1.time, price: newP1Price, logical: r1.logical },
                        point2: { time: r2.time, price: newP2Price, logical: r2.logical },
                        point3: { time: r3.time, price: newP3Price, logical: r3.logical },
                    });
                }
            }
        } else if (dragState.dragMode === 'anchor1') {
            const resolved = getTimeAtX(mouseX);
            const newPrice = series.coordinateToPrice(mouseY);
            if (resolved && newPrice != null) {
                updateDrawingPoints(dragState.drawingId, {
                    point1: { time: resolved.time, price: newPrice, logical: resolved.logical },
                });
            }
        } else if (dragState.dragMode === 'anchor2') {
            const resolved = getTimeAtX(mouseX);
            const newPrice = series.coordinateToPrice(mouseY);
            if (resolved && newPrice != null) {
                updateDrawingPoints(dragState.drawingId, {
                    point2: { time: resolved.time, price: newPrice, logical: resolved.logical },
                });
            }
        } else if (dragState.dragMode === 'anchor3') {
            const resolved = getTimeAtX(mouseX);
            const newPrice = series.coordinateToPrice(mouseY);
            if (resolved && newPrice != null) {
                updateDrawingPoints(dragState.drawingId, {
                    point3: { time: resolved.time, price: newPrice, logical: resolved.logical },
                });
            }
        } else {
            // Translate: move all points by the same delta
            const r1 = getTimeAtX(dragState.p1ScreenX + dx);
            const r2 = getTimeAtX(dragState.p2ScreenX + dx);
            const newP1Price = series.coordinateToPrice(dragState.p1ScreenY + dy);
            const newP2Price = series.coordinateToPrice(dragState.p2ScreenY + dy);
            if (r1 && r2 && newP1Price != null && newP2Price != null) {
                // Also move point3 if this is a 3-point drawing
                const has3 = dragState.p3ScreenX !== 0 || dragState.p3ScreenY !== 0;
                if (has3) {
                    const r3 = getTimeAtX(dragState.p3ScreenX + dx);
                    const newP3Price = series.coordinateToPrice(dragState.p3ScreenY + dy);
                    if (r3 && newP3Price != null) {
                        updateDrawingPoints(dragState.drawingId, {
                            point1: { time: r1.time, price: newP1Price, logical: r1.logical },
                            point2: { time: r2.time, price: newP2Price, logical: r2.logical },
                            point3: { time: r3.time, price: newP3Price, logical: r3.logical },
                        });
                    }
                } else {
                    updateDrawingPoints(dragState.drawingId, {
                        point1: { time: r1.time, price: newP1Price, logical: r1.logical },
                        point2: { time: r2.time, price: newP2Price, logical: r2.logical },
                    });
                }
            }
        }
    }, [dragState, updateHorizontalLinePrice, updateVerticalLineTime, updateDrawingPoints]);

    const handleDragEnd = useCallback(() => {
        if (dragState.active) {
            setDragState({ active: false, drawingId: null, drawingType: null, dragMode: 'translate', startScreenX: 0, startScreenY: 0, p1ScreenX: 0, p1ScreenY: 0, p2ScreenX: 0, p2ScreenY: 0, p3ScreenX: 0, p3ScreenY: 0 });
            stopDragging();
            setTimeout(() => selectDrawing(null), 50);
        }
    }, [dragState.active, stopDragging, selectDrawing]);

    // Disable scroll during drag or when drawing tool is active
    useEffect(() => {
        if (!chartRef.current) return;
        const toolActive = activeTool !== 'none';
        chartRef.current.applyOptions({
            handleScroll: {
                mouseWheel: !dragState.active,
                pressedMouseMove: !dragState.active && !toolActive,
                horzTouchDrag: !dragState.active,
                vertTouchDrag: false,
            },
        });
    }, [dragState.active, activeTool]);

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
                case 't':
                case 'T':
                    setActiveTool(activeTool === 'trendline' ? 'none' : 'trendline');
                    break;
                case 'f':
                case 'F':
                    setActiveTool(activeTool === 'fibonacci' ? 'none' : 'fibonacci');
                    break;
                case 'r':
                case 'R':
                    setActiveTool(activeTool === 'rectangle' ? 'none' : 'rectangle');
                    break;
                case 'v':
                case 'V':
                    setActiveTool(activeTool === 'vertical_line' ? 'none' : 'vertical_line');
                    break;
                case 'y':
                case 'Y':
                    setActiveTool(activeTool === 'ray' ? 'none' : 'ray');
                    break;
                case 'e':
                case 'E':
                    setActiveTool(activeTool === 'extended_line' ? 'none' : 'extended_line');
                    break;
                case 'c':
                case 'C':
                    if (!e.metaKey && !e.ctrlKey) {
                        setActiveTool(activeTool === 'circle' ? 'none' : 'circle');
                    }
                    break;
                case 'm':
                case 'M':
                    if (!e.metaKey && !e.ctrlKey) {
                        setActiveTool(activeTool === 'measure' ? 'none' : 'measure');
                    }
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

    const workerConfigs = useMemo((): WorkerIndicatorConfig[] => {
        return indicators.filter(i => i.visible).map(i => ({
            id: i.id,
            type: i.type,
            params: i.params,
        }));
    }, [indicators]);

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

        if (!workerReady || !data.length || workerConfigs.length === 0) return;
        calculate(currentTicker, data, workerConfigs, selectedInterval);
        lastBarCountRef.current = data.length;
    }, [workerReady, data, data.length, workerConfigs, currentTicker, selectedInterval, selectedRange, calculate, clearCache]);

    // ============================================================================
    // Update indicator series from worker results (unified)
    // ============================================================================

    useEffect(() => {
        if (!indicatorResults || !chartRef.current) return;

        for (const inst of indicators) {
            if (!inst.visible) continue;
            const result = (indicatorResults as any)[inst.id];
            if (!result) continue;
            const seriesMap = indicatorSeriesRef.current.get(inst.id);
            if (!seriesMap) continue;

            const { type, data: rData } = result as any;
            try {
                if (type === 'sma' || type === 'ema' || type === 'vwap' || type === 'rsi' || type === 'atr' || type === 'obv') {
                    const main = seriesMap.get('main');
                    if (main && Array.isArray(rData)) {
                        main.setData(rData.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    }
                } else if (type === 'bb' || type === 'keltner') {
                    if (rData?.upper) seriesMap.get('upper')?.setData(rData.upper.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.middle) seriesMap.get('middle')?.setData(rData.middle.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.lower) seriesMap.get('lower')?.setData(rData.lower.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'macd') {
                    if (rData?.histogram) seriesMap.get('histogram')?.setData(rData.histogram.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value, color: d.color || (d.value >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)') })));
                    if (rData?.macd) seriesMap.get('macd')?.setData(rData.macd.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.signal) seriesMap.get('signal')?.setData(rData.signal.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'stoch') {
                    if (rData?.k) seriesMap.get('k')?.setData(rData.k.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.d) seriesMap.get('d')?.setData(rData.d.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'adx') {
                    if (rData?.adx) seriesMap.get('adx')?.setData(rData.adx.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.pdi) seriesMap.get('pdi')?.setData(rData.pdi.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                    if (rData?.mdi) seriesMap.get('mdi')?.setData(rData.mdi.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value })));
                } else if (type === 'squeeze' || type === 'rvol') {
                    const main = seriesMap.get('main');
                    if (main && Array.isArray(rData)) {
                        main.setData(rData.map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value, color: d.color })));
                    }
                }
            } catch (err) {
                console.warn('[TradingChart] Error setting data for', inst.id, err);
            }
        }
    }, [indicatorResults, indicators]);

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

        const fsTimers: ReturnType<typeof setTimeout>[] = [];
        const handleFullscreenChange = () => {
            const isNowFullscreen = !!document.fullscreenElement;
            setIsFullscreen(isNowFullscreen);
            fsTimers.push(
                setTimeout(forceChartResize, 50),
                setTimeout(forceChartResize, 200),
                setTimeout(forceChartResize, 500),
            );
        };

        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => {
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
            fsTimers.forEach(clearTimeout);
        };
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
    const activeIndicatorCount = indicators.filter(i => i.visible).length + (showVolume ? 1 : 0) + (showNewsMarkers ? 1 : 0) + (showEarningsMarkers ? 1 : 0);

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
                /* ===== TradingView-style Toolbar ===== */
                <div className="flex items-center gap-0.5 px-1 py-[2px] border-b border-slate-200 bg-white text-[11px]" style={{ fontFamily }}>

                    {/* Timeframe selector */}
                    <div className="relative">
                        <button
                            onClick={() => setShowIntervalDropdown(!showIntervalDropdown)}
                            className="flex items-center gap-0.5 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-700 font-medium text-[12px]"
                        >
                            {INTERVALS.find(i => i.interval === selectedInterval)?.shortLabel || '1D'}
                            <ChevronDown className="w-3 h-3 text-slate-400" />
                        </button>
                        {showIntervalDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIntervalDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-xl z-50 min-w-[120px] py-1">
                                    {INTERVALS.map((int) => (
                                        <button key={int.interval} onClick={() => { setSelectedInterval(int.interval); setShowIntervalDropdown(false); }}
                                            className={`w-full px-3 py-1.5 text-left text-[11px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600 font-medium' : 'text-slate-600'}`}>
                                            {int.label}
                                        </button>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Candle type */}
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-500" title="Candle Type">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M9 4v4M9 14v6M15 4v6M15 18v2" />
                            <rect x="7" y="8" width="4" height="6" rx="0.5" fill="currentColor" stroke="none" />
                            <rect x="13" y="10" width="4" height="8" rx="0.5" stroke="currentColor" fill="none" />
                        </svg>
                    </button>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Drawing tools */}
                    <HeaderDrawingTools activeTool={activeTool} setActiveTool={setActiveTool} />

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Indicators button */}
                    <div className="relative" ref={indicatorDropdownRef}>
                        <button
                            onClick={() => setShowIndicatorDropdown(!showIndicatorDropdown)}
                            className={`flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-[12px] font-medium ${showIndicatorDropdown || activeIndicatorCount > 0 ? 'text-blue-600' : 'text-slate-500'}`}
                            title="Indicators"
                        >
                            <IndicatorsIcon className="w-[14px] h-[14px]" />
                            <span>Indicadores</span>
                            {activeIndicatorCount > 0 && (
                                <span className="text-[8px] bg-blue-600 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">{activeIndicatorCount}</span>
                            )}
                            <ChevronDown className="w-3 h-3 text-slate-400" />
                        </button>

                        {showIndicatorDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIndicatorDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-xl z-50 min-w-[200px] max-h-[420px] overflow-y-auto py-1">

                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-b border-slate-100 sticky top-0">Overlays</div>
                                    {[
                                        { type: 'sma', label: 'SMA' },
                                        { type: 'ema', label: 'EMA' },
                                        { type: 'bb', label: 'Bollinger Bands' },
                                        { type: 'keltner', label: 'Keltner Channels' },
                                        { type: 'vwap', label: 'VWAP' },
                                    ].map(p => (
                                        <button key={p.type} onClick={() => { addIndicator(p.type); }} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600">
                                            <span className="flex-1 text-left">{p.label}</span>
                                        </button>
                                    ))}

                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Oscillators</div>
                                    {[
                                        { type: 'rsi', label: 'RSI' },
                                        { type: 'macd', label: 'MACD' },
                                        { type: 'stoch', label: 'Stochastic' },
                                        { type: 'adx', label: 'ADX / DMI' },
                                    ].map(p => (
                                        <button key={p.type} onClick={() => { addIndicator(p.type); }} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600">
                                            <span className="flex-1 text-left">{p.label}</span>
                                        </button>
                                    ))}

                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Volatility & Volume</div>
                                    {[
                                        { type: 'atr', label: 'ATR' },
                                        { type: 'squeeze', label: 'TTM Squeeze' },
                                        { type: 'obv', label: 'OBV' },
                                        { type: 'rvol', label: 'RVOL' },
                                    ].map(p => (
                                        <button key={p.type} onClick={() => { addIndicator(p.type); }} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600">
                                            <span className="flex-1 text-left">{p.label}</span>
                                        </button>
                                    ))}
                                    <button onClick={() => setShowVolume(!showVolume)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showVolume ? 'text-blue-600 font-medium' : 'text-slate-600'}`}>
                                        <span className="flex-1 text-left">Volume</span>
                                        {showVolume && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>

                                    <div className="border-t border-slate-100 mt-1" />
                                    <button onClick={() => setShowNewsMarkers(!showNewsMarkers)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showNewsMarkers ? 'text-amber-600' : 'text-slate-600'}`}>
                                        <Newspaper className="w-3.5 h-3.5 flex-shrink-0" />
                                        <span className="flex-1 text-left">News Markers</span>
                                        {showNewsMarkers && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>
                                    <button onClick={() => setShowEarningsMarkers(!showEarningsMarkers)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showEarningsMarkers ? 'text-blue-600' : 'text-slate-600'}`}>
                                        <span className="w-3.5 h-3.5 flex-shrink-0 text-center font-bold text-[9px] leading-3 border border-current rounded-full">E</span>
                                        <span className="flex-1 text-left">Earnings</span>
                                        {showEarningsMarkers && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Layout */}
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-500" title="Layout">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <rect x="3" y="3" width="8" height="8" rx="1" />
                            <rect x="13" y="3" width="8" height="8" rx="1" />
                            <rect x="3" y="13" width="8" height="8" rx="1" />
                            <rect x="13" y="13" width="8" height="8" rx="1" />
                        </svg>
                    </button>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Alert */}
                    <button className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-500 text-[12px]" title="Alert">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <circle cx="12" cy="12" r="9" />
                            <path d="M12 8v4l2 2" />
                            <path d="M20 4l1.5-1.5M4 4L2.5 2.5" />
                        </svg>
                        <span>Alerta</span>
                    </button>

                    {/* Replay */}
                    <button className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-500 text-[12px]" title="Replay">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <polygon points="11,5 3,10 11,15" />
                            <polygon points="20,5 12,10 20,15" />
                        </svg>
                        <span>Replay</span>
                        <ChevronDown className="w-3 h-3 text-slate-400" />
                    </button>

                    <div className="w-px h-4 bg-slate-200" />

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Undo / Redo */}
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-400" title="Undo">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M3 10h13a4 4 0 0 1 0 8H11" />
                            <path d="M7 6l-4 4 4 4" />
                        </svg>
                    </button>
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-400" title="Redo">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M21 10H8a4 4 0 0 0 0 8h5" />
                            <path d="M17 6l4 4-4 4" />
                        </svg>
                    </button>

                    {/* Fullscreen */}
                    <button onClick={toggleFullscreen} className="p-1 rounded hover:bg-slate-100 text-slate-400" title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}>
                        {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                    </button>
                </div>
            )}

            {/* Chart + Toolbar row */}
            <div className="flex flex-1 overflow-hidden">
                {/* Left Drawing Toolbar */}
                {!minimal && (
                    <ChartToolbar
                        activeTool={activeTool}
                        setActiveTool={setActiveTool}
                        drawingCount={drawings.length}
                        clearAllDrawings={clearAllDrawings}
                        zoomIn={zoomIn}
                        zoomOut={zoomOut}
                        drawingsVisible={drawingsVisible}
                        toggleDrawingsVisibility={toggleDrawingsVisibility}
                    />
                )}

                {/* Chart area wrapper */}
                <div className="relative flex-1 overflow-hidden">
                    {/* Logo + Company + Exchange + OHLC */}
                    {!minimal && (
                        <div className="absolute top-1 left-2 z-10 text-[10px] pointer-events-none" style={{ fontFamily, maxWidth: '85%' }}>
                            <div className="flex items-center gap-1 flex-wrap">
                                {tickerMeta?.icon_url ? (
                                    <img
                                        src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/proxy/logo?url=${encodeURIComponent(tickerMeta.icon_url)}`}
                                        alt=""
                                        className="w-4 h-4 rounded-sm object-contain pointer-events-auto"
                                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                    />
                                ) : (
                                    <div className="w-4 h-4 rounded-sm bg-blue-500 flex items-center justify-center text-white text-[8px] font-bold flex-shrink-0">
                                        {currentTicker?.[0] || '?'}
                                    </div>
                                )}
                                <span className="font-semibold text-slate-700">{tickerMeta?.company_name || currentTicker}</span>
                                {tickerMeta?.exchange && (
                                    <span className="text-slate-400 text-[9px]">{tickerMeta.exchange}</span>
                                )}
                                {displayBar && (
                                    <>
                                        <span className="text-slate-400 ml-1">O<span className="text-slate-600 font-medium">{formatPrice(displayBar.open)}</span></span>
                                        <span className="text-slate-400">H<span className="text-emerald-600 font-medium">{formatPrice(displayBar.high)}</span></span>
                                        <span className="text-slate-400">L<span className="text-red-500 font-medium">{formatPrice(displayBar.low)}</span></span>
                                        <span className="text-slate-400">C<span className="text-slate-600 font-medium">{formatPrice(displayBar.close)}</span></span>
                                        {prevBar && (
                                            <span className={`font-medium ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
                                                {isPositive ? '+' : ''}{priceChange.toFixed(2)} ({isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%)
                                            </span>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Legend Overlay */}
                    {indicators.filter(i => i.visible).length > 0 && (
                        <div className="absolute top-5 left-2 z-10 pointer-events-none">
                            <div className="pointer-events-auto flex items-center gap-1 mb-0.5">
                                <button
                                    onClick={() => setLegendExpanded(!legendExpanded)}
                                    className="text-[10px] text-slate-500 hover:text-slate-700 font-medium flex items-center gap-0.5"
                                >
                                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                                        {legendExpanded ? <path d="M19 9l-7 7-7-7"/> : <path d="M9 5l7 7-7 7"/>}
                                    </svg>
                                    <span>{indicators.filter(i => i.visible).length}</span>
                                </button>
                            </div>
                            {legendExpanded && (
                                <div className="flex flex-col gap-0.5 mt-0.5">
                                    {indicators.filter(i => i.visible).map(inst => {
                                        const label = getInstanceLabel(inst);
                                        const mainColor = (inst.styles.color || inst.styles.upperColor || inst.styles.macdColor || inst.styles.kColor || inst.styles.adxColor || inst.styles.onColor || '#888') as string;
                                        return (
                                            <div key={inst.id} className={`flex items-center gap-1.5 pointer-events-auto group px-1 rounded cursor-pointer ${selectedIndicator === inst.id ? 'bg-blue-50 ring-1 ring-blue-400' : 'hover:bg-slate-50'}`} onClick={() => setSelectedIndicator(inst.id)}>
                                                <span className="w-3 h-[2px] rounded" style={{ background: mainColor }}></span>
                                                <span className="text-[11px] text-slate-700 font-medium cursor-pointer" onDoubleClick={(e) => openIndicatorSettings(inst.id, e)}>{label}</span>
                                                <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100">
                                                    <button onClick={(e) => { e.stopPropagation(); openIndicatorSettings(inst.id, e); }} className="text-slate-400 hover:text-slate-600" title="Settings"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg></button>
                                                    <button onClick={(e) => { e.stopPropagation(); removeIndicator(inst.id); }} className="text-slate-400 hover:text-red-500" title="Remove"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4h8v2M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6M10 11v6M14 11v6"/></svg></button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                    {/* Price + countdown overlay (TradingView-style, positioned over price axis) */}
                    <div
                        ref={priceOverlayRef}
                        style={{
                            position: 'absolute',
                            right: 0,
                            display: 'none',
                            flexDirection: 'column',
                            alignItems: 'center',
                            color: 'white',
                            padding: '1px 4px',
                            borderRadius: '2px',
                            textAlign: 'center',
                            zIndex: 20,
                            pointerEvents: 'none',
                            minWidth: '50px',
                        }}
                    />

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
                        <div className="absolute inset-0 z-50" style={{ cursor: dragState.dragMode === 'mid1' || dragState.dragMode === 'mid2' ? 'ns-resize' : dragState.dragMode !== 'translate' ? 'crosshair' : dragState.drawingType === 'horizontal_line' ? 'ns-resize' : dragState.drawingType === 'vertical_line' ? 'ew-resize' : 'grabbing' }} onMouseMove={handleDragMove} onMouseUp={handleDragEnd} onMouseLeave={handleDragEnd} />
                    )}

                    {/* Drawing mode indicator */}
                    {isDrawing && (
                        <div className="absolute top-1 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-2 py-1 bg-blue-500 text-white text-[10px] font-medium rounded shadow-lg">
                            <span>{pendingDrawing ? 'Click second point' : activeTool === 'horizontal_line' ? 'Click to place line' : 'Click first point'}</span>
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

                    {/* Portal: TickerSearch rendered into floating window header */}
                    {headerPortalTarget && createPortal(
                        <form onSubmit={handleTickerChange} className="flex items-center text-[11px]"
                              onMouseDown={(e) => e.stopPropagation()}>
                            <TickerSearch
                                ref={tickerSearchRef}
                                value={inputValue}
                                onChange={setInputValue}
                                onSelect={handleTickerSelect}
                                placeholder="Ticker"
                                className="w-16"
                                autoFocus={false}
                            />
                        </form>,
                        headerPortalTarget
                    )}

                    <div
                        ref={containerRef}
                        className="h-full w-full"
                        onMouseDown={activeTool === 'none' && !minimal ? handleDragStart : undefined}
                        onContextMenu={!minimal ? handleChartContextMenu : undefined}
                        style={{
                            cursor: hoveredDrawingId && activeTool === 'none' ? 'grab' : isDrawing ? 'crosshair' : 'default'
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
                            activeIndicators={indicators.filter(i => i.visible)}
                            chartApi={chartRef.current}
                            onClose={() => setCtxMenu(prev => ({ ...prev, visible: false }))}
                        />
                    )}
                </div>
            </div>

            {/* Footer — bar count & status */}
            {!minimal && (
                <div className="flex items-center justify-end px-2 py-0.5 border-t border-slate-100 text-[9px]" style={{ fontFamily }}>
                    <div className="flex items-center gap-2 text-slate-400">
                        {displayBar && <span className="font-mono">V:{formatVolume(displayBar.volume)}</span>}
                        {loadingMore && <RefreshCw className="w-2.5 h-2.5 animate-spin text-blue-500" />}
                        <span>{data.length.toLocaleString()} bars</span>
                        {hasMore && !loadingMore && <span>← more</span>}
                    </div>
                </div>
            )}

            {/* Indicator Settings Dialog */}
            {indicatorSettingsOpen && (
                <IndicatorSettingsDialog
                    indicatorId={indicatorSettingsOpen}
                    instanceData={indicators.find(i => i.id === indicatorSettingsOpen)}
                    onClose={() => setIndicatorSettingsOpen(null)}
                    onApply={onApplyIndicatorSettings}
                    position={indicatorSettingsPos}
                />
            )}
        </div>
    );
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
