/**
 * Layout templates — CSS grid definitions for each supported `LayoutId`.
 *
 * Each template declares:
 *   • `cellCount`    — how many cells the layout exposes.
 *   • `gridTemplate` — CSS `grid-template-areas` / cols / rows.
 *   • `category`     — used by the picker to group icons (TradingView style).
 *   • `label`        — accessible label shown in tooltips.
 *
 * Cell ids follow the convention `cell-1 … cell-N`, mapped 1:1 to grid areas
 * named `c1 … cN`. Order is the natural reading order (top-left → bottom-right).
 */

import type { LayoutId } from './types';

export interface LayoutTemplate {
    id: LayoutId;
    label: string;
    cellCount: number;
    category: '1' | '2' | '3' | '4' | '5+' | '8';
    grid: {
        columns: string;
        rows: string;
        areas: string;
    };
}

export const LAYOUT_TEMPLATES: Record<LayoutId, LayoutTemplate> = {
    // ── 1 chart ────────────────────────────────────────────────────────────
    'single': {
        id: 'single',
        label: '1 chart',
        cellCount: 1,
        category: '1',
        grid: {
            columns: '1fr',
            rows: '1fr',
            areas: '"c1"',
        },
    },

    // ── 2 charts ───────────────────────────────────────────────────────────
    '2v': {
        id: '2v',
        label: '2 charts (vertical split)',
        cellCount: 2,
        category: '2',
        grid: {
            columns: '1fr 1fr',
            rows: '1fr',
            areas: '"c1 c2"',
        },
    },
    '2h': {
        id: '2h',
        label: '2 charts (horizontal split)',
        cellCount: 2,
        category: '2',
        grid: {
            columns: '1fr',
            rows: '1fr 1fr',
            areas: '"c1" "c2"',
        },
    },

    // ── 3 charts ───────────────────────────────────────────────────────────
    '3-left': {
        id: '3-left',
        label: '3 charts (large left)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '2fr 1fr',
            rows: '1fr 1fr',
            areas: '"c1 c2" "c1 c3"',
        },
    },
    '3-right': {
        id: '3-right',
        label: '3 charts (large right)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '1fr 2fr',
            rows: '1fr 1fr',
            areas: '"c2 c1" "c3 c1"',
        },
    },
    '3-top': {
        id: '3-top',
        label: '3 charts (large top)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '1fr 1fr',
            rows: '2fr 1fr',
            areas: '"c1 c1" "c2 c3"',
        },
    },
    '3-bottom': {
        id: '3-bottom',
        label: '3 charts (large bottom)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '1fr 1fr',
            rows: '1fr 2fr',
            areas: '"c2 c3" "c1 c1"',
        },
    },
    '3-cols': {
        id: '3-cols',
        label: '3 charts (3 columns)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '1fr 1fr 1fr',
            rows: '1fr',
            areas: '"c1 c2 c3"',
        },
    },
    '3-rows': {
        id: '3-rows',
        label: '3 charts (3 rows)',
        cellCount: 3,
        category: '3',
        grid: {
            columns: '1fr',
            rows: '1fr 1fr 1fr',
            areas: '"c1" "c2" "c3"',
        },
    },

    // ── 4 charts ───────────────────────────────────────────────────────────
    '4-grid': {
        id: '4-grid',
        label: '4 charts (2×2 grid)',
        cellCount: 4,
        category: '4',
        grid: {
            columns: '1fr 1fr',
            rows: '1fr 1fr',
            areas: '"c1 c2" "c3 c4"',
        },
    },
    '4-rows': {
        id: '4-rows',
        label: '4 charts (4 rows)',
        cellCount: 4,
        category: '4',
        grid: {
            columns: '1fr',
            rows: '1fr 1fr 1fr 1fr',
            areas: '"c1" "c2" "c3" "c4"',
        },
    },
    '4-cols': {
        id: '4-cols',
        label: '4 charts (4 columns)',
        cellCount: 4,
        category: '4',
        grid: {
            columns: '1fr 1fr 1fr 1fr',
            rows: '1fr',
            areas: '"c1 c2 c3 c4"',
        },
    },
    '4-top1': {
        id: '4-top1',
        label: '4 charts (1 top, 3 bottom)',
        cellCount: 4,
        category: '4',
        grid: {
            columns: '1fr 1fr 1fr',
            rows: '2fr 1fr',
            areas: '"c1 c1 c1" "c2 c3 c4"',
        },
    },
    '4-left1': {
        id: '4-left1',
        label: '4 charts (1 left, 3 right)',
        cellCount: 4,
        category: '4',
        grid: {
            columns: '2fr 1fr',
            rows: '1fr 1fr 1fr',
            areas: '"c1 c2" "c1 c3" "c1 c4"',
        },
    },

    // ── 5 charts ───────────────────────────────────────────────────────────
    '5-left': {
        id: '5-left',
        label: '5 charts (1 left, 4 right)',
        cellCount: 5,
        category: '5+',
        grid: {
            columns: '2fr 1fr 1fr',
            rows: '1fr 1fr',
            areas: '"c1 c2 c3" "c1 c4 c5"',
        },
    },
    '5-right': {
        id: '5-right',
        label: '5 charts (4 left, 1 right)',
        cellCount: 5,
        category: '5+',
        grid: {
            columns: '1fr 1fr 2fr',
            rows: '1fr 1fr',
            areas: '"c2 c3 c1" "c4 c5 c1"',
        },
    },

    // ── 6 charts ───────────────────────────────────────────────────────────
    '6-grid': {
        id: '6-grid',
        label: '6 charts (3×2 grid)',
        cellCount: 6,
        category: '5+',
        grid: {
            columns: '1fr 1fr 1fr',
            rows: '1fr 1fr',
            areas: '"c1 c2 c3" "c4 c5 c6"',
        },
    },
    '6-rows': {
        id: '6-rows',
        label: '6 charts (6 rows)',
        cellCount: 6,
        category: '5+',
        grid: {
            columns: '1fr',
            rows: 'repeat(6, 1fr)',
            areas: '"c1" "c2" "c3" "c4" "c5" "c6"',
        },
    },
    '6-cols': {
        id: '6-cols',
        label: '6 charts (6 columns)',
        cellCount: 6,
        category: '5+',
        grid: {
            columns: 'repeat(6, 1fr)',
            rows: '1fr',
            areas: '"c1 c2 c3 c4 c5 c6"',
        },
    },

    // ── 8 charts ───────────────────────────────────────────────────────────
    '8-grid': {
        id: '8-grid',
        label: '8 charts (4×2 grid)',
        cellCount: 8,
        category: '8',
        grid: {
            columns: '1fr 1fr 1fr 1fr',
            rows: '1fr 1fr',
            areas: '"c1 c2 c3 c4" "c5 c6 c7 c8"',
        },
    },
};

