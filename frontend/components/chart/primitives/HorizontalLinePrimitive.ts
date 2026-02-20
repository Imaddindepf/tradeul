import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesPrimitiveAxisView,
  PrimitiveHoveredItem,
  Time,
  IChartApiBase,
  ISeriesApi,
  SeriesType,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { HorizontalLineDrawing } from './types';

// ─── Renderer ────────────────────────────────────────────────────────────────

class HLineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _y: number,
    private _color: string,
    private _lineWidth: number,
    private _isDashed: boolean,
    private _isSelected: boolean,
    private _isHovered: boolean,
    private _label: string,
    private _priceText: string,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const y = Math.round(this._y) + 0.5; // crisp pixel alignment
      if (y < -10 || y > mediaSize.height + 10) return;

      const active = this._isSelected || this._isHovered;

      // Main line
      ctx.beginPath();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = active ? this._lineWidth + 0.5 : this._lineWidth;
      if (this._isDashed) ctx.setLineDash([6, 4]);
      ctx.moveTo(0, y);
      ctx.lineTo(mediaSize.width, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Price tag on the right edge
      const tagText = this._label || this._priceText;
      if (tagText) {
        ctx.font = 'bold 10px -apple-system, BlinkMacSystemFont, sans-serif';
        const tm = ctx.measureText(tagText);
        const padH = 6;
        const padV = 3;
        const tagW = tm.width + padH * 2;
        const tagH = 14 + padV * 2;
        const tagX = mediaSize.width - tagW - 4;
        const tagY = y - tagH / 2;

        // Tag background
        ctx.beginPath();
        const r = 3;
        ctx.moveTo(tagX + r, tagY);
        ctx.lineTo(tagX + tagW - r, tagY);
        ctx.arcTo(tagX + tagW, tagY, tagX + tagW, tagY + r, r);
        ctx.lineTo(tagX + tagW, tagY + tagH - r);
        ctx.arcTo(tagX + tagW, tagY + tagH, tagX + tagW - r, tagY + tagH, r);
        ctx.lineTo(tagX + r, tagY + tagH);
        ctx.arcTo(tagX, tagY + tagH, tagX, tagY + tagH - r, r);
        ctx.lineTo(tagX, tagY + r);
        ctx.arcTo(tagX, tagY, tagX + r, tagY, r);
        ctx.closePath();
        ctx.fillStyle = this._color;
        ctx.fill();

        // Tag text
        ctx.fillStyle = '#ffffff';
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'center';
        ctx.fillText(tagText, tagX + tagW / 2, y + 0.5);
      }

      // Drag handles when selected
      if (this._isSelected) {
        const handlePositions = [mediaSize.width * 0.25, mediaSize.width * 0.5, mediaSize.width * 0.75];
        for (const hx of handlePositions) {
          ctx.beginPath();
          ctx.arc(hx, y, 4, 0, Math.PI * 2);
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

// ─── Price Axis View ─────────────────────────────────────────────────────────

class HLinePriceAxisView implements ISeriesPrimitiveAxisView {
  private _y = 0;
  private _price = '';
  private _color = '#3b82f6';
  private _visible = false;

  update(y: number, price: string, color: string, visible: boolean): void {
    this._y = y;
    this._price = price;
    this._color = color;
    this._visible = visible;
  }

  coordinate(): number { return this._y; }
  text(): string { return this._price; }
  textColor(): string { return '#ffffff'; }
  backColor(): string { return this._color; }
  visible(): boolean { return this._visible; }
}

// ─── PaneView ────────────────────────────────────────────────────────────────

class HLinePaneView implements IPrimitivePaneView {
  private _y = 0;
  private _active = false;
  private _color = '#3b82f6';
  private _lineWidth = 2;
  private _isDashed = false;
  private _isSelected = false;
  private _isHovered = false;
  private _label = '';
  private _priceText = '';
  private _id = '';

  update(
    y: number, color: string, lineWidth: number, isDashed: boolean,
    isSelected: boolean, isHovered: boolean, label: string, priceText: string, id: string,
  ): void {
    this._y = y; this._active = true; this._color = color;
    this._lineWidth = lineWidth; this._isDashed = isDashed;
    this._isSelected = isSelected; this._isHovered = isHovered;
    this._label = label; this._priceText = priceText; this._id = id;
  }

  clear(): void { this._active = false; }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (!this._active) return null;
    return new HLineRenderer(
      this._y, this._color, this._lineWidth, this._isDashed,
      this._isSelected, this._isHovered, this._label, this._priceText,
    );
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (!this._active) return null;
    if (Math.abs(y - this._y) < 8) {
      return { cursorStyle: 'ns-resize', externalId: this._id, zOrder: 'top' };
    }
    return null;
  }
}

// ─── Primitive ───────────────────────────────────────────────────────────────

export class HorizontalLinePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new HLinePaneView();
  private _priceAxisView = new HLinePriceAxisView();

  private _drawing: HorizontalLineDrawing;
  private _isSelected = false;
  private _isHovered = false;

  constructor(drawing: HorizontalLineDrawing) {
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

  updateDrawing(drawing: HorizontalLineDrawing, isSelected: boolean, isHovered?: boolean): void {
    this._drawing = drawing;
    this._isSelected = isSelected;
    this._isHovered = isHovered ?? false;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._series) return;

    const y = this._series.priceToCoordinate(this._drawing.price);
    if (y === null) {
      this._paneView.clear();
      this._priceAxisView.update(0, '', '', false);
      return;
    }

    const price = this._drawing.price;
    const priceText = price < 1 ? price.toFixed(4) : price < 100 ? price.toFixed(2) : price.toFixed(2);

    this._paneView.update(
      y as number,
      this._drawing.color,
      this._drawing.lineWidth,
      this._drawing.lineStyle === 'dashed',
      this._isSelected,
      this._isHovered,
      this._drawing.label || '',
      priceText,
      this._drawing.id,
    );

    this._priceAxisView.update(y as number, priceText, this._drawing.color, true);
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this._paneView];
  }

  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return [this._priceAxisView];
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    return this._paneView.hitTest(x, y);
  }
}
