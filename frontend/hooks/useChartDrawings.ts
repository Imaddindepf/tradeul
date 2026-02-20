/**
 * useChartDrawings - Hook para gestionar dibujos persistentes en charts
 * 
 * Soporta:
 * - Líneas horizontales (1 click)
 * - Trendlines (2 clicks)
 * - Fibonacci retracement (2 clicks)
 * - Rectángulos (2 clicks)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  Drawing,
  DrawingType,
  DrawingTool,
  DrawingPoint,
  HorizontalLineDrawing,
  TrendlineDrawing,
  FibonacciDrawing,
  RectangleDrawing,
  PendingDrawing,
} from '@/components/chart/primitives/types';
import { FIB_LEVELS, DRAWING_COLORS } from '@/components/chart/primitives/types';

// Re-export types for consumers
export type { Drawing, DrawingType, DrawingTool, DrawingPoint, PendingDrawing };
export type {
  HorizontalLineDrawing,
  TrendlineDrawing,
  FibonacciDrawing,
  RectangleDrawing,
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

  // Pending drawing state (for 2-click tools: first point placed, waiting for second)
  const [pendingDrawing, setPendingDrawing] = useState<PendingDrawing | null>(null);

  // Tentative endpoint (mouse position while placing second point)
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
  // Create drawings
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
      if (d.type === 'rectangle') {
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

  const updateDrawingPoints = useCallback((id: string, points: { point1?: DrawingPoint; point2?: DrawingPoint }) => {
    setDrawings(prev => prev.map(d => {
      if (d.id !== id) return d;
      if (d.type === 'horizontal_line') return d;
      const updated = { ...d } as any;
      if (points.point1) updated.point1 = points.point1;
      if (points.point2) updated.point2 = points.point2;
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

  // Find drawing near a price (for horizontal lines only - legacy compat)
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

    // Horizontal line: single click
    if (tool === 'horizontal_line') {
      const drawing = addHorizontalLine(price);
      setActiveTool('none');
      return drawing;
    }

    // 2-click tools: trendline, fibonacci, rectangle
    if (!pendingDrawing) {
      // First click → store point1
      setPendingDrawing({ type: tool, point1: { time, price, logical } });
      return null;
    }

    // Second click → create the drawing
    const p1 = pendingDrawing.point1;
    const p2: DrawingPoint = { time, price, logical };
    let drawing: Drawing | null = null;

    switch (pendingDrawing.type) {
      case 'trendline':
        drawing = addTrendline(p1, p2);
        break;
      case 'fibonacci':
        drawing = addFibonacci(p1, p2);
        break;
      case 'rectangle':
        drawing = addRectangle(p1, p2);
        break;
    }

    setPendingDrawing(null);
    setTentativeEndpoint(null);
    setActiveTool('none');
    return drawing;
  }, [activeTool, pendingDrawing, addHorizontalLine, addTrendline, addFibonacci, addRectangle]);

  // Update tentative endpoint (called on crosshair move while pending)
  const updateTentativeEndpoint = useCallback((x: number, y: number, price: number) => {
    if (pendingDrawing) {
      setTentativeEndpoint({ x, y, price });
    }
  }, [pendingDrawing]);

  // Cancel current drawing
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
    addTrendline,
    addFibonacci,
    addRectangle,
    removeDrawing,
    clearAllDrawings,

    // Modify
    updateDrawingColor,
    updateDrawingLineWidth,
    updateHorizontalLinePrice,
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
