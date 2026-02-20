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
import type { RectangleDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class RectRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number,
    private _y1: number,
    private _x2: number,
    private _y2: number,
    private _color: string,
    private _fillColor: string,
    private _lineWidth: number,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const left = Math.min(this._x1, this._x2);
      const top = Math.min(this._y1, this._y2);
      const w = Math.abs(this._x2 - this._x1);
      const h = Math.abs(this._y2 - this._y1);
      if (w < 1 || h < 1) return;

      // Fill
      ctx.fillStyle = this._fillColor;
      ctx.fillRect(left, top, w, h);

      // Stroke
      ctx.strokeStyle = this._color;
      ctx.lineWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.strokeRect(left, top, w, h);

      // Anchor dots when selected
      if (this._isSelected) {
        const corners = [
          [left, top], [left + w, top],
          [left, top + h], [left + w, top + h],
        ];
        for (const [cx, cy] of corners) {
          ctx.beginPath();
          ctx.arc(cx, cy, 4, 0, Math.PI * 2);
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

class RectPaneView implements IPrimitivePaneView {
  private _x1 = 0;
  private _y1 = 0;
  private _x2 = 0;
  private _y2 = 0;
  private _color = '#3b82f6';
  private _fillColor = 'rgba(59,130,246,0.1)';
  private _lineWidth = 1;
  private _isSelected = false;
  private _id = '';

  update(
    x1: number, y1: number, x2: number, y2: number,
    color: string, fillColor: string, lineWidth: number,
    isSelected: boolean, id: string,
  ): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._color = color; this._fillColor = fillColor;
    this._lineWidth = lineWidth; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new RectRenderer(
      this._x1, this._y1, this._x2, this._y2,
      this._color, this._fillColor, this._lineWidth, this._isSelected,
    );
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    // Check corner anchors
    const distP1 = Math.hypot(x - this._x1, y - this._y1);
    if (distP1 < 12) {
      return { cursorStyle: 'crosshair', externalId: this._id + ':p1', zOrder: 'top' };
    }
    const distP2 = Math.hypot(x - this._x2, y - this._y2);
    if (distP2 < 12) {
      return { cursorStyle: 'crosshair', externalId: this._id + ':p2', zOrder: 'top' };
    }
    // Check edges and interior
    const left = Math.min(this._x1, this._x2);
    const right = Math.max(this._x1, this._x2);
    const top = Math.min(this._y1, this._y2);
    const bot = Math.max(this._y1, this._y2);
    if (x >= left - 5 && x <= right + 5 && y >= top - 5 && y <= bot + 5) {
      return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    }
    return null;
  }
}

export class RectanglePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new RectPaneView();

  private _drawing: RectangleDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: RectangleDrawing) {
    this._drawing = drawing;
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this.updateAllViews();
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  updateDrawing(drawing: RectangleDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing;
    this._isSelected = isSelected;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;

    const ts = this._chart.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const y1 = this._series.priceToCoordinate(this._drawing.point1.price);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);
    const y2 = this._series.priceToCoordinate(this._drawing.point2.price);

    if (x1 === null || y1 === null || x2 === null || y2 === null) {
      this._paneView.update(0, 0, 0, 0, '', '', 0, false, '');
      return;
    }

    this._paneView.update(
      x1, y1 as number, x2, y2 as number,
      this._drawing.color,
      this._drawing.fillColor,
      this._drawing.lineWidth,
      this._isSelected,
      this._drawing.id,
    );
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this._paneView];
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    return this._paneView.hitTest(x, y);
  }
}
