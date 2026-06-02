/**
 * Multi-chart layout store — Zustand persisted in localStorage.
 *
 * Each chart FloatingWindow owns its own `WindowLayoutState`, keyed by the
 * window's stable id. This mirrors TradingView's "every layout window is
 * independent" behaviour while still sharing a single named-templates
 * library across the user's account.
 *
 * Design notes:
 *   • Per-window state: layoutId, cells map, activeCellId, sync flags.
 *   • Global state: savedLayouts library (named snapshots).
 *   • Cell ids are stable (`cell-1 … cell-N`) so resizing a layout keeps
 *     per-cell tickers/intervals when slots remain.
 *   • Persistence keeps everything alive across reloads.
 *
 * The action surface is per-window (`setLayoutId(windowId, ...)` etc.) and
 * each reducer is tiny so it's easy to follow in devtools.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ChartInterval } from '@/hooks/useLiveChartData';
import type { TimeRange } from '../constants';
import {
    type CellState,
    type LayoutId,
    type SavedLayout,
    type SyncFlags,
    DEFAULT_SYNC_FLAGS,
    DEFAULT_INTERVAL,
    DEFAULT_RANGE,
    createCell,
} from './types';
import { getLayoutTemplate, cellId } from './layoutTemplates';
import type { DrawingsSyncMode } from './drawingsSyncBus';

// ============================================================================
// Per-window state
// ============================================================================

export interface WindowLayoutState {
    layoutId: LayoutId;
    cells: Record<string, CellState>;
    activeCellId: string;
    sync: SyncFlags;
}

export interface ChartLayoutState {
    /** Per-window layout state, keyed by FloatingWindow id. */
    windows: Record<string, WindowLayoutState>;
    /** Shared, account-wide named template library. */
    savedLayouts: SavedLayout[];
    /**
     * Global preference for cross-instance drawings synchronisation:
     *   • `off`        — independent drawings per chart instance.
     *   • `in_layout`  — siblings in the same window with the same ticker.
     *   • `global`     — any chart in the workspace with the same ticker.
     */
    drawingsSyncMode: DrawingsSyncMode;

    // ── Ensure / read ─────────────────────────────────────────────────────
    /**
     * Ensure a window has layout state. Idempotent: if already present, no-op.
     * If not, creates a single-cell layout seeded with `initialTicker`.
     */
    ensureWindow: (windowId: string, initialTicker: string) => void;

    // ── Layout actions (per-window) ───────────────────────────────────────
    setLayoutId: (windowId: string, layoutId: LayoutId) => void;
    setActiveCellId: (windowId: string, cellIdValue: string) => void;

    // ── Cell mutations (per-window) ───────────────────────────────────────
    setCellTicker: (windowId: string, cellIdValue: string, ticker: string) => void;
    setCellInterval: (windowId: string, cellIdValue: string, interval: ChartInterval) => void;
    setCellRange: (windowId: string, cellIdValue: string, range: TimeRange) => void;
    broadcastTicker: (windowId: string, sourceCellId: string, ticker: string) => void;
    broadcastInterval: (windowId: string, sourceCellId: string, interval: ChartInterval) => void;
    broadcastRange: (windowId: string, sourceCellId: string, range: TimeRange) => void;

    // ── Sync flags (per-window) ───────────────────────────────────────────
    setSyncFlag: (windowId: string, flag: keyof SyncFlags, value: boolean) => void;
    setSyncFlags: (windowId: string, flags: Partial<SyncFlags>) => void;

    // ── Window lifecycle ──────────────────────────────────────────────────
    resetWindow: (windowId: string) => void;
    disposeWindow: (windowId: string) => void;

    // ── Saved layouts (global library) ────────────────────────────────────
    saveLayoutAs: (windowId: string, name: string) => string | null;
    loadSavedLayout: (windowId: string, savedId: string) => void;
    renameSavedLayout: (savedId: string, name: string) => void;
    deleteSavedLayout: (savedId: string) => void;

    // ── Drawings sync mode (global preference) ────────────────────────────
    setDrawingsSyncMode: (mode: DrawingsSyncMode) => void;
}

// ============================================================================
// Defaults & helpers
// ============================================================================

function buildInitialCells(layoutId: LayoutId, ticker: string): Record<string, CellState> {
    const tpl = getLayoutTemplate(layoutId);
    const cells: Record<string, CellState> = {};
    for (let i = 1; i <= tpl.cellCount; i++) {
        const id = cellId(i);
        cells[id] = createCell(id, ticker);
    }
    return cells;
}

function buildInitialWindow(initialTicker: string): WindowLayoutState {
    return {
        layoutId: 'single',
        cells: buildInitialCells('single', initialTicker),
        activeCellId: cellId(1),
        sync: { ...DEFAULT_SYNC_FLAGS },
    };
}

