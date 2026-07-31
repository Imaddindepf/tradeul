'use client';

/**
 * TVLayoutGrid — renderiza la rejilla de celdas de un layout a partir de su
 * árbol de partición: ["h",…] = fila de columnas, ["v",…] = columna de filas.
 *
 * IMPLEMENTACIÓN PLANA: todas las celdas son hijas directas de un contenedor
 * `relative`, posicionadas en absoluto con su rect calculado del árbol (calc
 * de % + px para respetar el gap). ¿Por qué? Las celdas contienen IFRAMES de
 * la Charting Library: si el cambio de layout cambiara su posición en el DOM
 * (árbol flex anidado), React los desmontaría y cada chart pagaría de nuevo
 * TODA su inicialización. Con la rejilla plana y keys estables (`cell-N`),
 * cambiar de layout solo cambia estilos: las celdas supervivientes conservan
 * su iframe vivo y el cambio es instantáneo; solo se montan/desmontan las
 * celdas del delta.
 *
 * Soporta los 55 layouts de TradingView sin plantillas CSS a medida.
 */

import { useMemo, type ReactNode } from 'react';
import { TV_LAYOUTS, type LayoutNode } from './tvLayouts';

interface TVLayoutGridProps {
    layoutId: string;
    /** Devuelve el contenido de la celda con ese índice (0-based). */
    renderCell: (cellIndex: number) => ReactNode;
    gap?: number;
}

/** Longitud como fracción del contenedor raíz: `calc(pct% + px)`. */
interface Frac {
    pct: number;
    px: number;
}

interface CellRect {
    left: Frac;
    top: Frac;
    width: Frac;
    height: Frac;
}

const frac = (pct: number, px: number): Frac => ({ pct, px });
const css = (f: Frac): string =>
    f.px === 0 ? `${f.pct}%` : `calc(${f.pct}% + ${f.px}px)`;

/**
 * Recorre el árbol de partición repartiendo el rect del padre a partes
 * iguales entre los hijos (mismo resultado visual que el flex `1 1 0` con
 * `gap` de la implementación anidada original).
 */
function computeRects(tree: LayoutNode, gap: number): Map<number, CellRect> {
    const rects = new Map<number, CellRect>();
    const walk = (node: LayoutNode, rect: CellRect) => {
        if (typeof node === 'number') {
            rects.set(node, rect);
            return;
        }
        const [kind, ...kids] = node;
        const k = kids.length;
        if (kind === 'h') {
            const w = frac(rect.width.pct / k, (rect.width.px - (k - 1) * gap) / k);
            kids.forEach((child, i) => {
                walk(child, {
                    left: frac(rect.left.pct + i * w.pct, rect.left.px + i * (w.px + gap)),
                    top: rect.top,
                    width: w,
                    height: rect.height,
                });
            });
        } else {
            const h = frac(rect.height.pct / k, (rect.height.px - (k - 1) * gap) / k);
            kids.forEach((child, i) => {
                walk(child, {
                    left: rect.left,
                    top: frac(rect.top.pct + i * h.pct, rect.top.px + i * (h.px + gap)),
                    width: rect.width,
                    height: h,
                });
            });
        }
    };
    walk(tree, {
        left: frac(0, 0),
        top: frac(0, 0),
        width: frac(100, 0),
        height: frac(100, 0),
    });
    return rects;
}

export function TVLayoutGrid({ layoutId, renderCell, gap = 2 }: TVLayoutGridProps) {
    const def = TV_LAYOUTS[layoutId] ?? TV_LAYOUTS.s;
    const rects = useMemo(() => computeRects(def.tree, gap), [def, gap]);
    // Orden de render SIEMPRE por índice de celda: si el orden de los hijos
    // cambiara entre layouts, React movería los nodos (insertBefore) y un
    // iframe movido en el DOM se RECARGA — adiós a la gracia de la rejilla
    // plana. Con orden estable, cambiar de layout solo toca estilos.
    const ordered = Array.from(rects.entries()).sort(([a], [b]) => a - b);
    return (
        <div style={{ position: 'relative', width: '100%', height: '100%' }}>
            {ordered.map(([index, r]) => (
                <div
                    key={`cell-${index}`}
                    style={{
                        position: 'absolute',
                        left: css(r.left),
                        top: css(r.top),
                        width: css(r.width),
                        height: css(r.height),
                    }}
                >
                    {renderCell(index)}
                </div>
            ))}
        </div>
    );
}
