'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { ISeriesPrimitive, Time } from 'lightweight-charts';
import { useLiveChartData } from '@/hooks/useLiveChartData';
import { useChartDrawings, type Drawing } from '@/hooks/useChartDrawings';
import {
    useUserPreferencesStore,
    selectFont,
    selectChartPrefs,
    type ChartCandleStyle,
} from '@/stores/useUserPreferencesStore';
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
import { ChartToolbar } from './ChartToolbar';
import { IndicatorSettingsDialog } from './IndicatorSettingsDialog';
import { ChartContextMenu, type ContextMenuState } from './ChartContextMenu';
import {
    RIGHT_OFFSET_BARS,
    type TradingChartProps,
    type Interval,
    type TimeRange,
    type ChartBar,
} from './constants';
import { formatVolume } from './formatters';
import { RefreshIcon } from './icons';

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
    useEventMarkers,
    useTickerManagement,
    useBarReplay,
    useExtendedHoursPrice,
} from './hooks';

// New UI sub-components
import { ChartProvider, type ChartContextValue, type CandleStyle, type MagnetMode } from './ChartContext';
import { ChartHeader } from './ChartHeader';
import { ChartOHLCOverlay } from './ChartOHLCOverlay';
import { ChartIndicatorLegend } from './ChartIndicatorLegend';
import { ChartReplayOverlay } from './ChartReplayOverlay';
import { ChartRealtimeJump } from './ChartLiveBadge';
import { ChartDrawingDialog } from './ChartDrawingDialog';
import { ChartSettingsDialog } from './ChartSettingsDialog';
import { ChartEarningsPopup } from './ChartEarningsPopup';
import type { EarningsRecord } from './hooks/useEarningsMarkers';

// ============================================================================
// Component
// ============================================================================

