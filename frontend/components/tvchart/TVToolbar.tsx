'use client';

/**
 * TVToolbar — LA toolbar de la ventana TradingView (una sola para todo el
 * layout, como en tradingview.com), con los ICONOS OFICIALES de TradingView
 * extraídos de la librería. Actúa sobre la celda enfocada; los diálogos
 * nativos (símbolo, indicadores, ajustes…) se abren dentro de esa celda.
 */

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { TVLayoutIcon } from './TVLayoutIcon';
import { TV_ICONS } from './tvIcons';

export interface TVToolbarActions {
    exec: (actionId: string) => void;
    setInterval: (resolution: string) => void;
    setChartType: (type: number) => void;
    undo: () => void;
    redo: () => void;
    screenshot: () => void;
}

interface TVToolbarProps {
    /** Símbolo/intervalo/tipo de la celda enfocada (para pintar el estado). */
    symbol: string;
    interval: string;
    chartType: number;
    actions: TVToolbarActions;
    /** Botón del picker de layouts (anclaje del popover del contenedor). */
    layoutId: string;
    layoutButtonRef: RefObject<HTMLButtonElement>;
    onLayoutClick: () => void;
}

function Icon({ name, className }: { name: string; className?: string }) {
    return (
        <span
            className={`pointer-events-none [&>svg]:block ${className ?? ''}`}
            dangerouslySetInnerHTML={{ __html: TV_ICONS[name] ?? '' }}
        />
    );
}

const INTERVALS: Array<{ res: string; label: string }> = [
    { res: '1', label: '1m' },
    { res: '2', label: '2m' },
    { res: '5', label: '5m' },
    { res: '15', label: '15m' },
    { res: '30', label: '30m' },
    { res: '60', label: '1h' },
    { res: '240', label: '4h' },
    { res: '720', label: '12h' },
    { res: '1D', label: 'D' },
    { res: '1W', label: 'S' },
    { res: '1M', label: 'M' },
    { res: '3M', label: '3M' },
    { res: '12M', label: '12M' },
];

const CHART_TYPES: Array<{ type: number; label: string }> = [
    { type: 1, label: 'Velas' },
    { type: 9, label: 'Velas huecas' },
    { type: 0, label: 'Barras' },
    { type: 8, label: 'Heikin Ashi' },
    { type: 2, label: 'Línea' },
    { type: 3, label: 'Área' },
    { type: 10, label: 'Línea base' },
    { type: 13, label: 'Columnas' },
];

function intervalLabel(res: string): string {
    return INTERVALS.find((i) => i.res === res)?.label ?? res;
}

const Caret = () => (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden>
        <path d="M1 2.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
);

/** Botón compacto de la toolbar (altura TV: 32px dentro de barra de 38). */
function TbButton({
    title,
    onClick,
    children,
    innerRef,
}: {
    title: string;
    onClick: () => void;
    children: ReactNode;
    innerRef?: RefObject<HTMLButtonElement>;
}) {
    return (
        <button
            ref={innerRef}
            title={title}
            aria-label={title}
            onClick={onClick}
            className="flex h-8 items-center justify-center gap-0.5 rounded px-1 text-sm hover:bg-black/10 dark:hover:bg-white/10"
        >
            {children}
        </button>
    );
}

