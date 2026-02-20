/**
 * Drawing Primitives Types for lightweight-charts v5
 */

// ============================================================================
// Drawing point (anchored to bar time + price)
// ============================================================================

export interface DrawingPoint {
  time: number;     // UTCTimestamp (seconds)
  price: number;
  logical?: number; // Logical bar index (for points beyond data range)
}

// ============================================================================
// Drawing types
// ============================================================================

export type DrawingType = 'horizontal_line' | 'trendline' | 'fibonacci' | 'rectangle';

export type DrawingTool = 'none' | DrawingType;

export interface BaseDrawing {
  id: string;
  type: DrawingType;
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
}

export interface HorizontalLineDrawing extends BaseDrawing {
  type: 'horizontal_line';
  price: number;
  label?: string;
}

export interface TrendlineDrawing extends BaseDrawing {
  type: 'trendline';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

export interface FibonacciDrawing extends BaseDrawing {
  type: 'fibonacci';
  point1: DrawingPoint;
  point2: DrawingPoint;
  levels: number[];
}

export interface RectangleDrawing extends BaseDrawing {
  type: 'rectangle';
  point1: DrawingPoint;
  point2: DrawingPoint;
  fillColor: string;
}

export type Drawing = HorizontalLineDrawing | TrendlineDrawing | FibonacciDrawing | RectangleDrawing;

// ============================================================================
// Fibonacci default levels
// ============================================================================

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

// ============================================================================
// Drawing colors
// ============================================================================

export const DRAWING_COLORS = [
  '#3b82f6', // blue
  '#ef4444', // red
  '#10b981', // green
  '#f59e0b', // amber
  '#8b5cf6', // violet
  '#ec4899', // pink
];

// ============================================================================
// Pending drawing state (while user is placing points)
// ============================================================================

export interface PendingDrawing {
  type: DrawingType;
  point1: DrawingPoint;
}
