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
import type { VerticalLineDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';

class VLineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x: number,
    private _color: string,
    private _lineWidth: number,
    private _isDashed: boolean,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const x = Math.round(this._x) + 0.5;
      if (x < -10 || x > mediaSize.width + 10) return;

      ctx.beginPath();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = this._isSelected ? this._lineWidth + 0.5 : this._lineWidth;
      if (this._isDashed) ctx.setLineDash([6, 4]);
      ctx.moveTo(x, 0);
      ctx.lineTo(x, mediaSize.height);
      ctx.stroke();
      ctx.setLineDash([]);

      if (this._isSelected) {
        const handles = [mediaSize.height * 0.25, mediaSize.height * 0.5, mediaSize.height * 0.75];
        for (const hy of handles) {
          ctx.beginPath();
          ctx.arc(x, hy, 4, 0, Math.PI * 2);
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

class VLinePaneView implements IPrimitivePaneView {
  private _x = 0;
  private _active = false;
  private _color = '#3b82f6';
  private _lineWidth = 2;
  private _isDashed = false;
  private _isSelected = false;
  private _id = '';

  update(x: number, color: string, lineWidth: number, isDashed: boolean, isSelected: boolean, id: string): void {
    this._x = x; this._active = true; this._color = color;
    this._lineWidth = lineWidth; this._isDashed = isDashed;
    this._isSelected = isSelected; this._id = id;
  }

  clear(): void { this._active = false; }
  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (!this._active) return null;
    return new VLineRenderer(this._x, this._color, this._lineWidth, this._isDashed, this._isSelected);
  }

  hitTest(x: number, _y: number): PrimitiveHoveredItem | null {
    if (!this._active) return null;
    if (Math.abs(x - this._x) < 8) {
      return { cursorStyle: 'ew-resize', externalId: this._id, zOrder: 'top' };
    }
    return null;
  }
}

class VLineTimeAxisView implements ISeriesPrimitiveAxisView {
  private _x = 0;
  private _text = '';
  private _color = '#3b82f6';
  private _visible = false;

  update(x: number, text: string, color: string, visible: boolean): void {
    this._x = x; this._text = text; this._color = color; this._visible = visible;
  }

  coordinate(): number { return this._x; }
  text(): string { return this._text; }
  textColor(): string { return '#ffffff'; }
  backColor(): string { return this._color; }
  visible(): boolean { return this._visible; }
}

export class VerticalLinePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new VLinePaneView();
  private _timeAxisView = new VLineTimeAxisView();
  private _drawing: VerticalLineDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: VerticalLineDrawing) {
    this._drawing = drawing;
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: VerticalLineDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing;
    this._isSelected = isSelected;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart) { this._paneView.clear(); return; }
    const ts = this._chart.timeScale();
    const x = timeToPixelX(this._drawing.time, this._dataTimes, ts);
    if (x === null) { this._paneView.clear(); return; }

    const date = new Date(this._drawing.time * 1000);
    const timeText = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

    this._paneView.update(x, this._drawing.color, this._drawing.lineWidth,
      this._drawing.lineStyle === 'dashed', this._isSelected, this._drawing.id);
    this._timeAxisView.update(x, timeText, this._drawing.color, true);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  timeAxisViews(): readonly ISeriesPrimitiveAxisView[] { return [this._timeAxisView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
