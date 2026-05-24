/**
 * SVG mini-miniature renderer for layout templates. Renders the grid as a
 * 22×22 svg where each cell becomes a filled rect with the same proportions
 * as the actual CSS template. Used by `<LayoutPickerPopover>`.
 */

import type { LayoutId } from './types';

interface CellRect {
    x: number;
    y: number;
    w: number;
    h: number;
}

const SIZE = 22;
const PAD = 2;
const GAP = 1.5;

/**
 * Geometry — for each layout, we encode the rectangle of every cell in the
 * normalised [0, 1] space. We then scale to the SVG viewport with padding.
 */
const LAYOUT_GEOMETRY: Record<LayoutId, CellRect[]> = {
    single: [{ x: 0, y: 0, w: 1, h: 1 }],
    '2v': [
        { x: 0, y: 0, w: 0.5, h: 1 },
        { x: 0.5, y: 0, w: 0.5, h: 1 },
    ],
    '2h': [
        { x: 0, y: 0, w: 1, h: 0.5 },
        { x: 0, y: 0.5, w: 1, h: 0.5 },
    ],
    '3-left': [
        { x: 0, y: 0, w: 2 / 3, h: 1 },
        { x: 2 / 3, y: 0, w: 1 / 3, h: 0.5 },
        { x: 2 / 3, y: 0.5, w: 1 / 3, h: 0.5 },
    ],
    '3-right': [
        { x: 1 / 3, y: 0, w: 2 / 3, h: 1 },
        { x: 0, y: 0, w: 1 / 3, h: 0.5 },
        { x: 0, y: 0.5, w: 1 / 3, h: 0.5 },
    ],
    '3-top': [
        { x: 0, y: 0, w: 1, h: 2 / 3 },
        { x: 0, y: 2 / 3, w: 0.5, h: 1 / 3 },
        { x: 0.5, y: 2 / 3, w: 0.5, h: 1 / 3 },
    ],
    '3-bottom': [
        { x: 0, y: 1 / 3, w: 1, h: 2 / 3 },
        { x: 0, y: 0, w: 0.5, h: 1 / 3 },
        { x: 0.5, y: 0, w: 0.5, h: 1 / 3 },
    ],
    '3-cols': [
        { x: 0, y: 0, w: 1 / 3, h: 1 },
        { x: 1 / 3, y: 0, w: 1 / 3, h: 1 },
        { x: 2 / 3, y: 0, w: 1 / 3, h: 1 },
    ],
    '3-rows': [
        { x: 0, y: 0, w: 1, h: 1 / 3 },
        { x: 0, y: 1 / 3, w: 1, h: 1 / 3 },
        { x: 0, y: 2 / 3, w: 1, h: 1 / 3 },
    ],
    '4-grid': [
        { x: 0, y: 0, w: 0.5, h: 0.5 },
        { x: 0.5, y: 0, w: 0.5, h: 0.5 },
        { x: 0, y: 0.5, w: 0.5, h: 0.5 },
        { x: 0.5, y: 0.5, w: 0.5, h: 0.5 },
    ],
    '4-rows': [
        { x: 0, y: 0, w: 1, h: 0.25 },
        { x: 0, y: 0.25, w: 1, h: 0.25 },
        { x: 0, y: 0.5, w: 1, h: 0.25 },
        { x: 0, y: 0.75, w: 1, h: 0.25 },
    ],
    '4-cols': [
        { x: 0, y: 0, w: 0.25, h: 1 },
        { x: 0.25, y: 0, w: 0.25, h: 1 },
        { x: 0.5, y: 0, w: 0.25, h: 1 },
        { x: 0.75, y: 0, w: 0.25, h: 1 },
    ],
    '4-top1': [
        { x: 0, y: 0, w: 1, h: 2 / 3 },
        { x: 0, y: 2 / 3, w: 1 / 3, h: 1 / 3 },
        { x: 1 / 3, y: 2 / 3, w: 1 / 3, h: 1 / 3 },
        { x: 2 / 3, y: 2 / 3, w: 1 / 3, h: 1 / 3 },
    ],
    '4-left1': [
        { x: 0, y: 0, w: 2 / 3, h: 1 },
        { x: 2 / 3, y: 0, w: 1 / 3, h: 1 / 3 },
        { x: 2 / 3, y: 1 / 3, w: 1 / 3, h: 1 / 3 },
        { x: 2 / 3, y: 2 / 3, w: 1 / 3, h: 1 / 3 },
    ],
    '5-left': [
        { x: 0, y: 0, w: 0.5, h: 1 },
        { x: 0.5, y: 0, w: 0.25, h: 0.5 },
        { x: 0.75, y: 0, w: 0.25, h: 0.5 },
        { x: 0.5, y: 0.5, w: 0.25, h: 0.5 },
        { x: 0.75, y: 0.5, w: 0.25, h: 0.5 },
    ],
    '5-right': [
        { x: 0.5, y: 0, w: 0.5, h: 1 },
        { x: 0, y: 0, w: 0.25, h: 0.5 },
        { x: 0.25, y: 0, w: 0.25, h: 0.5 },
        { x: 0, y: 0.5, w: 0.25, h: 0.5 },
        { x: 0.25, y: 0.5, w: 0.25, h: 0.5 },
    ],
    '6-grid': [
        { x: 0, y: 0, w: 1 / 3, h: 0.5 },
        { x: 1 / 3, y: 0, w: 1 / 3, h: 0.5 },
        { x: 2 / 3, y: 0, w: 1 / 3, h: 0.5 },
        { x: 0, y: 0.5, w: 1 / 3, h: 0.5 },
        { x: 1 / 3, y: 0.5, w: 1 / 3, h: 0.5 },
        { x: 2 / 3, y: 0.5, w: 1 / 3, h: 0.5 },
    ],
    '6-rows': Array.from({ length: 6 }, (_, i) => ({
        x: 0,
        y: i / 6,
        w: 1,
        h: 1 / 6,
    })),
    '6-cols': Array.from({ length: 6 }, (_, i) => ({
        x: i / 6,
        y: 0,
        w: 1 / 6,
        h: 1,
    })),
    '8-grid': [
        ...[0, 1, 2, 3].map((i) => ({ x: i / 4, y: 0, w: 1 / 4, h: 0.5 })),
        ...[0, 1, 2, 3].map((i) => ({ x: i / 4, y: 0.5, w: 1 / 4, h: 0.5 })),
    ],
};