function TradingChartComponent({
    ticker: initialTicker = 'AAPL',
    onTickerChange,
    minimal = false,
    onOpenChart,
    onOpenNews,
}: TradingChartProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const tickerSearchRef = useRef<TickerSearchRef>(null);
    const priceOverlayRef = useRef<HTMLDivElement>(null);

    // ── User preferences ────────────────────────────────────────────────
    const font = useUserPreferencesStore(selectFont);
    const chartPrefs = useUserPreferencesStore(selectChartPrefs);
    const setCandleStylePref = useUserPreferencesStore(s => s.setCandleStyle);
    const setChartGridVisible = useUserPreferencesStore(s => s.setChartGridVisible);
    const setChartWatermarkVisible = useUserPreferencesStore(s => s.setChartWatermarkVisible);
    const setChartLogScale = useUserPreferencesStore(s => s.setChartLogScale);
    const fontFamily = `var(--font-${font})`;

    // ── Ticker management ────────────────────────────────────────────────
    const ticker = useTickerManagement(initialTicker, tickerSearchRef, onTickerChange);
    const {
        currentTicker, inputValue, setInputValue, windowId, windowState,
        openWindow, tickerMeta, isMarketOpen,
    } = ticker;

    // ── Interval / range / view state ────────────────────────────────────
    const [selectedInterval, setSelectedInterval] = useState<Interval>(windowState.interval || '1day');
    const [selectedRange, setSelectedRange] = useState<TimeRange>(windowState.range || '1Y');
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);

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

    // ── Replay timestamp tracker ─────────────────────────────────────────
    const [replayTimestamp, setReplayTimestamp] = useState<number | null>(null);
    const replayTimeRef = useRef<number | null>(null);

    const handleIntervalChange = useCallback((newInterval: Interval) => {
        if (replayTimeRef.current) {
            setReplayTimestamp(replayTimeRef.current);
        }
        setSelectedInterval(newInterval);
    }, []);

    // dataRef is declared further down (after `data` is loaded) but the chart
    // crosshair needs it. Declare an early stable ref and keep it in sync below.
    const dataRefForChart = useRef<ChartBar[]>([]);

    // ── Chart initialization ────────────────────────────────────────────
    const chartCore = useChartInit(
        containerRef, currentTicker, selectedInterval, fontFamily, priceOverlayRef,
        { candleStyle: chartPrefs.candleStyle, dataRef: dataRefForChart },
    );
    const {
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef,
        whitespaceSeriesRef, lastPriceInfoRef, beforeDestroyCallbackRef,
        chartVersion, hoveredBar,
    } = chartCore;

    // ── Live data ────────────────────────────────────────────────────────
    const {
        data, loading, loadingMore, error, hasMore, isLive,
        refetch, loadMore, loadForward, registerUpdateHandler, registerExtendedHoursHandler,
    } = useLiveChartData(currentTicker, selectedInterval, replayTimestamp);

    // ── Indicators ───────────────────────────────────────────────────────
    const ind = useChartIndicators(chartRef, data, currentTicker, selectedInterval, selectedRange, windowState);
    const {
        indicators, nextInstanceIdRef,
        showVolume, setShowVolume,
        showNewsMarkers, setShowNewsMarkers,
        showEarningsMarkers, setShowEarningsMarkers,
        selectedIndicator, setSelectedIndicator,
        legendExpanded, setLegendExpanded,
        indicatorSettingsOpen, setIndicatorSettingsOpen, indicatorSettingsPos,
        indicatorResults,
        indicatorSeriesRef, panelPaneIndexRef,
        addIndicator, openIndicatorSettings, removeIndicator, onApplyIndicatorSettings,
        workerReady, calculate, clearCache,
    } = ind;

    // ── Replay-gate ref (shared between useChartData and useBarReplay) ──
    const replayControlsDataRef = useRef(false);

    // ── News + Earnings event streams (consolidated into one primitive) ─
    const news = useChartNews(candleSeriesRef, data, selectedInterval, currentTicker, showNewsMarkers, openWindow);
    const { newsEvents, newsTimeMapRef, showNewsMarkersRef, handleNewsMarkerClickRef } = news;
    const { earningsEvents } = useEarningsMarkers(currentTicker, showEarningsMarkers);

    const eventStreams = useMemo(() => [earningsEvents, newsEvents], [earningsEvents, newsEvents]);
    const { primitiveRef: eventPrimitiveRef } = useEventMarkers({
        candleSeriesRef, data, streams: eventStreams, chartVersion,
    });

    // ── Chart data updates (candle/volume/whitespace) ───────────────────
    const { isScrolledAway } = useChartData(
        chartRef, candleSeriesRef, volumeSeriesRef, whitespaceSeriesRef, lastPriceInfoRef,
        data, currentTicker, selectedInterval, hasMore, loadingMore, loadMore,
        replayControlsDataRef, chartVersion, chartPrefs.candleStyle,
    );

    // ── Session background ──────────────────────────────────────────────
    useSessionBackground(sessionBgSeriesRef, data, selectedInterval, replayControlsDataRef);

    // ── Bar replay (runs after useChartData / useSessionBackground) ─────
    const replay = useBarReplay(
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef, whitespaceSeriesRef,
        indicatorSeriesRef, lastPriceInfoRef, data, selectedInterval,
        indicators, indicatorResults, replayControlsDataRef, chartVersion,
        setReplayTimestamp, replayTimeRef, loadForward, chartPrefs.candleStyle,
    );

    const isReplayActive = replay.replayState.mode !== 'idle';

    // ── Indicator series on chart ───────────────────────────────────────
    useIndicatorSeries(
        chartRef, indicatorSeriesRef, panelPaneIndexRef,
        indicators, indicatorResults, data, currentTicker,
        selectedInterval, selectedRange, workerReady,
        calculate, clearCache, volumeSeriesRef, showVolume,
        chartVersion, isReplayActive,
    );

    // ── Realtime updates ────────────────────────────────────────────────
    useChartRealtime(
        chartRef, candleSeriesRef, volumeSeriesRef, sessionBgSeriesRef, whitespaceSeriesRef,
        indicatorSeriesRef, lastPriceInfoRef, data, selectedInterval, indicators,
        registerUpdateHandler, isReplayActive, chartPrefs.candleStyle,
    );

    // ── Extended hours price (pre/post market label on daily+) ─────────
    useExtendedHoursPrice({
        candleSeriesRef, priceOverlayRef, selectedInterval,
        currentSession: ticker.marketSession?.current_session ?? null,
        ticker: currentTicker,
        isReplayActive, registerExtendedHoursHandler,
    });

    // ── Zoom / time range ───────────────────────────────────────────────
    const { zoomIn, zoomOut, handleRangeChange } = useChartZoom(
        chartRef, data, currentTicker, selectedInterval, selectedRange,
        handleIntervalChange, setSelectedRange, isReplayActive,
    );

    // ── Persist window state ────────────────────────────────────────────
    useEffect(() => {
        ticker.persistState(selectedInterval, selectedRange, showVolume, indicators, nextInstanceIdRef.current);
    }, [currentTicker, selectedInterval, selectedRange, showVolume, indicators]);

    // ── Broadcast active chart for AI agent ─────────────────────────────
    useEffect(() => {
        if (!data || data.length === 0 || !currentTicker) return;
        const detail = { ticker: currentTicker, interval: selectedInterval, range: selectedRange, barCount: data.length };
        window.dispatchEvent(new CustomEvent('agent:chart-active', { detail }));
        return () => { window.dispatchEvent(new CustomEvent('agent:chart-active', { detail: null })); };
    }, [currentTicker, selectedInterval, selectedRange, data?.length]);

    // ── AI context menu ─────────────────────────────────────────────────
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

    // ────────────────────────────────────────────────────────────────────
    // Drawing tools
    // ────────────────────────────────────────────────────────────────────
    const {
        drawings, activeTool, isDrawing, selectedDrawingId, hoveredDrawingId,
        pendingDrawing, tentativeEndpoint,
        locked: drawingsLocked, toggleLocked: toggleDrawingsLocked,
        canUndo, canRedo, undo, redo,
        setActiveTool, cancelDrawing, handleChartClick, updateTentativeEndpoint,
        removeDrawing, clearAllDrawings, selectDrawing,
        updateHorizontalLinePrice, updateVerticalLineTime, updateDrawingPoints,
        updateDrawing, replaceDrawing,
        startDragging, stopDragging,
        findDrawingNearPrice, setHoveredDrawing, colors: drawingColors,
    } = useChartDrawings(currentTicker);

    const [drawingsVisible, setDrawingsVisible] = useState(true);
    const toggleDrawingsVisibility = useCallback(() => setDrawingsVisible(prev => !prev), []);

    const [editPopup, setEditPopup] = useState<{ visible: boolean; drawingId: string | null; x: number; y: number }>(
        { visible: false, drawingId: null, x: 0, y: 0 },
    );
    const editingDrawing = editPopup.drawingId ? drawings.find(d => d.id === editPopup.drawingId) : null;

    // Earnings click popup
    const [earningsPopup, setEarningsPopup] = useState<{
        visible: boolean;
        record: EarningsRecord | null;
        x: number;
        y: number;
    }>({ visible: false, record: null, x: 0, y: 0 });
    const openEarningsPopup = useCallback((p: { record: EarningsRecord; x: number; y: number }) => {
        setEarningsPopup({ visible: true, record: p.record, x: p.x, y: p.y });
    }, []);
    const closeEarningsPopup = useCallback(() => {
        setEarningsPopup({ visible: false, record: null, x: 0, y: 0 });
    }, []);
    const openEarningsPopupRef = useRef(openEarningsPopup);
    openEarningsPopupRef.current = openEarningsPopup;

    const openEditPopup = useCallback((drawingId: string, x: number, y: number) => {
        setEditPopup({ visible: true, drawingId, x, y });
        selectDrawing(drawingId);
    }, [selectDrawing]);
    const closeEditPopup = useCallback(() => setEditPopup({ visible: false, drawingId: null, x: 0, y: 0 }), []);
    const handleDialogUpdate = useCallback((patch: Partial<Drawing>) => {
        if (editPopup.drawingId) updateDrawing(editPopup.drawingId, patch);
    }, [editPopup.drawingId, updateDrawing]);
    const handleDialogReplace = useCallback((next: Drawing) => {
        if (editPopup.drawingId) replaceDrawing(editPopup.drawingId, next);
    }, [editPopup.drawingId, replaceDrawing]);
    const handleDialogDelete = useCallback(() => {
        if (editPopup.drawingId) { removeDrawing(editPopup.drawingId); closeEditPopup(); }
    }, [editPopup.drawingId, removeDrawing, closeEditPopup]);

    // Drawing primitive refs
    const drawingPrimitivesRef = useRef<Map<string, ISeriesPrimitive<Time>>>(new Map());
    const tentativePrimitiveRef = useRef<TentativePrimitive | null>(null);
    const dataTimes = useMemo(() => data.map(d => d.time), [data]);
    const dataTimesRef = useRef(dataTimes);
    dataTimesRef.current = dataTimes;
    const dataRef = useRef(data);
    dataRef.current = data;
    // Keep the chart's hover-resolution data ref in sync.
    dataRefForChart.current = data;

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

    // ── Ctrl key tracking for magnet snap ───────────────────────────────
    useEffect(() => {
        const down = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlPressedRef.current = true; };
        const up = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlPressedRef.current = false; };
        const blur = () => { ctrlPressedRef.current = false; };
        window.addEventListener('keydown', down);
        window.addEventListener('keyup', up);
        window.addEventListener('blur', blur);
        return () => {
            window.removeEventListener('keydown', down);
            window.removeEventListener('keyup', up);
            window.removeEventListener('blur', blur);
        };
    }, []);

    /** Magnet: snap raw price to nearest OHLC of bar at screenX. */
    const snapPriceToOHLC = useCallback((rawPrice: number, screenX: number): number => {
        const ctrl = ctrlPressedRef.current;
        const mode = magnetModeRef.current;
        const hasToolActive = activeToolRef.current !== 'none';
        if (!hasToolActive) return rawPrice;
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

    // ── Pre-destroy cleanup: detach all primitives before chart.remove() ─
    beforeDestroyCallbackRef.current = () => {
        const series = candleSeriesRef.current;
        if (series) {
            for (const [, prim] of drawingPrimitivesRef.current) {
                try { series.detachPrimitive(prim); } catch { /* */ }
            }
            if (tentativePrimitiveRef.current) {
                try { series.detachPrimitive(tentativePrimitiveRef.current); } catch { /* */ }
            }
            if (eventPrimitiveRef.current) {
                try { series.detachPrimitive(eventPrimitiveRef.current); } catch { /* */ }
            }
        }
        drawingPrimitivesRef.current.clear();
        tentativePrimitiveRef.current = null;
        indicatorSeriesRef.current.clear();
        panelPaneIndexRef.current.clear();
    };

    // ── Sync drawings to primitives (respects drawingsVisible) ──────────
    useEffect(() => {
        if (!candleSeriesRef.current || dataTimes.length === 0) return;
        const series = candleSeriesRef.current;
        const currentPrimitives = drawingPrimitivesRef.current;

        // Drawings hidden → detach everything
        if (!drawingsVisible) {
            for (const [, prim] of currentPrimitives) {
                try { series.detachPrimitive(prim); } catch { /* */ }
            }
            currentPrimitives.clear();
            return;
        }

        // Remove primitives whose drawing no longer exists
        for (const [id, primitive] of currentPrimitives) {
            if (!drawings.find(d => d.id === id)) {
                try { series.detachPrimitive(primitive); } catch { /* */ }
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
    }, [drawings, selectedDrawingId, hoveredDrawingId, chartVersion, dataTimes, drawingsVisible]);

    // ── Auto-loadMore for out-of-range drawings ─────────────────────────
    const autoLoadTriggeredRef = useRef(false);
    useEffect(() => { autoLoadTriggeredRef.current = false; }, [selectedInterval]);
    useEffect(() => {
        if (replayControlsDataRef.current) return;
        if (!hasMore || loadingMore || dataTimes.length === 0 || drawings.length === 0) return;
        if (autoLoadTriggeredRef.current) return;
        const firstDataTime = dataTimes[0];
        const hasOutOfRange = drawings.some(d => {
            if (d.type === 'horizontal_line') return false;
            if (d.type === 'vertical_line') return (d as any).time < firstDataTime;
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

    // ── Tentative drawing primitive ─────────────────────────────────────
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
                screenX: tentativeEndpoint?.x ?? -1,
                screenY: tentativeEndpoint?.y ?? -1,
                mousePrice: tentativeEndpoint?.price ?? pendingDrawing.point1.price,
                color: drawingColors[0],
            });
        } else {
            tentativePrimitiveRef.current.setState(null);
        }
    }, [pendingDrawing, tentativeEndpoint, drawingColors, chartVersion, dataTimes]);

    // ── Drag state ──────────────────────────────────────────────────────
    type DragMode = 'translate' | 'anchor1' | 'anchor2' | 'anchor3' | 'anchor4' | 'mid1' | 'mid2';
    const [dragState, setDragState] = useState<{
        active: boolean; drawingId: string | null; drawingType: string | null;
        dragMode: DragMode;
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

    // ── Click handler: selection / news / event markers ────────────────
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
            // Earnings marker hit-test (chart-pane coords). Open the details popup.
            const earningsHit = eventPrimitiveRef.current?.hitTestEvent(param.point.x, param.point.y);
            if (earningsHit && earningsHit.kind === 'earnings' && earningsHit.payload) {
                openEarningsPopupRef.current({
                    record: earningsHit.payload as EarningsRecord,
                    x: param.point.x,
                    y: param.point.y,
                });
                return;
            }
            if (showNewsMarkersRef.current && param.time && newsTimeMapRef.current.has(param.time as number)) {
                handleNewsMarkerClickRef.current(param.time as number);
                return;
            }
            let hitId: string | null = null;
            for (const [, primitive] of drawingPrimitivesRef.current) {
                const hit = (primitive as any).hitTest?.(param.point.x, param.point.y);
                if (hit) {
                    const eid = (hit.externalId ?? '') as string;
                    hitId = (eid.endsWith(':p1') || eid.endsWith(':p2') || eid.endsWith(':p3') || eid.endsWith(':p4') || eid.endsWith(':m1') || eid.endsWith(':m2'))
                        ? eid.slice(0, -3) : eid;
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

    // ── DOM click for drawing tools ─────────────────────────────────────
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

    // ── Hover detection ─────────────────────────────────────────────────
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

    // ── Mouse tracking for tentative drawing endpoint ───────────────────
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

    // ── Magnet: snap crosshair to nearest OHLC on mouse move ────────────
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
        const handleMouseLeave = () => { chartRef.current?.clearCrosshairPosition(); };
        container.addEventListener('mousemove', handleMouseMove);
        container.addEventListener('mouseleave', handleMouseLeave);
        return () => {
            container.removeEventListener('mousemove', handleMouseMove);
            container.removeEventListener('mouseleave', handleMouseLeave);
        };
    }, [chartVersion]);

    // ── Drag handlers ───────────────────────────────────────────────────
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if (activeTool !== 'none' || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        if (editPopup.visible) return;
        if (drawingsLocked) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        let hitId: string | null = null;
        let dragMode: DragMode = 'translate';
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
    }, [activeTool, drawings, selectDrawing, startDragging, editPopup.visible, dataTimes, drawingsLocked]);

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
            handleScroll: {
                mouseWheel: !dragState.active,
                pressedMouseMove: !dragState.active && !toolActive,
                horzTouchDrag: !dragState.active,
                vertTouchDrag: false,
            },
        });
    }, [dragState.active, activeTool]);

    // ── Keyboard shortcuts ─────────────────────────────────────────────
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            const tag = (e.target as HTMLElement).tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;

            // Undo / redo
            if ((e.metaKey || e.ctrlKey) && (e.key === 'z' || e.key === 'Z')) {
                e.preventDefault();
                if (e.shiftKey) {
                    if (canRedo) redo();
                } else {
                    if (canUndo) undo();
                }
                return;
            }
            if ((e.metaKey || e.ctrlKey) && (e.key === 'y' || e.key === 'Y')) {
                e.preventDefault();
                if (canRedo) redo();
                return;
            }

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
    }, [activeTool, selectedDrawingId, cancelDrawing, selectDrawing, setActiveTool, removeDrawing, replay, canUndo, canRedo, undo, redo]);

    // Drawing / replay cursor
    useEffect(() => {
        if (!containerRef.current) return;
        containerRef.current.style.cursor = (isDrawing || replay.replayState.mode === 'selecting') ? 'crosshair' : 'default';
    }, [isDrawing, replay.replayState.mode]);

    // ────────────────────────────────────────────────────────────────────
    // Fullscreen
    // ────────────────────────────────────────────────────────────────────
    const toggleFullscreen = useCallback(() => {
        const container = containerRef.current?.parentElement?.parentElement;
        if (!container) return;
        if (!document.fullscreenElement) { container.requestFullscreen(); setIsFullscreen(true); }
        else { document.exitFullscreen(); setIsFullscreen(false); }
    }, []);

    useEffect(() => {
        const forceChartResize = () => {
            if (chartRef.current && containerRef.current) {
                const w = containerRef.current.clientWidth;
                const h = containerRef.current.clientHeight;
                if (w > 0 && h > 0) {
                    chartRef.current.applyOptions({ width: w, height: h });
                    chartRef.current.timeScale().applyOptions({ rightOffset: RIGHT_OFFSET_BARS, barSpacing: 8 });
                }
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

    // ────────────────────────────────────────────────────────────────────
    // Apply grid / log-scale preferences live
    // ────────────────────────────────────────────────────────────────────
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;
        chart.applyOptions({
            grid: {
                vertLines: { visible: chartPrefs.gridVisible },
                horzLines: { visible: chartPrefs.gridVisible },
            },
            rightPriceScale: {
                mode: chartPrefs.logScale ? 1 /* PriceScaleMode.Logarithmic */ : 0 /* Normal */,
            },
        });
    }, [chartPrefs.gridVisible, chartPrefs.logScale, chartVersion]);

    // ────────────────────────────────────────────────────────────────────
    // Computed display values
    // ────────────────────────────────────────────────────────────────────
    const displayBar = hoveredBar || (data.length > 0 ? data[data.length - 1] : null);
    const prevBar = useMemo(() => {
        if (!displayBar || data.length < 2) return null;
        const idx = data.findIndex(b => b.time === displayBar.time);
        if (idx > 0) return data[idx - 1];
        return data[data.length - 2] ?? null;
    }, [displayBar, data]);
    const activeIndicatorCount = indicators.filter(i => i.visible).length
        + (showVolume ? 1 : 0) + (showNewsMarkers ? 1 : 0) + (showEarningsMarkers ? 1 : 0);
    const showLiveIndicator = isLive && isMarketOpen;

    const cycleMagnet = useCallback(() => {
        setMagnetMode(m => m === 'off' ? 'weak' : m === 'weak' ? 'strong' : 'off');
    }, []);

    const takeScreenshot = useCallback(() => {
        const chart = chartRef.current;
        if (!chart) return;
        const canvas = chart.takeScreenshot();
        canvas.toBlob((blob) => {
            if (!blob) return;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentTicker}_${selectedInterval}_${new Date().toISOString().slice(0, 10)}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    }, [currentTicker, selectedInterval]);

    // ────────────────────────────────────────────────────────────────────
    // Context value
    // ────────────────────────────────────────────────────────────────────
    const ctxValue: ChartContextValue = {
        chartRef, candleSeriesRef, volumeSeriesRef, containerRef,
        currentTicker, tickerMeta, isMarketOpen,
        selectedInterval, selectedRange,
        handleIntervalChange, handleRangeChange,
        data, hoveredBar, displayBar, prevBar,
        loading, loadingMore, hasMore, error, refetch,
        indicators, indicatorResults,
        showVolume, setShowVolume,
        showNewsMarkers, setShowNewsMarkers,
        showEarningsMarkers, setShowEarningsMarkers,
        addIndicator, removeIndicator, openIndicatorSettings,
        setSelectedIndicator, selectedIndicator,
        legendExpanded, setLegendExpanded,
        activeIndicatorCount,
        isLive, showLiveIndicator, isScrolledAway,
        replayState: replay.replayState,
        isReplayActive,
        enterSelectingMode: replay.enterSelectingMode,
        exitReplay: replay.exitReplay,
        togglePlay: replay.togglePlay,
        stepForward: replay.stepForward,
        stepBackward: replay.stepBackward,
        cycleSpeed: replay.cycleSpeed,
        activeTool, setActiveTool,
        drawingCount: drawings.length, clearAllDrawings,
        drawingsVisible, toggleDrawingsVisibility,
        drawingsLocked, toggleDrawingsLocked,
        canUndo, canRedo, undo, redo,
        isFullscreen, toggleFullscreen,
        magnetMode, cycleMagnet, setMagnetMode,
        zoomIn, zoomOut,
        candleStyle: chartPrefs.candleStyle as CandleStyle,
        setCandleStyle: (s: CandleStyle) => setCandleStylePref(s as ChartCandleStyle),
        gridVisible: chartPrefs.gridVisible,
        setGridVisible: setChartGridVisible,
        watermarkVisible: chartPrefs.watermarkVisible,
        setWatermarkVisible: setChartWatermarkVisible,
        logScale: chartPrefs.logScale,
        setLogScale: setChartLogScale,
        openSettings: () => setSettingsOpen(true),
        closeSettings: () => setSettingsOpen(false),
        settingsOpen,
        takeScreenshot,
        fontFamily,
    };

    // ────────────────────────────────────────────────────────────────────
    // RENDER
    // ────────────────────────────────────────────────────────────────────
    return (
        <ChartProvider value={ctxValue}>
            <div className="h-full flex flex-col bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg overflow-hidden">
                {minimal ? (
                    <MinimalHeader onOpenChart={onOpenChart} onOpenNews={onOpenNews} />
                ) : (
                    <ChartHeader />
                )}

                <div className="flex flex-1 overflow-hidden">
                    {!minimal && (
                        <ChartToolbar
                            activeTool={activeTool}
                            setActiveTool={setActiveTool}
                            drawingCount={drawings.length}
                            clearAllDrawings={clearAllDrawings}
                            zoomIn={zoomIn}
                            zoomOut={zoomOut}
                            magnetMode={magnetMode}
                            onCycleMagnet={cycleMagnet}
                        />
                    )}

                    <div className="relative flex-1 overflow-hidden" data-chart-container>
                        {!minimal && <ChartOHLCOverlay />}
                        {!minimal && <ChartIndicatorLegend />}

                        {/* Price overlay (lightweight-charts price label) */}
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

                        <ChartReplayOverlay />
                        {replay.replayState.mode === 'idle' && <ChartRealtimeJump />}

                        {dragState.active && (
                            <div
                                className="absolute inset-0 z-50"
                                style={{
                                    cursor: dragState.dragMode === 'mid1' || dragState.dragMode === 'mid2'
                                        ? 'ns-resize'
                                        : dragState.dragMode !== 'translate'
                                            ? 'crosshair'
                                            : dragState.drawingType === 'horizontal_line'
                                                ? 'ns-resize'
                                                : dragState.drawingType === 'vertical_line'
                                                    ? 'ew-resize'
                                                    : 'grabbing',
                                }}
                                onMouseMove={handleDragMove}
                                onMouseUp={handleDragEnd}
                                onMouseLeave={handleDragEnd}
                            />
                        )}

                        {isDrawing && (
                            <div className="absolute top-1 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-2 py-1 bg-[color:var(--color-primary)] text-white text-[10px] font-medium rounded shadow-lg">
                                <span>
                                    {pendingDrawing
                                        ? 'Click el segundo punto'
                                        : activeTool === 'horizontal_line'
                                            ? 'Click para colocar la línea'
                                            : 'Click el primer punto'}
                                </span>
                                <button onClick={cancelDrawing} className="hover:bg-white/10 rounded px-1">✕</button>
                            </div>
                        )}

                        {editPopup.visible && editingDrawing && (
                            <ChartDrawingDialog
                                drawing={editingDrawing}
                                colors={drawingColors}
                                initialX={editPopup.x}
                                initialY={editPopup.y}
                                containerWidth={containerRef.current?.clientWidth || 300}
                                containerHeight={containerRef.current?.clientHeight || 200}
                                onClose={closeEditPopup}
                                onUpdate={handleDialogUpdate}
                                onReplace={handleDialogReplace}
                                onDelete={handleDialogDelete}
                            />
                        )}

                        {earningsPopup.visible && earningsPopup.record && (
                            <ChartEarningsPopup
                                record={earningsPopup.record}
                                ticker={currentTicker}
                                x={earningsPopup.x}
                                y={earningsPopup.y}
                                containerWidth={containerRef.current?.clientWidth || 300}
                                containerHeight={containerRef.current?.clientHeight || 200}
                                onClose={closeEarningsPopup}
                            />
                        )}

                        {loading && (
                            <div className="absolute inset-0 flex items-center justify-center bg-[color:var(--color-surface)]/90 z-10">
                                <div className="flex items-center gap-2 text-[color:var(--color-muted-fg)]">
                                    <RefreshIcon className="w-5 h-5 animate-spin text-[color:var(--color-primary)]" />
                                    <span className="text-sm">Cargando {currentTicker}...</span>
                                </div>
                            </div>
                        )}
                        {error && (
                            <div className="absolute inset-0 flex items-center justify-center bg-[color:var(--color-surface)]/90 z-10">
                                <div className="text-center">
                                    <p className="text-[color:var(--color-danger)] text-sm mb-2">No se pudo cargar el gráfico</p>
                                    <p className="text-[color:var(--color-muted-fg)] text-xs mb-3">{error}</p>
                                    <button onClick={refetch} className="px-4 py-1.5 bg-[color:var(--color-primary)] text-white text-xs rounded-md hover:bg-[color:var(--color-primary-hover)] transition-colors">
                                        Reintentar
                                    </button>
                                </div>
                            </div>
                        )}

                        {headerPortalTarget && createPortal(
                            <form
                                onSubmit={ticker.handleTickerChange}
                                className="flex items-center text-[11px]"
                                onMouseDown={(e) => e.stopPropagation()}
                            >
                                <TickerSearch
                                    ref={tickerSearchRef}
                                    value={inputValue}
                                    onChange={setInputValue}
                                    onSelect={ticker.handleTickerSelect}
                                    placeholder="Ticker"
                                    className="w-16"
                                    autoFocus={false}
                                />
                            </form>,
                            headerPortalTarget,
                        )}

                        <div
                            ref={containerRef}
                            className="h-full w-full"
                            onMouseDown={activeTool === 'none' && !minimal ? handleDragStart : undefined}
                            onContextMenu={!minimal ? handleChartContextMenu : undefined}
                            style={{
                                cursor:
                                    hoveredDrawingId && activeTool === 'none'
                                        ? 'grab'
                                        : isDrawing
                                            ? 'crosshair'
                                            : 'default',
                            }}
                        />

                        <ChartSettingsDialog />

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

                {!minimal && (
                    <div
                        className="flex items-center justify-end px-2 py-0.5 border-t border-[color:var(--color-border-subtle)] text-[9px]"
                        style={{ fontFamily }}
                    >
                        <div className="flex items-center gap-2 text-[color:var(--color-muted-fg)]">
                            {displayBar && <span className="font-mono">V:{formatVolume(displayBar.volume)}</span>}
                            {loadingMore && <RefreshIcon className="w-2.5 h-2.5 animate-spin text-[color:var(--color-primary)]" />}
                            <span>{data.length.toLocaleString()} bars</span>
                            {hasMore && !loadingMore && <span>← more</span>}
                        </div>
                    </div>
                )}

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
        </ChartProvider>
    );
}

function MinimalHeader({
    onOpenChart, onOpenNews,
}: { onOpenChart?: () => void; onOpenNews?: () => void }) {
    return (
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-[color:var(--color-border)] bg-[color:var(--color-surface-hover)]">
            <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-[color:var(--color-fg)]/80 tracking-wide">PRICE CHART</span>
                <span className="text-[10px] text-[color:var(--color-muted-fg)]">1 Year</span>
            </div>
            <div className="flex items-center gap-2">
                {onOpenChart && (
                    <button
                        onClick={onOpenChart}
                        className="text-xs font-bold text-[color:var(--color-primary)] hover:opacity-80"
                        title="Abrir gráfico"
                    >
                        G <span className="font-normal">&gt;</span>
                    </button>
                )}
                {onOpenNews && (
                    <button
                        onClick={onOpenNews}
                        className="text-xs font-bold text-[color:var(--color-primary)] hover:opacity-80"
                        title="Abrir noticias"
                    >
                        N <span className="font-normal">&gt;</span>
                    </button>
                )}
            </div>
        </div>
    );
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
