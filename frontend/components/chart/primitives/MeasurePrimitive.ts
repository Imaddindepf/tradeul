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
import type { MeasureDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class MeasureRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number, private _y1: number,
    private _x2: number, private _y2: number,
    private _color: string,
    private _priceDiff: number,
    private _pctChange: number,
    private _barCount: number,
    private _timeDiff: string,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const left = Math.min(this._x1, this._x2);
      const top = Math.min(this._y1, this._y2);
      const w = Math.abs(this._x2 - this._x1);
      const h = Math.abs(this._y2 - this._y1);

      // Background rect (subtle fill)
      ctx.fillStyle = this._priceDiff >= 0 ? 'rgba(16,185,129,0.06)' : 'rgba(239,68,68,0.06)';
      ctx.fillRect(left, top, w, h);

      // Border
      const isPositive = this._priceDiff >= 0;
      const borderColor = isPositive ? '#10b981' : '#ef4444';
      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(left, top, w, h);
      ctx.setLineDash([]);

      // Diagonal line
      ctx.beginPath();
      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1.5;
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(this._x2, this._y2);
      ctx.stroke();

      // Info label
      const priceFmt = Math.abs(this._priceDiff) < 1
        ? this._priceDiff.toFixed(4)
        : this._priceDiff.toFixed(2);
      const pctFmt = this._pctChange.toFixed(2);
      const sign = this._priceDiff >= 0 ? '+' : '';
      const lines = [
        `${sign}${priceFmt}  (${sign}${pctFmt}%)`,
        `${this._barCount} bars  •  ${this._timeDiff}`,
      ];

      const fontSize = 11;
      ctx.font = `bold ${fontSize}px -apple-system, sans-serif`;

      // Measure text widths
      const maxWidth = Math.max(...lines.map(l => ctx.measureText(l).width));
      const padH = 8, padV = 5;
      const labelW = maxWidth + padH * 2;
      const labelH = fontSize * lines.length + padV * 2 + 4;

      // Position label at center of the measure zone
      const labelX = (this._x1 + this._x2) / 2 - labelW / 2;
      const labelY = (this._y1 + this._y2) / 2 - labelH / 2;

      // Label background
      ctx.fillStyle = isPositive ? '#10b981' : '#ef4444';
      ctx.globalAlpha = 0.95;
      const r = 4;
      ctx.beginPath();
      ctx.moveTo(labelX + r, labelY);
      ctx.lineTo(labelX + labelW - r, labelY);
      ctx.arcTo(labelX + labelW, labelY, labelX + labelW, labelY + r, r);
      ctx.lineTo(labelX + labelW, labelY + labelH - r);
      ctx.arcTo(labelX + labelW, labelY + labelH, labelX + labelW - r, labelY + labelH, r);
      ctx.lineTo(labelX + r, labelY + labelH);
      ctx.arcTo(labelX, labelY + labelH, labelX, labelY + labelH - r, r);
      ctx.lineTo(labelX, labelY + r);
      ctx.arcTo(labelX, labelY, labelX + r, labelY, r);
      ctx.closePath();
      ctx.fill();
      ctx.globalAlpha = 1;

      // Label text
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (let i = 0; i < lines.length; i++) {
        ctx.font = i === 0 ? `bold ${fontSize}px -apple-system, sans-serif` : `${fontSize - 1}px -apple-system, sans-serif`;
        ctx.fillText(lines[i], labelX + labelW / 2, labelY + padV + fontSize / 2 + i * (fontSize + 3));
      }

      // Anchor dots
      if (this._isSelected) {
        for (const [ax, ay] of [[this._x1, this._y1], [this._x2, this._y2]]) {
          ctx.beginPath();
          ctx.arc(ax, ay, 5, 0, Math.PI * 2);
          ctx.fillStyle = borderColor;
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    });
  }
}

class MeasurePaneView implements IPrimitivePaneView {
  private _x1 = 0; private _y1 = 0; private _x2 = 0; private _y2 = 0;
  private _color = '#3b82f6'; private _priceDiff = 0; private _pctChange = 0;
  private _barCount = 0; private _timeDiff = ''; private _isSelected = false; private _id = '';

  update(x1: number, y1: number, x2: number, y2: number,
    color: string, priceDiff: number, pctChange: number, barCount: number,
    timeDiff: string, isSelected: boolean, id: string): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._color = color; this._priceDiff = priceDiff; this._pctChange = pctChange;
    this._barCount = barCount; this._timeDiff = timeDiff;
    this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new MeasureRenderer(this._x1, this._y1, this._x2, this._y2,
      this._color, this._priceDiff, this._pctChange, this._barCount,
      this._timeDiff, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    if (Math.hypot(x - this._x1, y - this._y1) < 12)
      return { cursorStyle: 'crosshair', externalId: this._id + ':p1', zOrder: 'top' };
    if (Math.hypot(x - this._x2, y - this._y2) < 12)
      return { cursorStyle: 'crosshair', externalId: this._id + ':p2', zOrder: 'top' };
    const left = Math.min(this._x1, this._x2);
    const right = Math.max(this._x1, this._x2);
    const top = Math.min(this._y1, this._y2);
    const bot = Math.max(this._y1, this._y2);
    if (x >= left - 5 && x <= right + 5 && y >= top - 5 && y <= bot + 5)
      return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    return null;
  }
}

export class MeasurePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new MeasurePaneView();
  private _drawing: MeasureDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: MeasureDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: MeasureDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
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
      this._paneView.update(0, 0, 0, 0, '', 0, 0, 0, '', false, ''); return;
    }

    const p1Price = this._drawing.point1.price;
    const p2Price = this._drawing.point2.price;
    const priceDiff = p2Price - p1Price;
    const pctChange = p1Price !== 0 ? (priceDiff / p1Price) * 100 : 0;

    // Count bars between times
    const t1 = Math.min(this._drawing.point1.time, this._drawing.point2.time);
    const t2 = Math.max(this._drawing.point1.time, this._drawing.point2.time);
    let barCount = 0;
    for (const t of this._dataTimes) {
      if (t >= t1 && t <= t2) barCount++;
    }

    // Format time difference
    const diffSec = Math.abs(this._drawing.point2.time - this._drawing.point1.time);
    let timeDiff: string;
    if (diffSec < 3600) timeDiff = `${Math.round(diffSec / 60)}m`;
    else if (diffSec < 86400) timeDiff = `${(diffSec / 3600).toFixed(1)}h`;
    else timeDiff = `${(diffSec / 86400).toFixed(1)}d`;

    this._paneView.update(
      x1, y1 as number, x2, y2 as number,
      this._drawing.color, priceDiff, pctChange, barCount, timeDiff,
      this._isSelected, this._drawing.id,
    );
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
