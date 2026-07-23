'use client';

import { useTranslation } from 'react-i18next';
import { useChartContext } from './ChartContext';
import { ChartTimeframeTabs } from './ChartTimeframeTabs';
import { CandleStyleDropdown } from './CandleStyleDropdown';
import { ChartIndicatorMenu } from './ChartIndicatorMenu';
import { ChartReplayBar } from './ChartReplayBar';
import { HeaderDivider } from './HeaderDivider';
import { HeaderLayoutControls } from './HeaderLayoutControls';
import { Tooltip } from './Tooltip';
import {
    UndoIcon, RedoIcon, MaximizeIcon, MinimizeIcon, SettingsIcon,
    AlertIcon, LockIcon, UnlockIcon, EyeIcon, EyeOffIcon,
    CompareIcon, CameraIcon,
} from './icons';

/**
 * Full chart header — TradingView-style layout with strict separation between
 * chart actions (this header) and drawing tools (left vertical sidebar).
 *
 * Layout (left → right):
 *   1. Compare / add symbol               (placeholder)
 *   2. Timeframes
 *   3. Chart type (candle / line / area / bars / heikin-ashi)
 *   4. Indicators
 *   5. Templates / saved layouts          (placeholder)
 *   6. Alerts                             (placeholder)
 *   7. Replay
 *   ───── spacer ─────
 *   8. Undo / Redo
 *   9. Lock / Visibility (drawings)
 *   10. Chart settings
 *   11. Screenshot
 *   12. Fullscreen
 *
 * Drawing tools intentionally NOT shown here — they live in `ChartToolbar`
 * (the left vertical sidebar) to avoid duplication and keep this header
 * focused on chart-wide actions.
 */
