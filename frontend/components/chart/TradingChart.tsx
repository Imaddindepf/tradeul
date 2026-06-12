'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLiveChartData } from '@/hooks/useLiveChartData';
import { useChartDrawings, type Drawing } from '@/hooks/useChartDrawings';
import {
    useUserPreferencesStore,
    selectFont,
    selectChartPrefs,
    type ChartCandleStyle,
} from '@/stores/useUserPreferencesStore';
import { TickerSearch, type TickerSearchRef } from '@/components/common/TickerSearch';
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
import { useDrawingInteractions } from './hooks/useDrawingInteractions';

// New UI sub-components
import { ChartProvider, type ChartContextValue, type CandleStyle, type MagnetMode } from './ChartContext';
import { useDisplayBar } from './hoveredBarStore';
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
    controlledInterval,
    onIntervalChange: onIntervalChangeExternal,
    onChartReady,
    cellOverlay,
    inLayoutMode = false,
    hideHeader: hideHeaderProp,
    hideToolbar: hideToolbarProp,
    onContextValue,
    windowId: explicitWindowId,
}: TradingChartProps) {
    // In layout mode, the parent window owns header and toolbar by default.
    // Callers can still override per-prop if they want to keep the in-chart
    // chrome for an unusual case (we don't currently do this in code).
    const hideHeader = hideHeaderProp ?? inLayoutMode;
    const hideToolbar = hideToolbarProp ?? inLayoutMode;
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
    const ticker = useTickerManagement(initialTicker, tickerSearchRef, onTickerChange, { inLayoutMode });
    const {
        currentTicker, inputValue, setInputValue, windowId, windowState,
        openWindow, tickerMeta, isMarketOpen,
    } = ticker;

    // ── Interval / range / view state ────────────────────────────────────
    // When `controlledInterval` is provided, the parent owns the interval
    // (multi-chart sync flow). Otherwise we keep our own local state.
    const intervalIsControlled = controlledInterval !== undefined;
    const [internalInterval, setInternalInterval] = useState<Interval>(windowState.interval || '1day');
    const selectedInterval: Interval = intervalIsControlled
        ? (controlledInterval as Interval)
        : internalInterval;
    const setSelectedInterval = useCallback((next: Interval) => {
        // Stays as a no-op for the controlled path — parent will eventually
        // push a new prop value down. The internal updater stays for the
        // uncontrolled branch.
        if (!intervalIsControlled) setInternalInterval(next);
    }, [intervalIsControlled]);
    const [selectedRange, setSelectedRange] = useState<TimeRange>(windowState.range || '1Y');
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);

    const [magnetMode, setMagnetMode] = useState<MagnetMode>('off');
    const magnetModeRef = useRef<MagnetMode>('off');
    magnetModeRef.current = magnetMode;

    // ── Portal for TickerSearch in floating window header ────────────────
    // Disabled in layout mode: the window header is shared across cells,
    // so each cell relies on `cellOverlay` instead of leaking its search box.
    const [headerPortalTarget, setHeaderPortalTarget] = useState<HTMLElement | null>(null);
    useEffect(() => {
        if (windowId && !minimal && !inLayoutMode) {
            const el = document.getElementById(`window-header-extra-${windowId}`);
            if (el) setHeaderPortalTarget(el);
        } else {
            setHeaderPortalTarget(null);
        }
    }, [windowId, minimal, inLayoutMode]);

    // ── Replay timestamp tracker ─────────────────────────────────────────
    const [replayTimestamp, setReplayTimestamp] = useState<number | null>(null);
    const replayTimeRef = useRef<number | null>(null);

    const handleIntervalChange = useCallback((newInterval: Interval) => {
        if (replayTimeRef.current) {
            setReplayTimestamp(replayTimeRef.current);
        }
        setSelectedInterval(newInterval);
        onIntervalChangeExternal?.(newInterval);
    }, [setSelectedInterval, onIntervalChangeExternal]);

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
        beforeSeriesSwapCallbackRef,
        chartVersion, hoveredBarStore,
    } = chartCore;

    // ── Expose chart handle to external orchestrators (multi-chart sync) ─
    // Fires whenever the underlying chart is recreated (chartVersion bumps).
    useEffect(() => {
        if (!onChartReady) return;
        if (!chartRef.current || !candleSeriesRef.current) return;
        onChartReady({
            chart: chartRef.current,
            candleSeries: candleSeriesRef.current,
            ticker: currentTicker,
            interval: selectedInterval,
        });
    }, [chartVersion, onChartReady, currentTicker, selectedInterval]);

    // ── Live data ────────────────────────────────────────────────────────
    const {
        data, liveBarsRef, loading, loadingMore, error, hasMore, isLive,
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
    // In layout mode the per-cell state lives in `useChartLayoutStore`, so
    // we *must not* overwrite the shared windowState (which holds the layout
    // itself). Skipping persistState here is the right thing to do.
    useEffect(() => {
        if (inLayoutMode) return;
        ticker.persistState(selectedInterval, selectedRange, showVolume, indicators, nextInstanceIdRef.current);
    }, [currentTicker, selectedInterval, selectedRange, showVolume, indicators, inLayoutMode]);

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
            candle: hoveredBarStore.get(),
        });
    }, [hoveredBarStore]);

    // ────────────────────────────────────────────────────────────────────
    // Drawing tools
    // ────────────────────────────────────────────────────────────────────
    const drawingsApi = useChartDrawings(currentTicker, {
        windowId: explicitWindowId ?? windowId ?? null,
    });
    const {
        drawings, activeTool, isDrawing, hoveredDrawingId,
        pendingDrawing,
        locked: drawingsLocked, toggleLocked: toggleDrawingsLocked,
        canUndo, canRedo, undo, redo,
        setActiveTool, cancelDrawing,
        removeDrawing, clearAllDrawings, selectDrawing,
        updateDrawing, replaceDrawing,
        colors: drawingColors,
    } = drawingsApi;

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

    // Data-derived refs shared with the interactions hook + crosshair.
    // Both point at the LIVE bar array (state + WS ticks) so the crosshair
    // OHLC and the magnet snap don't lag behind the painted candles.
    const dataTimes = useMemo(() => data.map(d => d.time), [data]);
    const dataRef = useRef(liveBarsRef.current);
    dataRef.current = liveBarsRef.current;
    dataRefForChart.current = liveBarsRef.current;

    // ── Drawing interactions (primitives, drag, magnet, shortcuts) ──────
    const {
        drawingPrimitivesRef, tentativePrimitiveRef,
        dragState, handleDragStart, handleDragMove, handleDragEnd,
    } = useDrawingInteractions({
        chartRef, candleSeriesRef, containerRef, chartVersion,
        dataTimes, dataRef, magnetModeRef,
        drawingsApi, drawingsVisible,
        hasMore, loadingMore, loadMore,
        selectedInterval, replayControlsDataRef, replay,
        eventPrimitiveRef, openEarningsPopup,
        showNewsMarkersRef, newsTimeMapRef, handleNewsMarkerClickRef,
        openEditPopup, editDialogOpen: editPopup.visible,
    });

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

    // ── Pre-swap cleanup: the price series is being hot-swapped (candle style
    // change) but the chart survives. Detach only series-bound primitives —
    // indicator series live on the chart and must keep their refs. The
    // chartVersion bump after the swap re-attaches drawings/tentative/events
    // on the new series via their own effects.
    beforeSeriesSwapCallbackRef.current = () => {
        const series = candleSeriesRef.current;
        if (series) {
            for (const [, prim] of drawingPrimitivesRef.current) {
                try { series.detachPrimitive(prim); } catch { /* */ }
            }
            if (tentativePrimitiveRef.current) {
                try { series.detachPrimitive(tentativePrimitiveRef.current); } catch { /* */ }
            }
        }
        drawingPrimitivesRef.current.clear();
        tentativePrimitiveRef.current = null;
    };

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
    // NOTE: hovered/display bar are NOT computed here — they live in
    // hoveredBarStore so crosshair moves never re-render this component.
    // Consumers use useDisplayBar() (ChartOHLCOverlay, legend, footer).
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
        data, hoveredBarStore,
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

    /*
      Publish the chart context to a parent observer (ChartContent's
      elevated header/toolbar bridge).

      Two separate effects so we don't push a null between every re-render:
        • Push the latest ctxValue on every commit where the listener is
          present. The dependency intentionally includes `ctxValue` even
          though it's a fresh object each render — that's the desired
          cadence (matches the in-tree `<ChartProvider>` propagation).
        • Push null on unmount / when the listener changes (cell loses
          focus). That's the single "cleanup" path; we avoid a tear/blink
          between renders.
    */
    useEffect(() => {
        onContextValue?.(ctxValue);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ctxValue, onContextValue]);

    useEffect(() => {
        if (!onContextValue) return;
        return () => onContextValue(null);
    }, [onContextValue]);

    // ────────────────────────────────────────────────────────────────────
    // RENDER
    // ────────────────────────────────────────────────────────────────────
    return (
        <ChartProvider value={ctxValue}>
            {/*
              In layout mode the chart is a *cell* inside a parent grid — the
              host paints the surface, so we drop the outer border/rounded
              corners and let the grid handle the chrome.
            */}
            <div
                className={
                    inLayoutMode
                        ? 'h-full flex flex-col bg-[color:var(--color-surface)] overflow-hidden'
                        : 'h-full flex flex-col bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg overflow-hidden'
                }
            >
                {minimal ? (
                    <MinimalHeader onOpenChart={onOpenChart} onOpenNews={onOpenNews} />
                ) : (
                    !hideHeader && <ChartHeader />
                )}

                <div className="flex flex-1 overflow-hidden">
                    {!minimal && !hideToolbar && (
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
                        {cellOverlay && (
                            <div className="absolute top-1 left-1 z-30 pointer-events-auto">
                                {cellOverlay}
                            </div>
                        )}

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
                            <FooterVolumeStat />
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

/**
 * Footer volume readout. Isolated so crosshair-driven hovered-bar updates
 * only re-render this tiny span (via useDisplayBar) instead of TradingChart.
 */
function FooterVolumeStat() {
    const { displayBar } = useDisplayBar();
    if (!displayBar) return null;
    return <span className="font-mono">V:{formatVolume(displayBar.volume)}</span>;
}

export const TradingChart = memo(TradingChartComponent);
export default TradingChart;
