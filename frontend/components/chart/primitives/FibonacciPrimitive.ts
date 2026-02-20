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

      // Level lines + labels
      for (const { level, y, price } of this._levels) {
        const color = getLevelColor(level);
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = this._isSelected ? 1.5 : 1;
        ctx.setLineDash(level === 0 || level === 1 ? [] : [4, 3]);
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();
        ctx.setLineDash([]);

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
  private _isSelected = false;
  private _id = '';

  update(
    x1: number, x2: number,
    levels: { level: number; y: number; price: number }[],
    baseColor: string, isSelected: boolean, id: string,
  ): void {
    this._x1 = x1; this._x2 = x2; this._levels = levels;
    this._baseColor = baseColor; this._isSelected = isSelected; this._id = id;
  }

  zOrder(): 'normal' { return 'normal'; }

  renderer(): IPrimitivePaneRenderer | null {
    if (this._levels.length < 2) return null;
    return new FibRenderer(this._x1, this._x2, this._levels, this._baseColor, this._isSelected);
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this._x1 === 0 && this._x2 === 0 || this._levels.length < 2) return null;
    const y1 = this._levels[0].y;
    const y2 = this._levels[this._levels.length - 1].y;
    // Check anchor points
    const distP1 = Math.hypot(x - this._x1, y - y1);
    if (distP1 < 12) {
      return { cursorStyle: 'crosshair', externalId: this._id + ':p1', zOrder: 'top' };
    }
    const distP2 = Math.hypot(x - this._x2, y - y2);
    if (distP2 < 12) {
      return { cursorStyle: 'crosshair', externalId: this._id + ':p2', zOrder: 'top' };
    }
    // Check if within the fibonacci zone
    const top = Math.min(y1, y2);
    const bot = Math.max(y1, y2);
    const left = Math.min(this._x1, this._x2);
    const right = Math.max(this._x1, this._x2);
    if (x >= left - 5 && x <= right + 5 && y >= top - 5 && y <= bot + 5) {
      return { cursorStyle: 'grab', externalId: this._id, zOrder: 'top' };
    }
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

  updateDrawing(drawing: FibonacciDrawing, isSelected: boolean, _isHovered?: boolean, dataTimes?: number[]): void {
    this._drawing = drawing;
    this._isSelected = isSelected;
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
      this._paneView.update(0, 0, [], '', false, '');
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
      this._drawing.color, this._isSelected, this._drawing.id,
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
