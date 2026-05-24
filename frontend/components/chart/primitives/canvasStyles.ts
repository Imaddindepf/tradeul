/**
 * Shared canvas styling helpers for drawing primitives.
 *
 * Centralises how `lineStyle` ('solid' | 'dashed' | 'dotted') maps to canvas
 * dash patterns so every primitive renders consistently and `dotted` no longer
 * silently falls back to a solid line.
 */

import type { BaseDrawing } from './types';

export type LineStyle = BaseDrawing['lineStyle'];

/**
 * Returns the `setLineDash` pattern for a given style. The dotted pattern is
 * scaled with `lineWidth` so dots remain visible at thin strokes and grow
 * sensibly when thickening the line.
 */
export function lineDashPattern(style: LineStyle, lineWidth: number): number[] {
    if (style === 'solid') return [];
    if (style === 'dashed') return [6, 4];
    const w = Math.max(1, lineWidth);
    return [w, w * 2];
}

/**
 * Applies the line style to a 2D canvas context. For dotted lines we also
 * switch to `lineCap: 'round'` so each dash renders as a true dot rather than
 * a stubby rectangle. Caller MUST call `resetLineStyle` after the stroke if it
 * intends to draw additional paths with a different style.
 */
export function applyLineStyle(
    ctx: CanvasRenderingContext2D,
    style: LineStyle,
    lineWidth: number,
): void {
    const dash = lineDashPattern(style, lineWidth);
    if (dash.length === 0) {
        ctx.setLineDash([]);
        ctx.lineCap = 'butt';
        return;
    }
    if (style === 'dotted') {
        ctx.lineCap = 'round';
    } else {
        ctx.lineCap = 'butt';
    }
    ctx.setLineDash(dash);
}

/** Resets dash + cap to defaults. Always call after stroking with a dashed/dotted style. */
export function resetLineStyle(ctx: CanvasRenderingContext2D): void {
    ctx.setLineDash([]);
    ctx.lineCap = 'butt';
}

/**
 * Converts a hex color (#rrggbb or #rrggbbaa) plus optional alpha override into
 * an rgba string. If `hex` is already an rgba/rgb string, it is returned
 * unchanged when no `alpha` is provided, or re-emitted with the new alpha.
 */
export function colorWithAlpha(hex: string, alpha: number): string {
    if (hex.startsWith('rgba') || hex.startsWith('rgb')) {
        // Parse existing rgb(a) and replace alpha
        const m = hex.match(/rgba?\(([^)]+)\)/);
        if (m) {
            const parts = m[1].split(',').map(s => s.trim());
            const [r, g, b] = parts;
            return `rgba(${r},${g},${b},${clampAlpha(alpha)})`;
        }
    }
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${clampAlpha(alpha)})`;
}

/** Extracts the alpha component from an rgba string, defaulting to 1. */
export function alphaFromColor(color: string): number {
    if (color.startsWith('rgba')) {
        const m = color.match(/rgba\([^)]+,\s*([0-9.]+)\)/);
        if (m) return clampAlpha(parseFloat(m[1]));
    }
    return 1;
}

function clampAlpha(a: number): number {
    if (!Number.isFinite(a)) return 1;
    return Math.max(0, Math.min(1, a));
}
