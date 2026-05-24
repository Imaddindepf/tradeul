'use client';

import { useEffect, useRef, useState } from 'react';
import { useChartContext } from './ChartContext';
import { ChevronDownIcon, IndicatorsIcon, NewspaperIcon, EarningsBadgeIcon } from './icons';
import { Tooltip } from './Tooltip';

interface IndicatorOption {
    type: string;
    label: string;
}

const GROUPS: { title: string; items: IndicatorOption[] }[] = [
    {
        title: 'Overlays',
        items: [
            { type: 'sma', label: 'SMA' },
            { type: 'ema', label: 'EMA' },
            { type: 'bb', label: 'Bollinger Bands' },
            { type: 'keltner', label: 'Keltner Channels' },
            { type: 'vwap', label: 'VWAP' },
        ],
    },
    {
        title: 'Oscillators',
        items: [
            { type: 'rsi', label: 'RSI' },
            { type: 'macd', label: 'MACD' },
            { type: 'stoch', label: 'Stochastic' },
            { type: 'adx', label: 'ADX / DMI' },
        ],
    },
    {
        title: 'Volatility & Volume',
        items: [
            { type: 'atr', label: 'ATR' },
            { type: 'squeeze', label: 'TTM Squeeze' },
            { type: 'obv', label: 'OBV' },
            { type: 'rvol', label: 'RVOL' },
        ],
    },
];

export function ChartIndicatorMenu() {
    const ctx = useChartContext();
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

    return (
        <div className="relative" ref={ref}>
            <Tooltip content="Indicadores" placement="bottom">
                <button
                    onClick={() => setOpen(prev => !prev)}
                    className={`flex items-center gap-1 px-1.5 h-[22px] rounded-[3px] text-[12px] font-medium transition-colors ${
                        open || ctx.activeIndicatorCount > 0
                            ? 'text-[color:var(--color-primary)]'
                            : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                >
                    <IndicatorsIcon className="w-[14px] h-[14px]" />
                    <span>Indicadores</span>
                    {ctx.activeIndicatorCount > 0 && (
                        <span className="text-[8.5px] bg-[color:var(--color-primary)] text-white rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none font-bold">
                            {ctx.activeIndicatorCount}
                        </span>
                    )}
                    <ChevronDownIcon className="w-3 h-3" />
                </button>
            </Tooltip>
            {open && (
                <div className="absolute top-full left-0 mt-1 bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-md shadow-lg z-50 min-w-[220px] max-h-[440px] overflow-y-auto py-1">
                    {GROUPS.map(group => (
                        <div key={group.title}>
                            <GroupHeader title={group.title} />
                            {group.items.map(item => (
                                <button
                                    key={item.type}
                                    onClick={() => { ctx.addIndicator(item.type); setOpen(false); }}
                                    className="w-full text-left px-3 py-1.5 text-[11px] hover:bg-[color:var(--color-surface-hover)] text-[color:var(--color-fg)]/85"
                                >
                                    {item.label}
                                </button>
                            ))}
                        </div>
                    ))}
                    <GroupHeader title="Markers" />
                    <ToggleRow
                        icon={null}
                        label="Volume"
                        active={ctx.showVolume}
                        onClick={() => ctx.setShowVolume(!ctx.showVolume)}
                    />
                    <ToggleRow
                        icon={<NewspaperIcon className="w-3.5 h-3.5" />}
                        label="News markers"
                        active={ctx.showNewsMarkers}
                        onClick={() => ctx.setShowNewsMarkers(!ctx.showNewsMarkers)}
                    />
                    <ToggleRow
                        icon={<EarningsBadgeIcon className="w-3.5 h-3.5" />}
                        label="Earnings"
                        active={ctx.showEarningsMarkers}
                        onClick={() => ctx.setShowEarningsMarkers(!ctx.showEarningsMarkers)}
                    />
                </div>
            )}
        </div>
    );
}

function GroupHeader({ title }: { title: string }) {
    return (
        <div className="px-3 py-1 text-[9px] font-semibold text-[color:var(--color-muted-fg)] uppercase tracking-wider bg-[color:var(--color-surface-hover)] border-y border-[color:var(--color-border-subtle)]">
            {title}
        </div>
    );
}

function ToggleRow({
    icon, label, active, onClick,
}: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-[color:var(--color-surface-hover)] ${
                active ? 'text-[color:var(--color-primary)] font-semibold' : 'text-[color:var(--color-fg)]/85'
            }`}
        >
            {icon && <span className="flex-shrink-0">{icon}</span>}
            <span className="flex-1 text-left">{label}</span>
            {active && <span className="text-[9px]">✓</span>}
        </button>
    );
}
