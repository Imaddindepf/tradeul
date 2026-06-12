import type {
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  PrimitiveHoveredItem,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawingPrimitive, type DrawingPaneView } from './BaseDrawingPrimitive';
import type { TrendlineDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import { applyLineStyle, resetLineStyle, type LineStyle } from './canvasStyles';
import {
  BODY_HIT_TOLERANCE,
  HANDLE_RENDER_RADIUS,
  bodyHit,
  distToSegment,
  firstHandleHit,
} from './hitTesting';

// ─── Renderer ────────────────────────────────────────────────────────────────

class TrendlineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number,
    private _y1: number,
    private _x2: number,
    private _y2: number,
    private _color: string,
    private _lineWidth: number,
    private _lineStyle: LineStyle,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const strokeWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.beginPath();
      ctx.strokeStyle = this._color;
      ctx.lineWidth = strokeWidth;
      applyLineStyle(ctx, this._lineStyle, strokeWidth);
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(this._x2, this._y2);
      ctx.stroke();
      resetLineStyle(ctx);

      if (this._isSelected) {
        for (const [x, y] of [[this._x1, this._y1], [this._x2, this._y2]]) {
          ctx.beginPath();
          ctx.arc(x, y, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
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

// ─── PaneView ────────────────────────────────────────────────────────────────

class TrendlinePaneView implements IPrimitivePaneView {
  private _x1 = 0;
  private _y1 = 0;
  private _x2 = 0;
  private _y2 = 0;
  private _color = '#3b82f6';
  private _lineWidth = 2;
  private _lineStyle: LineStyle = 'solid';
  private _isSelected = false;
  private _id = '';

  update(
    x1: number, y1: number, x2: number, y2: number,
    color: string, lineWidth: number, lineStyle: LineStyle,
    isSelected: boolean, id: string,
  ): void {
    this._x1 = x1; this._y1 = y1;
    this._x2 = x2; this._y2 = y2;
    this._color = color;
    this._lineWidth = lineWidth;
    this._lineStyle = lineStyle;
    this._isSelected = isSelected;
    this._id = id;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new TrendlineRenderer(
      this._x1, this._y1, this._x2, this._y2,
      this._color, this._lineWidth, this._lineStyle, this._isSelected,
    );
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    const handle = firstHandleHit(x, y, this._id, [
      [this._x1, this._y1, ':p1'],
      [this._x2, this._y2, ':p2'],
    ]);
    if (handle) return handle;
    if (distToSegment(x, y, this._x1, this._y1, this._x2, this._y2) < BODY_HIT_TOLERANCE) {
      return bodyHit(this._id);
    }
    return null;
  }
}

// ─── Primitive ───────────────────────────────────────────────────────────────

export class TrendlinePrimitive extends BaseDrawingPrimitive<TrendlineDrawing> {
  private _paneView = new TrendlinePaneView();
  protected paneView(): DrawingPaneView { return this._paneView; }

  protected syncViews(): void {
    const ts = this._chart!.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const y1 = this._series!.priceToCoordinate(this._drawing.point1.price);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);
    const y2 = this._series!.priceToCoordinate(this._drawing.point2.price);

    if (x1 === null || y1 === null || x2 === null || y2 === null) {
      this._paneView.update(0, 0, 0, 0, '', 0, 'solid', false, '');
      return;
    }

    this._paneView.update(
      x1, y1 as number, x2, y2 as number,
      this._drawing.color,
      this._drawing.lineWidth,
      this._drawing.lineStyle,
      this.isActive,
      this._drawing.id,
    );
  }
}

