/**
 * EventMarkerPrimitive
 *
 * Renders TradingView-style event markers (earnings, news) anchored to the
 * **bottom of the chart pane**, sitting just above the time-axis separator so
 * they overlap the top of the volume histogram — exactly like TradingView's
 * placement. A dashed vertical guide line is drawn through the chart pane for
 * the next upcoming event of each kind.
 *
 * Visual language:
 *   • Donut badge: colored 2.5px ring around a hollow center filled with the
 *     surface color, with a bold "E"/"N" letter in the ring color.
 *   • Diameter ≈ 16px.
 *   • Anchored to the **actual candle** that falls on the event date — this
 *     works across every timeframe (1min, 5min, 1h, daily, weekly).
 *   • Future events without a candle anchor are projected onto the time
 *     scale by converting the calendar date to a unix timestamp.
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

export type EventKind = 'earnings' | 'news';

export interface ChartEvent {
    /** Calendar date "YYYY-MM-DD" in market timezone (America/New_York). */
    date: string;
    /** Visual variant ('earnings' = E, 'news' = N). */
    kind: EventKind;
    /** Tooltip/secondary metadata: "BMO" | "AMC" for earnings, headline for news. */
    label?: string;
    /** Optional payload for click/hover handlers (article, earnings record, etc.). */
    payload?: unknown;
}

interface RenderedPoint {
    x: number;
    event: ChartEvent;
    /** True if the underlying date is in the future (no candle yet). */
    isFuture: boolean;
}

interface PaletteEntry {
    fill: string;
    text: string;
}

/** Visual palette per event kind. */
interface MarkerPalette {
    earnings: PaletteEntry;
    news: PaletteEntry;
    surface: string;
    /** Color of the dashed guide line for upcoming events. */
    upcomingGuide: string;
}

/** Diameter ~ 16 px, ring stroke ~ 2.4 px. */
const MARKER_RADIUS = 8;
const MARKER_DIAMETER = MARKER_RADIUS * 2;
const RING_WIDTH = 2.4;
/** Distance from the bottom of the chart pane to the marker center. */
const BOTTOM_INSET = MARKER_RADIUS + 4;

// ─── Marker renderer (chart pane, bottom-anchored) ──────────────────────────

class EventMarkerRenderer implements IPrimitivePaneRenderer {
    private _points: RenderedPoint[];
    private _palette: MarkerPalette;
    private _hitTargets: { x: number; y: number; r: number; event: ChartEvent }[];

    constructor(
        points: RenderedPoint[],
        palette: MarkerPalette,
        hitTargets: { x: number; y: number; r: number; event: ChartEvent }[],
    ) {
        this._points = points;
        this._palette = palette;
        this._hitTargets = hitTargets;
    }

    draw(target: CanvasRenderingTarget2D): void {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            const w = mediaSize.width;
            const centerY = Math.max(MARKER_RADIUS + 1, mediaSize.height - BOTTOM_INSET);

            this._hitTargets.length = 0;

            for (const point of this._points) {
                const x = point.x;
                if (x < -MARKER_DIAMETER || x > w + MARKER_DIAMETER) continue;

                const entry = this._palette[point.event.kind];
                const letter = point.event.kind === 'earnings' ? 'E' : 'N';

                // 1. Inner disk in surface color so volume bars behind don't
                //    show through the badge — clean donut look.
                ctx.beginPath();
                ctx.arc(x, centerY, MARKER_RADIUS, 0, Math.PI * 2);
                ctx.fillStyle = this._palette.surface;
                ctx.fill();

                // 2. Colored ring.
                ctx.lineWidth = RING_WIDTH;
                ctx.strokeStyle = entry.fill;
                ctx.stroke();

                // 3. Letter centered inside the ring.
                ctx.font = '700 9px ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
                ctx.fillStyle = entry.fill;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(letter, x, centerY + 0.5);

                this._hitTargets.push({
                    x,
                    y: centerY,
                    r: MARKER_RADIUS + 2,
                    event: point.event,
                });
            }
        });
    }
}

class EventMarkerPaneView implements IPrimitivePaneView {
    private _points: RenderedPoint[] = [];
    private _palette: MarkerPalette;
    private _hitTargets: { x: number; y: number; r: number; event: ChartEvent }[];

