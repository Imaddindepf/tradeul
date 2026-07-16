'use client';

/**
 * useDrawingInteractions — all drawing-tool interaction logic for the chart:
 *
 *  - drawing ⇄ primitive sync (create/update/detach lightweight-charts primitives)
 *  - tentative (in-progress) drawing preview
 *  - click / double-click / hover hit-testing
 *  - drag (translate / anchor / midpoint reshaping) with history batching
 *  - magnet snap (Ctrl override + weak/strong modes)
 *  - keyboard shortcuts (tools, undo/redo, delete, replay)
 *  - auto-loadMore when a drawing references off-screen history
 *
 * Extracted from TradingChart (~670 LOC) so the orchestrator component stays
 * declarative. Everything here is imperative chart-DOM work driven by refs.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi, ISeriesPrimitive, Time } from 'lightweight-charts';
import type { useChartDrawings, Drawing } from '@/hooks/useChartDrawings';
import type { MagnetMode } from '../ChartContext';
import type { ChartBar } from '../constants';
import type { EarningsRecord } from './useEarningsMarkers';
import type { EventMarkerPrimitive } from '../primitives/EventMarkerPrimitive';
import { findBarIndexByTime } from '../hoveredBarStore';
import { pixelXToTime, timeToPixelX } from '../primitives/coordinateUtils';
import { TrendlinePrimitive } from '../primitives/TrendlinePrimitive';
import { HorizontalLinePrimitive } from '../primitives/HorizontalLinePrimitive';
import { VerticalLinePrimitive } from '../primitives/VerticalLinePrimitive';
import { RayPrimitive } from '../primitives/RayPrimitive';
import { ExtendedLinePrimitive } from '../primitives/ExtendedLinePrimitive';
import { ParallelChannelPrimitive } from '../primitives/ParallelChannelPrimitive';
import { FibonacciPrimitive } from '../primitives/FibonacciPrimitive';
import { RectanglePrimitive } from '../primitives/RectanglePrimitive';
import { CirclePrimitive } from '../primitives/CirclePrimitive';
import { TrianglePrimitive } from '../primitives/TrianglePrimitive';
import { MeasurePrimitive } from '../primitives/MeasurePrimitive';
import { ArrowPrimitive } from '../primitives/ArrowPrimitive';
import { TextPrimitive } from '../primitives/TextPrimitive';
import { PriceRangePrimitive } from '../primitives/PriceRangePrimitive';
import { DateRangePrimitive } from '../primitives/DateRangePrimitive';
import { TentativePrimitive } from '../primitives/TentativePrimitive';

type DrawingsApi = ReturnType<typeof useChartDrawings>;

export type DragMode = 'translate' | 'anchor1' | 'anchor2' | 'anchor3' | 'anchor4' | 'mid1' | 'mid2';

export interface DrawingDragState {
    active: boolean;
    drawingId: string | null;
    drawingType: string | null;
    dragMode: DragMode;
    startScreenX: number; startScreenY: number;
    p1ScreenX: number; p1ScreenY: number;
    p2ScreenX: number; p2ScreenY: number;
    p3ScreenX: number; p3ScreenY: number;
}

const IDLE_DRAG: DrawingDragState = {
    active: false, drawingId: null, drawingType: null, dragMode: 'translate',
    startScreenX: 0, startScreenY: 0, p1ScreenX: 0, p1ScreenY: 0,
    p2ScreenX: 0, p2ScreenY: 0, p3ScreenX: 0, p3ScreenY: 0,
};

/** Strip an anchor/midpoint suffix (":p1".. ":m2") from a hit externalId. */
function baseDrawingId(externalId: string): string {
    return /:(p[1-4]|m[12])$/.test(externalId) ? externalId.slice(0, -3) : externalId;
}

/** Drawing types whose body is a thin line — they must win the hit-test
 *  over filled areas (rectangle, channel, triangle…) that overlap them. */
const LINE_BODY_TYPES = new Set([
    'trendline', 'ray', 'extended_line', 'horizontal_line', 'vertical_line', 'arrow',
]);

