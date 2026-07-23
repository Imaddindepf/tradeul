'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CandleStyleIcon, ChevronDownIcon } from './icons';
import { Tooltip } from './Tooltip';
import type { ChartCandleStyle } from '@/stores/useUserPreferencesStore';

interface Props {
    value: ChartCandleStyle;
    onChange: (style: ChartCandleStyle) => void;
}

export function CandleStyleDropdown({ value, onChange }: Props) {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    const styles = useMemo(() => [
        { id: 'candles' as const, label: t('chart.styles.candles'), description: t('chart.styles.candlesDesc') },
        { id: 'bars' as const, label: t('chart.styles.bars'), description: t('chart.styles.barsDesc') },
        { id: 'heikin-ashi' as const, label: t('chart.styles.heikinAshi'), description: t('chart.styles.heikinAshiDesc') },
        { id: 'line' as const, label: t('chart.styles.line'), description: t('chart.styles.lineDesc') },
        { id: 'area' as const, label: t('chart.styles.area'), description: t('chart.styles.areaDesc') },
    ], [t]);

    useEffect(() => {
        if (!open) return;
        // pointerdown en captura — cierre garantizado al clicar fuera (canvas incluido).
        const handler = (e: PointerEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('pointerdown', handler, true);
        document.addEventListener('keydown', esc);
        return () => {
            document.removeEventListener('pointerdown', handler, true);
            document.removeEventListener('keydown', esc);
        };
    }, [open]);

    const select = (style: ChartCandleStyle) => {
        onChange(style);
        setOpen(false);
    };

    return (
        <div className="relative" ref={ref}>
            <Tooltip content={t('chart.chartType')} placement="bottom">
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
                    {styles.map(s => {
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
