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
const DEFAULT_LINE_WIDTH = 2;

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
  // Main state
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [activeTool, setActiveTool] = useState<DrawingTool>('none');
  const activeToolRef = useRef(activeTool);
  activeToolRef.current = activeTool;
  const [selectedColor, setSelectedColor] = useState(DRAWING_COLORS[0]);
  const [lineWidth, setLineWidth] = useState(DEFAULT_LINE_WIDTH);

  // Selection state
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [hoveredDrawingId, setHoveredDrawingId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Pending drawing state (for multi-click tools)
  const [pendingDrawing, setPendingDrawing] = useState<PendingDrawing | null>(null);

  // Tentative endpoint (mouse position while placing)
  const [tentativeEndpoint, setTentativeEndpoint] = useState<{ x: number; y: number; price: number } | null>(null);

  const tickerRef = useRef(ticker);

  // ============================================================================
  // Load / Save
  // ============================================================================

  useEffect(() => {
    tickerRef.current = ticker;
    const allDrawings = loadFromStorage();
    setDrawings(allDrawings[ticker] || []);
    setSelectedDrawingId(null);
    setPendingDrawing(null);
    setTentativeEndpoint(null);
  }, [ticker]);

  useEffect(() => {
    const allDrawings = loadFromStorage();
    allDrawings[tickerRef.current] = drawings;
    saveToStorage(allDrawings);
  }, [drawings]);

  // ============================================================================
  // Create drawings — 1-click
  // ============================================================================

  const addHorizontalLine = useCallback((price: number): HorizontalLineDrawing => {
    const drawing: HorizontalLineDrawing = {
      id: generateId(),
      type: 'horizontal_line',
      price,
      color: selectedColor,
      lineWidth,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  const addVerticalLine = useCallback((time: number): VerticalLineDrawing => {
    const drawing: VerticalLineDrawing = {
      id: generateId(),
      type: 'vertical_line',
      time,
      color: selectedColor,
      lineWidth,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  // ============================================================================
  // Create drawings — 2-click
  // ============================================================================

  const addTrendline = useCallback((p1: DrawingPoint, p2: DrawingPoint): TrendlineDrawing => {
    const drawing: TrendlineDrawing = {
      id: generateId(),
      type: 'trendline',
      point1: p1,
      point2: p2,
      color: selectedColor,
      lineWidth,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  const addRay = useCallback((p1: DrawingPoint, p2: DrawingPoint): RayDrawing => {
    const drawing: RayDrawing = {
      id: generateId(),
      type: 'ray',
      point1: p1,
      point2: p2,
      color: selectedColor,
      lineWidth,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  const addExtendedLine = useCallback((p1: DrawingPoint, p2: DrawingPoint): ExtendedLineDrawing => {
    const drawing: ExtendedLineDrawing = {
      id: generateId(),
      type: 'extended_line',
      point1: p1,
      point2: p2,
      color: selectedColor,
      lineWidth,
      lineStyle: 'dashed',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  const addFibonacci = useCallback((p1: DrawingPoint, p2: DrawingPoint): FibonacciDrawing => {
    const drawing: FibonacciDrawing = {
      id: generateId(),
      type: 'fibonacci',
      point1: p1,
      point2: p2,
      levels: [...FIB_LEVELS],
      color: selectedColor,
      lineWidth: 1,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor]);

  const addRectangle = useCallback((p1: DrawingPoint, p2: DrawingPoint): RectangleDrawing => {
    const drawing: RectangleDrawing = {
      id: generateId(),
      type: 'rectangle',
      point1: p1,
      point2: p2,
      color: selectedColor,
      fillColor: hexToRgba(selectedColor, 0.1),
      lineWidth: 1,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor]);

  const addCircle = useCallback((p1: DrawingPoint, p2: DrawingPoint): CircleDrawing => {
    const drawing: CircleDrawing = {
      id: generateId(),
      type: 'circle',
      point1: p1,
      point2: p2,
      color: selectedColor,
      fillColor: hexToRgba(selectedColor, 0.08),
      lineWidth: 1,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor]);

  const addMeasure = useCallback((p1: DrawingPoint, p2: DrawingPoint): MeasureDrawing => {
    const drawing: MeasureDrawing = {
      id: generateId(),
      type: 'measure',
      point1: p1,
      point2: p2,
      color: '#64748b',
      lineWidth: 1,
      lineStyle: 'dashed',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, []);

  // ============================================================================
  // Create drawings — 3-click
  // ============================================================================

  const addParallelChannel = useCallback((p1: DrawingPoint, p2: DrawingPoint, p3: DrawingPoint): ParallelChannelDrawing => {
    const drawing: ParallelChannelDrawing = {
      id: generateId(),
      type: 'parallel_channel',
      point1: p1,
      point2: p2,
      point3: p3,
      color: selectedColor,
      fillColor: hexToRgba(selectedColor, 0.08),
      lineWidth,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  const addTriangle = useCallback((p1: DrawingPoint, p2: DrawingPoint, p3: DrawingPoint): TriangleDrawing => {
    const drawing: TriangleDrawing = {
      id: generateId(),
      type: 'triangle',
      point1: p1,
      point2: p2,
      point3: p3,
      color: selectedColor,
      fillColor: hexToRgba(selectedColor, 0.08),
      lineWidth: 1,
      lineStyle: 'solid',
    };
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor]);

  // ============================================================================
  // Delete
  // ============================================================================

  const removeDrawing = useCallback((id: string) => {
    setDrawings(prev => prev.filter(d => d.id !== id));
    if (selectedDrawingId === id) setSelectedDrawingId(null);
  }, [selectedDrawingId]);

  const clearAllDrawings = useCallback(() => {
    setDrawings([]);
    setSelectedDrawingId(null);
  }, []);

  // ============================================================================
  // Modify
  // ============================================================================

  const updateDrawingColor = useCallback((id: string, newColor: string) => {
    setDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if ('fillColor' in d) {
        return { ...d, color: newColor, fillColor: hexToRgba(newColor, 0.1) };
      }
      return { ...d, color: newColor };
    }));
  }, []);

  const updateDrawingLineWidth = useCallback((id: string, newWidth: number) => {
    setDrawings(prev => prev.map(d => d.id === id ? { ...d, lineWidth: newWidth } : d));
  }, []);

  const updateHorizontalLinePrice = useCallback((id: string, newPrice: number) => {
    setDrawings(prev => prev.map(d => {
      if (d.id === id && d.type === 'horizontal_line') return { ...d, price: newPrice };
      return d;
    }));
  }, []);

  const updateVerticalLineTime = useCallback((id: string, newTime: number) => {
    setDrawings(prev => prev.map(d => {
      if (d.id === id && d.type === 'vertical_line') return { ...d, time: newTime };
      return d;
    }));
  }, []);

  const updateDrawingPoints = useCallback((id: string, points: { point1?: DrawingPoint; point2?: DrawingPoint; point3?: DrawingPoint }) => {
    setDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if (d.type === 'horizontal_line') return d;
      if (d.type === 'vertical_line') return d;
      const updated = { ...d } as any;
      if (points.point1) updated.point1 = points.point1;
      if (points.point2) updated.point2 = points.point2;
      if (points.point3 && 'point3' in updated) updated.point3 = points.point3;
      return updated;
    }));
  }, []);

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
    // State
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

    // Tool selection
    setActiveTool,
    setSelectedColor,
    setLineWidth,
    cancelDrawing,

    // CRUD
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

    // Modify
    updateDrawingColor,
    updateDrawingLineWidth,
    updateHorizontalLinePrice,
    updateVerticalLineTime,
    updateDrawingPoints,

    // Selection & drag
    selectDrawing,
    setHoveredDrawing,
    startDragging,
    stopDragging,
    findDrawingNearPrice,

    // Chart interaction
    handleChartClick,
    updateTentativeEndpoint,

    // Constants
    colors: DRAWING_COLORS,
  };
}

export default useChartDrawings;