/**
 * Resize the cell map for a new layout. Existing cells (by id) are preserved;
 * new ones are seeded from the last known cell (or fall back to a sensible
 * default); extras when shrinking are dropped from the tail.
 */
function resizeCells(
    cells: Record<string, CellState>,
    nextLayoutId: LayoutId,
): Record<string, CellState> {
    const tpl = getLayoutTemplate(nextLayoutId);
    const existing = Object.values(cells);
    const lastKnown = existing[existing.length - 1];
    const next: Record<string, CellState> = {};
    for (let i = 1; i <= tpl.cellCount; i++) {
        const id = cellId(i);
        if (cells[id]) {
            next[id] = cells[id];
        } else {
            next[id] = {
                id,
                ticker: lastKnown?.ticker ?? 'AAPL',
                interval: lastKnown?.interval ?? DEFAULT_INTERVAL,
                range: lastKnown?.range ?? DEFAULT_RANGE,
            };
        }
    }
    return next;
}

function randomId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Updates the per-window state in an immutable way. Returns the *new* full
 * `windows` map. Used by every per-window action.
 */
function updateWindow(
    state: ChartLayoutState,
    windowId: string,
    updater: (prev: WindowLayoutState) => WindowLayoutState,
): Record<string, WindowLayoutState> {
    const prev = state.windows[windowId];
    if (!prev) return state.windows;
    const next = updater(prev);
    if (next === prev) return state.windows;
    return { ...state.windows, [windowId]: next };
}

// ============================================================================
// Store
// ============================================================================

const STORAGE_KEY = 'tradeul-chart-layout-v2';

