'use client';

import { createContext, useContext, type MutableRefObject, type ReactNode } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { ChartBar, IndicatorInstance, Interval, TimeRange } from './constants';
import type { ReplayState, TickerMeta } from './hooks';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { HoveredBarStore } from './hoveredBarStore';

/** Magnet snap mode (single source of truth). */
export type MagnetMode = 'off' | 'weak' | 'strong';

/** Candle/bar style for the price series. */
export type CandleStyle = 'candles' | 'line' | 'area' | 'bars' | 'heikin-ashi';

/**
 * Aggregated chart state and handlers, exposed to every chart sub-component.
 * Refs are stable across renders so we don't trigger re-mounts when consumers
 * use them; primitive values trigger re-render normally.
 */
export interface ChartContextValue {
    // ── Refs ────────────────────────────────────────────────────────────
    chartRef: MutableRefObject<IChartApi | null>;
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>;
    volumeSeriesRef: MutableRefObject<ISeriesApi<any> | null>;
    containerRef: MutableRefObject<HTMLDivElement | null>;

    // ── Ticker / range ─────────────────────────────────────────────────
    currentTicker: string;
    tickerMeta: TickerMeta | null;
    isMarketOpen: boolean;
    selectedInterval: Interval;
    selectedRange: TimeRange;
    handleIntervalChange: (interval: Interval) => void;
    handleRangeChange: (range: TimeRange) => void;

    // ── Data ───────────────────────────────────────────────────────────
    data: ChartBar[];
    /**
     * External store for the crosshair-hovered bar. Components that display
     * it should use `useDisplayBar()` (from `hoveredBarStore.ts`) so only
     * they re-render on hover — never the whole chart tree.
     */
    hoveredBarStore: HoveredBarStore;
    loading: boolean;
    loadingMore: boolean;
    hasMore: boolean;
    error: string | null;
    refetch: () => void;

    // ── Indicators ─────────────────────────────────────────────────────
    indicators: IndicatorInstance[];
    indicatorResults: IndicatorResults | null;
    showVolume: boolean;
    setShowVolume: (visible: boolean) => void;
    showNewsMarkers: boolean;
    setShowNewsMarkers: (visible: boolean) => void;
    showEarningsMarkers: boolean;
    setShowEarningsMarkers: (visible: boolean) => void;
    addIndicator: (type: string) => void;
    removeIndicator: (id: string) => void;
    openIndicatorSettings: (id: string, event?: React.MouseEvent) => void;
    setSelectedIndicator: (id: string | null) => void;
    selectedIndicator: string | null;
    legendExpanded: boolean;
    setLegendExpanded: (expanded: boolean) => void;
    activeIndicatorCount: number;

    // ── Live status ────────────────────────────────────────────────────
    isLive: boolean;
    showLiveIndicator: boolean;
    isScrolledAway: boolean;

    // ── Replay ─────────────────────────────────────────────────────────
    replayState: ReplayState;
    isReplayActive: boolean;
    enterSelectingMode: () => void;
    exitReplay: () => void;
    togglePlay: () => void;
    stepForward: () => void;
    stepBackward: () => void;
    cycleSpeed: () => void;

    // ── Drawings ───────────────────────────────────────────────────────
    activeTool: string;
    setActiveTool: (tool: any) => void;
    drawingCount: number;
    clearAllDrawings: () => void;
    drawingsVisible: boolean;
    toggleDrawingsVisibility: () => void;
    drawingsLocked: boolean;
    toggleDrawingsLocked: () => void;
    canUndo: boolean;
    canRedo: boolean;
    undo: () => void;
    redo: () => void;

    // ── View ───────────────────────────────────────────────────────────
    isFullscreen: boolean;
    toggleFullscreen: () => void;
    magnetMode: MagnetMode;
    cycleMagnet: () => void;
    setMagnetMode: (mode: MagnetMode) => void;
    zoomIn: () => void;
    zoomOut: () => void;

    // ── Settings ───────────────────────────────────────────────────────
    candleStyle: CandleStyle;
    setCandleStyle: (s: CandleStyle) => void;
    gridVisible: boolean;
    setGridVisible: (v: boolean) => void;
    watermarkVisible: boolean;
    setWatermarkVisible: (v: boolean) => void;
    logScale: boolean;
    setLogScale: (v: boolean) => void;
    openSettings: () => void;
    closeSettings: () => void;
    settingsOpen: boolean;

    // ── Actions ────────────────────────────────────────────────────────
    /** Downloads the current chart as a PNG. Uses `chart.takeScreenshot()`. */
    takeScreenshot: () => void;

    // ── Typography ─────────────────────────────────────────────────────
    fontFamily: string;
}

const ChartContext = createContext<ChartContextValue | null>(null);

interface ChartProviderProps {
    value: ChartContextValue;
    children: ReactNode;
}

export function ChartProvider({ value, children }: ChartProviderProps) {
    return <ChartContext.Provider value={value}>{children}</ChartContext.Provider>;
}

export function useChartContext(): ChartContextValue {
    const ctx = useContext(ChartContext);
    if (!ctx) {
        throw new Error('useChartContext must be used inside <ChartProvider>');
    }
    return ctx;
}
