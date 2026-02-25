/**
 * TentativePrimitive — Live preview while placing a drawing.
 *
 * Supports all drawing types including 3-click tools.
 * Uses screen coordinates for mouse endpoint.
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
  point2?: DrawingPoint;  // For 3-click tools (set after 2nd click)
  screenX: number;   // -1 = anchor-only mode (no endpoint yet)
  screenY: number;
  mousePrice: number;
  color: string;
}

class TentativeRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _type: DrawingType,
    private _x1: number, private _y1: number,
    private _x2: number, private _y2: number,
    private _color: string,
    private _anchorOnly: boolean,
    private _fibLevels?: { y: number; level: number }[],
    private _x2anchor?: number, private _y2anchor?: number, // for 3-click: 2nd anchor
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
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

          case 'ray': {
            // Draw from p1 through p2 and extend
            ctx.beginPath();
            ctx.moveTo(this._x1, this._y1);
            const dx = this._x2 - this._x1, dy = this._y2 - this._y1;
            const len = Math.hypot(dx, dy);
            if (len > 0) {
              const extX = this._x1 + (dx / len) * 5000;
              const extY = this._y1 + (dy / len) * 5000;
              ctx.lineTo(extX, extY);
            } else {
              ctx.lineTo(this._x2, this._y2);
            }
            ctx.stroke();
            break;
          }

          case 'extended_line': {
            const dx = this._x2 - this._x1, dy = this._y2 - this._y1;
            ctx.beginPath();
            ctx.moveTo(this._x1 - dx * 5000, this._y1 - dy * 5000);
            ctx.lineTo(this._x1 + dx * 5000, this._y1 + dy * 5000);
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

          case 'vertical_line': {
            ctx.beginPath();
            ctx.moveTo(this._x1, 0);
            ctx.lineTo(this._x1, mediaSize.height);
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

          case 'circle': {
            const rx = Math.abs(this._x2 - this._x1);
            const ry = Math.abs(this._y2 - this._y1);
            if (rx > 1 || ry > 1) {
              ctx.beginPath();
              ctx.ellipse(this._x1, this._y1, rx, ry, 0, 0, Math.PI * 2);
              ctx.fillStyle = this._color;
              ctx.globalAlpha = 0.05;
              ctx.fill();
              ctx.globalAlpha = 0.6;
              ctx.stroke();
            }
            break;
          }

          case 'parallel_channel': {
            if (this._x2anchor !== undefined && this._y2anchor !== undefined) {
              // 3rd click preview: second line passes through cursor
              const dxLine = this._x2anchor! - this._x1;
              const t = dxLine !== 0 ? (this._x2 - this._x1) / dxLine : 0;
              const yOnLine = this._y1 + (this._y2anchor! - this._y1) * t;
              const offsetY = this._y2 - yOnLine;
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1);
              ctx.lineTo(this._x2anchor!, this._y2anchor!);
              ctx.stroke();
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1 + offsetY);
              ctx.lineTo(this._x2anchor!, this._y2anchor! + offsetY);
              ctx.stroke();
              // Fill between
              ctx.fillStyle = this._color;
              ctx.globalAlpha = 0.05;
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1);
              ctx.lineTo(this._x2anchor!, this._y2anchor!);
              ctx.lineTo(this._x2anchor!, this._y2anchor! + offsetY);
              ctx.lineTo(this._x1, this._y1 + offsetY);
              ctx.closePath();
              ctx.fill();
              ctx.globalAlpha = 0.6;
            } else {
              // 2nd click preview: just a line
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1);
              ctx.lineTo(this._x2, this._y2);
              ctx.stroke();
            }
            break;
          }

          case 'triangle': {
            if (this._x2anchor !== undefined && this._y2anchor !== undefined) {
              // 3rd click: full triangle
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1);
              ctx.lineTo(this._x2anchor!, this._y2anchor!);
              ctx.lineTo(this._x2, this._y2);
              ctx.closePath();
              ctx.fillStyle = this._color;
              ctx.globalAlpha = 0.05;
              ctx.fill();
              ctx.globalAlpha = 0.6;
              ctx.stroke();
            } else {
              // 2nd click: just a line
              ctx.beginPath();
              ctx.moveTo(this._x1, this._y1);
              ctx.lineTo(this._x2, this._y2);
              ctx.stroke();
            }
            break;
          }

          case 'measure': {
            const left = Math.min(this._x1, this._x2);
            const top = Math.min(this._y1, this._y2);
            const w = Math.abs(this._x2 - this._x1);
            const h = Math.abs(this._y2 - this._y1);
            ctx.strokeStyle = '#10b981';
            ctx.strokeRect(left, top, w, h);
            ctx.beginPath();
            ctx.moveTo(this._x1, this._y1);
            ctx.lineTo(this._x2, this._y2);
            ctx.stroke();
            break;
          }
        }
      }

      // Anchor dots
      ctx.globalAlpha = 0.8;
      ctx.setLineDash([]);

      // Point1 anchor
      ctx.beginPath();
      ctx.arc(this._x1, this._y1, 4, 0, Math.PI * 2);
      ctx.fillStyle = this._color;
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Point2 anchor (for 3-click tools after 2nd click)
      if (this._x2anchor !== undefined && this._y2anchor !== undefined) {
        ctx.beginPath();
        ctx.arc(this._x2anchor, this._y2anchor, 4, 0, Math.PI * 2);
        ctx.fillStyle = this._color;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    });
  }
}

class TentativePaneView implements IPrimitivePaneView {
  private _renderer: TentativeRenderer | null = null;
  setRenderer(renderer: TentativeRenderer | null): void { this._renderer = renderer; }
  zOrder(): 'top' { return 'top'; }
  renderer(): IPrimitivePaneRenderer | null { return this._renderer; }
}

export class TentativePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new TentativePaneView();
  private _state: TentativeState | null = null;
  private _dataTimes: number[] = [];

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  setDataTimes(dataTimes: number[]): void { this._dataTimes = dataTimes; }

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

    const anchorOnly = this._state.screenX < 0;
    const x2 = anchorOnly ? (x1 as number) : this._state.screenX;
    const y2 = anchorOnly ? (y1 as number) : this._state.screenY;

    // Compute point2 anchor for 3-click tools
    let x2anchor: number | undefined;
    let y2anchor: number | undefined;
    if (this._state.point2) {
      const xp2 = timeToPixelX(this._state.point2.time, this._dataTimes, ts);
      const yp2 = this._series.priceToCoordinate(this._state.point2.price);
      if (xp2 !== null && yp2 !== null) {
        x2anchor = xp2 as number;
        y2anchor = yp2 as number;
      }
    }

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
      x2anchor, y2anchor,
    ));
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this._paneView];
  }
}
