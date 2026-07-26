'use client';

/**
 * TVLayoutGrid — renderiza la rejilla de celdas de un layout a partir de su
 * árbol de partición (flexbox anidado): ["h",…] = fila de columnas, ["v",…] =
 * columna de filas. En cada hoja coloca `renderCell(cellIndex)`.
 *
 * Soporta los 55 layouts de TradingView sin plantillas CSS a medida.
 */

import { type ReactNode } from 'react';
import { TV_LAYOUTS, type LayoutNode } from './tvLayouts';

interface TVLayoutGridProps {
    layoutId: string;
    /** Devuelve el contenido de la celda con ese índice (0-based). */
    renderCell: (cellIndex: number) => ReactNode;
    gap?: number;
}

function renderNode(node: LayoutNode, renderCell: (i: number) => ReactNode, gap: number): ReactNode {
    if (typeof node === 'number') {
        return (
            <div key={`leaf-${node}`} style={{ flex: '1 1 0', minWidth: 0, minHeight: 0 }}>
                {renderCell(node)}
            </div>
        );
    }
    const [kind, ...kids] = node;
    return (
        <div
            style={{
                display: 'flex',
                flexDirection: kind === 'h' ? 'row' : 'column',
                flex: '1 1 0',
                minWidth: 0,
                minHeight: 0,
                gap,
            }}
        >
            {kids.map((child, i) => (
                <div key={i} style={{ display: 'flex', flex: '1 1 0', minWidth: 0, minHeight: 0 }}>
                    {renderNode(child, renderCell, gap)}
                </div>
            ))}
        </div>
    );
}

export function TVLayoutGrid({ layoutId, renderCell, gap = 2 }: TVLayoutGridProps) {
    const def = TV_LAYOUTS[layoutId] ?? TV_LAYOUTS.s;
    return (
        <div style={{ display: 'flex', width: '100%', height: '100%', minWidth: 0, minHeight: 0 }}>
            {renderNode(def.tree, renderCell, gap)}
        </div>
    );
}
