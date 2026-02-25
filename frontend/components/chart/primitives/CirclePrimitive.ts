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
import type { CircleDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class CircleRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _cx: number, private _cy: number,
    private _rx: number, private _ry: number,
    private _color: string, private _fillColor: string,
    private _lineWidth: number, private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      if (this._rx < 1 && this._ry < 1) return;

      ctx.beginPath();
      ctx.ellipse(this._cx, this._cy, this._rx, this._ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = this._fillColor;
      ctx.fill();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.stroke();

      if (this._isSelected) {
        // Center dot
        ctx.beginPath();
        ctx.arc(this._cx, this._cy, 4, 0, Math.PI * 2);
        ctx.fillStyle = this._color;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Edge handles (N, S, E, W)
        const handles = [
          [this._cx, this._cy - this._ry],
          [this._cx, this._cy + this._ry],
          [this._cx + this._rx, this._cy],
          [this._cx - this._rx, this._cy],
        ];
        for (const [hx, hy] of handles) {
          ctx.beginPath();
          ctx.arc(hx, hy, 4, 0, Math.PI * 2);
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

class CirclePaneView implements IPrimitivePaneView {
  private _cx = 0; private _cy = 0;
  private _rx = 0; private _ry = 0;
  private _ex = 0; private _ey = 0; // edge point for hit testing
  private _color = '#3b82f6'; private _fillColor = 'rgba(59,130,246,0.1)';
  private _lineWidth = 1; private _isSelected = false; private _id = '';

  update(cx: number, cy: number, ex: number, ey: number,
    color: string, fillColor: string, lineWidth: number, isSelected: boolean, id: string): void {
    this._cx = cx; this._cy = cy;
    this._ex = ex; this._ey = ey;
    this._rx = Math.abs(ex - cx);
    this._ry = Math.abs(ey - cy);
    this._color = color; this._fillColor = fillColor;
    this._lineWidth = lineWidth; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._rx < 1 && this._ry < 1) return null;
    return new CircleRenderer(this._cx, this._cy, this._rx, this._ry,
      this._color, this._fillColor, this._lineWidth, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._rx < 1 && this._ry < 1) return null;
    // Center — translate entire circle (not anchor)
    if (Math.hypot(x - this._cx, y - this._cy) < 12)
      return { cursorStyle: 'move', externalId: this._id, zOrder: 'top' };
    // Edge anchor
    if (Math.hypot(x - this._ex, y - this._ey) < 12)
      return { cursorStyle: 'crosshair', externalId: this._id + ':p2', zOrder: 'top' };
    // Inside ellipse?
    const nx = (x - this._cx) / this._rx;
    const ny = (y - this._cy) / this._ry;
    const d = nx * nx + ny * ny;
    if (d <= 1.15) return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    return null;
  }
}

export class CirclePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new CirclePaneView();
  private _drawing: CircleDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: CircleDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: CircleDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
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
      this._paneView.update(0, 0, 0, 0, '', '', 0, false, ''); return;
    }
    this._paneView.update(x1, y1 as number, x2, y2 as number,
      this._drawing.color, this._drawing.fillColor, this._drawing.lineWidth,
      this._isSelected, this._drawing.id);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
