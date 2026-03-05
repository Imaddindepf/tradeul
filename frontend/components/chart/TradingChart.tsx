'use client';

import { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react';
import { createPortal } from 'react-dom';
import type { ISeriesPrimitive, Time, UTCTimestamp } from 'lightweight-charts';
import { RefreshCw, Maximize2, Minimize2, Radio, Newspaper, ChevronDown } from 'lucide-react';
import { useLiveChartData } from '@/hooks/useLiveChartData';
import { useChartDrawings } from '@/hooks/useChartDrawings';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { TickerSearch, type TickerSearchRef } from '@/components/common/TickerSearch';
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
import { ChartToolbar, HeaderDrawingTools, IndicatorsIcon } from './ChartToolbar';
import { IndicatorSettingsDialog } from './IndicatorSettingsDialog';
import { ChartContextMenu, type ContextMenuState } from './ChartContextMenu';
import {
    CHART_COLORS, INTERVALS, INDICATOR_TYPE_DEFAULTS, RIGHT_OFFSET_BARS, getInstanceLabel,
    type ChartBar, type TradingChartProps, type Interval, type TimeRange,
} from './constants';
import { formatPrice, formatVolume } from './formatters';

// Hooks
import {
    useChartInit,
    useChartData,
    useChartIndicators,
    useIndicatorSeries,
    useChartRealtime,
    useChartZoom,
    useChartNews,
    useSessionBackground,
    useEarningsMarkers,
    useTickerManagement,
    useBarReplay,
    useExtendedHoursPrice,
} from './hooks';
import type { ReplaySpeed } from './hooks';

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
    const tickerSearchRef = useRef<TickerSearchRef>(null);
    const priceOverlayRef = useRef<HTMLDivElement>(null);

    // User preferences
    const font = useUserPreferencesStore(selectFont);
    const fontFamily = `var(--font-${font})`;

    // ── Ticker Management ────────────────────────────────────────────────
    const ticker = useTickerManagement(initialTicker, tickerSearchRef, onTickerChange);
    const { currentTicker, inputValue, setInputValue, windowId, windowState, openWindow, tickerMeta, isMarketOpen } = ticker;

    // ── Interval / Range state ───────────────────────────────────────────
    const [selectedInterval, setSelectedInterval] = useState<Interval>(windowState.interval || '1day');
    const [selectedRange, setSelectedRange] = useState<TimeRange>(windowState.range || '1Y');
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [showIntervalDropdown, setShowIntervalDropdown] = useState(false);

    // ── Magnet mode (snap to OHLC) ───────────────────────────────────────
    type MagnetMode = 'off' | 'weak' | 'strong';
    const [magnetMode, setMagnetMode] = useState<MagnetMode>('off');
    const magnetModeRef = useRef<MagnetMode>('off');
    magnetModeRef.current = magnetMode;
    const ctrlPressedRef = useRef(false);

    // ── Portal for TickerSearch in floating window header ────────────────
    const [headerPortalTarget, setHeaderPortalTarget] = useState<HTMLElement | null>(null);
    useEffect(() => {
        if (windowId && !minimal) {
            const el = document.getElementById(`window-header-extra-${windowId}`);
            if (el) setHeaderPortalTarget(el);
        }
    }, [windowId, minimal]);

    // ── Replay ────────────────────────────────────────────────────────────
    const [replayTimestamp, setReplayTimestamp] = useState<number | null>(null);
    const replayTimeRef = useRef<number | null>(null);

    const handleIntervalChange = useCallback((newInterval: Interval) => {
        if (replayTimeRef.current) {
            setReplayTimestamp(replayTimeRef.current);
        }
        setSelectedInterval(newInterval);
    }, []);

    // ── Chart Initialization ─────────────────────────────────────────────
    const chartCore = useChartInit(containerRef, currentTicker, selectedInterval, fontFamily, priceOverlayRef);
    const { chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef, whitespaceSeriesRef, lastPriceInfoRef, beforeDestroyCallbackRef, chartVersion, hoveredBar } = chartCore;

    // ── Live Data ────────────────────────────────────────────────────────
    const { data, loading, loadingMore, error, hasMore, isLive, refetch, loadMore, loadForward, registerUpdateHandler, registerExtendedHoursHandler } = useLiveChartData(currentTicker, selectedInterval, replayTimestamp);

    // ── Indicators ───────────────────────────────────────────────────────
    const ind = useChartIndicators(chartRef, data, currentTicker, selectedInterval, selectedRange, windowState);
    const {
        indicators, setIndicators, nextInstanceIdRef,
        showVolume, setShowVolume,
        showNewsMarkers, setShowNewsMarkers,
        showEarningsMarkers, setShowEarningsMarkers,
        selectedIndicator, setSelectedIndicator,
        legendExpanded, setLegendExpanded,
        indicatorSettingsOpen, setIndicatorSettingsOpen, indicatorSettingsPos,
        showIndicatorDropdown, setShowIndicatorDropdown, indicatorDropdownRef,
        indicatorResults,
        indicatorSeriesRef, panelPaneIndexRef,
        addIndicator, openIndicatorSettings, removeIndicator, onApplyIndicatorSettings,
        workerReady, calculate, clearCache,
    } = ind;

    // ── Replay gate ref (shared between useChartData and useBarReplay) ──
    const replayControlsDataRef = useRef(false);

    // ── Chart Data Updates ───────────────────────────────────────────────
    const news = useChartNews(candleSeriesRef, data, selectedInterval, currentTicker, showNewsMarkers, openWindow);
    const { newsMarkersRef, newsTimeMapRef, showNewsMarkersRef, handleNewsMarkerClickRef } = news;

    const { isScrolledAway } = useChartData(
        chartRef, candleSeriesRef, volumeSeriesRef, whitespaceSeriesRef, lastPriceInfoRef, newsMarkersRef,
        data, currentTicker, selectedInterval, showNewsMarkers, hasMore, loadingMore, loadMore,
        replayControlsDataRef, chartVersion,
    );

    // ── Session Background ───────────────────────────────────────────────
    useSessionBackground(sessionBgSeriesRef, data, selectedInterval, replayControlsDataRef);

    // ── Earnings Markers ─────────────────────────────────────────────────
    const { earningsPrimitiveRef } = useEarningsMarkers(candleSeriesRef, data, selectedInterval, currentTicker, showEarningsMarkers);

    // ── Bar Replay (MUST run AFTER useChartData/useSessionBackground) ───
    const replay = useBarReplay(
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef, whitespaceSeriesRef,
        indicatorSeriesRef, lastPriceInfoRef, data, selectedInterval,
        indicators, indicatorResults, replayControlsDataRef, chartVersion,
        setReplayTimestamp, replayTimeRef, loadForward,
    );

    // ── Indicator Series on Chart ────────────────────────────────────────
    const isReplayActive = replay.replayState.mode !== 'idle';
    useIndicatorSeries(
        chartRef, indicatorSeriesRef, panelPaneIndexRef,
        indicators, indicatorResults, data, currentTicker,
        selectedInterval, selectedRange, workerReady,
        calculate, clearCache, volumeSeriesRef, showVolume,
        chartVersion, isReplayActive,
    );

    // ── Realtime Updates ─────────────────────────────────────────────────
    useChartRealtime(
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef, whitespaceSeriesRef,
        indicatorSeriesRef, lastPriceInfoRef, data, selectedInterval, indicators, registerUpdateHandler,
        isReplayActive,
    );

    // ── Extended Hours Price (pre/post market label on daily+) ──────────
    useExtendedHoursPrice({
        candleSeriesRef,
        priceOverlayRef,
        selectedInterval,
        currentSession: ticker.marketSession?.current_session ?? null,
        ticker: currentTicker,
        isReplayActive,
        registerExtendedHoursHandler,
    });

    // ── Zoom / Time Range ────────────────────────────────────────────────
    const { zoomIn, zoomOut, handleRangeChange } = useChartZoom(
        chartRef, data, currentTicker, selectedInterval, selectedRange,
        handleIntervalChange, setSelectedRange, isReplayActive,
    );

    // ── Persist window state ─────────────────────────────────────────────
    useEffect(() => {
        ticker.persistState(selectedInterval, selectedRange, showVolume, indicators, nextInstanceIdRef.current);
    }, [currentTicker, selectedInterval, selectedRange, showVolume, indicators]);

    // ── Broadcast active chart for AI agent ──────────────────────────────
    useEffect(() => {
        if (!data || data.length === 0 || !currentTicker) return;
        const detail = { ticker: currentTicker, interval: selectedInterval, range: selectedRange, barCount: data.length };
        window.dispatchEvent(new CustomEvent('agent:chart-active', { detail }));
        return () => { window.dispatchEvent(new CustomEvent('agent:chart-active', { detail: null })); };
    }, [currentTicker, selectedInterval, selectedRange, data?.length]);

    // ── AI Context Menu ──────────────────────────────────────────────────
    const [ctxMenu, setCtxMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, candle: null });
    const handleChartContextMenu = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        setCtxMenu({
            visible: true,
            x: Math.min(e.clientX - rect.left, rect.width - 220),
            y: Math.min(e.clientY - rect.top, rect.height - 200),
            candle: hoveredBar,
        });
    }, [hoveredBar]);

    // ====================================================================
    // Drawing Tools
    // ====================================================================
    const {
        drawings, activeTool, isDrawing, selectedDrawingId, hoveredDrawingId,
        pendingDrawing, tentativeEndpoint,
        setActiveTool, cancelDrawing, handleChartClick, updateTentativeEndpoint,
        removeDrawing, clearAllDrawings, selectDrawing,
        updateHorizontalLinePrice, updateVerticalLineTime, updateDrawingPoints,
        updateDrawingLineWidth, updateDrawingColor, startDragging, stopDragging,
        findDrawingNearPrice, setHoveredDrawing, colors: drawingColors,
    } = useChartDrawings(currentTicker);

    const [drawingsVisible, setDrawingsVisible] = useState(true);
    const toggleDrawingsVisibility = useCallback(() => setDrawingsVisible(prev => !prev), []);

    const [editPopup, setEditPopup] = useState<{ visible: boolean; drawingId: string | null; x: number; y: number }>({ visible: false, drawingId: null, x: 0, y: 0 });
    const editingDrawing = editPopup.drawingId ? drawings.find(d => d.id === editPopup.drawingId) : null;

    const openEditPopup = useCallback((drawingId: string, x: number, y: number) => {
        setEditPopup({ visible: true, drawingId, x, y });
        selectDrawing(drawingId);
    }, [selectDrawing]);
    const closeEditPopup = useCallback(() => setEditPopup({ visible: false, drawingId: null, x: 0, y: 0 }), []);
    const handleEditColor = useCallback((color: string) => { if (editPopup.drawingId) updateDrawingColor(editPopup.drawingId, color); }, [editPopup.drawingId, updateDrawingColor]);
    const handleEditLineWidth = useCallback((width: number) => { if (editPopup.drawingId) updateDrawingLineWidth(editPopup.drawingId, width); }, [editPopup.drawingId, updateDrawingLineWidth]);
    const handleEditDelete = useCallback(() => { if (editPopup.drawingId) { removeDrawing(editPopup.drawingId); closeEditPopup(); } }, [editPopup.drawingId, removeDrawing, closeEditPopup]);

    // Drawing primitive refs
    const drawingPrimitivesRef = useRef<Map<string, ISeriesPrimitive<Time>>>(new Map());
    const tentativePrimitiveRef = useRef<TentativePrimitive | null>(null);
    const dataTimes = useMemo(() => data.map(d => d.time), [data]);
    const dataTimesRef = useRef(dataTimes);
    dataTimesRef.current = dataTimes;
    const dataRef = useRef(data);
    dataRef.current = data;

    // Stable refs for event handlers
    const activeToolRef = useRef(activeTool); activeToolRef.current = activeTool;
    const handleChartClickRef = useRef(handleChartClick); handleChartClickRef.current = handleChartClick;
    const selectDrawingRef = useRef(selectDrawing); selectDrawingRef.current = selectDrawing;
    const pendingDrawingRef = useRef(pendingDrawing); pendingDrawingRef.current = pendingDrawing;
    const updateTentativeEndpointRef = useRef(updateTentativeEndpoint); updateTentativeEndpointRef.current = updateTentativeEndpoint;
    const openEditPopupRef = useRef(openEditPopup); openEditPopupRef.current = openEditPopup;
    const findDrawingNearPriceRef = useRef(findDrawingNearPrice); findDrawingNearPriceRef.current = findDrawingNearPrice;
    const replayModeRef = useRef(replay.replayState.mode); replayModeRef.current = replay.replayState.mode;
    const selectStartPointRef = useRef(replay.selectStartPoint); selectStartPointRef.current = replay.selectStartPoint;

    // ── Ctrl key tracking for magnet snap ─────────────────────────────────
    useEffect(() => {
        const down = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlPressedRef.current = true; };
        const up = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlPressedRef.current = false; };
        const blur = () => { ctrlPressedRef.current = false; };
        window.addEventListener('keydown', down);
        window.addEventListener('keyup', up);
        window.addEventListener('blur', blur);
        return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); window.removeEventListener('blur', blur); };
    }, []);

    /**
     * Snap a raw price to the nearest OHLC value of the bar at screen X.
     * Returns the original price if magnet is not active or no bar is found.
     *
     * Magnet activates when:
     *  - Ctrl/Cmd is held (temporary toggle), OR
     *  - magnetMode is 'weak' or 'strong' (permanent, Ctrl disables temporarily)
     *
     * Weak: only snaps when cursor is within 40% of bar range from an OHLC value.
     * Strong: always snaps to nearest OHLC.
     */
    const snapPriceToOHLC = useCallback((rawPrice: number, screenX: number): number => {
        const ctrl = ctrlPressedRef.current;
        const mode = magnetModeRef.current;
        const hasToolActive = activeToolRef.current !== 'none';

        // Magnet only works when a drawing tool is active
        if (!hasToolActive) return rawPrice;

        // Determine if snap should be active:
        // Ctrl toggles: if magnet off → Ctrl enables; if magnet on → Ctrl disables
        const shouldSnap = mode === 'off' ? ctrl : !ctrl;
        if (!shouldSnap) return rawPrice;

        const chart = chartRef.current;
        const series = candleSeriesRef.current;
        if (!chart || !series) return rawPrice;

        const ts = chart.timeScale();
        const time = ts.coordinateToTime(screenX);
        if (time == null) return rawPrice;

        const bar = dataRef.current.find(d => d.time === (time as number));
        if (!bar) return rawPrice;

        const ohlc = [bar.open, bar.high, bar.low, bar.close];
        let closest = ohlc[0];
        let minDist = Math.abs(rawPrice - ohlc[0]);
        for (let i = 1; i < ohlc.length; i++) {
            const dist = Math.abs(rawPrice - ohlc[i]);
            if (dist < minDist) { minDist = dist; closest = ohlc[i]; }
        }

        if (mode === 'weak' && !ctrl) {
            const barRange = bar.high - bar.low;
            const threshold = barRange > 0 ? barRange * 0.4 : Math.abs(bar.close) * 0.005;
            if (minDist > threshold) return rawPrice;
        }

        return closest;
    }, []);
    const snapPriceRef = useRef(snapPriceToOHLC);
    snapPriceRef.current = snapPriceToOHLC;

    // ── Pre-destroy cleanup: detach all primitives before chart.remove() ──
    beforeDestroyCallbackRef.current = () => {
        const series = candleSeriesRef.current;
        if (series) {
            for (const [, prim] of drawingPrimitivesRef.current) {
                try { series.detachPrimitive(prim); } catch { }
            }
            if (tentativePrimitiveRef.current) {
                try { series.detachPrimitive(tentativePrimitiveRef.current); } catch { }
            }
            if (earningsPrimitiveRef.current) {
                try { series.detachPrimitive(earningsPrimitiveRef.current); } catch { }
            }
        }
        drawingPrimitivesRef.current.clear();
        tentativePrimitiveRef.current = null;
        earningsPrimitiveRef.current = null;
        indicatorSeriesRef.current.clear();
        panelPaneIndexRef.current.clear();
    };

    // ── Sync drawings to primitives ──────────────────────────────────────
    useEffect(() => {
        if (!candleSeriesRef.current || dataTimes.length === 0) return;
        const series = candleSeriesRef.current;
        const currentPrimitives = drawingPrimitivesRef.current;

        for (const [id, primitive] of currentPrimitives) {
            if (!drawings.find(d => d.id === id)) {
                try { series.detachPrimitive(primitive); } catch { }
                currentPrimitives.delete(id);
            }
        }

        for (const drawing of drawings) {
            const isSelected = selectedDrawingId === drawing.id;
            const isHovered = hoveredDrawingId === drawing.id;
            const existing = currentPrimitives.get(drawing.id);

            if (existing) {
                (existing as any).updateDrawing(drawing, isSelected, isHovered, dataTimes);
            } else {
                let primitive: ISeriesPrimitive<Time> | null = null;
                switch (drawing.type) {
                    case 'horizontal_line': primitive = new HorizontalLinePrimitive(drawing); break;
                    case 'vertical_line': primitive = new VerticalLinePrimitive(drawing); break;
                    case 'trendline': primitive = new TrendlinePrimitive(drawing); break;
                    case 'ray': primitive = new RayPrimitive(drawing); break;
                    case 'extended_line': primitive = new ExtendedLinePrimitive(drawing); break;
                    case 'parallel_channel': primitive = new ParallelChannelPrimitive(drawing); break;
                    case 'fibonacci': primitive = new FibonacciPrimitive(drawing); break;
                    case 'rectangle': primitive = new RectanglePrimitive(drawing); break;
                    case 'circle': primitive = new CirclePrimitive(drawing); break;
                    case 'triangle': primitive = new TrianglePrimitive(drawing); break;
                    case 'measure': primitive = new MeasurePrimitive(drawing); break;
                }
                if (primitive) {
                    series.attachPrimitive(primitive);
                    currentPrimitives.set(drawing.id, primitive);
                    (primitive as any).updateDrawing(drawing, isSelected, isHovered, dataTimes);
                }
            }
        }
    }, [drawings, selectedDrawingId, hoveredDrawingId, chartVersion, dataTimes]);

    // ── Auto-loadMore for out-of-range drawings ──────────────────────────
    const autoLoadTriggeredRef = useRef(false);
    useEffect(() => { autoLoadTriggeredRef.current = false; }, [selectedInterval]);
    useEffect(() => {
        if (replayControlsDataRef.current) return;
        if (!hasMore || loadingMore || dataTimes.length === 0 || drawings.length === 0) return;
        if (autoLoadTriggeredRef.current) return;
        const firstDataTime = dataTimes[0];
        const hasOutOfRange = drawings.some(d => {
            if (d.type === "horizontal_line") return false;
            if (d.type === "vertical_line") return (d as any).time < firstDataTime;
            const dd = d as any;
            if (dd.point1 && dd.point1.time < firstDataTime) return true;
            if (dd.point2 && dd.point2.time < firstDataTime) return true;
            if (dd.point3 && dd.point3.time < firstDataTime) return true;
            return false;
        });
        if (hasOutOfRange) {
            autoLoadTriggeredRef.current = true;
            loadMore().then((loaded) => { if (loaded) autoLoadTriggeredRef.current = false; });
        }
    }, [drawings, dataTimes, hasMore, loadingMore, loadMore]);

    // ── Tentative drawing primitive ──────────────────────────────────────
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
                type: pendingDrawing.type, point1: pendingDrawing.point1, point2: pendingDrawing.point2,
                screenX: tentativeEndpoint?.x ?? -1, screenY: tentativeEndpoint?.y ?? -1,
                mousePrice: tentativeEndpoint?.price ?? pendingDrawing.point1.price, color: drawingColors[0],
            });
        } else {
            tentativePrimitiveRef.current.setState(null);
        }
    }, [pendingDrawing, tentativeEndpoint, drawingColors, chartVersion, dataTimes]);

    // ── Drag state ───────────────────────────────────────────────────────
    const [dragState, setDragState] = useState<{
        active: boolean; drawingId: string | null; drawingType: string | null;
        dragMode: 'translate' | 'anchor1' | 'anchor2' | 'anchor3' | 'anchor4' | 'mid1' | 'mid2';
        startScreenX: number; startScreenY: number;
        p1ScreenX: number; p1ScreenY: number; p2ScreenX: number; p2ScreenY: number;
        p3ScreenX: number; p3ScreenY: number;
    }>({ active: false, drawingId: null, drawingType: null, dragMode: 'translate', startScreenX: 0, startScreenY: 0, p1ScreenX: 0, p1ScreenY: 0, p2ScreenX: 0, p2ScreenY: 0, p3ScreenX: 0, p3ScreenY: 0 });

    const getTimeAtX = (x: number): { time: number; logical?: number } | null => {
        if (!chartRef.current) return null;
        const ts = chartRef.current.timeScale();
        const time = ts.coordinateToTime(x);
        if (time != null) return { time: time as number };
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

    // ── Click handler for selection/news ──────────────────────────────────
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;
        const chart = chartRef.current;
        const handleClick = (param: any) => {
            if (!param.point || !candleSeriesRef.current) return;
            if (replayModeRef.current === 'selecting' && param.time) {
                selectStartPointRef.current(param.time as number);
                return;
            }
            if (activeToolRef.current !== 'none') return;
            const price = candleSeriesRef.current.coordinateToPrice(param.point.y);
            if (price === null) return;
            if (showNewsMarkersRef.current && param.time && newsTimeMapRef.current.has(param.time as number)) {
                handleNewsMarkerClickRef.current(param.time as number);
                return;
            }
            let hitId: string | null = null;
            for (const [, primitive] of drawingPrimitivesRef.current) {
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
        return () => { chart.unsubscribeClick(handleClick); chart.unsubscribeDblClick(handleDoubleClick); };
    }, [chartVersion]);

    // ── DOM click for drawing tools ──────────────────────────────────────
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        const handleDrawingClick = (e: MouseEvent) => {
            if (activeToolRef.current === 'none') return;
            if (!candleSeriesRef.current || !chartRef.current) return;
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const rawPrice = candleSeriesRef.current.coordinateToPrice(y);
            if (rawPrice === null) return;
            const price = snapPriceRef.current(rawPrice, x);
            const ts = chartRef.current.timeScale();
            const time = ts.coordinateToTime(x);
            const resolved = time != null ? { time: time as number } : getTimeAtX(x);
            if (!resolved) return;
            handleChartClickRef.current(resolved.time, price, resolved.logical);
        };
        container.addEventListener('click', handleDrawingClick);
        return () => container.removeEventListener('click', handleDrawingClick);
    }, [chartVersion]);

    // ── Hover detection ──────────────────────────────────────────────────
    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;
        const handleCrosshairMove = (param: any) => {
            if (dragState.active || activeToolRef.current !== 'none') return;
            if (!param.point) { setHoveredDrawing(null); return; }
            let hitId: string | null = null;
            for (const [, primitive] of drawingPrimitivesRef.current) {
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

    // ── Mouse tracking for tentative drawing ─────────────────────────────
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;
        const chart = chartRef.current;
        const handleMove = (param: any) => {
            if (!param.point || !pendingDrawingRef.current || !candleSeriesRef.current) return;
            const rawPrice = candleSeriesRef.current.coordinateToPrice(param.point.y);
            if (rawPrice === null) return;
            const price = snapPriceRef.current(rawPrice, param.point.x);
            updateTentativeEndpointRef.current(param.point.x, param.point.y, price);
        };
        chart.subscribeCrosshairMove(handleMove);
        return () => { chart.unsubscribeCrosshairMove(handleMove); };
    }, [chartVersion]);

    // ── Magnet: snap crosshair to nearest OHLC on mouse move ─────────────
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const handleMouseMove = (e: MouseEvent) => {
            const chart = chartRef.current;
            const series = candleSeriesRef.current;
            if (!chart || !series) return;

            const ctrl = ctrlPressedRef.current;
            const mode = magnetModeRef.current;
            const hasToolActive = activeToolRef.current !== 'none';
            if (!hasToolActive) return;
            const shouldSnap = mode === 'off' ? ctrl : !ctrl;
            if (!shouldSnap) return;

            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const ts = chart.timeScale();
            const time = ts.coordinateToTime(x);
            if (time == null) return;

            const rawPrice = series.coordinateToPrice(y);
            if (rawPrice === null) return;

            const bar = dataRef.current.find(d => d.time === (time as number));
            if (!bar) return;

            const ohlc = [bar.open, bar.high, bar.low, bar.close];
            let closest = ohlc[0];
            let minDist = Math.abs(rawPrice - ohlc[0]);
            for (let i = 1; i < ohlc.length; i++) {
                const dist = Math.abs(rawPrice - ohlc[i]);
                if (dist < minDist) { minDist = dist; closest = ohlc[i]; }
            }

            if (mode === 'weak' && !ctrl) {
                const barRange = bar.high - bar.low;
                const threshold = barRange > 0 ? barRange * 0.4 : Math.abs(bar.close) * 0.005;
                if (minDist > threshold) return;
            }

            chart.setCrosshairPosition(closest, time, series);
        };

        const handleMouseLeave = () => {
            chartRef.current?.clearCrosshairPosition();
        };

        container.addEventListener('mousemove', handleMouseMove);
        container.addEventListener('mouseleave', handleMouseLeave);
        return () => {
            container.removeEventListener('mousemove', handleMouseMove);
            container.removeEventListener('mouseleave', handleMouseLeave);
        };
    }, [chartVersion]);

    // ── Drag handlers ────────────────────────────────────────────────────
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if (activeTool !== 'none' || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        if (editPopup.visible) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        let hitId: string | null = null;
        let dragMode: typeof dragState.dragMode = 'translate';
        for (const [, primitive] of drawingPrimitivesRef.current) {
            const hit = (primitive as any).hitTest?.(mouseX, mouseY);
            if (hit) {
                const eid = (hit.externalId ?? '') as string;
                if (eid.endsWith(':p1')) { hitId = eid.slice(0, -3); dragMode = 'anchor1'; }
                else if (eid.endsWith(':p2')) { hitId = eid.slice(0, -3); dragMode = 'anchor2'; }
                else if (eid.endsWith(':p3')) { hitId = eid.slice(0, -3); dragMode = 'anchor3'; }
                else if (eid.endsWith(':p4')) { hitId = eid.slice(0, -3); dragMode = 'anchor4'; }
                else if (eid.endsWith(':m1')) { hitId = eid.slice(0, -3); dragMode = 'mid1'; }
                else if (eid.endsWith(':m2')) { hitId = eid.slice(0, -3); dragMode = 'mid2'; }
                else { hitId = eid; dragMode = 'translate'; }
                break;
            }
        }
        if (!hitId) return;
        const drawing = drawings.find(d => d.id === hitId);
        if (!drawing) return;
        e.preventDefault(); e.stopPropagation();
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
        setDragState({ active: true, drawingId: hitId, drawingType: drawing.type, dragMode, startScreenX: mouseX, startScreenY: mouseY, p1ScreenX, p1ScreenY, p2ScreenX, p2ScreenY, p3ScreenX, p3ScreenY });
        selectDrawing(hitId);
        startDragging();
    }, [activeTool, drawings, selectDrawing, startDragging, editPopup.visible, dataTimes]);

    const handleDragMove = useCallback((e: React.MouseEvent) => {
        if (!dragState.active || !dragState.drawingId || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const dx = mouseX - dragState.startScreenX;
        const dy = mouseY - dragState.startScreenY;
        const series = candleSeriesRef.current;
        const isAnchor = dragState.dragMode.startsWith('anchor');
        const sp = (raw: number | null, sx: number) => {
            if (raw == null) return raw;
            return isAnchor ? snapPriceRef.current(raw, sx) : raw;
        };

        if (dragState.drawingType === 'horizontal_line') {
            const newPrice = sp(series.coordinateToPrice(dragState.p1ScreenY + dy), mouseX);
            if (newPrice !== null && newPrice > 0) updateHorizontalLinePrice(dragState.drawingId, newPrice);
        } else if (dragState.drawingType === 'vertical_line') {
            const resolved = getTimeAtX(dragState.p1ScreenX + dx);
            if (resolved) updateVerticalLineTime(dragState.drawingId, resolved.time);
        } else if (dragState.drawingType === 'parallel_channel') {
            if (dragState.dragMode === 'anchor2') {
                const resolved = getTimeAtX(mouseX);
                const newPrice = sp(series.coordinateToPrice(mouseY), mouseX);
                if (resolved && newPrice != null) updateDrawingPoints(dragState.drawingId, { point2: { time: resolved.time, price: newPrice, logical: resolved.logical } });
            } else if (dragState.dragMode === 'anchor1') {
                const resolved = getTimeAtX(mouseX);
                const newAPrice = sp(series.coordinateToPrice(mouseY), mouseX);
                const newCPrice = series.coordinateToPrice(dragState.p3ScreenY + (mouseY - dragState.p1ScreenY));
                if (resolved && newAPrice != null && newCPrice != null) updateDrawingPoints(dragState.drawingId, { point1: { time: resolved.time, price: newAPrice, logical: resolved.logical }, point3: { time: resolved.time, price: newCPrice } });
            } else if (dragState.dragMode === 'anchor3') {
                const resolved = getTimeAtX(mouseX);
                const newCPrice = sp(series.coordinateToPrice(mouseY), mouseX);
                const newAPrice = series.coordinateToPrice(dragState.p1ScreenY + (mouseY - dragState.p3ScreenY));
                if (resolved && newCPrice != null && newAPrice != null) updateDrawingPoints(dragState.drawingId, { point1: { time: resolved.time, price: newAPrice }, point3: { time: resolved.time, price: newCPrice, logical: resolved.logical } });
            } else if (dragState.dragMode === 'anchor4') {
                const bNewScreenY = dragState.p1ScreenY + (mouseY - dragState.p3ScreenY);
                const resolvedB = getTimeAtX(mouseX);
                const bPrice = sp(series.coordinateToPrice(bNewScreenY), mouseX);
                if (resolvedB && bPrice != null) updateDrawingPoints(dragState.drawingId, { point2: { time: resolvedB.time, price: bPrice, logical: resolvedB.logical } });
            } else if (dragState.dragMode === 'mid1') {
                const newAPrice = series.coordinateToPrice(dragState.p1ScreenY + dy);
                const newBPrice = series.coordinateToPrice(dragState.p2ScreenY + dy);
                const aR = getTimeAtX(dragState.p1ScreenX); const bR = getTimeAtX(dragState.p2ScreenX);
                if (newAPrice != null && newBPrice != null && aR && bR) updateDrawingPoints(dragState.drawingId, { point1: { time: aR.time, price: newAPrice }, point2: { time: bR.time, price: newBPrice } });
            } else if (dragState.dragMode === 'mid2') {
                const newCPrice = series.coordinateToPrice(dragState.p3ScreenY + dy);
                const cR = getTimeAtX(dragState.p1ScreenX);
                if (newCPrice != null && cR) updateDrawingPoints(dragState.drawingId, { point3: { time: cR.time, price: newCPrice } });
            } else {
                const r1 = getTimeAtX(dragState.p1ScreenX + dx); const r2 = getTimeAtX(dragState.p2ScreenX + dx); const r3 = getTimeAtX(dragState.p1ScreenX + dx);
                const np1 = series.coordinateToPrice(dragState.p1ScreenY + dy); const np2 = series.coordinateToPrice(dragState.p2ScreenY + dy); const np3 = series.coordinateToPrice(dragState.p3ScreenY + dy);
                if (r1 && r2 && r3 && np1 != null && np2 != null && np3 != null) updateDrawingPoints(dragState.drawingId, { point1: { time: r1.time, price: np1, logical: r1.logical }, point2: { time: r2.time, price: np2, logical: r2.logical }, point3: { time: r3.time, price: np3, logical: r3.logical } });
            }
        } else if (dragState.dragMode === 'anchor1') {
            const resolved = getTimeAtX(mouseX); const newPrice = sp(series.coordinateToPrice(mouseY), mouseX);
            if (resolved && newPrice != null) updateDrawingPoints(dragState.drawingId, { point1: { time: resolved.time, price: newPrice, logical: resolved.logical } });
        } else if (dragState.dragMode === 'anchor2') {
            const resolved = getTimeAtX(mouseX); const newPrice = sp(series.coordinateToPrice(mouseY), mouseX);
            if (resolved && newPrice != null) updateDrawingPoints(dragState.drawingId, { point2: { time: resolved.time, price: newPrice, logical: resolved.logical } });
        } else if (dragState.dragMode === 'anchor3') {
            const resolved = getTimeAtX(mouseX); const newPrice = sp(series.coordinateToPrice(mouseY), mouseX);
            if (resolved && newPrice != null) updateDrawingPoints(dragState.drawingId, { point3: { time: resolved.time, price: newPrice, logical: resolved.logical } });
        } else {
            const r1 = getTimeAtX(dragState.p1ScreenX + dx); const r2 = getTimeAtX(dragState.p2ScreenX + dx);
            const np1 = series.coordinateToPrice(dragState.p1ScreenY + dy); const np2 = series.coordinateToPrice(dragState.p2ScreenY + dy);
            if (r1 && r2 && np1 != null && np2 != null) {
                const has3 = dragState.p3ScreenX !== 0 || dragState.p3ScreenY !== 0;
                if (has3) {
                    const r3 = getTimeAtX(dragState.p3ScreenX + dx); const np3 = series.coordinateToPrice(dragState.p3ScreenY + dy);
                    if (r3 && np3 != null) updateDrawingPoints(dragState.drawingId, { point1: { time: r1.time, price: np1, logical: r1.logical }, point2: { time: r2.time, price: np2, logical: r2.logical }, point3: { time: r3.time, price: np3, logical: r3.logical } });
                } else {
                    updateDrawingPoints(dragState.drawingId, { point1: { time: r1.time, price: np1, logical: r1.logical }, point2: { time: r2.time, price: np2, logical: r2.logical } });
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

    // Disable scroll during drag/drawing
    useEffect(() => {
        if (!chartRef.current) return;
        const toolActive = activeTool !== 'none';
        chartRef.current.applyOptions({
            handleScroll: { mouseWheel: !dragState.active, pressedMouseMove: !dragState.active && !toolActive, horzTouchDrag: !dragState.active, vertTouchDrag: false },
        });
    }, [dragState.active, activeTool]);

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.target as HTMLElement).tagName === 'INPUT') return;
            switch (e.key) {
                case 'Escape': cancelDrawing(); selectDrawing(null); break;
                case 'h': case 'H': setActiveTool(activeTool === 'horizontal_line' ? 'none' : 'horizontal_line'); break;
                case 't': case 'T': setActiveTool(activeTool === 'trendline' ? 'none' : 'trendline'); break;
                case 'f': case 'F': setActiveTool(activeTool === 'fibonacci' ? 'none' : 'fibonacci'); break;
                case 'r': case 'R': setActiveTool(activeTool === 'rectangle' ? 'none' : 'rectangle'); break;
                case 'v': case 'V': setActiveTool(activeTool === 'vertical_line' ? 'none' : 'vertical_line'); break;
                case 'y': case 'Y': setActiveTool(activeTool === 'ray' ? 'none' : 'ray'); break;
                case 'e': case 'E': setActiveTool(activeTool === 'extended_line' ? 'none' : 'extended_line'); break;
                case 'c': case 'C': if (!e.metaKey && !e.ctrlKey) setActiveTool(activeTool === 'circle' ? 'none' : 'circle'); break;
                case 'm': case 'M': if (!e.metaKey && !e.ctrlKey) setActiveTool(activeTool === 'measure' ? 'none' : 'measure'); break;
                case 'Delete': case 'Backspace': if (selectedDrawingId) removeDrawing(selectedDrawingId); break;
            }
            // Replay hotkeys
            if (e.shiftKey && replay.replayState.mode !== 'idle') {
                switch (e.key) {
                    case 'ArrowRight': e.preventDefault(); replay.stepForward(); break;
                    case 'ArrowLeft': e.preventDefault(); replay.stepBackward(); break;
                    case 'ArrowDown': e.preventDefault(); replay.togglePlay(); break;
                }
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [activeTool, selectedDrawingId, cancelDrawing, selectDrawing, setActiveTool, removeDrawing, replay]);

    // Drawing / Replay cursor
    useEffect(() => {
        if (!containerRef.current) return;
        containerRef.current.style.cursor = (isDrawing || replay.replayState.mode === 'selecting') ? 'crosshair' : 'default';
    }, [isDrawing, replay.replayState.mode]);

    // ====================================================================
    // Fullscreen
    // ====================================================================
    const toggleFullscreen = () => {
        const container = containerRef.current?.parentElement?.parentElement;
        if (!container) return;
        if (!document.fullscreenElement) { container.requestFullscreen(); setIsFullscreen(true); }
        else { document.exitFullscreen(); setIsFullscreen(false); }
    };

    useEffect(() => {
        const forceChartResize = () => {
            if (chartRef.current && containerRef.current) {
                const w = containerRef.current.clientWidth;
                const h = containerRef.current.clientHeight;
                if (w > 0 && h > 0) { chartRef.current.applyOptions({ width: w, height: h }); chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_OFFSET_BARS, barSpacing: 8 }); }
            }
        };
        const fsTimers: ReturnType<typeof setTimeout>[] = [];
        const handleFullscreenChange = () => {
            setIsFullscreen(!!document.fullscreenElement);
            fsTimers.push(setTimeout(forceChartResize, 50), setTimeout(forceChartResize, 200), setTimeout(forceChartResize, 500));
        };
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => { document.removeEventListener('fullscreenchange', handleFullscreenChange); fsTimers.forEach(clearTimeout); };
    }, []);

    // ====================================================================
    // Computed display values
    // ====================================================================
    const displayBar = hoveredBar || (data.length > 0 ? data[data.length - 1] : null);
    const prevBar = data.length > 1 ? data[data.length - 2] : null;
    const priceChange = displayBar && prevBar ? displayBar.close - prevBar.close : 0;
    const priceChangePercent = displayBar && prevBar && prevBar.close !== 0 ? ((priceChange / prevBar.close) * 100) : 0;
    const isPositive = priceChange >= 0;
    const activeIndicatorCount = indicators.filter(i => i.visible).length + (showVolume ? 1 : 0) + (showNewsMarkers ? 1 : 0) + (showEarningsMarkers ? 1 : 0);
    const showLiveIndicator = isLive && isMarketOpen;

    // ====================================================================
    // RENDER
    // ====================================================================
    return (
        <div className="h-full flex flex-col bg-white border border-slate-200 rounded-lg overflow-hidden">
            {minimal ? (
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-600 tracking-wide">PRICE CHART</span>
                        <span className="text-[10px] text-slate-400">1 Year</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {onOpenChart && <button onClick={onOpenChart} className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors" title="Open Chart Window">G <span className="font-normal">&gt;</span></button>}
                        {onOpenNews && <button onClick={onOpenNews} className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors" title="Open News Window">N <span className="font-normal">&gt;</span></button>}
                    </div>
                </div>
            ) : (
                <div className="flex items-center gap-0.5 px-1 py-[2px] border-b border-slate-200 bg-white text-[11px]" style={{ fontFamily }}>
                    {/* Timeframe selector */}
                    <div className="relative">
                        <button onClick={() => setShowIntervalDropdown(!showIntervalDropdown)} className="flex items-center gap-0.5 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-700 font-medium text-[12px]">
                            {INTERVALS.find(i => i.interval === selectedInterval)?.shortLabel || '1D'}
                            <ChevronDown className="w-3 h-3 text-slate-400" />
                        </button>
                        {showIntervalDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIntervalDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-xl z-50 min-w-[140px] py-1">
                                    <div className="px-2 py-0.5 text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Minutes</div>
                                    {INTERVALS.filter(i => ['1min', '2min', '5min', '15min', '30min'].includes(i.interval)).map((int) => (
                                        <button key={int.interval} onClick={() => { handleIntervalChange(int.interval); setShowIntervalDropdown(false); }}
                                            className={`w-full px-3 py-1.5 text-left text-[11px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600 font-medium' : 'text-slate-600'}`}>
                                            {int.label}
                                        </button>
                                    ))}
                                    <div className="border-t border-slate-100 my-0.5" />
                                    <div className="px-2 py-0.5 text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Hours</div>
                                    {INTERVALS.filter(i => ['1hour', '4hour', '12hour'].includes(i.interval)).map((int) => (
                                        <button key={int.interval} onClick={() => { handleIntervalChange(int.interval); setShowIntervalDropdown(false); }}
                                            className={`w-full px-3 py-1.5 text-left text-[11px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600 font-medium' : 'text-slate-600'}`}>
                                            {int.label}
                                        </button>
                                    ))}
                                    <div className="border-t border-slate-100 my-0.5" />
                                    <div className="px-2 py-0.5 text-[9px] text-slate-400 font-semibold uppercase tracking-wider">Days+</div>
                                    {INTERVALS.filter(i => ['1day', '1week', '1month', '3month', '1year'].includes(i.interval)).map((int) => (
                                        <button key={int.interval} onClick={() => { handleIntervalChange(int.interval); setShowIntervalDropdown(false); }}
                                            className={`w-full px-3 py-1.5 text-left text-[11px] hover:bg-slate-50 ${selectedInterval === int.interval ? 'bg-blue-50 text-blue-600 font-medium' : 'text-slate-600'}`}>
                                            {int.label}
                                        </button>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                    <div className="w-px h-4 bg-slate-200" />
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-500" title="Candle Type">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 4v4M9 14v6M15 4v6M15 18v2" /><rect x="7" y="8" width="4" height="6" rx="0.5" fill="currentColor" stroke="none" /><rect x="13" y="10" width="4" height="8" rx="0.5" stroke="currentColor" fill="none" /></svg>
                    </button>
                    <div className="w-px h-4 bg-slate-200" />
                    <HeaderDrawingTools activeTool={activeTool} setActiveTool={setActiveTool} />
                    <div className="w-px h-4 bg-slate-200" />
                    {/* Indicators dropdown */}
                    <div className="relative" ref={indicatorDropdownRef}>
                        <button onClick={() => setShowIndicatorDropdown(!showIndicatorDropdown)} className={`flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-[12px] font-medium ${showIndicatorDropdown || activeIndicatorCount > 0 ? 'text-blue-600' : 'text-slate-500'}`} title="Indicators">
                            <IndicatorsIcon className="w-[14px] h-[14px]" />
                            <span>Indicadores</span>
                            {activeIndicatorCount > 0 && <span className="text-[8px] bg-blue-600 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">{activeIndicatorCount}</span>}
                            <ChevronDown className="w-3 h-3 text-slate-400" />
                        </button>
                        {showIndicatorDropdown && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowIndicatorDropdown(false)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-xl z-50 min-w-[200px] max-h-[420px] overflow-y-auto py-1">
                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-b border-slate-100 sticky top-0">Overlays</div>
                                    {[{ type: 'sma', label: 'SMA' }, { type: 'ema', label: 'EMA' }, { type: 'bb', label: 'Bollinger Bands' }, { type: 'keltner', label: 'Keltner Channels' }, { type: 'vwap', label: 'VWAP' }].map(p => (
                                        <button key={p.type} onClick={() => addIndicator(p.type)} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600"><span className="flex-1 text-left">{p.label}</span></button>
                                    ))}
                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Oscillators</div>
                                    {[{ type: 'rsi', label: 'RSI' }, { type: 'macd', label: 'MACD' }, { type: 'stoch', label: 'Stochastic' }, { type: 'adx', label: 'ADX / DMI' }].map(p => (
                                        <button key={p.type} onClick={() => addIndicator(p.type)} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600"><span className="flex-1 text-left">{p.label}</span></button>
                                    ))}
                                    <div className="px-3 py-1.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-50 border-y border-slate-100">Volatility & Volume</div>
                                    {[{ type: 'atr', label: 'ATR' }, { type: 'squeeze', label: 'TTM Squeeze' }, { type: 'obv', label: 'OBV' }, { type: 'rvol', label: 'RVOL' }].map(p => (
                                        <button key={p.type} onClick={() => addIndicator(p.type)} className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 text-slate-600"><span className="flex-1 text-left">{p.label}</span></button>
                                    ))}
                                    <button onClick={() => setShowVolume(!showVolume)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showVolume ? 'text-blue-600 font-medium' : 'text-slate-600'}`}>
                                        <span className="flex-1 text-left">Volume</span>{showVolume && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>
                                    <div className="border-t border-slate-100 mt-1" />
                                    <button onClick={() => setShowNewsMarkers(!showNewsMarkers)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showNewsMarkers ? 'text-amber-600' : 'text-slate-600'}`}>
                                        <Newspaper className="w-3.5 h-3.5 flex-shrink-0" /><span className="flex-1 text-left">News Markers</span>{showNewsMarkers && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>
                                    <button onClick={() => setShowEarningsMarkers(!showEarningsMarkers)} className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-slate-50 ${showEarningsMarkers ? 'text-blue-600' : 'text-slate-600'}`}>
                                        <span className="w-3.5 h-3.5 flex-shrink-0 text-center font-bold text-[9px] leading-3 border border-current rounded-full">E</span><span className="flex-1 text-left">Earnings</span>{showEarningsMarkers && <span className="text-emerald-500 text-[9px]">&#10003;</span>}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                    <div className="w-px h-4 bg-slate-200" />
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-500" title="Layout"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="8" height="8" rx="1" /><rect x="13" y="3" width="8" height="8" rx="1" /><rect x="3" y="13" width="8" height="8" rx="1" /><rect x="13" y="13" width="8" height="8" rx="1" /></svg></button>
                    <div className="w-px h-4 bg-slate-200" />
                    <button className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-500 text-[12px]" title="Alert"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="9" /><path d="M12 8v4l2 2" /><path d="M20 4l1.5-1.5M4 4L2.5 2.5" /></svg><span>Alerta</span></button>
                    {replay.replayState.mode === 'idle' ? (
                        <button onClick={replay.enterSelectingMode} className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-slate-100 text-slate-500 text-[12px]" title="Replay">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="11,5 3,10 11,15" /><polygon points="20,5 12,10 20,15" /></svg>
                            <span>Replay</span>
                        </button>
                    ) : replay.replayState.mode === 'selecting' ? (
                        <div className="flex items-center gap-1 px-1.5 py-1 rounded bg-blue-50 text-blue-600 text-[11px] font-medium">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /></svg>
                            <span>Click en el gráfico para elegir punto de inicio</span>
                            <button onClick={replay.exitReplay} className="ml-1 px-1 rounded hover:bg-blue-100 text-blue-500">✕</button>
                        </div>
                    ) : (
                        <div className="flex items-center gap-0.5 px-1 py-0.5 rounded bg-slate-50 border border-slate-200">
                            <button onClick={() => replay.stepBackward()} className="p-0.5 rounded hover:bg-slate-200 text-slate-600" title="Step Back (Shift+←)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11,5 3,12 11,19" fill="currentColor" /><line x1="19" y1="5" x2="19" y2="19" /></svg>
                            </button>
                            <button onClick={replay.togglePlay} className="p-0.5 rounded hover:bg-slate-200 text-slate-600" title={replay.replayState.mode === 'playing' ? 'Pause (Shift+↓)' : 'Play (Shift+↓)'}>
                                {replay.replayState.mode === 'playing' ? (
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></svg>
                                ) : (
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,4 20,12 6,20" /></svg>
                                )}
                            </button>
                            <button onClick={() => replay.stepForward()} className="p-0.5 rounded hover:bg-slate-200 text-slate-600" title="Step Forward (Shift+→)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13,5 21,12 13,19" fill="currentColor" /><line x1="5" y1="5" x2="5" y2="19" /></svg>
                            </button>
                            <button onClick={replay.cycleSpeed} className="px-1.5 py-0.5 rounded hover:bg-slate-200 text-[10px] font-bold text-slate-600 min-w-[32px]" title="Speed">
                                {replay.replayState.speed}x
                            </button>
                            <div className="text-[10px] text-slate-400 px-1 tabular-nums">
                                {replay.replayState.currentIndex - replay.replayState.startIndex}/{replay.replayState.totalBars - replay.replayState.startIndex}
                            </div>
                            <button onClick={replay.exitReplay} className="p-0.5 rounded hover:bg-red-100 text-red-500 ml-0.5" title="Exit Replay">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                            </button>
                        </div>
                    )}
                    <div className="w-px h-4 bg-slate-200" />
                    <div className="flex-1" />
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-400" title="Undo"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 10h13a4 4 0 0 1 0 8H11" /><path d="M7 6l-4 4 4 4" /></svg></button>
                    <button className="p-1 rounded hover:bg-slate-100 text-slate-400" title="Redo"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 10H8a4 4 0 0 0 0 8h5" /><path d="M17 6l4 4-4 4" /></svg></button>
                    <button onClick={toggleFullscreen} className="p-1 rounded hover:bg-slate-100 text-slate-400" title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}>
                        {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                    </button>
                </div>
            )}

            <div className="flex flex-1 overflow-hidden">
                {!minimal && (
                    <ChartToolbar activeTool={activeTool} setActiveTool={setActiveTool} drawingCount={drawings.length} clearAllDrawings={clearAllDrawings} zoomIn={zoomIn} zoomOut={zoomOut} drawingsVisible={drawingsVisible} toggleDrawingsVisibility={toggleDrawingsVisibility} magnetMode={magnetMode} onCycleMagnet={() => setMagnetMode(m => m === 'off' ? 'weak' : m === 'weak' ? 'strong' : 'off')} />
                )}

                <div className="relative flex-1 overflow-hidden" data-chart-container>
                    {/* OHLC Legend */}
                    {!minimal && (
                        <div className="absolute top-1 left-2 z-10 text-[10px] pointer-events-none" style={{ fontFamily, maxWidth: '85%' }}>
                            <div className="flex items-center gap-1 flex-wrap">
                                {tickerMeta?.icon_url ? (
                                    <img src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/proxy/logo?url=${encodeURIComponent(tickerMeta.icon_url)}`} alt="" className="w-4 h-4 rounded-sm object-contain pointer-events-auto" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                                ) : (
                                    <div className="w-4 h-4 rounded-sm bg-blue-500 flex items-center justify-center text-white text-[8px] font-bold flex-shrink-0">{currentTicker?.[0] || '?'}</div>
                                )}
                                <span className="font-semibold text-slate-700">{tickerMeta?.company_name || currentTicker}</span>
                                {tickerMeta?.exchange && <span className="text-slate-400 text-[9px]">{tickerMeta.exchange}</span>}
                                {displayBar && (
                                    <>
                                        <span className="text-slate-400 ml-1">O<span className="text-slate-600 font-medium">{formatPrice(displayBar.open)}</span></span>
                                        <span className="text-slate-400">H<span className="text-emerald-600 font-medium">{formatPrice(displayBar.high)}</span></span>
                                        <span className="text-slate-400">L<span className="text-red-500 font-medium">{formatPrice(displayBar.low)}</span></span>
                                        <span className="text-slate-400">C<span className="text-slate-600 font-medium">{formatPrice(displayBar.close)}</span></span>
                                        {prevBar && <span className={`font-medium ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>{isPositive ? '+' : ''}{priceChange.toFixed(2)} ({isPositive ? '+' : ''}{priceChangePercent.toFixed(2)}%)</span>}
                                    </>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Indicator Legend */}
                    {indicators.filter(i => i.visible).length > 0 && (
                        <div className="absolute top-5 left-2 z-10 pointer-events-none">
                            <div className="pointer-events-auto flex items-center gap-1 mb-0.5">
                                <button onClick={() => setLegendExpanded(!legendExpanded)} className="text-[10px] text-slate-500 hover:text-slate-700 font-medium flex items-center gap-0.5">
                                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">{legendExpanded ? <path d="M19 9l-7 7-7-7" /> : <path d="M9 5l7 7-7 7" />}</svg>
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
                                                    <button onClick={(e) => { e.stopPropagation(); openIndicatorSettings(inst.id, e); }} className="text-slate-400 hover:text-slate-600" title="Settings"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg></button>
                                                    <button onClick={(e) => { e.stopPropagation(); removeIndicator(inst.id); }} className="text-slate-400 hover:text-red-500" title="Remove"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4h8v2M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6M10 11v6M14 11v6" /></svg></button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Price overlay */}
                    <div ref={priceOverlayRef} style={{ position: 'absolute', right: 0, display: 'none', flexDirection: 'column', alignItems: 'center', color: 'white', padding: '1px 4px', borderRadius: '2px', textAlign: 'center', zIndex: 20, pointerEvents: 'none', minWidth: '50px' }} />

                    {replay.replayState.mode !== 'idle' && replay.replayState.mode !== 'selecting' && (
                        <div className="absolute top-2 right-14 z-20 flex items-center gap-1.5 px-2 py-1 bg-orange-500/90 text-white text-[10px] font-bold rounded shadow-lg tracking-wider">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="11,5 3,10 11,15" /><polygon points="20,5 12,10 20,15" /></svg>
                            REPLAY
                        </div>
                    )}
                    {isScrolledAway && isLive && replay.replayState.mode === 'idle' && (
                        <button onClick={() => chartRef.current?.timeScale().scrollToRealTime()} className="absolute bottom-3 right-14 z-20 flex items-center gap-1 px-2 py-1 bg-blue-600 text-white text-[10px] font-medium rounded shadow-lg hover:bg-blue-700 transition-colors">
                            <Radio className="w-2.5 h-2.5" /> Realtime
                        </button>
                    )}

                    {dragState.active && (
                        <div className="absolute inset-0 z-50" style={{ cursor: dragState.dragMode === 'mid1' || dragState.dragMode === 'mid2' ? 'ns-resize' : dragState.dragMode !== 'translate' ? 'crosshair' : dragState.drawingType === 'horizontal_line' ? 'ns-resize' : dragState.drawingType === 'vertical_line' ? 'ew-resize' : 'grabbing' }} onMouseMove={handleDragMove} onMouseUp={handleDragEnd} onMouseLeave={handleDragEnd} />
                    )}

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
                            <div className="absolute z-50 bg-white rounded-lg shadow-xl border border-slate-200 p-3 min-w-[160px]" style={{ left: Math.min(editPopup.x, (containerRef.current?.clientWidth || 300) - 180), top: Math.min(editPopup.y, (containerRef.current?.clientHeight || 200) - 150) }}>
                                <div className="text-xs font-semibold text-slate-700 mb-2 pb-2 border-b border-slate-100">Edit line</div>
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Color</div>
                                    <div className="flex gap-1.5">
                                        {drawingColors.map(color => (
                                            <button key={color} onClick={() => handleEditColor(color)} className={`w-5 h-5 rounded-full transition-all ${editingDrawing.color === color ? 'ring-2 ring-offset-1 ring-slate-400 scale-110' : 'hover:scale-110'}`} style={{ backgroundColor: color }} />
                                        ))}
                                    </div>
                                </div>
                                <div className="mb-3">
                                    <div className="text-[10px] text-slate-500 mb-1.5">Width</div>
                                    <div className="flex gap-1">
                                        {[1, 2, 3, 4].map(width => (
                                            <button key={width} onClick={() => handleEditLineWidth(width)} className={`flex-1 h-6 flex items-center justify-center rounded border transition-all ${editingDrawing.lineWidth === width ? 'bg-blue-50 border-blue-300' : 'border-slate-200 hover:bg-slate-50'}`}>
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
                            <div className="flex items-center gap-2 text-slate-500"><RefreshCw className="w-5 h-5 animate-spin text-blue-500" /><span className="text-sm">Loading {currentTicker}...</span></div>
                        </div>
                    )}
                    {error && (
                        <div className="absolute inset-0 flex items-center justify-center bg-white/90 z-10">
                            <div className="text-center"><p className="text-red-500 text-sm mb-2">Failed to load chart</p><p className="text-slate-400 text-xs mb-3">{error}</p><button onClick={refetch} className="px-4 py-1.5 bg-blue-600 text-white text-xs rounded-md hover:bg-blue-700 transition-colors">Retry</button></div>
                        </div>
                    )}

                    {headerPortalTarget && createPortal(
                        <form onSubmit={ticker.handleTickerChange} className="flex items-center text-[11px]" onMouseDown={(e) => e.stopPropagation()}>
                            <TickerSearch ref={tickerSearchRef} value={inputValue} onChange={setInputValue} onSelect={ticker.handleTickerSelect} placeholder="Ticker" className="w-16" autoFocus={false} />
                        </form>,
                        headerPortalTarget
                    )}

                    <div ref={containerRef} className="h-full w-full" onMouseDown={activeTool === 'none' && !minimal ? handleDragStart : undefined} onContextMenu={!minimal ? handleChartContextMenu : undefined} style={{ cursor: hoveredDrawingId && activeTool === 'none' ? 'grab' : isDrawing ? 'crosshair' : 'default' }} />

                    {ctxMenu.visible && (
                        <ChartContextMenu state={ctxMenu} ticker={currentTicker} interval={selectedInterval} range={selectedRange} data={data} indicatorResults={indicatorResults} drawings={drawings} activeIndicators={indicators.filter(i => i.visible)} chartApi={chartRef.current} onClose={() => setCtxMenu(prev => ({ ...prev, visible: false }))} />
                    )}
                </div>
            </div>

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

            {indicatorSettingsOpen && (
                <IndicatorSettingsDialog indicatorId={indicatorSettingsOpen} instanceData={indicators.find(i => i.id === indicatorSettingsOpen)} onClose={() => setIndicatorSettingsOpen(null)} onApply={onApplyIndicatorSettings} position={indicatorSettingsPos} />
            )}
        </div>
    );
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
