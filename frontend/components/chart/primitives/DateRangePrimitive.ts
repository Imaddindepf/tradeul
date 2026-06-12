import type {
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  PrimitiveHoveredItem,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import { BaseDrawingPrimitive, type DrawingPaneView } from './BaseDrawingPrimitive';
import type { DateRangeDrawing } from './types';
import { timeToPixelX } from './coordinateUtils';
import {
  HANDLE_RENDER_RADIUS,
  ZONE_HIT_PADDING,
  bodyHit,
  firstHandleHit,
} from './hitTesting';

/**
 * Horizontal-only measurement. Renders as a translucent vertical band that
 * spans the full chart height between the two times, with a label showing
 * bar count and Δtime.
 */
class DateRangeRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number, private _x2: number,
    private _barCount: number, private _timeDiff: string,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const left = Math.min(this._x1, this._x2);
      const right = Math.max(this._x1, this._x2);
      const w = right - left;
      if (w < 1) return;

      ctx.fillStyle = 'rgba(96,165,250,0.10)';
      ctx.fillRect(left, 0, w, mediaSize.height);

      ctx.beginPath();
      ctx.strokeStyle = '#60a5fa';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.moveTo(this._x1, 0); ctx.lineTo(this._x1, mediaSize.height);
      ctx.moveTo(this._x2, 0); ctx.lineTo(this._x2, mediaSize.height);
      ctx.stroke();
      ctx.setLineDash([]);

      const label = `${this._barCount} bars  •  ${this._timeDiff}`;
      ctx.font = 'bold 11px -apple-system, sans-serif';
      const tm = ctx.measureText(label);
      const padH = 7, padV = 4;
      const labelW = tm.width + padH * 2;
      const labelH = 14 + padV * 2;
      const labelX = (this._x1 + this._x2) / 2 - labelW / 2;
      const labelY = mediaSize.height / 2 - labelH / 2;

      ctx.beginPath();
      const r = 4;
      ctx.fillStyle = '#60a5fa';
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
        for (const hx of [this._x1, this._x2]) {
          ctx.beginPath();
          ctx.arc(hx, mediaSize.height / 2, HANDLE_RENDER_RADIUS, 0, Math.PI * 2);
          ctx.fillStyle = '#60a5fa';
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    });
  }
}

class DateRangePaneView implements IPrimitivePaneView {
  private _x1 = 0; private _x2 = 0;
  private _barCount = 0; private _timeDiff = '';
  private _isSelected = false; private _id = '';
  private _midY = 0;

  update(x1: number, x2: number, barCount: number, timeDiff: string,
    isSelected: boolean, id: string, midY: number): void {
    this._x1 = x1; this._x2 = x2;
    this._barCount = barCount; this._timeDiff = timeDiff;
    this._isSelected = isSelected; this._id = id; this._midY = midY;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    return new DateRangeRenderer(this._x1, this._x2, this._barCount, this._timeDiff, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0) return null;
    const handle = firstHandleHit(x, y, this._id, [
      [this._x1, this._midY, ':p1'],
      [this._x2, this._midY, ':p2'],
    ]);
    if (handle) return handle;
    const left = Math.min(this._x1, this._x2);
    const right = Math.max(this._x1, this._x2);
    if (x >= left - ZONE_HIT_PADDING && x <= right + ZONE_HIT_PADDING) return bodyHit(this._id);
    return null;
  }
}

export class DateRangePrimitive extends BaseDrawingPrimitive<DateRangeDrawing> {
  private _paneView = new DateRangePaneView();
  protected paneView(): DrawingPaneView { return this._paneView; }

  protected syncViews(): void {
    const ts = this._chart!.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);
    if (x1 === null || x2 === null) {
      this._paneView.update(0, 0, 0, '', false, '', 0); return;
    }
    const t1 = Math.min(this._drawing.point1.time, this._drawing.point2.time);
    const t2 = Math.max(this._drawing.point1.time, this._drawing.point2.time);
    let barCount = 0;
    for (const t of this._dataTimes) if (t >= t1 && t <= t2) barCount++;
    const diffSec = Math.abs(this._drawing.point2.time - this._drawing.point1.time);
    let timeDiff: string;
    if (diffSec < 3600) timeDiff = `${Math.round(diffSec / 60)}m`;
    else if (diffSec < 86400) timeDiff = `${(diffSec / 3600).toFixed(1)}h`;
    else timeDiff = `${(diffSec / 86400).toFixed(1)}d`;

    // The chart height is needed for the mid-Y handle position; lightweight-
    // charts doesn't expose a stable getter so we recompute from the price
    // scale's coordinate range using a known price (drawing's point1).
    const yMid = this._series!.priceToCoordinate(this._drawing.point1.price) as number | null;
    this._paneView.update(x1, x2, barCount, timeDiff,
      this.isActive, this._drawing.id, yMid ?? 0);
  }
}
