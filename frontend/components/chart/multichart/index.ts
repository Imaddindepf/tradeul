/**
 * Multi-chart layout system — public surface.
 *
 * The orchestration lives in `<ChartContent>` (top-level export from
 * `components/chart/ChartContent.tsx`). Everything in this folder is the
 * implementation detail backing that single component.
 */

export { ChartLayoutContainer } from './ChartLayoutContainer';
export { ChartWindowHeader } from './ChartWindowHeader';
export {
    useChartLayoutStore,
    selectWindow,
    selectSavedLayouts,
    selectDrawingsSyncMode,
} from './useChartLayoutStore';
export type { WindowLayoutState } from './useChartLayoutStore';
export type { LayoutId, SyncFlags, CellState, SavedLayout } from './types';
export {
    drawingsBus,
    shouldReactToDrawingsEvent,
    type DrawingsSyncMode,
    type DrawingsChangeEvent,
} from './drawingsSyncBus';
