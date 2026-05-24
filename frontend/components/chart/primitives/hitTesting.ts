/**
 * Shared hit-testing primitives + cursor semantics for chart drawing tools.
 *
 * Design rules (TradingView-style):
 *   • Handles (endpoints / corners / mid-edges) always win over the body —
 *     priority order in every primitive's hitTest must be:
 *       1) per-handle tests   → cursor = HANDLE_CURSOR ("default", i.e. the
 *          OS arrow), externalId carries the handle suffix (":p1", ":p2",
 *          ":p3", ":p4", ":m1", ":m2", ":m3", ":m4")
 *       2) line-body / fill   → cursor = BODY_CURSOR ("grab", open hand),
 *          externalId is just the drawing id (no suffix → translate)
 *   • While the user is dragging:
 *       - dragging a handle     → cursor = HANDLE_DRAG_CURSOR ("default")
 *       - dragging the body     → cursor = DRAGGING_CURSOR ("grabbing")
 *     The drag controller in TradingChart.tsx is responsible for setting
 *     `document.body.style.cursor` during the drag — primitives only define
 *     the static hover cursor.
 *
 * All radii and tolerances live here so every tool feels identical.
 */

import type { PrimitiveHoveredItem } from 'lightweight-charts';

// ────────────────────────────────────────────────────────────────────────────
// Tunables — change once, applies to every drawing tool
// ────────────────────────────────────────────────────────────────────────────

/** Pixel radius for handle hit-detection (slightly larger than visual). */
export const HANDLE_HIT_RADIUS = 9;

/** Pixel tolerance for "I'm touching the line body". */
export const BODY_HIT_TOLERANCE = 6;

/** Padding around filled rectangular zones (rectangles, fib zones, etc.). */
export const ZONE_HIT_PADDING = 4;

/** Visual radius of the rendered handle dot (drawn by each primitive). */
export const HANDLE_RENDER_RADIUS = 5;

// ────────────────────────────────────────────────────────────────────────────
// Cursor semantics — single source of truth
// ────────────────────────────────────────────────────────────────────────────

/** Cursor when hovering a reshape handle: the OS default arrow. */
export const HANDLE_CURSOR = 'default';

/** Cursor when hovering the body of a drawing: open hand. */
export const BODY_CURSOR = 'grab';

/** Cursor while actively dragging the body: closed hand. */
export const DRAGGING_CURSOR = 'grabbing';

/** Cursor while actively dragging a handle: OS default arrow. */
export const HANDLE_DRAG_CURSOR = 'default';

// ────────────────────────────────────────────────────────────────────────────
// Handle suffix conventions (match the drag pipeline in TradingChart.tsx)
// ────────────────────────────────────────────────────────────────────────────

export type HandleSuffix = ':p1' | ':p2' | ':p3' | ':p4' | ':m1' | ':m2' | ':m3' | ':m4';

// ────────────────────────────────────────────────────────────────────────────
// Geometric predicates
// ────────────────────────────────────────────────────────────────────────────

/** True if (px,py) is within the handle hit radius of (hx,hy). */
export function isOverHandle(px: number, py: number, hx: number, hy: number): boolean {
  const dx = px - hx;
  const dy = py - hy;
  return dx * dx + dy * dy < HANDLE_HIT_RADIUS * HANDLE_HIT_RADIUS;
}

/** Distance from (px,py) to the finite segment p1→p2. */
export function distToSegment(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** Distance to a ray that starts at p1 and goes through p2 (clamped at p1, infinite past p2). */
export function distToRay(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, ((px - x1) * dx + (py - y1) * dy) / lenSq);
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** Distance to an infinite line through (x1,y1)→(x2,y2). */
export function distToLine(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  const t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** True if (px,py) lies inside the axis-aligned bounding box, with optional padding. */
export function inBox(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
  padding: number = ZONE_HIT_PADDING,
): boolean {
  const minX = Math.min(x1, x2) - padding;
  const maxX = Math.max(x1, x2) + padding;
  const minY = Math.min(y1, y2) - padding;
  const maxY = Math.max(y1, y2) + padding;
  return px >= minX && px <= maxX && py >= minY && py <= maxY;
}

/** Inclusive point-in-triangle test using barycentric sign check. */
export function inTriangle(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
  x3: number, y3: number,
): boolean {
  const d1 = (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2);
  const d2 = (px - x3) * (y2 - y3) - (x2 - x3) * (py - y3);
  const d3 = (px - x1) * (y3 - y1) - (x3 - x1) * (py - y1);
  const hasNeg = d1 < 0 || d2 < 0 || d3 < 0;
  const hasPos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(hasNeg && hasPos);
}

/** Inside-or-on the boundary of an axis-aligned ellipse centered at (cx,cy). */
export function inEllipse(
  px: number, py: number,
  cx: number, cy: number,
  rx: number, ry: number,
  slack: number = 0.15,
): boolean {
  if (rx < 0.5 || ry < 0.5) return false;
  const nx = (px - cx) / rx;
  const ny = (py - cy) / ry;
  return nx * nx + ny * ny <= 1 + slack;
}

/** True if (px,py) sits inside a convex polygon (vertices ordered, no self-intersections). */
export function inPolygon(px: number, py: number, pts: ReadonlyArray<readonly [number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i];
    const [xj, yj] = pts[j];
    const intersect = ((yi > py) !== (yj > py)) && (px < ((xj - xi) * (py - yi)) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// ────────────────────────────────────────────────────────────────────────────
// Hit-result factories — keep externalId conventions in one place
// ────────────────────────────────────────────────────────────────────────────

/** Build a handle-hit result. */
export function handleHit(id: string, suffix: HandleSuffix): PrimitiveHoveredItem {
  return { cursorStyle: HANDLE_CURSOR, externalId: id + suffix, zOrder: 'top' };
}

/** Build a body-hit result (cursor defaults to BODY_CURSOR). */
export function bodyHit(id: string, cursorStyle: string = BODY_CURSOR): PrimitiveHoveredItem {
  return { cursorStyle, externalId: id, zOrder: 'top' };
}

/**
 * Iterate handles in priority order and return the first hit, or null.
 * Use inside every primitive's hitTest before testing the body.
 */
export function firstHandleHit(
  px: number, py: number,
  id: string,
  handles: ReadonlyArray<readonly [number, number, HandleSuffix]>,
): PrimitiveHoveredItem | null {
  for (const [hx, hy, suffix] of handles) {
    if (isOverHandle(px, py, hx, hy)) return handleHit(id, suffix);
  }
  return null;
}
