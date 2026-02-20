/**
 * TentativePrimitive — Live preview while placing a drawing.
 *
 * Uses screen coordinates for the mouse endpoint so the preview works
 * everywhere on the canvas, including beyond the last data bar.
 * Uses timeToPixelX for point1 so previews work across timeframe changes.
 *
 * Supports "anchor only" mode: when screenX < 0, only renders the anchor
 * dot at point1 (used immediately after first click, before mouse moves).
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
import type { DrawingType, DrawingPoint } from './types';
import { FIB_LEVELS } from './types';
import { timeToPixelX } from './coordinateUtils';

export interface TentativeState {
  type: DrawingType;
  point1: DrawingPoint;
  screenX: number;   // -1 = anchor-only mode (no point2 yet)
  screenY: number;
  mousePrice: number;
  color: string;
}

// ─── Renderer ────────────────────────────────────────────────────────────────

class TentativeRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _type: DrawingType,
    private _x1: number,
    private _y1: number,
    private _x2: number,
    private _y2: number,
    private _color: string,
    private _anchorOnly: boolean,
    private _fibLevels?: { y: number; level: number }[],
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      // ── Shape/line preview (skip in anchor-only mode) ──────────────
      if (!this._anchorOnly) {
        ctx.globalAlpha = 0.6;
        ctx.strokeStyle = this._color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);

        switch (this._type) {
          case 'trendline': {
            ctx.beginPath();
            ctx.moveTo(this._x1, this._y1);
            ctx.lineTo(this._x2, this._y2);
            ctx.stroke();
            break;
          }

          case 'horizontal_line': {
            ctx.beginPath();
            ctx.moveTo(0, this._y1);
            ctx.lineTo(mediaSize.width, this._y1);
            ctx.stroke();
            break;
          }

          case 'fibonacci': {
            if (this._fibLevels) {
              const left = Math.min(this._x1, this._x2);
              const right = Math.max(this._x1, this._x2);
              for (const { y } of this._fibLevels) {
                ctx.beginPath();
                ctx.moveTo(left, y);
                ctx.lineTo(right, y);
                ctx.stroke();
              }
            }
            break;
          }

          case 'rectangle': {
            const left = Math.min(this._x1, this._x2);
            const top = Math.min(this._y1, this._y2);
            const w = Math.abs(this._x2 - this._x1);
            const h = Math.abs(this._y2 - this._y1);
            ctx.fillStyle = this._color;
            ctx.globalAlpha = 0.05;
            ctx.fillRect(left, top, w, h);
            ctx.globalAlpha = 0.6;
            ctx.strokeRect(left, top, w, h);
            break;
          }
        }
      }

      // ── Anchor dot at point1 (always drawn) ───────────────────────
      ctx.globalAlpha = 0.8;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(this._x1, this._y1, 4, 0, Math.PI * 2);
      ctx.fillStyle = this._color;
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    });
  }
}

// ─── PaneView ────────────────────────────────────────────────────────────────

class TentativePaneView implements IPrimitivePaneView {
  private _renderer: TentativeRenderer | null = null;

  setRenderer(renderer: TentativeRenderer | null): void {
    this._renderer = renderer;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    return this._renderer;
  }
}

// ─── Primitive ───────────────────────────────────────────────────────────────

export class TentativePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new TentativePaneView();
  private _state: TentativeState | null = null;
  private _dataTimes: number[] = [];

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

  setDataTimes(dataTimes: number[]): void {
    this._dataTimes = dataTimes;
  }

  setState(state: TentativeState | null): void {
    this._state = state;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._state || !this._chart || !this._series) {
      this._paneView.setRenderer(null);
      return;
    }

    const ts = this._chart.timeScale();
    const x1 = timeToPixelX(this._state.point1.time, this._dataTimes, ts);
    const y1 = this._series.priceToCoordinate(this._state.point1.price);

    if (x1 === null || y1 === null) {
      this._paneView.setRenderer(null);
      return;
    }

    // Anchor-only mode: screenX < 0 means no point2 yet
    const anchorOnly = this._state.screenX < 0;
    const x2 = anchorOnly ? (x1 as number) : this._state.screenX;
    const y2 = anchorOnly ? (y1 as number) : this._state.screenY;

    let fibLevels: { y: number; level: number }[] | undefined;
    if (!anchorOnly && this._state.type === 'fibonacci') {
      const p1 = this._state.point1.price;
      const p2 = this._state.mousePrice;
      const diff = p2 - p1;
      fibLevels = FIB_LEVELS.map(level => {
        const price = p1 + diff * level;
        const y = this._series!.priceToCoordinate(price);
        return { y: (y as number) ?? 0, level };
      }).filter(l => l.y !== 0);
    }

    this._paneView.setRenderer(new TentativeRenderer(
      this._state.type,
      x1 as number, y1 as number,
      x2, y2,
      this._state.color,
      anchorOnly,
      fibLevels,
    ));
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this._paneView];
  }
}
