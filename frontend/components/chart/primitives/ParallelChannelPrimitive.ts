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
import type { ParallelChannelDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class ChannelRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number, private _y1: number,   // A (top-left)
    private _x2: number, private _y2: number,   // B (top-right)
    private _x3: number, private _y3: number,   // C (bottom-left)
    private _x4: number, private _y4: number,   // D (bottom-right, derived)
    private _color: string, private _fillColor: string,
    private _lineWidth: number, private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      // Fill between the two lines
      ctx.beginPath();
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(this._x2, this._y2);
      ctx.lineTo(this._x4, this._y4);
      ctx.lineTo(this._x3, this._y3);
      ctx.closePath();
      ctx.fillStyle = this._fillColor;
      ctx.fill();

      // Main line (A → B)
      ctx.beginPath();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(this._x2, this._y2);
      ctx.stroke();

      // Parallel line (C → D)
      ctx.beginPath();
      ctx.moveTo(this._x3, this._y3);
      ctx.lineTo(this._x4, this._y4);
      ctx.stroke();

      // Middle line (dashed)
      const mx1 = (this._x1 + this._x3) / 2, my1 = (this._y1 + this._y3) / 2;
      const mx2 = (this._x2 + this._x4) / 2, my2 = (this._y2 + this._y4) / 2;
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 0.8;
      ctx.globalAlpha = 0.5;
      ctx.moveTo(mx1, my1);
      ctx.lineTo(mx2, my2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      if (this._isSelected) {
        // 4 corner anchors (squares) — A, B, C, D
        for (const [cx, cy] of [
          [this._x1, this._y1], [this._x2, this._y2],
          [this._x3, this._y3], [this._x4, this._y4],
        ]) {
          ctx.fillStyle = this._color;
          ctx.fillRect(cx - 5, cy - 5, 10, 10);
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.strokeRect(cx - 5, cy - 5, 10, 10);
        }

        // 2 midpoint anchors (circles) — M1, M2
        const m1x = (this._x1 + this._x2) / 2, m1y = (this._y1 + this._y2) / 2;
        const m2x = (this._x3 + this._x4) / 2, m2y = (this._y3 + this._y4) / 2;
        for (const [mx, my] of [[m1x, m1y], [m2x, m2y]]) {
          ctx.beginPath();
          ctx.arc(mx, my, 4.5, 0, Math.PI * 2);
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

class ChannelPaneView implements IPrimitivePaneView {
  private _x1 = 0; private _y1 = 0; private _x2 = 0; private _y2 = 0;
  private _x3 = 0; private _y3 = 0; private _x4 = 0; private _y4 = 0;
  private _color = '#3b82f6'; private _fillColor = 'rgba(59,130,246,0.08)';
  private _lineWidth = 2; private _isSelected = false; private _id = '';

  update(x1: number, y1: number, x2: number, y2: number,
    x3: number, y3: number, x4: number, y4: number,
    color: string, fillColor: string, lineWidth: number, isSelected: boolean, id: string): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._x3 = x3; this._y3 = y3; this._x4 = x4; this._y4 = y4;
    this._color = color; this._fillColor = fillColor;
    this._lineWidth = lineWidth; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new ChannelRenderer(this._x1, this._y1, this._x2, this._y2,
      this._x3, this._y3, this._x4, this._y4,
      this._color, this._fillColor, this._lineWidth, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;

    // 4 corner anchors: A(:p1), B(:p2), C(:p3), D(:p4)
    for (const [px, py, label] of [
      [this._x1, this._y1, ':p1'],
      [this._x2, this._y2, ':p2'],
      [this._x3, this._y3, ':p3'],
      [this._x4, this._y4, ':p4'],
    ] as [number, number, string][]) {
      if (Math.hypot(x - px, y - py) < 12)
        return { cursorStyle: 'crosshair', externalId: this._id + label, zOrder: 'top' };
    }

    // 2 midpoint anchors: M1(:m1), M2(:m2) — for channel width
    const m1x = (this._x1 + this._x2) / 2, m1y = (this._y1 + this._y2) / 2;
    const m2x = (this._x3 + this._x4) / 2, m2y = (this._y3 + this._y4) / 2;
    if (Math.hypot(x - m1x, y - m1y) < 12)
      return { cursorStyle: 'ns-resize', externalId: this._id + ':m1', zOrder: 'top' };
    if (Math.hypot(x - m2x, y - m2y) < 12)
      return { cursorStyle: 'ns-resize', externalId: this._id + ':m2', zOrder: 'top' };

    // Interior — translate
    const minX = Math.min(this._x1, this._x2, this._x3, this._x4);
    const maxX = Math.max(this._x1, this._x2, this._x3, this._x4);
    const minY = Math.min(this._y1, this._y2, this._y3, this._y4);
    const maxY = Math.max(this._y1, this._y2, this._y3, this._y4);
    if (x >= minX - 5 && x <= maxX + 5 && y >= minY - 5 && y <= maxY + 5) {
      return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    }
    return null;
  }
}

export class ParallelChannelPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new ChannelPaneView();
  private _drawing: ParallelChannelDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: ParallelChannelDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: ParallelChannelDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
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
      this._paneView.update(0, 0, 0, 0, 0, 0, 0, 0, '', '', 0, false, ''); return;
    }

    // D = C + (B - A) in price space. C shares X with A, D shares X with B.
    const priceOffset = this._drawing.point3.price - this._drawing.point1.price;
    const y3 = this._series.priceToCoordinate(this._drawing.point3.price);
    const y4 = this._series.priceToCoordinate(this._drawing.point2.price + priceOffset);

    if (y3 === null || y4 === null) return;

    this._paneView.update(
      x1, y1 as number, x2, y2 as number,
      x1, y3 as number, x2, y4 as number,
      this._drawing.color, this._drawing.fillColor, this._drawing.lineWidth,
      this._isSelected, this._drawing.id,
    );
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
