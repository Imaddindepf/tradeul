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
import type { TextDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import {
  HANDLE_RENDER_RADIUS,
  bodyHit,
  firstHandleHit,
  inBox,
} from './hitTesting';

const PAD_H = 6;
const PAD_V = 4;
const RADIUS = 4;
const FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

function measureBoxSize(ctx: CanvasRenderingContext2D, text: string, fontSize: number): { w: number; h: number; lines: string[] } {
  ctx.font = `${fontSize}px ${FONT_FAMILY}`;
  const lines = text.split('\n');
  let maxW = 0;
  for (const line of lines) {
    const m = ctx.measureText(line || ' ');
    if (m.width > maxW) maxW = m.width;
  }
  const lineH = Math.round(fontSize * 1.25);
  return { w: maxW + PAD_H * 2, h: lineH * lines.length + PAD_V * 2, lines };
}

class TextRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x: number, private _y: number,
    private _text: string,
    private _fontSize: number,
    private _color: string,
    private _background: boolean,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const { w, h, lines } = measureBoxSize(ctx, this._text, this._fontSize);
      const x = this._x;
      const y = this._y;

      if (this._background) {
        ctx.beginPath();
        ctx.fillStyle = this._color;
        roundedRect(ctx, x, y, w, h, RADIUS);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
      } else {
        ctx.fillStyle = this._color;
      }

      ctx.font = `${this._fontSize}px ${FONT_FAMILY}`;
      ctx.textBaseline = 'top';
      const lineH = Math.round(this._fontSize * 1.25);
      for (let i = 0; i < lines.length; i++) {
        ctx.fillText(lines[i], x + PAD_H, y + PAD_V + i * lineH);
      }

      if (this._isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = this._color;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 2]);
        roundedRect(ctx, x - 1, y - 1, w + 2, h + 2, RADIUS + 1);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.beginPath();
        ctx.arc(x, y, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = this._color;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    });
  }
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
}

class TextPaneView implements IPrimitivePaneView {
  private _x = 0; private _y = 0;
  private _text = '';
  private _fontSize = 12;
  private _color = '#3b82f6';
  private _background = true;
  private _isSelected = false;
  private _id = '';
  private _boxW = 0;
  private _boxH = 0;

  update(
    x: number, y: number, text: string, fontSize: number,
    color: string, background: boolean, isSelected: boolean, id: string,
    boxW: number, boxH: number,
  ): void {
    this._x = x; this._y = y; this._text = text;
    this._fontSize = fontSize; this._color = color; this._background = background;
    this._isSelected = isSelected; this._id = id;
    this._boxW = boxW; this._boxH = boxH;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x === 0 && this._y === 0) return null;
    return new TextRenderer(this._x, this._y, this._text, this._fontSize, this._color, this._background, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x === 0 && this._y === 0) return null;
    const handle = firstHandleHit(x, y, this._id, [[this._x, this._y, ':p1']]);
    if (handle) return handle;
    if (inBox(x, y, this._x, this._y, this._x + this._boxW, this._y + this._boxH, 0)) {
      return bodyHit(this._id);
    }
    return null;
  }
}

export class TextPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new TextPaneView();
  private _drawing: TextDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: TextDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: TextDrawing, isSelected: boolean, isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing; this._isSelected = isSelected || !!isHovered;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews(); this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;
    const ts = this._chart.timeScale();
    const x = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const y = this._series.priceToCoordinate(this._drawing.point1.price);
    if (x === null || y === null) {
      this._paneView.update(0, 0, '', 12, '', false, false, '', 0, 0); return;
    }
    // Pre-measure off-screen so the hit-box matches the rendered size.
    const tmp = document.createElement('canvas').getContext('2d');
    let boxW = 60, boxH = 22;
    if (tmp) {
      const sz = measureBoxSize(tmp, this._drawing.text, this._drawing.fontSize);
      boxW = sz.w; boxH = sz.h;
    }
    this._paneView.update(x, y as number, this._drawing.text, this._drawing.fontSize,
      this._drawing.color, this._drawing.background, this._isSelected, this._drawing.id, boxW, boxH);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
