/**
 * Multi-chart layout system — types
 *
 * Layout identifiers, cell/sync state shapes and saved-layout records.
 * Pure data types so they can be imported safely from store, UI and bus.
 */

import type { ChartInterval } from '@/hooks/useLiveChartData';
import type { TimeRange } from '../constants';

// ============================================================================
// Layout identifiers
// ============================================================================

/**
 * Catalogue of supported grid templates. Mirrors TradingView's layout picker:
 *   1 chart      → single
 *   2 charts     → 2v / 2h
 *   3 charts     → 3-left / 3-right / 3-top / 3-bottom / 3-cols / 3-rows
 *   4 charts     → 4-grid / 4-rows / 4-cols / 4-top1 / 4-left1
 *   5–8 charts   → 5-left / 5-right / 6-grid / 6-rows / 6-cols / 8-grid
 *
 * Keep this list in sync with `LAYOUT_TEMPLATES` in `layoutTemplates.ts`.
 */
export type LayoutId =
    | 'single'
    | '2v' | '2h'
    | '3-left' | '3-right' | '3-top' | '3-bottom' | '3-cols' | '3-rows'
    | '4-grid' | '4-rows' | '4-cols' | '4-top1' | '4-left1'
    | '5-left' | '5-right'
    | '6-grid' | '6-rows' | '6-cols'
    | '8-grid';

// ============================================================================
// Per-cell state
// ============================================================================

export interface CellState {
    /** Stable identifier within the layout (e.g. 'cell-1', 'cell-2'). */
    id: string;
    /** Symbol displayed in this cell. */
    ticker: string;
    /** Interval (timeframe) used by this cell. */
    interval: ChartInterval;
    /** Visible window range (default time range). */
    range: TimeRange;
}

// ============================================================================
// Sync flags
// ============================================================================

/**
 * Per-axis synchronisation flags. Each flag is independent: e.g. you can sync
 * crosshair without syncing symbols (handy for comparing different tickers
 * but pointing at the same timestamp).
 */
export interface SyncFlags {
    /** Same symbol everywhere. */
    symbol: boolean;
    /** Same timeframe (interval) everywhere. */
    interval: boolean;
    /** Synced crosshair (time + price ghost on remote cells). */
    crosshair: boolean;
    /** Synced visible-time range (zoom/pan). */
    time: boolean;
    /** Synced default date range (1Y, 6M, etc.). */
    dateRange: boolean;
}

// ============================================================================
// Saved layout (template)
// ============================================================================

/**
 * Named snapshot of a layout: its grid template, per-cell symbols/intervals
 * and current sync flags. Users can save N of these and switch between them.
 */
export interface SavedLayout {
    id: string;
    name: string;
    layoutId: LayoutId;
    cells: CellState[];
    sync: SyncFlags;
    createdAt: number;
    updatedAt: number;
}

// ============================================================================
// Defaults & helpers
// ============================================================================

export const DEFAULT_SYNC_FLAGS: SyncFlags = {
    symbol: false,
    interval: false,
    crosshair: true,
    time: true,
    dateRange: false,
};

export const DEFAULT_INTERVAL: ChartInterval = '1day';
export const DEFAULT_RANGE: TimeRange = '1Y';

/** Build a fresh cell with stable id. */
export function createCell(id: string, ticker: string): CellState {
    return {
        id,
        ticker,
        interval: DEFAULT_INTERVAL,
        range: DEFAULT_RANGE,
    };
}
