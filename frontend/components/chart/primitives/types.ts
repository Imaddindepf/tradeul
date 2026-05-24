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
  | 'measure'
  | 'arrow'
  | 'text'
  | 'price_range'
  | 'date_range';

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

/** Single-anchor directional marker. Renders as an arrow head pointing at the
 *  anchor from `direction` (the tail extends outward; the tip sits on the
 *  anchor — same way TradingView mounts its "Arrow" tool). */
export type ArrowDirection = 'up' | 'down' | 'left' | 'right';

export interface ArrowDrawing extends BaseDrawing {
  type: 'arrow';
  point1: DrawingPoint;
  direction: ArrowDirection;
}

/** Single-anchor text annotation. The anchor is the top-left corner of the
 *  rendered label box (no draggable resize box — handle = the anchor itself).
 */
export interface TextDrawing extends BaseDrawing {
  type: 'text';
  point1: DrawingPoint;
  text: string;
  fontSize: number;        // px
  background: boolean;     // true → filled pill, false → transparent
}

/** Vertical-only measurement: locks X (uses point1.time for both ends) and
 *  reports Δprice + percentage between point1.price and point2.price. */
export interface PriceRangeDrawing extends BaseDrawing {
  type: 'price_range';
  point1: DrawingPoint;
  point2: DrawingPoint;
}

/** Horizontal-only measurement: locks Y (uses point1.price for both ends) and
 *  reports bar count + Δtime between point1.time and point2.time. */
export interface DateRangeDrawing extends BaseDrawing {
  type: 'date_range';
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
  | MeasureDrawing
  | ArrowDrawing
  | TextDrawing
  | PriceRangeDrawing
  | DateRangeDrawing;

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
  arrow: 1,
  text: 1,
  price_range: 2,
  date_range: 2,
};
