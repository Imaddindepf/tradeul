import type {
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  PrimitiveHoveredItem,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawingPrimitive, type DrawingPaneView } from './BaseDrawingPrimitive';
import type { TriangleDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import { applyLineStyle, resetLineStyle, type LineStyle } from './canvasStyles';
import {
  HANDLE_RENDER_RADIUS,
  bodyHit,
  firstHandleHit,
  inTriangle,
} from './hitTesting';

class TriRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number, private _y1: number,
    private _x2: number, private _y2: number,
    private _x3: number, private _y3: number,
    private _color: string, private _fillColor: string,
    private _lineWidth: number, private _lineStyle: LineStyle, private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.beginPath();
      ctx.moveTo(this._x1, this._y1);
      ctx.lineTo(this._x2, this._y2);
      ctx.lineTo(this._x3, this._y3);
      ctx.closePath();
      ctx.fillStyle = this._fillColor;
      ctx.fill();
      const strokeWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.strokeStyle = this._color;
      ctx.lineWidth = strokeWidth;
      applyLineStyle(ctx, this._lineStyle, strokeWidth);
      ctx.stroke();
      resetLineStyle(ctx);

      if (this._isSelected) {
        for (const [x, y] of [[this._x1, this._y1], [this._x2, this._y2], [this._x3, this._y3]]) {
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

class TriPaneView implements IPrimitivePaneView {
  private _x1 = 0; private _y1 = 0;
  private _x2 = 0; private _y2 = 0;
  private _x3 = 0; private _y3 = 0;
  private _color = '#3b82f6'; private _fillColor = 'rgba(59,130,246,0.1)';
  private _lineWidth = 1; private _lineStyle: LineStyle = 'solid';
  private _isSelected = false; private _id = '';

  update(x1: number, y1: number, x2: number, y2: number, x3: number, y3: number,
    color: string, fillColor: string, lineWidth: number, lineStyle: LineStyle,
    isSelected: boolean, id: string): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._x3 = x3; this._y3 = y3;
    this._color = color; this._fillColor = fillColor;
    this._lineWidth = lineWidth; this._lineStyle = lineStyle;
    this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0 && this._x3 === 0) return null;
    return new TriRenderer(this._x1, this._y1, this._x2, this._y2, this._x3, this._y3,
      this._color, this._fillColor, this._lineWidth, this._lineStyle, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    const handle = firstHandleHit(x, y, this._id, [
      [this._x1, this._y1, ':p1'],
      [this._x2, this._y2, ':p2'],
      [this._x3, this._y3, ':p3'],
    ]);
    if (handle) return handle;
    if (inTriangle(x, y, this._x1, this._y1, this._x2, this._y2, this._x3, this._y3)) {
      return bodyHit(this._id);
    }
    return null;
  }
}

export class TrianglePrimitive extends BaseDrawingPrimitive<TriangleDrawing> {
  private _paneView = new TriPaneView();
  protected paneView(): DrawingPaneView { return this._paneView; }

  protected syncViews(): void {
    const ts = this._chart!.timeScale();
    const coords = [this._drawing.point1, this._drawing.point2, this._drawing.point3].map(p => ({
      x: timeToPixelX(p.time, this._dataTimes, ts),
      y: this._series!.priceToCoordinate(p.price),
    }));
    if (coords.some(c => c.x === null || c.y === null)) {
      this._paneView.update(0, 0, 0, 0, 0, 0, '', '', 0, 'solid', false, ''); return;
    }
    this._paneView.update(
      coords[0].x!, coords[0].y as number,
      coords[1].x!, coords[1].y as number,
      coords[2].x!, coords[2].y as number,
      this._drawing.color, this._drawing.fillColor, this._drawing.lineWidth,
      this._drawing.lineStyle, this.isActive, this._drawing.id,
    );
  }
}
