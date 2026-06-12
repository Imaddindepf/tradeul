'use client';

import { useMemo } from 'react';
import { useChartContext } from './ChartContext';
import { useDisplayBar } from './hoveredBarStore';
import { ChevronDownIcon, ChevronRightIcon, SettingsIcon, TrashIcon } from './icons';
import { Tooltip } from './Tooltip';
import { computeIndicatorLiveLines } from './utils/indicatorValueAt';
import { formatPrice } from './formatters';

/**
 * Floating legend (top-left, under OHLC overlay) listing every active indicator
 * with its live value at the hovered (or last) bar — TradingView-style.
 *
 *  - Click an instance row to select it.
 *  - Double-click the name to open the settings dialog.
 *  - Buttons on hover: open settings / remove.
 *  - Header chevron collapses/expands the list.
 */
export function ChartIndicatorLegend() {
    const ctx = useChartContext();
    const {
        indicators,
        indicatorResults,
        legendExpanded,
        setLegendExpanded,
        selectedIndicator,
        setSelectedIndicator,
        openIndicatorSettings,
        removeIndicator,
    } = ctx;
    const { displayBar } = useDisplayBar();

    const visible = useMemo(() => indicators.filter(i => i.visible), [indicators]);
    const referenceTime = displayBar ? displayBar.time : null;
    const lines = useMemo(
        () => computeIndicatorLiveLines(visible, indicatorResults, referenceTime),
        [visible, indicatorResults, referenceTime],
    );

    if (visible.length === 0) return null;

    return (
        <div className="absolute top-9 left-2 z-10 pointer-events-none">
            <div className="flex flex-col gap-0.5">
                <button
                    onClick={() => setLegendExpanded(!legendExpanded)}
                    className="pointer-events-auto inline-flex items-center gap-1 text-[10px] font-semibold text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)]"
                    aria-expanded={legendExpanded}
                >
                    {legendExpanded
                        ? <ChevronDownIcon className="w-2.5 h-2.5" />
                        : <ChevronRightIcon className="w-2.5 h-2.5" />}
                    <span>{visible.length}</span>
                </button>
                {legendExpanded && (
                    <div className="flex flex-col gap-0.5 mt-0.5">
                        {lines.map(line => (
                            <LegendRow
                                key={line.id}
                                line={line}
                                selected={selectedIndicator === line.id}
                                onSelect={() => setSelectedIndicator(line.id)}
                                onSettings={(e) => openIndicatorSettings(line.id, e)}
                                onRemove={() => removeIndicator(line.id)}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function LegendRow({
    line, selected, onSelect, onSettings, onRemove,
}: {
    line: ReturnType<typeof computeIndicatorLiveLines>[number];
    selected: boolean;
    onSelect: () => void;
    onSettings: (e: React.MouseEvent) => void;
    onRemove: () => void;
}) {
    return (
        <div
            className={`pointer-events-auto group flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[11px] cursor-pointer ${
                selected
                    ? 'bg-[color:var(--color-primary)]/10 ring-1 ring-[color:var(--color-primary)]'
                    : 'hover:bg-[color:var(--color-surface-hover)]'
            }`}
            onClick={onSelect}
            onDoubleClick={onSettings as any}
        >
            <span
                className="inline-block w-3 h-[2px] rounded-sm flex-shrink-0"
                style={{ background: line.mainColor }}
            />
            <span className="font-semibold text-[color:var(--color-fg)] whitespace-nowrap">
                {line.label}
            </span>
            <span className="flex items-center gap-1 font-mono tabular-nums text-[color:var(--color-fg)]/85">
                {line.values.length === 0 ? (
                    <span className="text-[color:var(--color-muted-fg)]">—</span>
                ) : line.values.map((v, idx) => (
                    <span key={idx} className="flex items-center gap-0.5">
                        {v.name && <span className="text-[9.5px] text-[color:var(--color-muted-fg)]">{v.name}</span>}
                        <span style={{ color: v.color }}>
                            {v.value == null ? '—' : formatPrice(v.value)}
                        </span>
                    </span>
                ))}
            </span>
            <div className="ml-1 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <Tooltip content="Configurar" placement="top">
                    <button
                        onClick={(e) => { e.stopPropagation(); onSettings(e); }}
                        className="text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)]"
                        aria-label="Configurar indicador"
                    >
                        <SettingsIcon className="w-3 h-3" />
                    </button>
                </Tooltip>
                <Tooltip content="Eliminar" placement="top">
                    <button
                        onClick={(e) => { e.stopPropagation(); onRemove(); }}
                        className="text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-danger)]"
                        aria-label="Eliminar indicador"
                    >
                        <TrashIcon className="w-3 h-3" />
                    </button>
                </Tooltip>
            </div>
        </div>
    );
}
