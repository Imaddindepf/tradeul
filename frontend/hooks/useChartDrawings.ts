/**
 * useChartDrawings - Hook para gestionar dibujos persistentes en charts
 *
 * Soporta:
 * - 1-click: Horizontal line, Vertical line
 * - 2-click: Trendline, Ray, Extended line, Fibonacci, Rectangle, Circle, Measure
 * - 3-click: Parallel channel, Triangle
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  Drawing,
  DrawingType,
  DrawingTool,
  DrawingPoint,
  HorizontalLineDrawing,
  VerticalLineDrawing,
  TrendlineDrawing,
  RayDrawing,
  ExtendedLineDrawing,
  ParallelChannelDrawing,
  FibonacciDrawing,
  RectangleDrawing,
  CircleDrawing,
  TriangleDrawing,
  MeasureDrawing,
  PendingDrawing,
} from '@/components/chart/primitives/types';
import { FIB_LEVELS, DRAWING_COLORS, TOOL_CLICKS } from '@/components/chart/primitives/types';

// Re-export types for consumers
export type { Drawing, DrawingType, DrawingTool, DrawingPoint, PendingDrawing };
export type {
  HorizontalLineDrawing,
  VerticalLineDrawing,
  TrendlineDrawing,
  RayDrawing,
  ExtendedLineDrawing,
  ParallelChannelDrawing,
  FibonacciDrawing,
  RectangleDrawing,
  CircleDrawing,
  TriangleDrawing,
  MeasureDrawing,
};

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = 'tradeul_chart_drawings_v2';
const LOCKED_KEY = 'tradeul_chart_drawings_locked_v1';
const DEFAULT_LINE_WIDTH = 1;

/** Hard cap on per-ticker undo history. */
const MAX_HISTORY = 50;

// ============================================================================
// Helpers
// ============================================================================

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function loadFromStorage(): Record<string, Drawing[]> {
  if (typeof window === 'undefined') return {};
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function saveToStorage(state: Record<string, Drawing[]>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.error('[ChartDrawings] Failed to save:', e);
  }
}

