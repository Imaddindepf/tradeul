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
import type { PriceRangeDrawing } from './types';
import {
  HANDLE_RENDER_RADIUS,
  ZONE_HIT_PADDING,
  bodyHit,
  firstHandleHit,
  inBox,
} from './hitTesting';

/**
 * Vertical-only measurement. Renders as a translucent horizontal band that
 * spans the full chart width between the two prices, with a label showing
 * Δprice and % change.
 */
class PriceRangeRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _y1: number, private _y2: number,
    private _priceDiff: number, private _pctChange: number,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const top = Math.min(this._y1, this._y2);
      const bot = Math.max(this._y1, this._y2);
      const h = bot - top;
      if (h < 1) return;

      const isPos = this._priceDiff >= 0;
      const bgColor = isPos ? 'rgba(16,185,129,0.10)' : 'rgba(239,68,68,0.10)';
      const borderColor = isPos ? '#10b981' : '#ef4444';

      ctx.fillStyle = bgColor;
      ctx.fillRect(0, top, mediaSize.width, h);

      ctx.beginPath();
      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.moveTo(0, this._y1); ctx.lineTo(mediaSize.width, this._y1);
      ctx.moveTo(0, this._y2); ctx.lineTo(mediaSize.width, this._y2);
      ctx.stroke();
      ctx.setLineDash([]);

      const priceFmt = Math.abs(this._priceDiff) < 1
        ? this._priceDiff.toFixed(4)
        : this._priceDiff.toFixed(2);
      const sign = this._priceDiff >= 0 ? '+' : '';
      const label = `${sign}${priceFmt}  (${sign}${this._pctChange.toFixed(2)}%)`;

      ctx.font = 'bold 11px -apple-system, sans-serif';
      const tm = ctx.measureText(label);
      const padH = 7, padV = 4;
      const labelW = tm.width + padH * 2;
      const labelH = 14 + padV * 2;
      const labelX = mediaSize.width / 2 - labelW / 2;
      const labelY = (this._y1 + this._y2) / 2 - labelH / 2;

      ctx.beginPath();
      const r = 4;
      ctx.fillStyle = borderColor;
      ctx.globalAlpha = 0.95;
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

      ctx.fillStyle = '#ffffff';
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'center';
      ctx.fillText(label, labelX + labelW / 2, labelY + labelH / 2 + 0.5);

      if (this._isSelected) {
        for (const hy of [this._y1, this._y2]) {
          ctx.beginPath();
          ctx.arc(mediaSize.width / 2, hy, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
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

class PriceRangePaneView implements IPrimitivePaneView {
  private _y1 = 0; private _y2 = 0;
  private _priceDiff = 0; private _pctChange = 0;
  private _isSelected = false; private _id = '';
  private _midX = 0;

  update(y1: number, y2: number, priceDiff: number, pctChange: number,
    isSelected: boolean, id: string, midX: number): void {
    this._y1 = y1; this._y2 = y2;
    this._priceDiff = priceDiff; this._pctChange = pctChange;
    this._isSelected = isSelected; this._id = id; this._midX = midX;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._y1 === 0 && this._y2 === 0) return null;
    return new PriceRangeRenderer(this._y1, this._y2, this._priceDiff, this._pctChange, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._y1 === 0 && this._y2 === 0) return null;
    // The two handles sit at the centre of the band horizontally.
    const handle = firstHandleHit(x, y, this._id, [
      [this._midX, this._y1, ':p1'],
      [this._midX, this._y2, ':p2'],
    ]);
    if (handle) return handle;
    const top = Math.min(this._y1, this._y2);
    const bot = Math.max(this._y1, this._y2);
    if (y >= top - ZONE_HIT_PADDING && y <= bot + ZONE_HIT_PADDING) return bodyHit(this._id);
    return null;
  }
}

export class PriceRangePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new PriceRangePaneView();
  private _drawing: PriceRangeDrawing;
  private _isSelected = false;

  constructor(drawing: PriceRangeDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: PriceRangeDrawing, isSelected: boolean, isHovered?: boolean): void {
    this._drawing = drawing; this._isSelected = isSelected || !!isHovered;
    this.updateAllViews(); this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;
    const y1 = this._series.priceToCoordinate(this._drawing.point1.price);
    const y2 = this._series.priceToCoordinate(this._drawing.point2.price);
    if (y1 === null || y2 === null) {
      this._paneView.update(0, 0, 0, 0, false, '', 0); return;
    }
    const p1 = this._drawing.point1.price;
    const p2 = this._drawing.point2.price;
    const priceDiff = p2 - p1;
    const pctChange = p1 !== 0 ? (priceDiff / p1) * 100 : 0;
    const mid = this._chart ? (this._chart.timeScale().width() / 2) : 0;
    this._paneView.update(y1 as number, y2 as number, priceDiff, pctChange,
      this._isSelected, this._drawing.id, mid);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