export interface LayoutIconProps {
    layoutId: LayoutId;
    size?: number;
    /** When true, highlight the icon (selected/hover state in the picker). */
    active?: boolean;
    className?: string;
}

export function LayoutIcon({ layoutId, size = SIZE, active = false, className }: LayoutIconProps) {
    const geom = LAYOUT_GEOMETRY[layoutId] ?? LAYOUT_GEOMETRY.single;
    const inner = size - PAD * 2;

    const fill = active ? 'currentColor' : 'currentColor';
    const opacity = active ? 1 : 0.85;
    const strokeOpacity = active ? 1 : 0.65;

    return (
        <svg
            width={size}
            height={size}
            viewBox={`0 0 ${size} ${size}`}
            className={className}
            aria-hidden
        >
            {geom.map((r, idx) => {
                const x = PAD + r.x * inner + GAP / 2;
                const y = PAD + r.y * inner + GAP / 2;
                const w = r.w * inner - GAP;
                const h = r.h * inner - GAP;
                return (
                    <rect
                        key={idx}
                        x={x}
                        y={y}
                        width={Math.max(0, w)}
                        height={Math.max(0, h)}
                        rx={1.5}
                        ry={1.5}
                        fill={fill}
                        fillOpacity={opacity * 0.18}
                        stroke={fill}
                        strokeOpacity={strokeOpacity}
                        strokeWidth={1}
                    />
                );
            })}
        </svg>
    );
}
