'use client';

/**
 * TVToolbar — LA toolbar de la ventana TradingView (una sola para todo el
 * layout, como en tradingview.com), con los ICONOS OFICIALES de TradingView
 * extraídos de la librería. Actúa sobre la celda enfocada; los diálogos
 * nativos (símbolo, indicadores, ajustes…) se abren dentro de esa celda.
 */

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
// El gestor de diseños se inyecta desde el contenedor (prop designManager).
import { TVLayoutIcon } from './TVLayoutIcon';
import { TV_ICONS } from './tvIcons';
import { useTVPopover } from './tvPopovers';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useReplayClockStore } from '@/stores/useReplayClockStore';

export interface TVToolbarActions {
    exec: (actionId: string) => void;
    setInterval: (resolution: string) => void;
    setChartType: (type: number) => void;
    undo: () => void;
    redo: () => void;
    screenshot: () => void;
    /** Entra en modo "señalar vela" para arrancar una reproducción. */
    pickReplayBar: () => void;
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
    /** Gestor de diseños (nombre + Guardar/guardado + menú), estilo TV. */
    designManager?: ReactNode;
}

function Icon({ name, className }: { name: string; className?: string }) {
    return (
        <span
            className={`pointer-events-none [&>svg]:block ${className ?? ''}`}
            dangerouslySetInnerHTML={{ __html: TV_ICONS[name] ?? '' }}
        />
    );
}

/** Texto bilingüe (nombres oficiales TV): la toolbar sigue el idioma de la app. */
interface Bi {
    en: string;
    es: string;
}
const bi = (en: string, es: string): Bi => ({ en, es });

const INTERVALS: Array<{ res: string; label: Bi }> = [
    { res: '1', label: bi('1m', '1m') },
    { res: '2', label: bi('2m', '2m') },
    { res: '5', label: bi('5m', '5m') },
    { res: '15', label: bi('15m', '15m') },
    { res: '30', label: bi('30m', '30m') },
    { res: '60', label: bi('1h', '1h') },
    { res: '240', label: bi('4h', '4h') },
    { res: '720', label: bi('12h', '12h') },
    { res: '1D', label: bi('D', 'D') },
    { res: '1W', label: bi('W', 'S') },
    { res: '1M', label: bi('M', 'M') },
    { res: '3M', label: bi('3M', '3M') },
    { res: '12M', label: bi('12M', '12M') },
];

const CHART_TYPES: Array<{ type: number; label: Bi }> = [
    { type: 1, label: bi('Candles', 'Velas') },
    { type: 9, label: bi('Hollow candles', 'Velas huecas') },
    { type: 0, label: bi('Bars', 'Barras') },
    { type: 8, label: bi('Heikin Ashi', 'Heikin Ashi') },
    { type: 2, label: bi('Line', 'Línea') },
    { type: 3, label: bi('Area', 'Área') },
    { type: 10, label: bi('Baseline', 'Línea base') },
    { type: 13, label: bi('Columns', 'Columnas') },
];