export function ChartHeader() {
    const ctx = useChartContext();
    const { t } = useTranslation();

    return (
        <div
            className="flex items-center gap-0.5 px-1 py-0.5 border-b border-[color:var(--color-border)] bg-[color:var(--color-surface)] text-[11px]"
            style={{ fontFamily: ctx.fontFamily }}
        >
            {/* 1. Compare / add symbol */}
            <Tooltip content={t('chart.compareTooltip')}>
                <button
                    disabled
                    className="flex items-center gap-1 px-1.5 h-[22px] rounded-[3px] text-[12px] text-[color:var(--color-muted-fg)]/60 cursor-not-allowed"
                    aria-label={t('chart.compare')}
                >
                    <CompareIcon className="w-[14px] h-[14px]" />
                    <span>{t('chart.compare')}</span>
                </button>
            </Tooltip>
            <HeaderDivider />

            {/* 2. Timeframes */}
            <ChartTimeframeTabs
                selectedInterval={ctx.selectedInterval}
                onSelect={ctx.handleIntervalChange}
            />
            <HeaderDivider />

            {/* 3. Chart type */}
            <CandleStyleDropdown
                value={ctx.candleStyle}
                onChange={ctx.setCandleStyle}
            />
            <HeaderDivider />

            {/* 4. Indicators */}
            <ChartIndicatorMenu />
            <HeaderDivider />

            {/* 5. Layout / Sync / Saved layouts (window-scoped, TV-style) */}
            <HeaderLayoutControls />

            {/* 6. Alerts */}
            <Tooltip content={t('chart.alertTooltip')}>
                <button
                    disabled
                    className="flex items-center gap-1 px-1.5 h-[22px] rounded-[3px] text-[12px] text-[color:var(--color-muted-fg)]/60 cursor-not-allowed"
                    aria-label={t('chart.alert')}
                >
                    <AlertIcon className="w-[14px] h-[14px]" />
                    <span>{t('chart.alert')}</span>
                </button>
            </Tooltip>

            {/* 7. Replay */}
            <ChartReplayBar />

            <div className="flex-1" />

            {/* 8. Undo / Redo */}
            <HeaderIconBtn
                tooltip={t('chart.undo')}
                shortcut="Ctrl+Z"
                disabled={!ctx.canUndo}
                onClick={ctx.undo}
                ariaLabel={t('chart.undo')}
            >
                <UndoIcon className="w-3.5 h-3.5" />
            </HeaderIconBtn>
            <HeaderIconBtn
                tooltip={t('chart.redo')}
                shortcut="Ctrl+Shift+Z"
                disabled={!ctx.canRedo}
                onClick={ctx.redo}
                ariaLabel={t('chart.redo')}
            >
                <RedoIcon className="w-3.5 h-3.5" />
            </HeaderIconBtn>
            <HeaderDivider />

            {/* 9. Lock / Visibility (drawings) */}
            <HeaderIconBtn
                tooltip={ctx.drawingsLocked ? t('chart.unlockDrawings') : t('chart.lockDrawings')}
                onClick={ctx.toggleDrawingsLocked}
                active={ctx.drawingsLocked}
                ariaLabel={t('chart.lockDrawings')}
            >
                {ctx.drawingsLocked
                    ? <LockIcon className="w-3.5 h-3.5" />
                    : <UnlockIcon className="w-3.5 h-3.5" />}
            </HeaderIconBtn>
            <HeaderIconBtn
                tooltip={ctx.drawingsVisible ? t('chart.hideDrawings') : t('chart.showDrawings')}
                onClick={ctx.toggleDrawingsVisibility}
                active={!ctx.drawingsVisible}
                ariaLabel={t('chart.hideDrawings')}
            >
                {ctx.drawingsVisible
                    ? <EyeIcon className="w-3.5 h-3.5" />
                    : <EyeOffIcon className="w-3.5 h-3.5" />}
            </HeaderIconBtn>
            <HeaderDivider />

            {/* 10. Chart settings */}
            <HeaderIconBtn
                tooltip={t('chart.settings')}
                onClick={ctx.openSettings}
                ariaLabel={t('chart.settings')}
            >
                <SettingsIcon className="w-3.5 h-3.5" />
            </HeaderIconBtn>

            {/* 11. Screenshot */}
            <HeaderIconBtn
                tooltip={t('chart.screenshot')}
                onClick={ctx.takeScreenshot}
                ariaLabel={t('chart.screenshot')}
            >
                <CameraIcon className="w-3.5 h-3.5" />
            </HeaderIconBtn>

            {/* 12. Fullscreen */}
            <HeaderIconBtn
                tooltip={ctx.isFullscreen ? t('chart.exitFullscreen') : t('chart.fullscreen')}
                onClick={ctx.toggleFullscreen}
                ariaLabel={t('chart.fullscreen')}
            >
                {ctx.isFullscreen
                    ? <MinimizeIcon className="w-3.5 h-3.5" />
                    : <MaximizeIcon className="w-3.5 h-3.5" />}
            </HeaderIconBtn>
        </div>
    );
}

// ─── Reusable icon button (right-side actions) ──────────────────────────────

interface HeaderIconBtnProps {
    tooltip: string;
    shortcut?: string;
    onClick?: () => void;
    disabled?: boolean;
    active?: boolean;
    ariaLabel?: string;
    children: React.ReactNode;
}

function HeaderIconBtn({
    tooltip, shortcut, onClick, disabled, active, ariaLabel, children,
}: HeaderIconBtnProps) {
    const cls = disabled
        ? 'text-[color:var(--color-muted-fg)]/40 cursor-not-allowed'
        : active
            ? 'text-[color:var(--color-warning)] bg-[color:var(--color-warning)]/10'
            : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]';
    return (
        <Tooltip content={tooltip} shortcut={shortcut}>
            <button
                onClick={onClick}
                disabled={disabled}
                aria-label={ariaLabel ?? tooltip}
                aria-pressed={active}
                className={`p-1 rounded-[3px] transition-colors ${cls}`}
            >
                {children}
            </button>
        </Tooltip>
    );
}
