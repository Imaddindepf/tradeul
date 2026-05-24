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
import type { ArrowDirection, ArrowDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import {
  HANDLE_RENDER_RADIUS,
  bodyHit,
  firstHandleHit,
  inPolygon,
} from './hitTesting';

/**
 * Geometry note: the arrow head is anchored at (cx,cy). The tail extends
 * `LENGTH` pixels away in the chosen direction; the wedge width is `WIDTH`.
 * All four directions share the same shape (just rotated).
 */
const LENGTH = 28;
const WIDTH = 14;

function buildShape(cx: number, cy: number, dir: ArrowDirection): Array<[number, number]> {
  // Tip is always at (cx,cy). Tail base is 2/3 along the shaft, wedge head
  // is the last 1/3.
  switch (dir) {
    case 'up': {
      const tail = LENGTH;
      const w = WIDTH / 2;
      return [
        [cx, cy],
        [cx + w, cy + LENGTH * 0.4],
        [cx + w * 0.5, cy + LENGTH * 0.4],
        [cx + w * 0.5, cy + tail],
        [cx - w * 0.5, cy + tail],
        [cx - w * 0.5, cy + LENGTH * 0.4],
        [cx - w, cy + LENGTH * 0.4],
      ];
    }
    case 'down': {
      const w = WIDTH / 2;
      return [
        [cx, cy],
        [cx + w, cy - LENGTH * 0.4],
        [cx + w * 0.5, cy - LENGTH * 0.4],
        [cx + w * 0.5, cy - LENGTH],
        [cx - w * 0.5, cy - LENGTH],
        [cx - w * 0.5, cy - LENGTH * 0.4],
        [cx - w, cy - LENGTH * 0.4],
      ];
    }
    case 'left': {
      const w = WIDTH / 2;
      return [
        [cx, cy],
        [cx + LENGTH * 0.4, cy - w],
        [cx + LENGTH * 0.4, cy - w * 0.5],
        [cx + LENGTH, cy - w * 0.5],
        [cx + LENGTH, cy + w * 0.5],
        [cx + LENGTH * 0.4, cy + w * 0.5],
        [cx + LENGTH * 0.4, cy + w],
      ];
    }
    case 'right': {
      const w = WIDTH / 2;
      return [
        [cx, cy],
        [cx - LENGTH * 0.4, cy - w],
        [cx - LENGTH * 0.4, cy - w * 0.5],
        [cx - LENGTH, cy - w * 0.5],
        [cx - LENGTH, cy + w * 0.5],
        [cx - LENGTH * 0.4, cy + w * 0.5],
        [cx - LENGTH * 0.4, cy + w],
      ];
    }
  }
}

class ArrowRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _cx: number, private _cy: number,
    private _direction: ArrowDirection,
    private _color: string, private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const pts = buildShape(this._cx, this._cy, this._direction);
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.closePath();
      ctx.fillStyle = this._color;
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      if (this._isSelected) {
        ctx.beginPath();
        ctx.arc(this._cx, this._cy, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = this._color;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    });
  }
}

class ArrowPaneView implements IPrimitivePaneView {
  private _cx = 0; private _cy = 0;
  private _direction: ArrowDirection = 'up';
  private _color = '#3b82f6';
  private _isSelected = false;
  private _id = '';

  update(cx: number, cy: number, direction: ArrowDirection, color: string, isSelected: boolean, id: string): void {
    this._cx = cx; this._cy = cy; this._direction = direction;
    this._color = color; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'top' { return 'top'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._cx === 0 && this._cy === 0) return null;
    return new ArrowRenderer(this._cx, this._cy, this._direction, this._color, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._cx === 0 && this._cy === 0) return null;
    const handle = firstHandleHit(x, y, this._id, [[this._cx, this._cy, ':p1']]);
    if (handle) return handle;
    const pts = buildShape(this._cx, this._cy, this._direction);
    if (inPolygon(x, y, pts)) return bodyHit(this._id);
    return null;
  }
}

export class ArrowPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new ArrowPaneView();
  private _drawing: ArrowDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: ArrowDrawing) { this._drawing = drawing; }

  attached(param: SeriesAttachedParameter<Time>): void {
    this._chart = param.chart; this._series = param.series;
    this._requestUpdate = param.requestUpdate; this.updateAllViews();
  }

  detached(): void { this._chart = null; this._series = null; this._requestUpdate = null; }

  updateDrawing(drawing: ArrowDrawing, isSelected: boolean, isHovered?: boolean, dataTimes?: number[]): void {
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
      this._paneView.update(0, 0, 'up', '', false, ''); return;
    }
    this._paneView.update(x, y as number, this._drawing.direction,
      this._drawing.color, this._isSelected, this._drawing.id);
  }

  paneViews(): readonly IPrimitivePaneView[] { this.updateAllViews(); return [this._paneView]; }
  hitTest(x: number, y: number): PrimitiveHoveredItem | null { return this._paneView.hitTest(x, y); }
}
