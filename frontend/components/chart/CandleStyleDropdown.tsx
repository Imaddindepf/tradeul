'use client';

import { useEffect, useRef, useState } from 'react';
import { CandleStyleIcon, ChevronDownIcon } from './icons';
import { Tooltip } from './Tooltip';
import type { ChartCandleStyle } from '@/stores/useUserPreferencesStore';

const STYLES: { id: ChartCandleStyle; label: string; description: string }[] = [
    { id: 'candles', label: 'Candles', description: 'Standard OHLC candles' },
    { id: 'bars', label: 'Bars', description: 'OHLC bars (OHLC ticks)' },
    { id: 'heikin-ashi', label: 'Heikin-Ashi', description: 'Smoothed candles, slower signals' },
    { id: 'line', label: 'Line', description: 'Closes only — fastest read' },
    { id: 'area', label: 'Area', description: 'Filled close line' },
];

interface Props {
    value: ChartCandleStyle;
    onChange: (style: ChartCandleStyle) => void;
}

export function CandleStyleDropdown({ value, onChange }: Props) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', handler);
        document.addEventListener('keydown', esc);
        return () => {
            document.removeEventListener('mousedown', handler);
            document.removeEventListener('keydown', esc);
        };
    }, [open]);

    const select = (style: ChartCandleStyle) => {
        onChange(style);
        setOpen(false);
    };

    return (
        <div className="relative" ref={ref}>
            <Tooltip content="Tipo de gráfico" placement="bottom">
                <button
                    onClick={() => setOpen(prev => !prev)}
                    className="flex items-center gap-0.5 h-[22px] px-1.5 rounded-[3px] text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                >
                    <CandleStyleIcon className="w-[14px] h-[14px]" />
                    <ChevronDownIcon className="w-3 h-3" />
                </button>
            </Tooltip>
            {open && (
                <div className="absolute top-full left-0 mt-1 bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-md shadow-lg z-50 min-w-[200px] py-1">
                    {STYLES.map(s => {
                        const isActive = value === s.id;
                        return (
                            <button
                                key={s.id}
                                onClick={() => select(s.id)}
                                className={`w-full text-left px-3 py-1.5 text-[11px] hover:bg-[color:var(--color-surface-hover)] ${
                                    isActive
                                        ? 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] font-semibold'
                                        : 'text-[color:var(--color-fg)]/85'
                                }`}
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <span>{s.label}</span>
                                    {isActive && <span className="text-[9px]">✓</span>}
                                </div>
                                <div className="text-[9.5px] text-[color:var(--color-muted-fg)] mt-0.5">{s.description}</div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