function intervalLabel(res: string, lang: keyof Bi): string {
    const found = INTERVALS.find((i) => i.res === res);
    return found ? found.label[lang] : res;
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
function TbDropdown<T>({
    title,
    trigger,
    items,
    labelOf,
    onPick,
    isSelected,
}: {
    title: string;
    trigger: ReactNode;
    items: T[];
    labelOf: (item: T) => string;
    onPick: (item: T) => void;
    isSelected: (item: T) => boolean;
}) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    // Exclusividad + cierre por clic fuera (incl. iframes) + Escape.
    useTVPopover(open, () => setOpen(false), (t) => rootRef.current?.contains(t) ?? false);

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
                            key={labelOf(item)}
                            onClick={() => {
                                setOpen(false);
                                onPick(item);
                            }}
                            className={`block w-full px-3 py-1.5 text-left text-xs hover:bg-black/10 dark:hover:bg-white/10 ${
                                isSelected(item) ? 'font-bold' : ''
                            }`}
                        >
                            {labelOf(item)}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

/**
 * Botón de reproducción con su desplegable.
 *
 * El alcance (este gráfico / todos) sigue la convención de la barra: es lo que
 * el usuario espera encontrar ahí. La opción de Level 2 abre la ventana del
 * libro, que es quien pide el flujo; a partir de ahí gráfico, libro y cinta
 * comparten reloj y no hace falta sincronizarlos a mano.
 */
function ReplayControl({ symbol, lang, actions }: { symbol: string; lang: keyof Bi; actions: TVToolbarActions }) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    // Se reusa el camino del comando L2R: asi la ventana nace con el mismo
    // tamano, posicion y titulo que si se abriera desde el terminal, y el
    // restore del workspace la reconoce por su titulo.
    const { executeTickerCommand } = useCommandExecutor();
    const active = useReplayClockStore((s) => s.active);
    const request = useReplayClockStore((s) => s.request);
    const L = (b: Bi) => b[lang];

    useTVPopover(open, () => setOpen(false), (t) => rootRef.current?.contains(t) ?? false);

    // Como TradingView: pulsar el botón ENTRA en el modo selección — tijeras
    // sobre el gráfico, sin diálogos por medio y con el gráfico despejado.
    // La ventana del libro se abre DESPUÉS, cuando la vela ya está señalada:
    // abrirla antes tapaba justo la zona donde se iba a hacer clic.
    const pickingRef = useRef(false);
    const empezar = () => {
        setOpen(false);
        if (!symbol) return;
        pickingRef.current = true;
        actions.pickReplayBar();
    };

    // La vela señalada llega por el reloj compartido; solo el control que
    // inició la selección abre la ventana (con varios gráficos abiertos, cada
    // uno tiene su botón y no deben abrirla todos).
    useEffect(() => {
        if (!request || !pickingRef.current) return;
        pickingRef.current = false;
        executeTickerCommand(request.symbol, 'l2replay');
    }, [request, executeTickerCommand]);

    return (
        <div ref={rootRef} className="relative flex items-center">
            <button
                title={L(bi('Replay', 'Reproducción'))}
                onClick={empezar}
                disabled={!symbol}
                className={`flex h-8 items-center rounded px-1 text-sm hover:bg-black/10 dark:hover:bg-white/10 ${
                    active ? 'text-primary' : ''
                }`}
            >
                <Icon name="replay" />
            </button>
            <button
                title={L(bi('Replay options', 'Opciones de reproducción'))}
                onClick={() => setOpen((v) => !v)}
                className="flex h-8 items-center rounded px-0.5 text-sm hover:bg-black/10 dark:hover:bg-white/10"
            >
                <Caret />
            </button>
            {open && (
                <div
                    className="absolute left-0 top-9 z-50 rounded border py-1 shadow-lg"
                    style={{
                        background: 'var(--color-bg, #fff)',
                        borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
                        minWidth: 190,
                    }}
                >
                    <button
                        onClick={empezar}
                        disabled={!symbol}
                        className="block w-full px-3 py-1.5 text-left text-xs font-medium hover:bg-black/10 dark:hover:bg-white/10"
                    >
                        {L(bi('Replay with Level 2 — pick a bar', 'Reproducción con Level 2 — señala una vela'))}
                    </button>
                    <div
                        className="my-1 h-px"
                        style={{ background: 'var(--color-border, rgba(128,128,128,0.25))' }}
                    />
                    <div className="px-3 py-1 text-[10px] uppercase tracking-wider opacity-50">
                        {L(bi('Scope', 'Alcance'))}
                    </div>
                    {(['single', 'all'] as const).map((k) => (
                        <button
                            key={k}
                            disabled
                            title={L(bi('Available with Level 2 replay', 'Disponible con la reproducción con Level 2'))}
                            className="block w-full cursor-default px-3 py-1.5 text-left text-xs opacity-40"
                        >
                            {k === 'single'
                                ? L(bi('This chart', 'Este gráfico'))
                                : L(bi('All charts', 'Todos los gráficos'))}
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
    designManager,
}: TVToolbarProps) {
    const { i18n } = useTranslation();
    const lang: keyof Bi = i18n.language?.toLowerCase().startsWith('es') ? 'es' : 'en';
    const L = (b: Bi) => b[lang];
    return (
        <div
            className="flex shrink-0 items-center gap-0.5 border-b px-1.5"
            style={{
                height: 38,
                borderColor: 'var(--color-border, rgba(128,128,128,0.25))',
                background: 'var(--color-surface, transparent)',
            }}
        >
            {/* Símbolo de la celda enfocada → diálogo nativo de búsqueda */}
            <TbButton title={L(bi('Change Symbol', 'Cambiar símbolo'))} onClick={() => actions.exec('symbolSearch')}>
                <span className="px-0.5 font-semibold">{symbol || '—'}</span>
                <Caret />
            </TbButton>

            {/* Comparar / añadir símbolo */}
            <TbButton title={L(bi('Compare Symbol', 'Comparar símbolo'))} onClick={() => actions.exec('compareOrAdd')}>
                <Icon name="comparePlus" />
            </TbButton>

            {/* Reproducción. El desplegable elige el alcance; con Level 2 abre
                la ventana del libro, que es la que sirve el flujo y arrastra al
                gráfico y a la cinta por el reloj compartido. */}
            <ReplayControl symbol={symbol} lang={lang} actions={actions} />

            <Sep />

            {/* Intervalo (estilo TV: texto plano) */}
            <TbDropdown
                title={L(bi('Interval', 'Intervalo'))}
                trigger={<span>{intervalLabel(interval, lang)}</span>}
                items={INTERVALS}
                labelOf={(i) => L(i.label)}
                onPick={(i) => actions.setInterval(i.res)}
                isSelected={(i) => i.res === interval}
            />

            <Sep />

            {/* Tipo de gráfico (icono velas oficial) */}
            <TbDropdown
                title={L(bi('Chart Type', 'Tipo de gráfico'))}
                trigger={<Icon name="candles" />}
                items={CHART_TYPES}
                labelOf={(t) => L(t.label)}
                onPick={(t) => actions.setChartType(t.type)}
                isSelected={(t) => t.type === chartType}
            />

            <Sep />

            {/* Indicadores (icono oficial) */}
            <TbButton title={L(bi('Indicators', 'Indicadores'))} onClick={() => actions.exec('insertIndicator')}>
                <Icon name="indicators" />
                <span className="hidden text-sm md:inline">{L(bi('Indicators', 'Indicadores'))}</span>
            </TbButton>

            <Sep />

            {/* Undo / Redo (iconos oficiales) */}
            <TbButton title={L(bi('Undo', 'Deshacer'))} onClick={actions.undo}>
                <Icon name="undo" />
            </TbButton>
            <TbButton title={L(bi('Redo', 'Rehacer'))} onClick={actions.redo}>
                <Icon name="redo" />
            </TbButton>

            <div className="min-w-0 flex-1" />

            {/* Picker de layout (posición TV: antes de ajustes/cámara) */}
            <button
                ref={layoutButtonRef}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={onLayoutClick}
                title={L(bi('Select Layout', 'Seleccionar layout'))}
                aria-label={L(bi('Select Layout', 'Seleccionar layout'))}
                className="flex h-8 items-center gap-1 rounded px-1.5 hover:bg-black/10 dark:hover:bg-white/10"
            >
                <TVLayoutIcon layoutId={layoutId} size={20} />
                <Caret />
            </button>

            {designManager}

            <Sep />

            {/* Ajustes / captura (iconos oficiales) */}
            <TbButton title={L(bi('Chart Settings', 'Ajustes del gráfico'))} onClick={() => actions.exec('chartProperties')}>
                <Icon name="settings" />
            </TbButton>
            <TbButton title={L(bi('Chart Snapshot', 'Captura del gráfico'))} onClick={actions.screenshot}>
                <Icon name="camera" />
            </TbButton>
        </div>
    );
}