/**
 * Hit-test every drawing primitive at (x, y) with focus prioritisation:
 *   1. any reshape handle (":p1".. ":m2") — immediate win, it's the most
 *      precise target the user can aim at;
 *   2. line bodies — a trendline crossing a rectangle must be pickable;
 *   3. filled areas / zones — lowest priority.
 * Iteration order (insertion order of the Map) only breaks ties inside the
 * same tier.
 */
function hitTestPrimitives(
    primitives: Map<string, ISeriesPrimitive<Time>>,
    x: number,
    y: number,
): { externalId: string } | null {
    let lineHit: { externalId: string } | null = null;
    let areaHit: { externalId: string } | null = null;
    for (const [, primitive] of primitives) {
        const hit = (primitive as any).hitTest?.(x, y);
        if (!hit) continue;
        const externalId = (hit.externalId ?? '') as string;
        if (/:(p[1-4]|m[12])$/.test(externalId)) return { externalId };
        const type = (primitive as any).drawingType ?? '';
        if (LINE_BODY_TYPES.has(type)) {
            if (!lineHit) lineHit = { externalId };
        } else if (!areaHit) {
            areaHit = { externalId };
        }
    }
    return lineHit ?? areaHit;
}

function createPrimitiveFor(drawing: Drawing): ISeriesPrimitive<Time> | null {
    switch (drawing.type) {
        case 'horizontal_line': return new HorizontalLinePrimitive(drawing);
        case 'vertical_line': return new VerticalLinePrimitive(drawing);
        case 'trendline': return new TrendlinePrimitive(drawing);
        case 'ray': return new RayPrimitive(drawing);
        case 'extended_line': return new ExtendedLinePrimitive(drawing);
        case 'parallel_channel': return new ParallelChannelPrimitive(drawing);
        case 'fibonacci': return new FibonacciPrimitive(drawing);
        case 'rectangle': return new RectanglePrimitive(drawing);
        case 'circle': return new CirclePrimitive(drawing);
        case 'triangle': return new TrianglePrimitive(drawing);
        case 'measure': return new MeasurePrimitive(drawing);
        case 'arrow': return new ArrowPrimitive(drawing);
        case 'text': return new TextPrimitive(drawing);
        case 'price_range': return new PriceRangePrimitive(drawing);
        case 'date_range': return new DateRangePrimitive(drawing);
        default: return null;
    }
}

export interface UseDrawingInteractionsParams {
    chartRef: MutableRefObject<IChartApi | null>;
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>;
    containerRef: MutableRefObject<HTMLDivElement | null>;
    chartVersion: number;
    dataTimes: number[];
    dataRef: MutableRefObject<ChartBar[]>;
    magnetModeRef: MutableRefObject<MagnetMode>;
    drawingsApi: DrawingsApi;
    drawingsVisible: boolean;
    hasMore: boolean;
    loadingMore: boolean;
    loadMore: () => Promise<unknown>;
    selectedInterval: string;
    replayControlsDataRef: MutableRefObject<boolean>;
    replay: {
        replayState: { mode: string };
        selectStartPoint: (time: number) => void;
        stepForward: () => void;
        stepBackward: () => void;
        togglePlay: () => void;
    };
    eventPrimitiveRef: MutableRefObject<EventMarkerPrimitive | null>;
    openEarningsPopup: (p: { record: EarningsRecord; x: number; y: number }) => void;
    showNewsMarkersRef: MutableRefObject<boolean>;
    newsTimeMapRef: MutableRefObject<Map<number, unknown>>;
    handleNewsMarkerClickRef: MutableRefObject<(time: number) => void>;
    openEditPopup: (drawingId: string, x: number, y: number) => void;
    editDialogOpen: boolean;
    /** Hit-test de indicadores overlay (useIndicatorHover). Los dibujos ganan. */
    indicatorHitTest: (param: { point?: { x: number; y: number }; time?: unknown; paneIndex?: number }) => { id: string } | null;
    setHoveredIndicator: (id: string | null) => void;
    setSelectedIndicator: (id: string | null) => void;
}

