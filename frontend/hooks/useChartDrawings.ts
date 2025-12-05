/**
 * useChartDrawings - Hook para gestionar dibujos persistentes en charts
 * 
 * Actualmente soporta:
 * - Líneas horizontales (niveles de precio)
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// ============================================================================
// Types
// ============================================================================

export type DrawingType = 'horizontal_line';

export interface HorizontalLineDrawing {
  id: string;
  type: 'horizontal_line';
  price: number;
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  label?: string;
}

export type Drawing = HorizontalLineDrawing;

export type DrawingTool = 'none' | 'horizontal_line';

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = 'tradeul_chart_drawings';

const DEFAULT_COLORS = [
  '#3b82f6', // blue
  '#ef4444', // red
  '#10b981', // green
  '#f59e0b', // amber
  '#8b5cf6', // violet
  '#ec4899', // pink
];

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
    const data = stored ? JSON.parse(stored) : {};
    // Filtrar solo líneas horizontales (limpiar datos antiguos de trend_line)
    for (const ticker of Object.keys(data)) {
      data[ticker] = (data[ticker] as any[]).filter((d: any) => d.type === 'horizontal_line');
    }
    return data;
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

// ============================================================================
// Hook
// ============================================================================

export function useChartDrawings(ticker: string) {
  // Estado principal
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [activeTool, setActiveTool] = useState<DrawingTool>('none');
  const [selectedColor, setSelectedColor] = useState(DEFAULT_COLORS[0]);
  const [lineWidth, setLineWidth] = useState(DEFAULT_LINE_WIDTH);
  
  // Estado de selección/drag
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [hoveredDrawingId, setHoveredDrawingId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  const tickerRef = useRef(ticker);

  // ============================================================================
  // Cargar/Guardar
  // ============================================================================

  useEffect(() => {
    tickerRef.current = ticker;
    const allDrawings = loadFromStorage();
    setDrawings(allDrawings[ticker] || []);
    setSelectedDrawingId(null);
  }, [ticker]);

  useEffect(() => {
    const allDrawings = loadFromStorage();
    allDrawings[tickerRef.current] = drawings;
    saveToStorage(allDrawings);
  }, [drawings]);

  // ============================================================================
  // Crear dibujos
  // ============================================================================

  const addHorizontalLine = useCallback((price: number) => {
    const drawing: HorizontalLineDrawing = {
      id: generateId(),
      type: 'horizontal_line',
      price,
      color: selectedColor,
      lineWidth: lineWidth,
      lineStyle: 'solid',
    };
    
    setDrawings(prev => [...prev, drawing]);
    setSelectedDrawingId(drawing.id);
    return drawing;
  }, [selectedColor, lineWidth]);

  // ============================================================================
  // Eliminar dibujos
  // ============================================================================

  const removeDrawing = useCallback((id: string) => {
    setDrawings(prev => prev.filter(d => d.id !== id));
    if (selectedDrawingId === id) {
      setSelectedDrawingId(null);
    }
  }, [selectedDrawingId]);

  const clearAllDrawings = useCallback(() => {
    setDrawings([]);
    setSelectedDrawingId(null);
  }, []);

  // ============================================================================
  // Modificar dibujos (UNIFICADO para todos los tipos)
  // ============================================================================

  const updateDrawingColor = useCallback((id: string, newColor: string) => {
    setDrawings(prev => prev.map(d => 
      d.id === id ? { ...d, color: newColor } : d
    ));
  }, []);

  const updateDrawingLineWidth = useCallback((id: string, newWidth: number) => {
    setDrawings(prev => prev.map(d => 
      d.id === id ? { ...d, lineWidth: newWidth } : d
    ));
  }, []);

  // Actualizar precio de línea horizontal
  const updateHorizontalLinePrice = useCallback((id: string, newPrice: number) => {
    setDrawings(prev => prev.map(d => {
      if (d.id === id && d.type === 'horizontal_line') {
        return { ...d, price: newPrice };
      }
      return d;
    }));
  }, []);

  // ============================================================================
  // Selección y drag (UNIFICADO)
  // ============================================================================

  const selectDrawing = useCallback((id: string | null) => {
    setSelectedDrawingId(id);
  }, []);

  const setHoveredDrawing = useCallback((id: string | null) => {
    setHoveredDrawingId(id);
  }, []);

  const startDragging = useCallback(() => {
    setIsDragging(true);
  }, []);

  const stopDragging = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Encontrar dibujo cercano a coordenadas de precio
  const findDrawingNearPrice = useCallback((
    price: number, 
    tolerance: number = 1.5
  ): Drawing | null => {
    let closestDrawing: Drawing | null = null;
    let closestDiff = Infinity;
    
    for (const drawing of drawings) {
      if (drawing.type === 'horizontal_line') {
        const diff = Math.abs(drawing.price - price);
        const pctDiff = (diff / price) * 100;
        if (pctDiff < tolerance && pctDiff < closestDiff) {
          closestDiff = pctDiff;
          closestDrawing = drawing;
        }
      }
    }
    
    return closestDrawing;
  }, [drawings]);

  // ============================================================================
  // Manejo de clicks en el chart
  // ============================================================================

  const handleChartClick = useCallback((price: number) => {
    if (activeTool === 'none') return null;

    if (activeTool === 'horizontal_line') {
      const drawing = addHorizontalLine(price);
      setActiveTool('none');
      return drawing;
    }

    return null;
  }, [activeTool, addHorizontalLine]);

  const cancelDrawing = useCallback(() => {
    setActiveTool('none');
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
    
    // Tool selection
    setActiveTool,
    setSelectedColor,
    setLineWidth,
    cancelDrawing,
    
    // CRUD
    addHorizontalLine,
    removeDrawing,
    clearAllDrawings,
    
    // Modificación
    updateDrawingColor,
    updateDrawingLineWidth,
    updateHorizontalLinePrice,
    
    // Selección y drag
    selectDrawing,
    setHoveredDrawing,
    startDragging,
    stopDragging,
    findDrawingNearPrice,
    
    // Chart interaction
    handleChartClick,
    
    // Constants
    colors: DEFAULT_COLORS,
  };
}

export default useChartDrawings;