/** Dropdown minimalista anclado bajo su botón. */
function TbDropdown<T extends { label: string }>({
    title,
    trigger,
    items,
    onPick,
    isSelected,
}: {
    title: string;
    trigger: ReactNode;
    items: T[];
    onPick: (item: T) => void;
    isSelected: (item: T) => boolean;
}) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const close = (e: MouseEvent) => {
            if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
        };
        window.addEventListener('mousedown', close);
        return () => window.removeEventListener('mousedown', close);
    }, [open]);

    return (
        <div ref={rootRef} className="relative">
            <button
                title={title}
                onClick={() => setOpen((v) => !v)}
                className="flex h-8 items-center gap-0.5 rounded px-1.5 text-sm font-medium hover:bg-black/10 dark:hover:bg-white/10"
            >
                {trigger}
                <Caret />
            </button>
            {open && (
                <div
                    className="absolute left-0 top-9 z-50 max-h-72 overflow-y-auto rounded border py-1 shadow-lg"
                    style={{
                        background: 'var(--color-bg, #fff)',
                        borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
                        minWidth: 120,
                    }}
                >
                    {items.map((item) => (
                        <button
                            key={item.label}
                            onClick={() => {
                                setOpen(false);
                                onPick(item);
                            }}
                            className={`block w-full px-3 py-1.5 text-left text-xs hover:bg-black/10 dark:hover:bg-white/10 ${
                                isSelected(item) ? 'font-bold' : ''
                            }`}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

const Sep = () => (
    <div
        className="mx-1 h-5 w-px shrink-0"
        style={{ background: 'var(--color-border, rgba(128,128,128,0.3))' }}
    />
);

export function TVToolbar({
    symbol,
    interval,
    chartType,
    actions,
    layoutId,
    layoutButtonRef,
    onLayoutClick,
}: TVToolbarProps) {
    return (
        <div
            className="flex shrink-0 items-center gap-0.5 border-b px-1.5"
            style={{
                height: 38,
                borderColor: 'var(--color-border, rgba(128,128,128,0.25))',
                background: 'var(--color-bg, transparent)',
            }}
        >
            {/* Símbolo de la celda enfocada → diálogo nativo de búsqueda */}
            <TbButton title="Cambiar símbolo" onClick={() => actions.exec('symbolSearch')}>
                <span className="px-0.5 font-semibold">{symbol || '—'}</span>
                <Caret />
            </TbButton>

            {/* Comparar / añadir símbolo */}
            <TbButton title="Comparar símbolo" onClick={() => actions.exec('compareOrAdd')}>
                <Icon name="comparePlus" />
            </TbButton>

            <Sep />

            {/* Intervalo (estilo TV: texto plano) */}
            <TbDropdown
                title="Intervalo"
                trigger={<span>{intervalLabel(interval)}</span>}
                items={INTERVALS}
                onPick={(i) => actions.setInterval(i.res)}
                isSelected={(i) => i.res === interval}
            />

            <Sep />

            {/* Tipo de gráfico (icono velas oficial) */}
            <TbDropdown
                title="Tipo de gráfico"
                trigger={<Icon name="candles" />}
                items={CHART_TYPES}
                onPick={(t) => actions.setChartType(t.type)}
                isSelected={(t) => t.type === chartType}
            />

            <Sep />

            {/* Indicadores (icono oficial) */}
            <TbButton title="Indicadores" onClick={() => actions.exec('insertIndicator')}>
                <Icon name="indicators" />
                <span className="hidden text-sm md:inline">Indicadores</span>
            </TbButton>

            <Sep />

            {/* Undo / Redo (iconos oficiales) */}
            <TbButton title="Deshacer" onClick={actions.undo}>
                <Icon name="undo" />
            </TbButton>
            <TbButton title="Rehacer" onClick={actions.redo}>
                <Icon name="redo" />
            </TbButton>

            <div className="min-w-0 flex-1" />

            {/* Picker de layout (posición TV: antes de ajustes/cámara) */}
            <button
                ref={layoutButtonRef}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={onLayoutClick}
                title="Seleccionar layout"
                aria-label="Seleccionar layout"
                className="flex h-8 items-center gap-1 rounded px-1.5 hover:bg-black/10 dark:hover:bg-white/10"
            >
                <TVLayoutIcon layoutId={layoutId} size={20} />
                <Caret />
            </button>

            <Sep />

            {/* Ajustes / captura (iconos oficiales) */}
            <TbButton title="Ajustes del gráfico" onClick={() => actions.exec('chartProperties')}>
                <Icon name="settings" />
            </TbButton>
            <TbButton title="Captura del gráfico" onClick={actions.screenshot}>
                <Icon name="camera" />
            </TbButton>
        </div>
    );
}
