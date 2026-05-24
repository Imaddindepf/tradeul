'use client';

import { useChartContext } from './ChartContext';
import { Tooltip } from './Tooltip';
import {
    ReplayIcon,
    StepBackIcon,
    StepForwardIcon,
    PlayIcon,
    PauseIcon,
    CloseIcon,
} from './icons';

/**
 * Replay control surface — three states:
 *   1. idle      → "Replay" button entering selection mode
 *   2. selecting → instruction badge with cancel button
 *   3. paused/playing → playback transport with step / play / speed / exit
 */
export function ChartReplayBar() {
    const ctx = useChartContext();
    const { replayState } = ctx;

    if (replayState.mode === 'idle') {
        return (
            <Tooltip content="Bar Replay" shortcut="" placement="bottom">
                <button
                    onClick={ctx.enterSelectingMode}
                    className="flex items-center gap-1 px-1.5 h-[22px] rounded-[3px] text-[12px] text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                >
                    <ReplayIcon className="w-[14px] h-[14px]" />
                    <span>Replay</span>
                </button>
            </Tooltip>
        );
    }

    if (replayState.mode === 'selecting') {
        return (
            <div className="flex items-center gap-1 px-2 h-[22px] rounded-[3px] bg-[color:var(--color-primary)]/12 text-[color:var(--color-primary)] text-[11px] font-medium">
                <ReplayIcon className="w-[12px] h-[12px]" />
                <span>Click en el gráfico para elegir punto de inicio</span>
                <button
                    onClick={ctx.exitReplay}
                    className="ml-1 px-1 rounded hover:bg-[color:var(--color-primary)]/15"
                    aria-label="Cancelar replay"
                >
                    <CloseIcon className="w-3 h-3" />
                </button>
            </div>
        );
    }

    const bars = replayState.currentIndex - replayState.startIndex;
    const total = replayState.totalBars - replayState.startIndex;

    return (
        <div className="flex items-center gap-0.5 px-1 h-[22px] rounded-[3px] bg-[color:var(--color-surface-hover)] border border-[color:var(--color-border)]">
            <Tooltip content="Step back" shortcut="Shift+←">
                <button onClick={() => ctx.stepBackward()} className="p-0.5 rounded hover:bg-[color:var(--color-surface-inset)] text-[color:var(--color-fg)]/85">
                    <StepBackIcon className="w-[12px] h-[12px]" />
                </button>
            </Tooltip>
            <Tooltip content={replayState.mode === 'playing' ? 'Pause' : 'Play'} shortcut="Shift+↓">
                <button onClick={ctx.togglePlay} className="p-0.5 rounded hover:bg-[color:var(--color-surface-inset)] text-[color:var(--color-fg)]/85">
                    {replayState.mode === 'playing'
                        ? <PauseIcon className="w-[14px] h-[14px]" />
                        : <PlayIcon className="w-[14px] h-[14px]" />}
                </button>
            </Tooltip>
            <Tooltip content="Step forward" shortcut="Shift+→">
                <button onClick={() => ctx.stepForward()} className="p-0.5 rounded hover:bg-[color:var(--color-surface-inset)] text-[color:var(--color-fg)]/85">
                    <StepForwardIcon className="w-[12px] h-[12px]" />
                </button>
            </Tooltip>
            <Tooltip content="Cycle speed">
                <button
                    onClick={ctx.cycleSpeed}
                    className="px-1.5 py-0.5 rounded hover:bg-[color:var(--color-surface-inset)] text-[10px] font-bold tabular-nums text-[color:var(--color-fg)]/85 min-w-[32px]"
                >
                    {replayState.speed}x
                </button>
            </Tooltip>
            <span className="px-1 text-[10px] tabular-nums text-[color:var(--color-muted-fg)]">
                {bars}/{total}
            </span>
            <Tooltip content="Exit replay">
                <button
                    onClick={ctx.exitReplay}
                    className="p-0.5 rounded hover:bg-[color:var(--color-danger)]/12 text-[color:var(--color-danger)]"
                    aria-label="Salir del replay"
                >
                    <CloseIcon className="w-[12px] h-[12px]" />
                </button>
            </Tooltip>
        </div>
    );
}
