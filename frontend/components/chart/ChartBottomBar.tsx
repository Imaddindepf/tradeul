/**
 * ChartBottomBar — the row that closes the chart window's L-shape, under the
 * grid of cells. Mirrors TradingView's bottom toolbar.
 *
 *   ┌──────────────────────────────────────────────┐
 *   │  ChartHeader                                 │
 *   ├──────┬───────────────────────────────────────┤
 *   │ Tool │  ChartLayoutContainer                 │
 *   │ bar  │                                       │
 *   ├──────┴───────────────────────────────────────┤
 *   │  ChartBottomBar        ← this                │
 *   └──────────────────────────────────────────────┘
 *
 * TradingView's version carries, left → right: date-range tabs, "go to date",
 * a separator, timezone clock, session (RTH/ETH), a separator, and finally the
 * maximize-chart toggle pinned to the right edge. Only that last control is
 * wired here; the left half is deliberately an empty slot so the date ranges
 * can land later without moving anything that already works.
 *
 * Deliberately independent of `ChartContext`: the window renders this row in
 * both the "active cell published its ctx" and the skeleton branch, so making
 * it ctx-free keeps the row's height identical across the first-paint gap and
 * avoids a layout shift.
 */

'use client';

import { useTranslation } from 'react-i18next';
import { Tooltip } from './Tooltip';
import { MaximizeChartIcon, RestoreChartIcon } from './icons';

interface ChartBottomBarProps {
    /** Number of cells in the current layout. */
    cellCount: number;
    /** Whether a cell is currently maximized. */
    maximized: boolean;
    /** Toggle maximize on the active cell. */
    onToggleMaximize: () => void;
}

export function ChartBottomBar({
    cellCount,
    maximized,
    onToggleMaximize,
}: ChartBottomBarProps) {
    const { t } = useTranslation();

    /*
      TradingView gates this control on `chartCount > 1` — with a single chart
      there is nothing to maximize *into*, so the button is not rendered at all
      (verified: the node is absent from the DOM, and the internal
      `requestFullscreen` is a no-op behind the same condition). We match that
      rather than showing a disabled button, so a single-chart window keeps a
      clean, empty bar.
    */
    const canMaximize = cellCount > 1;

    return (
        <div className="flex items-center gap-0.5 px-1 py-0.5 border-t border-[color:var(--color-border)] bg-[color:var(--color-surface)] text-[11px]">
            {/* Left slot — date ranges / go-to-date land here later. */}

            <div className="flex-1" />

            {canMaximize && (
                <BottomIconBtn
                    tooltip={maximized ? t('chart.restoreChart') : t('chart.maximizeChart')}
                    onClick={onToggleMaximize}
                    active={maximized}
                >
                    {maximized
                        ? <RestoreChartIcon className="w-3.5 h-3.5" />
                        : <MaximizeChartIcon className="w-3.5 h-3.5" />}
                </BottomIconBtn>
            )}
        </div>
    );
}

// ─── Icon button — same visual contract as ChartHeader's HeaderIconBtn ───────

interface BottomIconBtnProps {
    tooltip: string;
    onClick?: () => void;
    active?: boolean;
    children: React.ReactNode;
}

function BottomIconBtn({ tooltip, onClick, active, children }: BottomIconBtnProps) {
    const cls = active
        ? 'text-[color:var(--color-warning)] bg-[color:var(--color-warning)]/10'
        : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]';
    return (
        <Tooltip content={tooltip}>
            <button
                onClick={onClick}
                aria-label={tooltip}
                aria-pressed={active}
                className={`p-1 rounded-[3px] transition-colors ${cls}`}
            >
                {children}
            </button>
        </Tooltip>
    );
}
