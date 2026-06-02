'use client';

import { useEffect, useRef, useState } from 'react';
import { ChevronDownIcon } from './icons';
import { INTERVAL_GROUPS, type Interval } from './constants';
import { Tooltip } from './Tooltip';

/**
 * ChartTimeframeTabs — single compact trigger showing the current timeframe
 * followed by a chevron, exactly like TradingView's collapsed timeframe
 * control. Clicking opens a grouped popover (Minutes / Hours / Days+).
 *
 * Keeping it compact frees up horizontal space for the rest of the header
 * (indicators, layout, replay…). Power users still get every timeframe via
 * the dropdown, plus quick keyboard navigation.
 */

interface Props {
    selectedInterval: Interval;
    onSelect: (interval: Interval) => void;
}

const ALL_ITEMS = [
    ...INTERVAL_GROUPS.intraday,
    ...INTERVAL_GROUPS.hourly,
    ...INTERVAL_GROUPS.daily,
];

export function ChartTimeframeTabs({ selectedInterval, onSelect }: Props) {
    const [open, setOpen] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const onMouseDown = (e: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    const select = (interval: Interval) => {
        onSelect(interval);
        setOpen(false);
    };

    const currentLabel =
        ALL_ITEMS.find((i) => i.interval === selectedInterval)?.label ?? '—';

    return (
        <div className="relative" ref={wrapperRef}>
            <Tooltip content="Timeframe" placement="bottom">
                <button
                    onClick={() => setOpen((v) => !v)}
                    aria-haspopup="menu"
                    aria-expanded={open}
                    className={`flex items-center gap-0.5 px-2 h-[22px] rounded-[3px] text-[11px] font-semibold transition-colors ${
                        open
                            ? 'bg-[color:var(--color-primary)]/12 text-[color:var(--color-primary)]'
                            : 'text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                >
                    <span>{currentLabel}</span>
                    <ChevronDownIcon className="w-3 h-3 opacity-70" />
                </button>
            </Tooltip>

            {open && (
                <div
                    role="menu"
                    className="absolute top-full left-0 mt-1 bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-md shadow-xl z-50 min-w-[160px] py-1"
                    onMouseDown={(e) => e.stopPropagation()}
                >
                    <DropdownGroup
                        title="Minutos"
                        items={INTERVAL_GROUPS.intraday}
                        selected={selectedInterval}
                        onSelect={select}
                    />
                    <div className="my-0.5 border-t border-[color:var(--color-border-subtle)]" />
                    <DropdownGroup
                        title="Horas"
                        items={INTERVAL_GROUPS.hourly}
                        selected={selectedInterval}
                        onSelect={select}
                    />
                    <div className="my-0.5 border-t border-[color:var(--color-border-subtle)]" />
                    <DropdownGroup
                        title="Días"
                        items={INTERVAL_GROUPS.daily}
                        selected={selectedInterval}
                        onSelect={select}
                    />
                </div>
            )}
        </div>
    );
}

function DropdownGroup({
    title,
    items,
    selected,
    onSelect,
}: {
    title: string;
    items: { label: string; interval: Interval }[];
    selected: Interval;
    onSelect: (i: Interval) => void;
}) {
    return (
        <>
            <div className="px-3 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-[color:var(--color-muted-fg)]">
                {title}
            </div>
            {items.map(({ label, interval }) => {
                const isActive = selected === interval;
                return (
                    <button
                        key={interval}
                        role="menuitemradio"
                        aria-checked={isActive}
                        onClick={() => onSelect(interval)}
                        className={`w-full text-left px-3 py-1 text-[11px] hover:bg-[color:var(--color-surface-hover)] ${
                            isActive
                                ? 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] font-semibold'
                                : 'text-[color:var(--color-fg)]/85'
                        }`}
                    >
                        {label}
                    </button>
                );
            })}
        </>
    );
}
