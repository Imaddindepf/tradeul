import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  IPrimitivePaneView,
  PrimitiveHoveredItem,
  Time,
  IChartApiBase,
  ISeriesApi,
  SeriesType,
} from 'lightweight-charts';

/** Pane view contract shared by every drawing primitive. */
export interface DrawingPaneView extends IPrimitivePaneView {
  hitTest(x: number, y: number): PrimitiveHoveredItem | null;
}

/**
 * BaseDrawingPrimitive — shared shell for the 15 drawing primitives.
 *
 * Owns the attach/detach lifecycle, the drawing/selection/hover state and a
 * dirty-checked `updateDrawing`. The drawings→primitives sync effect calls
 * `updateDrawing` on EVERY drawing whenever hover or selection changes; the
 * dirty-check below makes the untouched primitives no-ops so a hover over one
 * line no longer triggers a repaint request per drawing on the chart.
 *
 * Subclasses implement `syncViews()` (project the drawing into pixel space and
 * push it into their pane view) and `paneView()` (expose that view).
 */
export abstract class BaseDrawingPrimitive<TDrawing> implements ISeriesPrimitive<Time> {
  protected _chart: IChartApiBase<Time> | null = null;
  protected _series: ISeriesApi<SeriesType, Time> | null = null;
  protected _requestUpdate: (() => void) | null = null;

  protected _drawing: TDrawing;
  protected _isSelected = false;
  protected _isHovered = false;
  protected _dataTimes: number[] = [];

  constructor(drawing: TDrawing) {
    this._drawing = drawing;
  }

  /** The subclass's pane view (created as a subclass field). */
  protected abstract paneView(): DrawingPaneView;

  /**
   * Project `_drawing` into pixel coordinates and update the pane view(s).
   * Called with `_chart`/`_series` guaranteed non-null.
   */
  protected abstract syncViews(): void;

  /** "Active" = selected OR hovered — the visual state most renderers use. */
  protected get isActive(): boolean {
    return this._isSelected || this._isHovered;
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

  updateDrawing(drawing: TDrawing, isSelected: boolean, isHovered?: boolean, dataTimes?: number[]): void {
    const hovered = !!isHovered;
    // Dirty-check: skip the view refresh + repaint request when nothing
    // relevant to this primitive changed.
    if (
      drawing === this._drawing &&
      isSelected === this._isSelected &&
      hovered === this._isHovered &&
      (dataTimes === undefined || dataTimes === this._dataTimes)
    ) {
      return;
    }
    this._drawing = drawing;
    this._isSelected = isSelected;
    this._isHovered = hovered;
    if (dataTimes) this._dataTimes = dataTimes;
    this.updateAllViews();
    this._requestUpdate?.();
  }

  updateAllViews(): void {
    if (!this._chart || !this._series) return;
    this.syncViews();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    this.updateAllViews();
    return [this.paneView()];
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    return this.paneView().hitTest(x, y);
  }
}