    constructor(
        initialPalette: MarkerPalette,
        hitTargets: { x: number; y: number; r: number; event: ChartEvent }[],
    ) {
        this._palette = initialPalette;
        this._hitTargets = hitTargets;
    }

    update(points: RenderedPoint[], palette: MarkerPalette): void {
        this._points = points;
        this._palette = palette;
    }

    zOrder(): 'top' {
        // Render above candles + volume so badges are always visible.
        return 'top';
    }

    renderer(): IPrimitivePaneRenderer | null {
        if (this._points.length === 0) {
            this._hitTargets.length = 0;
            return null;
        }
        return new EventMarkerRenderer(this._points, this._palette, this._hitTargets);
    }
}

// ─── Guide line renderer (vertical dashed line for upcoming events) ─────────

interface GuideLine {
    x: number;
    color: string;
}

class GuideLineRenderer implements IPrimitivePaneRenderer {
    private _lines: GuideLine[];

    constructor(lines: GuideLine[]) {
        this._lines = lines;
    }

    draw(target: CanvasRenderingTarget2D): void {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            if (this._lines.length === 0) return;
            ctx.save();
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            for (const line of this._lines) {
                if (line.x < -2 || line.x > mediaSize.width + 2) continue;
                ctx.strokeStyle = line.color;
                ctx.beginPath();
                ctx.moveTo(line.x, 0);
                // Stop just above the marker so the line "enters" the badge.
                ctx.lineTo(line.x, Math.max(0, mediaSize.height - BOTTOM_INSET - MARKER_RADIUS));
                ctx.stroke();
            }
            ctx.restore();
        });
    }
}

class GuideLinePaneView implements IPrimitivePaneView {
    private _lines: GuideLine[] = [];

    update(lines: GuideLine[]): void {
        this._lines = lines;
    }

    zOrder(): 'bottom' {
        // Behind candles so it doesn't obstruct price action.
        return 'bottom';
    }