export const useChartLayoutStore = create<ChartLayoutState>()(
    persist(
        (set) => ({
            windows: {},
            savedLayouts: [],
            drawingsSyncMode: 'in_layout',

            // ── Ensure ────────────────────────────────────────────────────
            ensureWindow: (windowId, initialTicker) =>
                set((state) => {
                    if (state.windows[windowId]) return state;
                    return {
                        windows: {
                            ...state.windows,
                            [windowId]: buildInitialWindow(initialTicker),
                        },
                    };
                }),

            // ── Layout ────────────────────────────────────────────────────
            setLayoutId: (windowId, layoutId) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const cells = resizeCells(prev.cells, layoutId);
                        const activeCellId = cells[prev.activeCellId]
                            ? prev.activeCellId
                            : cellId(1);
                        return { ...prev, layoutId, cells, activeCellId };
                    }),
                })),

            setActiveCellId: (windowId, cellIdValue) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) =>
                        prev.cells[cellIdValue]
                            ? { ...prev, activeCellId: cellIdValue }
                            : prev,
                    ),
                })),

            // ── Cell mutations ────────────────────────────────────────────
            setCellTicker: (windowId, cellIdValue, ticker) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const cell = prev.cells[cellIdValue];
                        if (!cell || cell.ticker === ticker) return prev;
                        return {
                            ...prev,
                            cells: { ...prev.cells, [cellIdValue]: { ...cell, ticker } },
                        };
                    }),
                })),

            setCellInterval: (windowId, cellIdValue, interval) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const cell = prev.cells[cellIdValue];
                        if (!cell || cell.interval === interval) return prev;
                        return {
                            ...prev,
                            cells: { ...prev.cells, [cellIdValue]: { ...cell, interval } },
                        };
                    }),
                })),

            setCellRange: (windowId, cellIdValue, range) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const cell = prev.cells[cellIdValue];
                        if (!cell || cell.range === range) return prev;
                        return {
                            ...prev,
                            cells: { ...prev.cells, [cellIdValue]: { ...cell, range } },
                        };
                    }),
                })),

            broadcastTicker: (windowId, sourceCellId, ticker) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const next: Record<string, CellState> = {};
                        let changed = false;
                        for (const id of Object.keys(prev.cells)) {
                            const cell = prev.cells[id];
                            if (id === sourceCellId || cell.ticker === ticker) {
                                next[id] = cell;
                            } else {
                                next[id] = { ...cell, ticker };
                                changed = true;
                            }
                        }
                        // Always update the source so its own ticker matches.
                        if (
                            prev.cells[sourceCellId] &&
                            prev.cells[sourceCellId].ticker !== ticker
                        ) {
                            next[sourceCellId] = { ...prev.cells[sourceCellId], ticker };
                            changed = true;
                        }
                        return changed ? { ...prev, cells: next } : prev;
                    }),
                })),

            broadcastInterval: (windowId, sourceCellId, interval) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const next: Record<string, CellState> = {};
                        let changed = false;
                        for (const id of Object.keys(prev.cells)) {
                            const cell = prev.cells[id];
                            if (id === sourceCellId || cell.interval === interval) {
                                next[id] = cell;
                            } else {
                                next[id] = { ...cell, interval };
                                changed = true;
                            }
                        }
                        if (
                            prev.cells[sourceCellId] &&
                            prev.cells[sourceCellId].interval !== interval
                        ) {
                            next[sourceCellId] = {
                                ...prev.cells[sourceCellId],
                                interval,
                            };
                            changed = true;
                        }
                        return changed ? { ...prev, cells: next } : prev;
                    }),
                })),

            broadcastRange: (windowId, sourceCellId, range) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => {
                        const next: Record<string, CellState> = {};
                        let changed = false;
                        for (const id of Object.keys(prev.cells)) {
                            const cell = prev.cells[id];
                            if (id === sourceCellId || cell.range === range) {
                                next[id] = cell;
                            } else {
                                next[id] = { ...cell, range };
                                changed = true;
                            }
                        }
                        if (
                            prev.cells[sourceCellId] &&
                            prev.cells[sourceCellId].range !== range
                        ) {
                            next[sourceCellId] = { ...prev.cells[sourceCellId], range };
                            changed = true;
                        }
                        return changed ? { ...prev, cells: next } : prev;
                    }),
                })),

            // ── Sync flags ────────────────────────────────────────────────
            setSyncFlag: (windowId, flag, value) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => ({
                        ...prev,
                        sync: { ...prev.sync, [flag]: value },
                    })),
                })),

            setSyncFlags: (windowId, flags) =>
                set((state) => ({
                    windows: updateWindow(state, windowId, (prev) => ({
                        ...prev,
                        sync: { ...prev.sync, ...flags },
                    })),
                })),

            // ── Window lifecycle ──────────────────────────────────────────
            resetWindow: (windowId) =>
                set((state) => {
                    const prev = state.windows[windowId];
                    if (!prev) return state;
                    const seedTicker =
                        Object.values(prev.cells)[0]?.ticker ?? 'AAPL';
                    return {
                        windows: {
                            ...state.windows,
                            [windowId]: buildInitialWindow(seedTicker),
                        },
                    };
                }),

            disposeWindow: (windowId) =>
                set((state) => {
                    if (!state.windows[windowId]) return state;
                    const next = { ...state.windows };
                    delete next[windowId];
                    return { windows: next };
                }),

            // ── Saved layouts (global) ────────────────────────────────────
            saveLayoutAs: (windowId, name) => {
                const id = randomId();
                const now = Date.now();
                let didSave = false;
                set((state) => {
                    const w = state.windows[windowId];
                    if (!w) return state;
                    didSave = true;
                    const snapshot: SavedLayout = {
                        id,
                        name: name.trim() || 'Untitled layout',
                        layoutId: w.layoutId,
                        cells: Object.values(w.cells).map((c) => ({ ...c })),
                        sync: { ...w.sync },
                        createdAt: now,
                        updatedAt: now,
                    };
                    return { savedLayouts: [snapshot, ...state.savedLayouts] };
                });
                return didSave ? id : null;
            },

            loadSavedLayout: (windowId, savedId) =>
                set((state) => {
                    const saved = state.savedLayouts.find((s) => s.id === savedId);
                    if (!saved) return state;
                    const cells: Record<string, CellState> = {};
                    for (const c of saved.cells) cells[c.id] = { ...c };
                    return {
                        windows: {
                            ...state.windows,
                            [windowId]: {
                                layoutId: saved.layoutId,
                                cells,
                                activeCellId: saved.cells[0]?.id ?? cellId(1),
                                sync: { ...saved.sync },
                            },
                        },
                    };
                }),

            renameSavedLayout: (savedId, name) =>
                set((state) => ({
                    savedLayouts: state.savedLayouts.map((s) =>
                        s.id === savedId
                            ? { ...s, name: name.trim() || s.name, updatedAt: Date.now() }
                            : s,
                    ),
                })),

            deleteSavedLayout: (savedId) =>
                set((state) => ({
                    savedLayouts: state.savedLayouts.filter((s) => s.id !== savedId),
                })),

            // ── Drawings sync mode (global) ───────────────────────────────
            setDrawingsSyncMode: (mode) =>
                set(() => ({ drawingsSyncMode: mode })),
        }),
        {
            name: STORAGE_KEY,
            storage: createJSONStorage(() => localStorage),
            version: 3,
            partialize: (state) => ({
                windows: state.windows,
                savedLayouts: state.savedLayouts,
                drawingsSyncMode: state.drawingsSyncMode,
            }),
        },
    ),
);

// ============================================================================
// Per-window selectors (stable identities for components)
// ============================================================================

export const selectWindow = (windowId: string | null) =>
    (s: ChartLayoutState): WindowLayoutState | null =>
        windowId ? s.windows[windowId] ?? null : null;

export const selectSavedLayouts = (s: ChartLayoutState) => s.savedLayouts;

export const selectDrawingsSyncMode = (s: ChartLayoutState) => s.drawingsSyncMode;
