'use client';

/**
 * TVLayoutIcon — miniatura de un layout, renderizada desde su árbol de
 * partición (igual que TradingView): rectángulos redondeados con divisores
 * finos. Mismo árbol que usa la rejilla real, así el icono siempre coincide.
 */

import { TV_LAYOUTS, type LayoutNode } from './tvLayouts';

interface TVLayoutIconProps {
    layoutId: string;
    size?: number;
    active?: boolean;
}

interface Rect {
    x: number;
    y: number;
    w: number;
    h: number;
}

/** Recorre el árbol repartiendo el rectángulo en celdas (mismo criterio TV). */
function collectRects(node: LayoutNode, r: Rect, out: Rect[]): void {
    if (typeof node === 'number') {
        out.push(r);
        return;
    }
    const [kind, ...kids] = node;
    const n = kids.length;
    if (kind === 'h') {
        const w = r.w / n;
        kids.forEach((k, i) => collectRects(k, { x: r.x + i * w, y: r.y, w, h: r.h }, out));
    } else {
        const h = r.h / n;
        kids.forEach((k, i) => collectRects(k, { x: r.x, y: r.y + i * h, w: r.w, h }, out));
    }
}

export function TVLayoutIcon({ layoutId, size = 22, active = false }: TVLayoutIconProps) {
    const def = TV_LAYOUTS[layoutId] ?? TV_LAYOUTS.s;
    const pad = 1;
    const inner = size - pad * 2;
    const gap = 1;
    const rects: Rect[] = [];
    collectRects(def.tree, { x: 0, y: 0, w: 1, h: 1 }, rects);

    return (
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
            {rects.map((rc, i) => {
                const x = pad + rc.x * inner + gap / 2;
                const y = pad + rc.y * inner + gap / 2;
                const w = Math.max(0, rc.w * inner - gap);
                const h = Math.max(0, rc.h * inner - gap);
                return (
                    <rect
                        key={i}
                        x={x}
                        y={y}
                        width={w}
                        height={h}
                        rx={1.2}
                        fill="currentColor"
                        opacity={active ? 1 : 0.85}
                    />
                );
            })}
        </svg>
    );
}
