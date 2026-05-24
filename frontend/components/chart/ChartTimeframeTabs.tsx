'use client';

import { useEffect, useRef, useState } from 'react';
import { ChevronDownIcon } from './icons';
import { INTERVAL_GROUPS, type Interval } from './constants';
import { Tooltip } from './Tooltip';

/**
 * ChartTimeframeTabs — replaces the cramped single-dropdown with always-visible
 * primary timeframes plus a dropdown for the long-horizon ones.
 *
 * "Primary" tabs are shown inline (5m, 15m, 1H, 4H, 1D, 1W); the rest live in
 * a dropdown grouped by Minutes / Hours / Days.
 */

const PRIMARY_INTERVALS: { label: string; interval: Interval }[] = [
    { label: '1m', interval: '1min' },
    { label: '5m', interval: '5min' },
    { label: '15m', interval: '15min' },
    { label: '1H', interval: '1hour' },
    { label: '4H', interval: '4hour' },
    { label: '1D', interval: '1day' },
    { label: '1W', interval: '1week' },
];

const PRIMARY_SET = new Set(PRIMARY_INTERVALS.map(p => p.interval));

interface Props {
    selectedInterval: Interval;
    onSelect: (interval: Interval) => void;
}

export function ChartTimeframeTabs({ selectedInterval, onSelect }: Props) {
    const [open, setOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', handler);
        document.addEventListener('keydown', esc);
        return () => {
            document.removeEventListener('mousedown', handler);
            document.removeEventListener('keydown', esc);
        };
    }, [open]);

    const select = (interval: Interval) => {
        onSelect(interval);
        setOpen(false);
    };

    const showsInPrimary = PRIMARY_SET.has(selectedInterval);
    // Find the label for the "more" dropdown trigger
    const allItems = [...INTERVAL_GROUPS.intraday, ...INTERVAL_GROUPS.hourly, ...INTERVAL_GROUPS.daily];
    const moreLabel = showsInPrimary
        ? '···'
        : allItems.find(i => i.interval === selectedInterval)?.label ?? '···';

    return (
        <div className="flex items-center gap-px">
            {PRIMARY_INTERVALS.map(({ label, interval }) => {
                const isActive = selectedInterval === interval;
                return (
                    <Tooltip key={interval} content={label} placement="bottom">
                        <button
                            onClick={() => select(interval)}
                            className={`px-2 h-[22px] rounded-[3px] text-[11px] font-semibold transition-colors ${
                                isActive
                                    ? 'bg-[color:var(--color-primary)]/12 text-[color:var(--color-primary)]'
                                    : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                            }`}
                        >
                            {label}
                        </button>
                    </Tooltip>
                );
            })}
            <div className="relative" ref={dropdownRef}>
                <Tooltip content="Más temporalidades" placement="bottom">
                    <button
                        onClick={() => setOpen(prev => !prev)}
                        className={`flex items-center gap-0.5 px-2 h-[22px] rounded-[3px] text-[11px] font-semibold transition-colors ${
                            !showsInPrimary
                                ? 'bg-[color:var(--color-primary)]/12 text-[color:var(--color-primary)]'
                                : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                        }`}
                    >
                        <span>{moreLabel}</span>
                        <ChevronDownIcon className="w-3 h-3" />
                    </button>
                </Tooltip>
                {open && (
                    <div className="absolute top-full left-0 mt-1 bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-md shadow-lg z-50 min-w-[160px] py-1">
                        <DropdownGroup
                            title="Minutes"
                            items={INTERVAL_GROUPS.intraday}
                            selected={selectedInterval}
                            onSelect={select}
                        />
                        <div className="my-0.5 border-t border-[color:var(--color-border-subtle)]" />
                        <DropdownGroup
                            title="Hours"
                            items={INTERVAL_GROUPS.hourly}
                            selected={selectedInterval}
                            onSelect={select}
                        />
                        <div className="my-0.5 border-t border-[color:var(--color-border-subtle)]" />
                        <DropdownGroup
                            title="Days+"
                            items={INTERVAL_GROUPS.daily}
                            selected={selectedInterval}
                            onSelect={select}
                        />
                    </div>
                )}
            </div>
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
