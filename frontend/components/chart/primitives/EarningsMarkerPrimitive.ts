/**
 * EarningsMarkerPrimitive
 *
 * Draws small "E" circles directly on the time axis (x-axis) strip,
 * similar to TradingView's earnings markers.
 *
 * Uses timeAxisPaneViews() to render on the time axis canvas area,
 * not on the chart pane.
 *
 * KEY APPROACH: Instead of fabricating timestamps, we find the actual
 * candle in the chart data that falls on the earnings date, and use
 * its exact timestamp for coordinate mapping. This works across ALL
 * timeframes (1min, 5min, 1h, 1day, 1week).
 */
import type {
    ISeriesPrimitive,
    SeriesAttachedParameter,
    IPrimitivePaneView,
    IPrimitivePaneRenderer,
    Time,
    IChartApiBase,
    ISeriesApi,
    SeriesType,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface EarningsDate {
    date: string;      // "2026-01-29"
    time_slot: string;  // "BMO", "AMC", etc.
}

interface EarningsMarkerPoint {
    x: number;
    earning: EarningsDate;
}

// ─── Renderer ───────────────────────────────────────────────────────────────

class EarningsTimeAxisRenderer implements IPrimitivePaneRenderer {
    private _points: EarningsMarkerPoint[];
    private _color: string;

    constructor(points: EarningsMarkerPoint[], color: string) {
        this._points = points;
        this._color = color;
    }

    draw(target: CanvasRenderingTarget2D): void {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            const w = mediaSize.width;
            const radius = 6;
            const centerY = 2 + radius;

            for (const point of this._points) {
                const x = point.x;
                if (x < -radius || x > w + radius) continue;

                // Filled circle
                ctx.beginPath();
                ctx.arc(x, centerY, radius, 0, Math.PI * 2);
                ctx.fillStyle = this._color;
                ctx.fill();

                // Border
                ctx.strokeStyle = 'rgba(255,255,255,0.8)';
                ctx.lineWidth = 1;
                ctx.stroke();

                // "E" text
                ctx.font = 'bold 8px -apple-system, BlinkMacSystemFont, sans-serif';
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('E', x, centerY);
            }
        });
    }
}

// ─── PaneView ───────────────────────────────────────────────────────────────

class EarningsTimeAxisPaneView implements IPrimitivePaneView {
    private _points: EarningsMarkerPoint[] = [];
    private _color = '#5b9bd5';

    update(points: EarningsMarkerPoint[], color: string): void {
        this._points = points;
        this._color = color;
    }

    zOrder(): 'top' {
        return 'top';
    }

    renderer(): IPrimitivePaneRenderer | null {
        if (this._points.length === 0) return null;
        return new EarningsTimeAxisRenderer(this._points, this._color);
    }
}

// ─── Helper: get calendar date from unix timestamp ──────────────────────────

/** Returns "YYYY-MM-DD" in US Eastern (market tz) for a unix timestamp (seconds). */
function tsToDateStr(ts: number): string {
    // Use America/New_York so overnight UTC candles map to the correct trading date.
    // en-CA locale gives YYYY-MM-DD format directly.
    return new Date(ts * 1000).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

// ─── Primitive ──────────────────────────────────────────────────────────────

export class EarningsMarkerPrimitive implements ISeriesPrimitive<Time> {
    private _chart: IChartApiBase<Time> | null = null;
    private _series: ISeriesApi<SeriesType, Time> | null = null;
    private _requestUpdate: (() => void) | null = null;

    private _timeAxisPaneView = new EarningsTimeAxisPaneView();
    private _earningsDates: EarningsDate[] = [];
    private _dataTimes: number[] = [];
    private _color = '#5b9bd5';
    private _visible = true;
    private _interval = '1day';

    // Pre-built index: "YYYY-MM-DD" -> index of first candle on that date
    private _dateIndex = new Map<string, number>();

    attached(param: SeriesAttachedParameter<Time>): void {
        this._chart = param.chart;
        this._series = param.series;
        this._requestUpdate = param.requestUpdate;
    }

    detached(): void {
        this._chart = null;
        this._series = null;
        this._requestUpdate = null;
    }

    setEarnings(dates: EarningsDate[]): void {
        this._earningsDates = dates;
        this._requestUpdate?.();
    }

    setDataTimes(times: number[]): void {
        this._dataTimes = times;
        this._rebuildDateIndex();
        this._requestUpdate?.();
    }

    setInterval(interval: string): void {
        this._interval = interval;
        this._requestUpdate?.();
    }

    setVisible(visible: boolean): void {
        this._visible = visible;
        this._requestUpdate?.();
    }

    setColor(color: string): void {
        this._color = color;
        this._requestUpdate?.();
    }

    /**
     * Build an index from calendar date -> first candle index on that date.
     * This is O(n) but only runs when data changes.
     */
    private _rebuildDateIndex(): void {
        this._dateIndex.clear();
        for (let i = 0; i < this._dataTimes.length; i++) {
            const dateStr = tsToDateStr(this._dataTimes[i]);
            // Store first candle of each date (for BMO positioning)
            if (!this._dateIndex.has(dateStr)) {
                this._dateIndex.set(dateStr, i);
            }
        }
    }

    updateAllViews(): void {
        if (!this._chart || !this._visible || this._earningsDates.length === 0 || this._dataTimes.length === 0) {
            this._timeAxisPaneView.update([], this._color);
            return;
        }

        const ts = this._chart.timeScale();
        const points: EarningsMarkerPoint[] = [];

        for (const earning of this._earningsDates) {
            if (!earning.date) continue;

            // Find the first candle on this earnings date
            const idx = this._dateIndex.get(earning.date);
            if (idx === undefined) continue; // date not in chart data → skip

            // Use the exact candle timestamp → guaranteed coordinate match
            const candleTime = this._dataTimes[idx];
            const x = ts.timeToCoordinate(candleTime as unknown as Time);
            if (x !== null) {
                points.push({ x: x as number, earning });
            }
        }

        this._timeAxisPaneView.update(points, this._color);
    }

    timeAxisPaneViews(): readonly IPrimitivePaneView[] {
        this.updateAllViews();
        return [this._timeAxisPaneView];
    }
}