    renderer(): IPrimitivePaneRenderer | null {
        if (this._lines.length === 0) return null;
        return new GuideLineRenderer(this._lines);
    }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Returns "YYYY-MM-DD" in US Eastern (market tz) for a unix timestamp (seconds). */
function tsToDateStr(ts: number): string {
    return new Date(ts * 1000).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

/** Returns today's "YYYY-MM-DD" in market tz, used to split past vs upcoming. */
function todayStr(): string {
    return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

/** Convert "YYYY-MM-DD" assumed at NY noon → unix seconds. Used to map future
 *  events that don't yet have a candle anchor. */
function dateStrToTs(dateStr: string): number | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
    if (!m) return null;
    const y = +m[1];
    const mo = +m[2] - 1;
    const d = +m[3];
    return Math.floor(Date.UTC(y, mo, d, 16, 0, 0) / 1000); // 16:00 UTC ≈ market noon ET
}

function readPalette(): MarkerPalette {
    const root = typeof document !== 'undefined' ? document.documentElement : null;
    const getVar = (name: string, fallback: string) => {
        if (!root) return fallback;
        const v = getComputedStyle(root).getPropertyValue(name).trim();
        return v || fallback;
    };
    return {
        earnings: { fill: getVar('--color-chart-marker-earnings', '#2563eb'), text: '#ffffff' },
        news: { fill: getVar('--color-chart-marker-news', '#f59e0b'), text: '#ffffff' },
        surface: getVar('--color-bg', '#ffffff'),
        upcomingGuide: getVar('--color-chart-marker-upcoming', '#d946ef'),
    };
}

// ─── Primitive ──────────────────────────────────────────────────────────────

export class EventMarkerPrimitive implements ISeriesPrimitive<Time> {
    private _chart: IChartApiBase<Time> | null = null;
    private _series: ISeriesApi<SeriesType, Time> | null = null;
    private _requestUpdate: (() => void) | null = null;

    private _hitTargets: { x: number; y: number; r: number; event: ChartEvent }[] = [];
    private _markerPaneView: EventMarkerPaneView;
    private _guidePaneView: GuideLinePaneView;
    private _events: ChartEvent[] = [];
    private _dataTimes: number[] = [];
    private _visible = true;
    private _palette: MarkerPalette;

    /** Pre-built index: "YYYY-MM-DD" -> first candle index on that date. */
    private _dateIndex = new Map<string, number>();

    constructor() {
        this._palette = readPalette();
        this._markerPaneView = new EventMarkerPaneView(this._palette, this._hitTargets);
        this._guidePaneView = new GuideLinePaneView();
    }

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

    refreshPalette(): void {
        this._palette = readPalette();
        this._requestUpdate?.();
    }

    setEvents(events: ChartEvent[]): void {
        this._events = events;
        this._requestUpdate?.();
    }

    setDataTimes(times: number[]): void {
        this._dataTimes = times;
        this._rebuildDateIndex();
        this._requestUpdate?.();
    }

    setVisible(visible: boolean): void {
        this._visible = visible;
        this._requestUpdate?.();
    }

    /**
     * Hit-test in chart-pane local coordinates. Returns the closest event marker
     * within radius, or null. Named `hitTestEvent` to avoid colliding with the
     * core `ISeriesPrimitiveBase.hitTest`, which has a different return shape.
     */
    hitTestEvent(x: number, y: number): ChartEvent | null {
        let nearest: { dist: number; event: ChartEvent } | null = null;
        for (const t of this._hitTargets) {
            const dx = x - t.x;
            const dy = y - t.y;
            const d2 = dx * dx + dy * dy;
            const r2 = t.r * t.r;
            if (d2 <= r2) {
                if (!nearest || d2 < nearest.dist) {
                    nearest = { dist: d2, event: t.event };
                }
            }
        }
        return nearest?.event ?? null;
    }

    private _rebuildDateIndex(): void {
        this._dateIndex.clear();
        for (let i = 0; i < this._dataTimes.length; i++) {
            const dateStr = tsToDateStr(this._dataTimes[i]);
            if (!this._dateIndex.has(dateStr)) {
                this._dateIndex.set(dateStr, i);
            }
        }
    }

    updateAllViews(): void {
        if (!this._chart || !this._visible || this._events.length === 0 || this._dataTimes.length === 0) {
            this._markerPaneView.update([], this._palette);
            this._guidePaneView.update([]);
            return;
        }

        const ts = this._chart.timeScale();
        const today = todayStr();
        const points: RenderedPoint[] = [];
        const nextUpcoming: Partial<Record<EventKind, { x: number; date: string }>> = {};

        for (const event of this._events) {
            if (!event.date) continue;
            const isFuture = event.date > today;

            let x: number | null = null;
            const candleIdx = this._dateIndex.get(event.date);
            if (candleIdx !== undefined) {
                const candleTime = this._dataTimes[candleIdx];
                x = ts.timeToCoordinate(candleTime as unknown as Time);
            } else if (isFuture) {
                const futureTs = dateStrToTs(event.date);
                if (futureTs !== null) {
                    x = ts.timeToCoordinate(futureTs as unknown as Time);
                }
            }
            if (x === null || !Number.isFinite(x)) continue;

            points.push({ x: x as number, event, isFuture });

            if (isFuture) {
                const existing = nextUpcoming[event.kind];
                if (!existing || event.date < existing.date) {
                    nextUpcoming[event.kind] = { x: x as number, date: event.date };
                }
            }
        }

        this._markerPaneView.update(points, this._palette);

        // Single guide color for whichever upcoming event is nearest, so the
        // chart isn't crowded with multiple vertical lines.
        const guides: GuideLine[] = [];
        for (const kind of Object.keys(nextUpcoming) as EventKind[]) {
            const entry = nextUpcoming[kind];
            if (entry) {
                guides.push({ x: entry.x, color: this._palette.upcomingGuide });
            }
        }
        this._guidePaneView.update(guides);
    }

    paneViews(): readonly IPrimitivePaneView[] {
        this.updateAllViews();
        // Order matters only for the same z-order; the markers explicitly
        // return 'top' and the guide line 'bottom', so the lightweight-charts
        // core will composite them correctly across pane elements.
        return [this._guidePaneView, this._markerPaneView];
    }
}