function loadLockedMap(): Record<string, boolean> {
  if (typeof window === 'undefined') return {};
  try {
    const stored = localStorage.getItem(LOCKED_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function saveLockedMap(state: Record<string, boolean>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LOCKED_KEY, JSON.stringify(state));
  } catch { /* ignore */ }
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ============================================================================
// Hook
// ============================================================================

export function useChartDrawings(ticker: string) {
  const [drawings, setDrawingsState] = useState<Drawing[]>([]);
  const [activeTool, setActiveTool] = useState<DrawingTool>('none');
  const activeToolRef = useRef(activeTool);
  activeToolRef.current = activeTool;
  const [selectedColor, setSelectedColor] = useState(DRAWING_COLORS[0]);
  const [lineWidth, setLineWidth] = useState(DEFAULT_LINE_WIDTH);
  const [locked, setLockedState] = useState(false);
  const lockedRef = useRef(locked);
  lockedRef.current = locked;

  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [hoveredDrawingId, setHoveredDrawingId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const [pendingDrawing, setPendingDrawing] = useState<PendingDrawing | null>(null);
  const [tentativeEndpoint, setTentativeEndpoint] = useState<{ x: number; y: number; price: number } | null>(null);

  const tickerRef = useRef(ticker);

  // ============================================================================
  // History (per-ticker, in-memory) — drives undo/redo
  // ============================================================================

  const undoStackRef = useRef<Drawing[][]>([]);
  const redoStackRef = useRef<Drawing[][]>([]);
  const suppressHistoryRef = useRef(false);
  const drawingsRef = useRef<Drawing[]>(drawings);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const recomputeAvailability = useCallback(() => {
    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(redoStackRef.current.length > 0);
  }, []);

  /**
   * Single mutator used by ALL drawing mutations. Pushes the current state to
   * the undo stack (unless suppressed by undo/redo themselves) and clears the
   * redo stack since a new branch was created. Caps stack size at MAX_HISTORY.
   */
  const commitDrawings = useCallback((producer: (prev: Drawing[]) => Drawing[]) => {
    setDrawingsState(prev => {
      const next = producer(prev);
      if (next === prev) return prev;
      if (!suppressHistoryRef.current) {
        undoStackRef.current.push(prev);
        if (undoStackRef.current.length > MAX_HISTORY) {
          undoStackRef.current.shift();
        }
        redoStackRef.current = [];
      }
      drawingsRef.current = next;
      // recomputeAvailability scheduled after state commit
      queueMicrotask(recomputeAvailability);
      return next;
    });
  }, [recomputeAvailability]);

  // ============================================================================
  // Load / Save (resets history on ticker change)
  // ============================================================================

  useEffect(() => {
    tickerRef.current = ticker;
    const allDrawings = loadFromStorage();
    const next = allDrawings[ticker] || [];
    suppressHistoryRef.current = true;
    setDrawingsState(next);
    drawingsRef.current = next;
    undoStackRef.current = [];
    redoStackRef.current = [];
    setSelectedDrawingId(null);
    setPendingDrawing(null);
    setTentativeEndpoint(null);
    queueMicrotask(() => {
      suppressHistoryRef.current = false;
      recomputeAvailability();
    });
    const lockedMap = loadLockedMap();
    setLockedState(!!lockedMap[ticker]);
  }, [ticker, recomputeAvailability]);

  useEffect(() => {
    const allDrawings = loadFromStorage();
    allDrawings[tickerRef.current] = drawings;
    saveToStorage(allDrawings);
    drawingsRef.current = drawings;
  }, [drawings]);

  useEffect(() => {
    const map = loadLockedMap();
    map[tickerRef.current] = locked;
    saveLockedMap(map);
  }, [locked]);

  const undo = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    redoStackRef.current.push(drawingsRef.current);
    suppressHistoryRef.current = true;
    setDrawingsState(prev);
    drawingsRef.current = prev;
    setSelectedDrawingId(null);
    queueMicrotask(() => {
      suppressHistoryRef.current = false;
      recomputeAvailability();
    });
  }, [recomputeAvailability]);

  const redo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;
    undoStackRef.current.push(drawingsRef.current);
    suppressHistoryRef.current = true;
    setDrawingsState(next);
    drawingsRef.current = next;
    setSelectedDrawingId(null);
    queueMicrotask(() => {
      suppressHistoryRef.current = false;
      recomputeAvailability();
    });
  }, [recomputeAvailability]);

  const toggleLocked = useCallback(() => {
    setLockedState(prev => !prev);
  }, []);
  const setLocked = useCallback((value: boolean) => setLockedState(value), []);

  // ============================================================================
  // Create drawings — 1-click
  // ============================================================================

  const addHorizontalLine = useCallback((price: number): HorizontalLineDrawing => {
    const drawing: HorizontalLineDrawing = {
      id: generateId(), type: 'horizontal_line', price, color: selectedColor, lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addVerticalLine = useCallback((time: number): VerticalLineDrawing => {
    const drawing: VerticalLineDrawing = {
      id: generateId(), type: 'vertical_line', time, color: selectedColor, lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  // ============================================================================
  // Create drawings — 2-click
  // ============================================================================

  const addTrendline = useCallback((p1: DrawingPoint, p2: DrawingPoint): TrendlineDrawing => {
    const drawing: TrendlineDrawing = {
      id: generateId(), type: 'trendline', point1: p1, point2: p2, color: selectedColor, lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addRay = useCallback((p1: DrawingPoint, p2: DrawingPoint): RayDrawing => {
    const drawing: RayDrawing = {
      id: generateId(), type: 'ray', point1: p1, point2: p2, color: selectedColor, lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addExtendedLine = useCallback((p1: DrawingPoint, p2: DrawingPoint): ExtendedLineDrawing => {
    const drawing: ExtendedLineDrawing = {
      id: generateId(), type: 'extended_line', point1: p1, point2: p2, color: selectedColor, lineWidth, lineStyle: 'dashed',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addFibonacci = useCallback((p1: DrawingPoint, p2: DrawingPoint): FibonacciDrawing => {
    const drawing: FibonacciDrawing = {
      id: generateId(), type: 'fibonacci', point1: p1, point2: p2, levels: [...FIB_LEVELS],
      color: selectedColor, lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addRectangle = useCallback((p1: DrawingPoint, p2: DrawingPoint): RectangleDrawing => {
    const drawing: RectangleDrawing = {
      id: generateId(), type: 'rectangle', point1: p1, point2: p2,
      color: selectedColor, fillColor: hexToRgba(selectedColor, 0.1),
      lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addCircle = useCallback((p1: DrawingPoint, p2: DrawingPoint): CircleDrawing => {
    const drawing: CircleDrawing = {
      id: generateId(), type: 'circle', point1: p1, point2: p2,
      color: selectedColor, fillColor: hexToRgba(selectedColor, 0.08),
      lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addMeasure = useCallback((p1: DrawingPoint, p2: DrawingPoint): MeasureDrawing => {
    const drawing: MeasureDrawing = {
      id: generateId(), type: 'measure', point1: p1, point2: p2,
      color: '#64748b', lineWidth: 1, lineStyle: 'dashed',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [commitDrawings]);

  // ============================================================================
  // Create drawings — 3-click
  // ============================================================================

  const addParallelChannel = useCallback((p1: DrawingPoint, p2: DrawingPoint, p3: DrawingPoint): ParallelChannelDrawing => {
    const drawing: ParallelChannelDrawing = {
      id: generateId(), type: 'parallel_channel', point1: p1, point2: p2, point3: p3,
      color: selectedColor, fillColor: hexToRgba(selectedColor, 0.08), lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  const addTriangle = useCallback((p1: DrawingPoint, p2: DrawingPoint, p3: DrawingPoint): TriangleDrawing => {
    const drawing: TriangleDrawing = {
      id: generateId(), type: 'triangle', point1: p1, point2: p2, point3: p3,
      color: selectedColor, fillColor: hexToRgba(selectedColor, 0.08),
      lineWidth, lineStyle: 'solid',
    };
    commitDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth, commitDrawings]);

  // ============================================================================
  // Delete / Mutate — gated by `locked` flag
  // ============================================================================

  const removeDrawing = useCallback((id: string) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.filter(d => d.id !== id));
    if (selectedDrawingId === id) setSelectedDrawingId(null);
  }, [selectedDrawingId, commitDrawings]);

  const clearAllDrawings = useCallback(() => {
    if (lockedRef.current) return;
    commitDrawings(() => []);
    setSelectedDrawingId(null);
  }, [commitDrawings]);

  const updateDrawingColor = useCallback((id: string, newColor: string) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if ('fillColor' in d) {
        return { ...d, color: newColor, fillColor: hexToRgba(newColor, 0.1) };
      }
      return { ...d, color: newColor };
    }));
  }, [commitDrawings]);

  const updateDrawingLineWidth = useCallback((id: string, newWidth: number) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => d.id === id ? { ...d, lineWidth: newWidth } : d));
  }, [commitDrawings]);

  const updateHorizontalLinePrice = useCallback((id: string, newPrice: number) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id === id && d.type === 'horizontal_line') return { ...d, price: newPrice };
      return d;
    }));
  }, [commitDrawings]);

  const updateVerticalLineTime = useCallback((id: string, newTime: number) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id === id && d.type === 'vertical_line') return { ...d, time: newTime };
      return d;
    }));
  }, [commitDrawings]);

  /**
   * Generic shallow merge for a drawing. The `type` discriminator is preserved
   * — callers must NOT supply it in the patch. Used by the per-tool properties
   * dialog where any subset of fields may be edited at once.
   */
  const updateDrawing = useCallback((id: string, patch: Partial<Drawing>) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      const merged = { ...d, ...patch, type: d.type, id: d.id } as Drawing;
      return merged;
    }));
  }, [commitDrawings]);

  /**
   * Full-replace of a drawing's payload. Preserves `id` and `type` discriminator
   * but replaces every other field. Used for "Cancelar" in the properties
   * dialog to restore a pre-edit snapshot.
   */
  const replaceDrawing = useCallback((id: string, next: Drawing) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if (d.type !== next.type) return d; // type mismatch → silently ignore
      return { ...next, id: d.id } as Drawing;
    }));
  }, [commitDrawings]);

  const updateDrawingPoints = useCallback((id: string, points: { point1?: DrawingPoint; point2?: DrawingPoint; point3?: DrawingPoint }) => {
    if (lockedRef.current) return;
    commitDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if (d.type === 'horizontal_line') return d;
      if (d.type === 'vertical_line') return d;
      const updated = { ...d } as any;
      if (points.point1) updated.point1 = points.point1;
      if (points.point2) updated.point2 = points.point2;
      if (points.point3 && 'point3' in updated) updated.point3 = points.point3;
      return updated;
    }));
  }, [commitDrawings]);

  // ============================================================================
  // Selection & drag
  // ============================================================================

  const selectDrawing = useCallback((id: string | null) => {
    setSelectedDrawingId(id);
  }, []);

  const setHoveredDrawing = useCallback((id: string | null) => {
    setHoveredDrawingId(id);
  }, []);

  const startDragging = useCallback(() => setIsDragging(true), []);
  const stopDragging = useCallback(() => setIsDragging(false), []);

  const findDrawingNearPrice = useCallback((price: number, tolerance: number = 1.5): Drawing | null => {
    let closest: Drawing | null = null;
    let closestDiff = Infinity;
    for (const drawing of drawings) {
      if (drawing.type === 'horizontal_line') {
        const pctDiff = (Math.abs(drawing.price - price) / price) * 100;
        if (pctDiff < tolerance && pctDiff < closestDiff) {
          closestDiff = pctDiff;
          closest = drawing;
        }
      }
    }
    return closest;
  }, [drawings]);

  // ============================================================================
  // Chart click handler — unified for all drawing tools
  // ============================================================================

  const handleChartClick = useCallback((time: number, price: number, logical?: number): Drawing | null => {
    const tool = activeToolRef.current;
    if (tool === 'none') return null;

    const clicksNeeded = TOOL_CLICKS[tool as DrawingType] ?? 2;
    const point: DrawingPoint = { time, price, logical };

    // ── 1-click tools ────────────────────────────────────────────────
    if (clicksNeeded === 1) {
      let drawing: Drawing | null = null;
      switch (tool) {
        case 'horizontal_line':
          drawing = addHorizontalLine(price);
          break;
        case 'vertical_line':
          drawing = addVerticalLine(time);
          break;
      }
      setActiveTool('none');
      return drawing;
    }

    // ── 2-click tools ────────────────────────────────────────────────
    if (clicksNeeded === 2) {
      if (!pendingDrawing) {
        setPendingDrawing({ type: tool as DrawingType, point1: point });
        return null;
      }
      const p1 = pendingDrawing.point1;
      let drawing: Drawing | null = null;
      switch (pendingDrawing.type) {
        case 'trendline': drawing = addTrendline(p1, point); break;
        case 'ray': drawing = addRay(p1, point); break;
        case 'extended_line': drawing = addExtendedLine(p1, point); break;
        case 'fibonacci': drawing = addFibonacci(p1, point); break;
        case 'rectangle': drawing = addRectangle(p1, point); break;
        case 'circle': drawing = addCircle(p1, point); break;
        case 'measure': drawing = addMeasure(p1, point); break;
      }
      setPendingDrawing(null);
      setTentativeEndpoint(null);
      setActiveTool('none');
      return drawing;
    }

    // ── 3-click tools ────────────────────────────────────────────────
    if (clicksNeeded === 3) {
      if (!pendingDrawing) {
        // Click 1: set point1
        setPendingDrawing({ type: tool as DrawingType, point1: point });
        return null;
      }
      if (!pendingDrawing.point2) {
        // Click 2: set point2
        setPendingDrawing({ ...pendingDrawing, point2: point });
        return null;
      }
      // Click 3: finalize
      const p1 = pendingDrawing.point1;
      const p2 = pendingDrawing.point2;
      let drawing: Drawing | null = null;
      switch (pendingDrawing.type) {
        case 'parallel_channel': {
                    // Calculate offset so second line passes through click position
                    const dt = p2.time - p1.time;
                    const tRatio = dt !== 0 ? (point.time - p1.time) / dt : 0;
                    const priceOnLine = p1.price + (p2.price - p1.price) * tRatio;
                    const offset = point.price - priceOnLine;
                    drawing = addParallelChannel(p1, p2, { time: p1.time, price: p1.price + offset });
                    break;
                }
        case 'triangle': drawing = addTriangle(p1, p2, point); break;
      }
      setPendingDrawing(null);
      setTentativeEndpoint(null);
      setActiveTool('none');
      return drawing;
    }

    return null;
  }, [activeTool, pendingDrawing, addHorizontalLine, addVerticalLine, addTrendline,
    addRay, addExtendedLine, addFibonacci, addRectangle, addCircle, addMeasure,
    addParallelChannel, addTriangle]);

  const updateTentativeEndpoint = useCallback((x: number, y: number, price: number) => {
    if (pendingDrawing) {
      setTentativeEndpoint({ x, y, price });
    }
  }, [pendingDrawing]);

  const cancelDrawing = useCallback(() => {
    setActiveTool('none');
    setPendingDrawing(null);
    setTentativeEndpoint(null);
  }, []);

  // ============================================================================
  // Return
  // ============================================================================

  return {
    drawings,
    activeTool,
    selectedColor,
    lineWidth,
    isDrawing: activeTool !== 'none',
    selectedDrawingId,
    isDragging,
    hoveredDrawingId,
    pendingDrawing,
    tentativeEndpoint,
    locked,
    canUndo,
    canRedo,

    setActiveTool,
    setSelectedColor,
    setLineWidth,
    cancelDrawing,
    setLocked,
    toggleLocked,
    undo,
    redo,

    addHorizontalLine,
    addVerticalLine,
    addTrendline,
    addRay,
    addExtendedLine,
    addParallelChannel,
    addFibonacci,
    addRectangle,
    addCircle,
    addTriangle,
    addMeasure,
    removeDrawing,
    clearAllDrawings,

    updateDrawingColor,
    updateDrawingLineWidth,
    updateDrawing,
    replaceDrawing,
    updateHorizontalLinePrice,
    updateVerticalLineTime,
    updateDrawingPoints,

    selectDrawing,
    setHoveredDrawing,
    startDragging,
    stopDragging,
    findDrawingNearPrice,

    handleChartClick,
    updateTentativeEndpoint,

    colors: DRAWING_COLORS,
  };
}

export default useChartDrawings;
