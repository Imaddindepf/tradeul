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
import type { FibonacciDrawing } from './types';
import { FIB_LEVELS } from './types';
import { timeToPixelX } from './coordinateUtils';
import { applyLineStyle, resetLineStyle, type LineStyle } from './canvasStyles';
import {
  ZONE_HIT_PADDING,
  bodyHit,
  firstHandleHit,
  inBox,
} from './hitTesting';

const LEVEL_COLORS: Record<number, string> = {
  0:     '#787b86',
  0.236: '#f59e0b',
  0.382: '#10b981',
  0.5:   '#3b82f6',
  0.618: '#ef4444',
  0.786: '#8b5cf6',
  1:     '#787b86',
};

function getLevelColor(level: number): string {
  return LEVEL_COLORS[level] || '#787b86';
}

class FibRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _x1: number,
    private _x2: number,
    private _levels: { level: number; y: number; price: number }[],
    private _baseColor: string,
    private _lineWidth: number,
    private _lineStyle: LineStyle,
    private _isSelected: boolean,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const left = Math.min(this._x1, this._x2);
      const right = Math.max(this._x1, this._x2);
      const width = right - left;
      if (width < 2) return;

      // Filled zones between levels
      for (let i = 0; i < this._levels.length - 1; i++) {
        const top = Math.min(this._levels[i].y, this._levels[i + 1].y);
        const bottom = Math.max(this._levels[i].y, this._levels[i + 1].y);
        const levelColor = getLevelColor(this._levels[i].level);
        ctx.fillStyle = levelColor;
        ctx.globalAlpha = 0.06;
        ctx.fillRect(left, top, width, bottom - top);
        ctx.globalAlpha = 1;
      }

      // Level lines + labels.
      // Boundary levels (0 and 1) always render with the user-selected line
      // style. Intermediate levels (.236, .382, .5, .618, .786) keep the
      // dashed-by-default look unless the user explicitly switched to dotted
      // — solid is treated as the override that solidifies everything.
      const baseStroke = this._isSelected ? this._lineWidth + 0.5 : this._lineWidth;
      for (const { level, y, price } of this._levels) {
        const color = getLevelColor(level);
        const isBoundary = level === 0 || level === 1;
        const style: LineStyle = isBoundary
          ? this._lineStyle
          : this._lineStyle === 'solid'
            ? 'dashed'
            : this._lineStyle;
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = baseStroke;
        applyLineStyle(ctx, style, baseStroke);
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();
        resetLineStyle(ctx);

        const pctLabel = (level * 100).toFixed(1) + '%';
        const priceLabel = price < 1 ? price.toFixed(4) : price.toFixed(2);
        const text = pctLabel + '  (' + priceLabel + ')';
        ctx.font = '10px sans-serif';
        ctx.fillStyle = color;
        ctx.textBaseline = 'bottom';
        ctx.fillText(text, left + 6, y - 3);
      }

      // Boundary lines when selected
      if (this._isSelected) {
        ctx.beginPath();
        ctx.strokeStyle = this._baseColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        const topY = this._levels[0]?.y ?? 0;
        const bottomY = this._levels[this._levels.length - 1]?.y ?? 0;
        ctx.moveTo(this._x1, topY);
        ctx.lineTo(this._x1, bottomY);
        ctx.moveTo(this._x2, topY);
        ctx.lineTo(this._x2, bottomY);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }
}

class FibPaneView implements IPrimitivePaneView {
  private _x1 = 0;
  private _x2 = 0;
  private _levels: { level: number; y: number; price: number }[] = [];
  private _baseColor = '#3b82f6';
  private _lineWidth = 1;
  private _lineStyle: LineStyle = 'solid';
  private _isSelected = false;
  private _id = '';

  update(
    x1: number, x2: number,
    levels: { level: number; y: number; price: number }[],
    baseColor: string, lineWidth: number, lineStyle: LineStyle,
    isSelected: boolean, id: string,
  ): void {
    this._x1 = x1; this._x2 = x2; this._levels = levels;
    this._baseColor = baseColor; this._lineWidth = lineWidth;
    this._lineStyle = lineStyle; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._levels.length < 2) return null;
    return new FibRenderer(
      this._x1, this._x2, this._levels, this._baseColor,
      this._lineWidth, this._lineStyle, this._isSelected,
    );
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if ((this._x1 === 0 && this._x2 === 0) || this._levels.length < 2) return null;
    const y1 = this._levels[0].y;
    const y2 = this._levels[this._levels.length - 1].y;
    const handle = firstHandleHit(x, y, this._id, [
      [this._x1, y1, ':p1'],
      [this._x2, y2, ':p2'],
    ]);
    if (handle) return handle;
    if (inBox(x, y, this._x1, y1, this._x2, y2, ZONE_HIT_PADDING)) return bodyHit(this._id);
    return null;
  }
}

export class FibonacciPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneView = new FibPaneView();

  private _drawing: FibonacciDrawing;
  private _isSelected = false;
  private _dataTimes: number[] = [];

  constructor(drawing: FibonacciDrawing) {
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

  updateDrawing(drawing: FibonacciDrawing, isSelected: boolean, isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing;
    this._isSelected = isSelected || !!isHovered;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;

    const ts = this._chart.timeScale();
    const x1 = timeToPixelX(this._drawing.point1.time, this._dataTimes, ts);
    const x2 = timeToPixelX(this._drawing.point2.time, this._dataTimes, ts);

    if (x1 === null || x2 === null) {
      this._paneView.update(0, 0, [], '', 1, 'solid', false, '');
      return;
    }

    const p1 = this._drawing.point1.price;
    const p2 = this._drawing.point2.price;
    const priceDiff = p2 - p1;
    const levels = this._drawing.levels || FIB_LEVELS;

    const computedLevels = levels.map(level => {
      const price = p1 + priceDiff * level;
      const y = this._series!.priceToCoordinate(price);
      return { level, y: (y as number) ?? 0, price };
    }).filter(l => l.y !== 0);

    this._paneView.update(
      x1, x2, computedLevels,
      this._drawing.color, this._drawing.lineWidth, this._drawing.lineStyle,
      this._isSelected, this._drawing.id,
    );
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this._paneView];
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    return this._paneView.hitTest(x, y);
  }
}
