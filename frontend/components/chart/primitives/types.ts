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

export type DrawingType =
  | 'horizontal_line'
  | 'trendline'
  | 'fibonacci'
  | 'rectangle'
  | 'vertical_line'
  | 'ray'
  | 'extended_line'
  | 'parallel_channel'
  | 'circle'
  | 'triangle'
  | 'measure';

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

export interface VerticalLineDrawing extends BaseDrawing {
  type: 'vertical_line';
  time: number;
}

export interface TrendlineDrawing extends BaseDrawing {
  type: 'trendline';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

export interface RayDrawing extends BaseDrawing {
  type: 'ray';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

export interface ExtendedLineDrawing extends BaseDrawing {
  type: 'extended_line';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

export interface ParallelChannelDrawing extends BaseDrawing {
  type: 'parallel_channel';
  point1: DrawingPoint;
  point2: DrawingPoint;
  point3: DrawingPoint; // Defines the channel width offset
  fillColor: string;
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

export interface CircleDrawing extends BaseDrawing {
  type: 'circle';
  point1: DrawingPoint; // center
  point2: DrawingPoint; // edge point (defines radius)
  fillColor: string;
}

export interface TriangleDrawing extends BaseDrawing {
  type: 'triangle';
  point1: DrawingPoint;
  point2: DrawingPoint;
  point3: DrawingPoint;
  fillColor: string;
}

export interface MeasureDrawing extends BaseDrawing {
  type: 'measure';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

export type Drawing =
  | HorizontalLineDrawing
  | VerticalLineDrawing
  | TrendlineDrawing
  | RayDrawing
  | ExtendedLineDrawing
  | ParallelChannelDrawing
  | FibonacciDrawing
  | RectangleDrawing
  | CircleDrawing
  | TriangleDrawing
  | MeasureDrawing;

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
  point2?: DrawingPoint; // For 3-click tools (parallel_channel, triangle)
}

// ============================================================================
// Click counts per tool
// ============================================================================

export const TOOL_CLICKS: Record<DrawingType, number> = {
  horizontal_line: 1,
  vertical_line: 1,
  trendline: 2,
  ray: 2,
  extended_line: 2,
  fibonacci: 2,
  rectangle: 2,
  circle: 2,
  measure: 2,
  parallel_channel: 3,
  triangle: 3,
};
