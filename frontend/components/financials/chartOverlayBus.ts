// ============================================================================
// Chart overlay bus
// ----------------------------------------------------------------------------
// Lets a Financials dashboard push a metric onto one of *its own* already-open
// chart windows (the "lock overlay" mode), instead of opening a new chart.
//
// Scoping: every FinancialsContent instance owns a unique `dashboardId`, so two
// FA windows never cross-talk. Each open FinancialChartPro registers a handler
// under that id; the most recently mounted chart is the active overlay target.
// ============================================================================

export interface OverlaySeriesPayload {
    key: string;
    label: string;
    dataType?: string;
    /** See ChartSeriesField.percentScale — defaults to 'fraction'. */
    percentScale?: 'fraction' | 'points';
    balance?: 'debit' | 'credit' | null;
    periods: string[];          // source periods (newest-first)
    values: (number | null)[];  // aligned to `periods`
}

// Returns true if the series was accepted (false e.g. when the chart is full).
type OverlayHandler = (payload: OverlaySeriesPayload) => boolean;

const registry = new Map<string, OverlayHandler[]>();

export function registerOverlayTarget(dashboardId: string, handler: OverlayHandler): () => void {
    const arr = registry.get(dashboardId) || [];
    arr.push(handler);
    registry.set(dashboardId, arr);
    return () => {
        const cur = registry.get(dashboardId);
        if (!cur) return;
        const idx = cur.indexOf(handler);
        if (idx >= 0) cur.splice(idx, 1);
        if (cur.length === 0) registry.delete(dashboardId);
    };
}

export function hasOverlayTarget(dashboardId: string): boolean {
    const arr = registry.get(dashboardId);
    return !!arr && arr.length > 0;
}

// Delivers the payload to the most recently mounted chart for this dashboard.
// Returns true if a chart accepted it, false if there is no target or it was
// rejected (e.g. the chart already holds the max number of series).
export function pushOverlaySeries(dashboardId: string, payload: OverlaySeriesPayload): boolean {
    const arr = registry.get(dashboardId);
    if (!arr || arr.length === 0) return false;
    const handler = arr[arr.length - 1];
    try {
        return handler(payload);
    } catch {
        return false;
    }
}