/** All layout ids ordered as shown in the picker. */
export const LAYOUT_ORDER: LayoutId[] = [
    'single',
    '2v', '2h',
    '3-left', '3-right', '3-top', '3-bottom', '3-cols', '3-rows',
    '4-grid', '4-rows', '4-cols', '4-top1', '4-left1',
    '5-left', '5-right',
    '6-grid', '6-rows', '6-cols',
    '8-grid',
];

/** Category labels for the picker groups. */
export const LAYOUT_CATEGORIES: { id: LayoutTemplate['category']; label: string }[] = [
    { id: '1', label: '1 chart' },
    { id: '2', label: '2 charts' },
    { id: '3', label: '3 charts' },
    { id: '4', label: '4 charts' },
    { id: '5+', label: '5–6 charts' },
    { id: '8', label: '8 charts' },
];

export function getLayoutTemplate(id: LayoutId): LayoutTemplate {
    return LAYOUT_TEMPLATES[id] ?? LAYOUT_TEMPLATES.single;
}

/**
 * Build the cell id ('cell-1' … 'cell-N') from its 1-based index.
 * The grid area assigned to the cell is `c{index}` — mapping handled in CSS.
 */
export function cellId(index: number): string {
    return `cell-${index}`;
}

export function cellArea(index: number): string {
    return `c${index}`;
}
