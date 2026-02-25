import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  PrimitiveHoveredItem,
  Time,
  IChartApiBase,
  ISeriesApi,
  SeriesType,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { RayDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class RayRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number, private _y1: number,
    private _x2: number, private _y2: number,
    private _color: string, private _lineWidth: number,
    private _isDashed: boolean, private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      // Extend the ray from p1 through p2 to the canvas edge
      const dx = this._x2 - this._x1;
      const dy = this._y2 - this._y1;

      let endX = this._x2, endY = this._y2;
      if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001) {
        // Find intersection with canvas edges
        const maxT = 10000;
        endX = this._x1 + dx * maxT;
        endY = this._y1 + dy * maxT;
        // Clip to canvas bounds
        if (endX > mediaSize.width + 100) {
          const t = (mediaSize.width + 100 - this._x1) / dx;
          endX = mediaSize.width + 100;
          endY = this._y1 + dy * t;
        } else if (endX < -100) {
          const t = (-100 - this._x1) / dx;
          endX = -100;
          endY = this._y1 + dy * t;
        }
      }

      ctx.beginPath();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      if (this._isDashed) ctx.setLineDash([6, 4]);
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(endX, endY);
      ctx.stroke();
      ctx.setLineDash([]);

      if (this._isSelected) {
        for (const [x, y] of [[this._x1, this._y1], [this._x2, this._y2]]) {
          ctx.beginPath();
          ctx.arc(x, y, 5, 0, Math.PI * 2);
          ctx.fillStyle = this._color;
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    });
  }
}

class RayPaneView implements IPrimitivePaneView {
  private _x1 = 0; private _y1 = 0; private _x2 = 0; private _y2 = 0;
  private _color = '#3b82f6'; private _lineWidth = 2;
  private _isDashed = false; private _isSelected = false; private _id = '';

  update(x1: number, y1: number, x2: number, y2: number,
    color: string, lineWidth: number, isDashed: boolean, isSelected: boolean, id: string): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._color = color; this._lineWidth = lineWidth;
    this._isDashed = isDashed; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new RayRenderer(this._x1, this._y1, this._x2, this._y2,
      this._color, this._lineWidth, this._isDashed, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    if (Math.hypot(x - this._x1, y - this._y1) < 12)
      return { cursorStyle: 'crosshair', externalId: this._id + ':p1', zOrder: 'top' };
    if (Math.hypot(x - this._x2, y - this._y2) < 12)
      return { cursorStyle: 'crosshair', externalId: this._id + ':p2', zOrder: 'top' };
    const dist = pointToRayDistance(x, y, this._x1, this._y1, this._x2, this._y2);
    if (dist < 8) return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    return null;
  }
}

export class RayPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new RayPaneView();
  private _drawing: RayDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: RayDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: RayDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing; this._isSelected = isSelected;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews(); this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;
    const ts = this._chart.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const y1 = this._series.priceToCoordinate(this._drawing.point1.price);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);
    const y2 = this._series.priceToCoordinate(this._drawing.point2.price);
    if (x1 === null || y1 === null || x2 === null || y2 === null) {
      this._paneView.update(0, 0, 0, 0, '', 0, false, false, ''); return;
    }
    this._paneView.update(x1, y1 as number, x2, y2 as number,
      this._drawing.color, this._drawing.lineWidth,
      this._drawing.lineStyle === 'dashed', this._isSelected, this._drawing.id);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}

function pointToRayDistance(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1, dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, ((px - x1) * dx + (py - y1) * dy) / lenSq); // No upper clamp — ray extends
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