export function useDrawingInteractions({
    chartRef,
    candleSeriesRef,
    containerRef,
    chartVersion,
    dataTimes,
    dataRef,
    magnetModeRef,
    drawingsApi,
    drawingsVisible,
    hasMore,
    loadingMore,
    loadMore,
    selectedInterval,
    replayControlsDataRef,
    replay,
    eventPrimitiveRef,
    openEarningsPopup,
    showNewsMarkersRef,
    newsTimeMapRef,
    handleNewsMarkerClickRef,
    openEditPopup,
    editDialogOpen,
    indicatorHitTest,
    setHoveredIndicator,
    setSelectedIndicator,
}: UseDrawingInteractionsParams) {
    const {
        drawings, activeTool, isDrawing, selectedDrawingId, hoveredDrawingId,
        pendingDrawing, tentativeEndpoint,
        locked: drawingsLocked,
        canUndo, canRedo, undo, redo,
        setActiveTool, cancelDrawing, handleChartClick, updateTentativeEndpoint,
        removeDrawing, selectDrawing,
        updateHorizontalLinePrice, updateVerticalLineTime, updateDrawingPoints,
        startDragging, stopDragging,
        findDrawingNearPrice, setHoveredDrawing,
        beginHistoryTransaction, endHistoryTransaction,
        colors: drawingColors,
    } = drawingsApi;

    // ── Primitive registries ────────────────────────────────────────────
    const drawingPrimitivesRef = useRef<Map<string, ISeriesPrimitive<Time>>>(new Map());
    const tentativePrimitiveRef = useRef<TentativePrimitive | null>(null);

    const dataTimesRef = useRef(dataTimes);
    dataTimesRef.current = dataTimes;

    // ── Stable refs for event handlers ──────────────────────────────────
    const activeToolRef = useRef(activeTool); activeToolRef.current = activeTool;
    const handleChartClickRef = useRef(handleChartClick); handleChartClickRef.current = handleChartClick;
    const selectDrawingRef = useRef(selectDrawing); selectDrawingRef.current = selectDrawing;
    const pendingDrawingRef = useRef(pendingDrawing); pendingDrawingRef.current = pendingDrawing;
    const updateTentativeEndpointRef = useRef(updateTentativeEndpoint); updateTentativeEndpointRef.current = updateTentativeEndpoint;
    const openEditPopupRef = useRef(openEditPopup); openEditPopupRef.current = openEditPopup;
    const findDrawingNearPriceRef = useRef(findDrawingNearPrice); findDrawingNearPriceRef.current = findDrawingNearPrice;
    const replayModeRef = useRef(replay.replayState.mode); replayModeRef.current = replay.replayState.mode;
    const selectStartPointRef = useRef(replay.selectStartPoint); selectStartPointRef.current = replay.selectStartPoint;
    const openEarningsPopupRef = useRef(openEarningsPopup); openEarningsPopupRef.current = openEarningsPopup;
    const indicatorHitTestRef = useRef(indicatorHitTest); indicatorHitTestRef.current = indicatorHitTest;
    const setHoveredIndicatorRef = useRef(setHoveredIndicator); setHoveredIndicatorRef.current = setHoveredIndicator;
    const setSelectedIndicatorRef = useRef(setSelectedIndicator); setSelectedIndicatorRef.current = setSelectedIndicator;

    // ── Ctrl key tracking for magnet snap ───────────────────────────────
    const ctrlPressedRef = useRef(false);
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

    /**
     * Magnet core: resolve the snapped price (and bar time) for a screen
     * position, or null when no snap applies. Shared by the price-snap helper
     * and the crosshair magnet so the rules can't diverge.
     */
    const computeSnap = useCallback((rawPrice: number, screenX: number): { price: number; time: number } | null => {
        const ctrl = ctrlPressedRef.current;
        const mode = magnetModeRef.current;
        if (activeToolRef.current === 'none') return null;
        const shouldSnap = mode === 'off' ? ctrl : !ctrl;
        if (!shouldSnap) return null;

        const chart = chartRef.current;
        if (!chart) return null;
        const time = chart.timeScale().coordinateToTime(screenX);
        if (time == null) return null;
        const idx = findBarIndexByTime(dataRef.current, time as number);
        if (idx === -1) return null;
        const bar = dataRef.current[idx];

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
            if (minDist > threshold) return null;
        }
        return { price: closest, time: time as number };
    }, [chartRef, dataRef, magnetModeRef]);

    /** Magnet: snap raw price to nearest OHLC of bar at screenX (passthrough when off). */
    const snapPriceToOHLC = useCallback((rawPrice: number, screenX: number): number => {
        return computeSnap(rawPrice, screenX)?.price ?? rawPrice;
    }, [computeSnap]);
    const snapPriceRef = useRef(snapPriceToOHLC);
    snapPriceRef.current = snapPriceToOHLC;

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
                const primitive = createPrimitiveFor(drawing);
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
    const [dragState, setDragState] = useState<DrawingDragState>(IDLE_DRAG);

    const getTimeAtX = useCallback((x: number): { time: number; logical?: number } | null => {
        if (!chartRef.current) return null;
        const ts = chartRef.current.timeScale();
        /*
          pixelXToTime es la INVERSA EXACTA de timeToPixelX (la función con la
          que los primitives pintan): un punto colocado en el hueco a la
          derecha de la última vela debe volver a renderizarse en ese mismo
          píxel. Antes esta función extrapolaba con el ÚLTIMO gap (que en
          intradía suele ser el salto overnight/finde, p.ej. 19h en un 4H) y
          el render extrapolaba con el gap MEDIANO (4h): el punto se guardaba
          ~5× más lejos de lo clicado y la línea/círculo aparecía disparada o
          directamente fuera de pantalla.
        */
        const time = pixelXToTime(x, dataTimesRef.current, ts);
        if (time == null) return null;
        const logical = ts.coordinateToLogical(x);
        return { time, logical: logical == null ? undefined : (logical as number) };
    }, [chartRef]);

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
            const hit = hitTestPrimitives(drawingPrimitivesRef.current, param.point.x, param.point.y);
            const hitId = hit ? baseDrawingId(hit.externalId) : null;
            selectDrawingRef.current(hitId);
            // Un click en vacío (o sobre un dibujo) también resuelve el foco
            // de indicadores: si no hay dibujo, el indicador bajo el cursor
            // queda seleccionado; si no hay nada, se limpia la selección.
            if (hitId) {
                setSelectedIndicatorRef.current?.(null);
            } else {
                const indHit = indicatorHitTestRef.current?.(param);
                setSelectedIndicatorRef.current?.(indHit ? indHit.id : null);
            }
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
            const resolved = getTimeAtX(x);
            if (!resolved) return;
            handleChartClickRef.current(resolved.time, price, resolved.logical);
        };
        container.addEventListener('click', handleDrawingClick);
        return () => container.removeEventListener('click', handleDrawingClick);
    }, [chartVersion, getTimeAtX]);

    // ── Hover detection ─────────────────────────────────────────────────
    useEffect(() => {
        if (!chartRef.current) return;
        const chart = chartRef.current;
        const handleCrosshairMove = (param: any) => {
            if (dragState.active || activeToolRef.current !== 'none') return;
            if (!param.point) {
                setHoveredDrawing(null);
                setHoveredIndicatorRef.current?.(null);
                return;
            }
            const hit = hitTestPrimitives(drawingPrimitivesRef.current, param.point.x, param.point.y);
            const hitId = hit ? baseDrawingId(hit.externalId) : null;
            setHoveredDrawing(hitId);
            // Los dibujos del usuario ganan el foco a los indicadores; solo
            // si el cursor no toca ningún dibujo se evalúan las líneas de
            // los estudios (BB, medias, VWAP…).
            const indHit = hitId ? null : indicatorHitTestRef.current?.(param) ?? null;
            setHoveredIndicatorRef.current?.(indHit ? indHit.id : null);
        };
        chart.subscribeCrosshairMove(handleCrosshairMove);
        return () => { chart.unsubscribeCrosshairMove(handleCrosshairMove); };
    }, [dragState.active, setHoveredDrawing, chartVersion]);

    // ── Mouse tracking for tentative drawing endpoint ───────────────────
    /*
      mousemove DOM sobre el CONTENEDOR, no subscribeCrosshairMove: el evento
      de crosshair de lightweight-charts solo se emite mientras el puntero
      está sobre el pane de velas. Al cruzar a la franja del eje de precios o
      al hueco a la derecha de la última vela, deja de disparar y la vista
      previa del dibujo se congelaba en la última posición del pane — el
      usuario "perdía" el dibujo mientras lo formaba, aunque el click final
      (que ya usa un listener DOM idéntico a este) sí lo colocaba bien. El
      contenedor comparte sistema de coordenadas con el pane (mismo origen),
      igual que en handleDrawingClick y el handler del imán.
    */
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        const handleMove = (e: MouseEvent) => {
            if (!pendingDrawingRef.current || !candleSeriesRef.current) return;
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const rawPrice = candleSeriesRef.current.coordinateToPrice(y);
            if (rawPrice === null) return;
            const price = snapPriceRef.current(rawPrice, x);
            updateTentativeEndpointRef.current(x, y, price);
        };
        container.addEventListener('mousemove', handleMove);
        return () => container.removeEventListener('mousemove', handleMove);
    }, [chartVersion]);

    // ── Magnet: snap crosshair to nearest OHLC on mouse move ────────────
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        const handleMouseMove = (e: MouseEvent) => {
            const chart = chartRef.current;
            const series = candleSeriesRef.current;
            if (!chart || !series) return;
            const rect = container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const rawPrice = series.coordinateToPrice(y);
            if (rawPrice === null) return;
            const snap = computeSnap(rawPrice, x);
            if (!snap) return;
            chart.setCrosshairPosition(snap.price, snap.time as Time, series);
        };
        const handleMouseLeave = () => { chartRef.current?.clearCrosshairPosition(); };
        container.addEventListener('mousemove', handleMouseMove);
        container.addEventListener('mouseleave', handleMouseLeave);
        return () => {
            container.removeEventListener('mousemove', handleMouseMove);
            container.removeEventListener('mouseleave', handleMouseLeave);
        };
    }, [chartVersion, computeSnap]);

    // ── Drag handlers ───────────────────────────────────────────────────
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if (activeTool !== 'none' || !candleSeriesRef.current || !containerRef.current || !chartRef.current) return;
        if (editDialogOpen) return;
        if (drawingsLocked) return;
        const rect = containerRef.current.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        let hitId: string | null = null;
        let dragMode: DragMode = 'translate';
        const hit = hitTestPrimitives(drawingPrimitivesRef.current, mouseX, mouseY);
        if (hit) {
            const eid = hit.externalId;
            if (eid.endsWith(':p1')) { hitId = eid.slice(0, -3); dragMode = 'anchor1'; }
            else if (eid.endsWith(':p2')) { hitId = eid.slice(0, -3); dragMode = 'anchor2'; }
            else if (eid.endsWith(':p3')) { hitId = eid.slice(0, -3); dragMode = 'anchor3'; }
            else if (eid.endsWith(':p4')) { hitId = eid.slice(0, -3); dragMode = 'anchor4'; }
            else if (eid.endsWith(':m1')) { hitId = eid.slice(0, -3); dragMode = 'mid1'; }
            else if (eid.endsWith(':m2')) { hitId = eid.slice(0, -3); dragMode = 'mid2'; }
            else { hitId = eid; dragMode = 'translate'; }
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
        // Batch the whole drag into one undo entry + one persist on release.
        beginHistoryTransaction();
        setDragState({ active: true, drawingId: hitId, drawingType: drawing.type, dragMode, startScreenX: mouseX, startScreenY: mouseY, p1ScreenX, p1ScreenY, p2ScreenX, p2ScreenY, p3ScreenX, p3ScreenY });
        selectDrawing(hitId);
        startDragging();
    }, [activeTool, drawings, selectDrawing, startDragging, editDialogOpen, dataTimes, drawingsLocked, beginHistoryTransaction]);

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
        } else if (dragState.drawingType === 'rectangle' && (dragState.dragMode === 'anchor3' || dragState.dragMode === 'anchor4')) {
            // Rectangle non-diagonal corners. :p3 = (x2,y1)=TR shifts point1.price + point2.time;
            // :p4 = (x1,y2)=BL shifts point1.time + point2.price. The opposite axis of each
            // corner is held by re-asserting the existing values for the unchanged components.
            const resolved = getTimeAtX(mouseX);
            const newPrice = sp(series.coordinateToPrice(mouseY), mouseX);
            if (resolved && newPrice != null) {
                const cur = drawings.find(d => d.id === dragState.drawingId);
                if (cur && cur.type === 'rectangle') {
                    if (dragState.dragMode === 'anchor3') {
                        updateDrawingPoints(dragState.drawingId, {
                            point1: { time: cur.point1.time, price: newPrice, logical: cur.point1.logical },
                            point2: { time: resolved.time, price: cur.point2.price, logical: resolved.logical },
                        });
                    } else {
                        updateDrawingPoints(dragState.drawingId, {
                            point1: { time: resolved.time, price: cur.point1.price, logical: resolved.logical },
                            point2: { time: cur.point2.time, price: newPrice, logical: cur.point2.logical },
                        });
                    }
                }
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
    }, [dragState, drawings, updateHorizontalLinePrice, updateVerticalLineTime, updateDrawingPoints, getTimeAtX]);

    const handleDragEnd = useCallback(() => {
        if (dragState.active) {
            // Flush the batched drag: one undo entry + one persist/emit.
            endHistoryTransaction();
            setDragState(IDLE_DRAG);
            stopDragging();
            setTimeout(() => selectDrawing(null), 50);
        }
    }, [dragState.active, stopDragging, selectDrawing, endHistoryTransaction]);

    // ── Disable scroll during drag/drawing ──────────────────────────────
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

    // Global cursor while dragging: closed hand for body translation, default
    // arrow for handle reshaping. Restored when the drag ends. We force this
    // at the <body> level because lightweight-charts only controls the cursor
    // on hover, not during our custom drag.
    useEffect(() => {
        if (!dragState.active) return;
        const prev = document.body.style.cursor;
        document.body.style.cursor = dragState.dragMode === 'translate' ? 'grabbing' : 'default';
        return () => { document.body.style.cursor = prev; };
    }, [dragState.active, dragState.dragMode]);

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
                case 'Escape': cancelDrawing(); selectDrawing(null); setSelectedIndicatorRef.current(null); break;
                case 'Delete': case 'Backspace': if (selectedDrawingId) removeDrawing(selectedDrawingId); break;
            }

            // Herramientas de dibujo: Alt + letra (estilo TradingView).
            // Las letras sueltas quedan libres para el buscador de ticker
            // (type-ahead) de la ventana enfocada. Usamos e.code porque en
            // algunos teclados Alt cambia el carácter de e.key.
            if (e.altKey && !e.metaKey && !e.ctrlKey) {
                switch (e.code) {
                    case 'KeyH': e.preventDefault(); setActiveTool(activeTool === 'horizontal_line' ? 'none' : 'horizontal_line'); break;
                    case 'KeyT': e.preventDefault(); setActiveTool(activeTool === 'trendline' ? 'none' : 'trendline'); break;
                    case 'KeyF': e.preventDefault(); setActiveTool(activeTool === 'fibonacci' ? 'none' : 'fibonacci'); break;
                    case 'KeyR': e.preventDefault(); setActiveTool(activeTool === 'rectangle' ? 'none' : 'rectangle'); break;
                    case 'KeyV': e.preventDefault(); setActiveTool(activeTool === 'vertical_line' ? 'none' : 'vertical_line'); break;
                    case 'KeyY': e.preventDefault(); setActiveTool(activeTool === 'ray' ? 'none' : 'ray'); break;
                    case 'KeyE': e.preventDefault(); setActiveTool(activeTool === 'extended_line' ? 'none' : 'extended_line'); break;
                    case 'KeyC': e.preventDefault(); setActiveTool(activeTool === 'circle' ? 'none' : 'circle'); break;
                    case 'KeyM': e.preventDefault(); setActiveTool(activeTool === 'measure' ? 'none' : 'measure'); break;
                }
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

    // ── Drawing / replay cursor ─────────────────────────────────────────
    useEffect(() => {
        if (!containerRef.current) return;
        containerRef.current.style.cursor = (isDrawing || replay.replayState.mode === 'selecting') ? 'crosshair' : 'default';
    }, [isDrawing, replay.replayState.mode]);

    return {
        drawingPrimitivesRef,
        tentativePrimitiveRef,
        dragState,
        handleDragStart,
        handleDragMove,
        handleDragEnd,
    };
}
