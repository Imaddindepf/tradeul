import type {
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  PrimitiveHoveredItem,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawingPrimitive, type DrawingPaneView } from './BaseDrawingPrimitive';
import type { RectangleDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import { applyLineStyle, resetLineStyle, type LineStyle } from './canvasStyles';
import {
  HANDLE_RENDER_RADIUS,
  ZONE_HIT_PADDING,
  bodyHit,
  firstHandleHit,
  inBox,
} from './hitTesting';

class RectRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number,
    private _y1: number,
    private _x2: number,
    private _y2: number,
    private _color: string,
    private _fillColor: string,
    private _lineWidth: number,
    private _lineStyle: LineStyle,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const left = Math.min(this._x1, this._x2);
      const top = Math.min(this._y1, this._y2);
      const w = Math.abs(this._x2 - this._x1);
      const h = Math.abs(this._y2 - this._y1);
      if (w < 1 || h < 1) return;

      ctx.fillStyle = this._fillColor;
      ctx.fillRect(left, top, w, h);

      const strokeWidth = this._isSelected ? this._lineWidth + 1 : this._lineWidth;
      ctx.strokeStyle = this._color;
      ctx.lineWidth = strokeWidth;
      applyLineStyle(ctx, this._lineStyle, strokeWidth);
      ctx.strokeRect(left, top, w, h);
      resetLineStyle(ctx);

      if (this._isSelected) {
        const corners = [
          [left, top], [left + w, top],
          [left, top + h], [left + w, top + h],
        ];
        for (const [cx, cy] of corners) {
          ctx.beginPath();
          ctx.arc(cx, cy, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
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
  private _lineStyle: LineStyle = 'solid';
  private _isSelected = false;
  private _id = '';

  update(
    x1: number, y1: number, x2: number, y2: number,
    color: string, fillColor: string, lineWidth: number, lineStyle: LineStyle,
    isSelected: boolean, id: string,
  ): void {
    this._x1 = x1; this._y1 = y1; this._x2 = x2; this._y2 = y2;
    this._color = color; this._fillColor = fillColor;
    this._lineWidth = lineWidth; this._lineStyle = lineStyle;
    this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new RectRenderer(
      this._x1, this._y1, this._x2, this._y2,
      this._color, this._fillColor, this._lineWidth, this._lineStyle, this._isSelected,
    );
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    // The four corners are reshape handles. :p1/:p2 are the user-defined
    // anchor pair; :p3/:p4 are the derived opposite corners.
    //   :p1 = (x1,y1)             :p3 = (x2,y1)
    //   :p4 = (x1,y2)             :p2 = (x2,y2)
    const handle = firstHandleHit(x, y, this._id, [
      [this._x1, this._y1, ':p1'],
      [this._x2, this._y2, ':p2'],
      [this._x2, this._y1, ':p3'],
      [this._x1, this._y2, ':p4'],
    ]);
    if (handle) return handle;
    if (inBox(x, y, this._x1, this._y1, this._x2, this._y2, ZONE_HIT_PADDING)) {
      return bodyHit(this._id);
    }
    return null;
  }
}

export class RectanglePrimitive extends BaseDrawingPrimitive<RectangleDrawing> {
  private _paneView = new RectPaneView();
  protected paneView(): DrawingPaneView { return this._paneView; }

  protected syncViews(): void {
    const ts = this._chart!.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const y1 = this._series!.priceToCoordinate(this._drawing.point1.price);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);
    const y2 = this._series!.priceToCoordinate(this._drawing.point2.price);

    if (x1 === null || y1 === null || x2 === null || y2 === null) {
      this._paneView.update(0, 0, 0, 0, '', '', 0, 'solid', false, '');
      return;
    }

    this._paneView.update(
      x1, y1 as number, x2, y2 as number,
      this._drawing.color,
      this._drawing.fillColor,
      this._drawing.lineWidth,
      this._drawing.lineStyle,
      this.isActive,
      this._drawing.id,
    );
  }
}
