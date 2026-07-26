'use client';

/**
 * TVDrawingBar — LA barra de dibujo de la ventana (una para todo el layout),
 * réplica de tradingview.com: cada botón principal abre un flyout con las
 * variantes agrupadas (Tendencia/Canales/Tridentes, Fibonacci/Gann, …).
 * Iconos oficiales de TradingView (tvIcons). Actúa sobre la celda enfocada.
 *
 * Botones directos (sin flyout, como en TV): regla, zoom+/-, "permanecer en
 * modo dibujo" y "bloquear dibujos". Imán/ojo/globo llevan mini-menú.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Z_INDEX } from '@/lib/z-index';
import { getOverlayRoot } from '@/lib/overlayRoot';
import { TV_ICONS } from './tvIcons';
import { useTVPopover } from './tvPopovers';
import type { TVChartCellApi } from './TVChartCell';

/**
 * Modos de sincronización de dibujos nuevos, calcados de tradingview.com
 * (sharingMode de la CL): 'layout' = entre charts del MISMO símbolo dentro
 * del diseño actual; 'global' = asociados al símbolo A NIVEL DE USUARIO
 * (aparecen en cualquier diseño/layout que cargue ese símbolo, persistidos
 * en el backend por (usuario, símbolo)).
 */
export type DrawingsSyncMode = 'off' | 'layout' | 'global';

interface TVDrawingBarProps {
    /** API de la celda enfocada (null si aún no hay ninguna montada). */
    getActiveCell: () => TVChartCellApi | null;
    /**
     * TODAS las celdas montadas: el estado de la barra es GLOBAL del layout
     * (como en tradingview.com): herramienta armada, imán, candados y ojo se
     * aplican a todas las celdas, no solo a la enfocada.
     */
    getCells: () => TVChartCellApi[];
    /** API de una celda por id (para re-aplicar el estado al llegar a ready). */
    getCellById: (cellId: string) => TVChartCellApi | null;
    /** Última celda cuyo widget llegó a ready (contador para re-aplicar). */
    readyCell?: { id: string; seq: number };
    /** Sincronización de dibujos nuevos entre celdas del layout. */
    drawingsSync: DrawingsSyncMode;
    onDrawingsSyncChange: (mode: DrawingsSyncMode) => void;
    /**
     * Señal de Escape proveniente de los iframes de las celdas (contador).
     * ESC: si hay flyout abierto lo cierra; si no, vuelve al modo cursor.
     */
    escSignal?: number;
}

function Icon({ name }: { name: string }) {
    return (
        <span
            className="pointer-events-none [&>svg]:block"
            dangerouslySetInnerHTML={{ __html: TV_ICONS[name] ?? '' }}
        />
    );
}

interface ToolItem {
    tool: string;
    icon: string;
    label: string;
}
interface ToolSection {
    header?: string;
    items: ToolItem[];
}
interface ToolGroup {
    id: string;
    title: string;
    /** Herramienta por defecto (icono del botón hasta que se elige otra). */
    defaultItem: ToolItem;
    sections: ToolSection[];
}

const GROUPS: ToolGroup[] = [
    {
        id: 'cursors',
        title: 'Cursores',
        defaultItem: { tool: 'cursor', icon: 'cursorCross', label: 'Cruz' },
        sections: [
            {
                items: [
                    { tool: 'cursor', icon: 'cursorCross', label: 'Cruz' },
                    { tool: 'dot', icon: 'cursorDot', label: 'Punto' },
                    { tool: 'arrow_cursor', icon: 'cursorArrow', label: 'Flecha' },
                    { tool: 'eraser', icon: 'trash', label: 'Borrador' },
                ],
            },
        ],
    },
    {
        id: 'trend',
        title: 'Herramientas de tendencia',
        defaultItem: { tool: 'trend_line', icon: 'trendLine', label: 'Línea de tendencia' },
        sections: [
            {
                items: [
                    { tool: 'trend_line', icon: 'trendLine', label: 'Línea de tendencia' },
                    { tool: 'ray', icon: 'ray', label: 'Rayo' },
                    { tool: 'info_line', icon: 'infoLine', label: 'Línea de información' },
                    { tool: 'extended', icon: 'extended', label: 'Línea extendida' },
                    { tool: 'trend_angle', icon: 'trendAngle', label: 'Ángulo de tendencia' },
                    { tool: 'horizontal_line', icon: 'horzLine', label: 'Línea horizontal' },
                    { tool: 'horizontal_ray', icon: 'horzRay', label: 'Rayo horizontal' },
                    { tool: 'vertical_line', icon: 'vertLine', label: 'Línea vertical' },
                    { tool: 'cross_line', icon: 'crossLine', label: 'Cruce de líneas' },
                ],
            },
            {
                header: 'CANALES',
                items: [
                    { tool: 'parallel_channel', icon: 'parallelChannel', label: 'Canal paralelo' },
                    { tool: 'regression_trend', icon: 'regressionTrend', label: 'Tendencia de regresión' },
                    { tool: 'flat_bottom', icon: 'flatBottom', label: 'Plano superior/inferior' },
                    { tool: 'disjoint_angle', icon: 'disjointAngle', label: 'Canal desconectado' },
                ],
            },
            {
                header: 'TRIDENTES',
                items: [
                    { tool: 'pitchfork', icon: 'pitchfork', label: 'Herramienta tridente' },
                    { tool: 'schiff_pitchfork', icon: 'schiffPitchfork', label: 'Tridente de Schiff' },
                    { tool: 'schiff_pitchfork_modified', icon: 'schiffPitchfork2', label: 'Tridente de Schiff modificado' },
                    { tool: 'inside_pitchfork', icon: 'insidePitchfork', label: 'Tridente interno' },
                ],
            },
        ],
    },
    {
        id: 'fib',
        title: 'Fibonacci y Gann',
        defaultItem: { tool: 'fib_retracement', icon: 'fibRetracement', label: 'Retroceso de Fibonacci' },
        sections: [
            {
                header: 'FIBONACCI',
                items: [
                    { tool: 'fib_retracement', icon: 'fibRetracement', label: 'Retroceso de Fibonacci' },
                    { tool: 'fib_trend_ext', icon: 'fibTrendExt', label: 'Extensión de Fibonacci en función de las tendencias' },
                    { tool: 'fib_channel', icon: 'fibChannel', label: 'Canal de Fibonacci' },
                    { tool: 'fib_timezone', icon: 'fibTimezone', label: 'Zona horaria de Fibonacci' },
                    { tool: 'fib_speed_resist_fan', icon: 'fibSpeedFan', label: 'Abanico de Fibonacci de resistencia de velocidad' },
                    { tool: 'fib_trend_time', icon: 'fibTrendTime', label: 'Proyección temporal de Fibonacci' },
                    { tool: 'fib_circles', icon: 'fibCircles', label: 'Círculos de Fibonacci' },
                    { tool: 'fib_spiral', icon: 'fibSpiral', label: 'Espiral de Fibonacci' },
                    { tool: 'fib_speed_resist_arcs', icon: 'fibArcs', label: 'Arcos de Fibonacci de resistencia de velocidad' },
                    { tool: 'fib_wedge', icon: 'fibWedge', label: 'Cuña de Fibonacci' },
                    { tool: 'pitchfan', icon: 'pitchfan', label: 'Herramienta abanico' },
                ],
            },
            {
                header: 'GANN',
                items: [
                    { tool: 'gannbox', icon: 'gannbox', label: 'Cuadrícula de Gann' },
                    { tool: 'gannbox_fixed', icon: 'gannSquareFixed', label: 'Cuadrado de Gann fijo' },
                    { tool: 'gannbox_square', icon: 'gannSquare', label: 'Cuadrado de Gann' },
                    { tool: 'gannbox_fan', icon: 'gannFan', label: 'Abanico de Gann' },
                ],
            },
        ],
    },
    {
        id: 'patterns',
        title: 'Patrones',
        defaultItem: { tool: 'xabcd_pattern', icon: 'xabcd', label: 'Patrón XABCD' },
        sections: [
            {
                header: 'PATRONES',
                items: [
                    { tool: 'xabcd_pattern', icon: 'xabcd', label: 'Patrón XABCD' },
                    { tool: 'cypher_pattern', icon: 'cypher', label: 'Patrón Cypher' },
                    { tool: 'abcd_pattern', icon: 'abcd', label: 'Patrón ABCD' },
                    { tool: 'triangle_pattern', icon: 'trianglePattern', label: 'Patrón de triángulo' },
                    { tool: '3divers_pattern', icon: 'threeDrivers', label: 'Patrón Three Drives' },
                    { tool: 'head_and_shoulders', icon: 'headShoulders', label: 'Hombro cabeza hombro' },
                ],
            },
            {
                header: 'ONDAS DE ELLIOTT',
                items: [
                    { tool: 'elliott_impulse_wave', icon: 'elliottImpulse', label: 'Onda de impulso de Elliott (12345)' },
                    { tool: 'elliott_correction', icon: 'elliottCorrection', label: 'Corrección de Elliott (ABC)' },
                    { tool: 'elliott_triangle_wave', icon: 'elliottTriangle', label: 'Triángulo de Elliott (ABCDE)' },
                    { tool: 'elliott_double_combo', icon: 'elliottDouble', label: 'Combo doble de Elliott (WXY)' },
                    { tool: 'elliott_triple_combo', icon: 'elliottTriple', label: 'Combo triple de Elliott (WXYXZ)' },
                ],
            },
            {
                header: 'CICLOS',
                items: [
                    { tool: 'cyclic_lines', icon: 'cyclicLines', label: 'Líneas cíclicas' },
                    { tool: 'time_cycles', icon: 'timeCycles', label: 'Ciclos temporales' },
                    { tool: 'sine_line', icon: 'sineLine', label: 'Línea sinusoidal' },
                ],
            },
        ],
    },
    {
        id: 'forecast',
        title: 'Previsión y medición',
        defaultItem: { tool: 'long_position', icon: 'longPosition', label: 'Posición larga' },
        sections: [
            {
                header: 'PREVISIÓN',
                items: [
                    { tool: 'long_position', icon: 'longPosition', label: 'Posición larga' },
                    { tool: 'short_position', icon: 'shortPosition', label: 'Posición corta' },
                    { tool: 'forecast', icon: 'forecast', label: 'Previsión de la posición' },
                    { tool: 'bars_pattern', icon: 'barsPattern', label: 'Patrón de barras' },
                    { tool: 'ghost_feed', icon: 'ghostFeed', label: 'Ghost feed' },
                    { tool: 'projection', icon: 'sector', label: 'Sector' },
                ],
            },
            {
                header: 'EN FUNCIÓN DEL VOLUMEN',
                items: [
                    { tool: 'anchored_vwap', icon: 'anchoredVwap', label: 'VWAP anclado' },
                    { tool: 'fixed_range_volume_profile', icon: 'fixedRangeVP', label: 'Perfil de volumen de rango fijo' },
                ],
            },
            {
                header: 'MEDIDORES',
                items: [
                    { tool: 'price_range', icon: 'priceRange', label: 'Rango de precios' },
                    { tool: 'date_range', icon: 'dateRange', label: 'Rango de fechas' },
                    { tool: 'date_and_price_range', icon: 'datePriceRange', label: 'Rango de fecha y precio' },
                ],
            },
        ],
    },
    {
        id: 'shapes',
        title: 'Figuras y pinceles',
        defaultItem: { tool: 'brush', icon: 'brush', label: 'Pincel' },
        sections: [
            {
                header: 'PINCELES',
                items: [
                    { tool: 'brush', icon: 'brush', label: 'Pincel' },
                    { tool: 'highlighter', icon: 'highlighter', label: 'Resaltador' },
                ],
            },
            {
                header: 'FLECHAS',
                items: [
                    { tool: 'arrow_marker', icon: 'arrowMarker', label: 'Marcador de flecha' },
                    { tool: 'arrow', icon: 'arrow', label: 'Flecha' },
                    { tool: 'arrow_up', icon: 'arrowUp', label: 'Marca de flecha hacia arriba' },
                    { tool: 'arrow_down', icon: 'arrowDown', label: 'Marca de flecha hacia abajo' },
                ],
            },
            {
                header: 'FIGURAS',
                items: [
                    { tool: 'rectangle', icon: 'rectangle', label: 'Rectángulo' },
                    { tool: 'rotated_rectangle', icon: 'rotatedRectangle', label: 'Rectángulo rotado' },
                    { tool: 'path', icon: 'path', label: 'Ruta' },
                    { tool: 'circle', icon: 'circle', label: 'Círculo' },
                    { tool: 'ellipse', icon: 'ellipse', label: 'Elipse' },
                    { tool: 'polyline', icon: 'polyline', label: 'Polilínea' },
                    { tool: 'triangle', icon: 'triangle', label: 'Triángulo' },
                    { tool: 'arc', icon: 'arc', label: 'Arco' },
                    { tool: 'curve', icon: 'curve', label: 'Curva' },
                    { tool: 'double_curve', icon: 'doubleCurve', label: 'Doble curva' },
                ],
            },
        ],
    },
    {
        id: 'text',
        title: 'Texto y notas',
        defaultItem: { tool: 'text', icon: 'text', label: 'Texto' },
        sections: [
            {
                header: 'TEXTO Y NOTAS',
                items: [
                    { tool: 'text', icon: 'text', label: 'Texto' },
                    { tool: 'note', icon: 'note', label: 'Nota' },
                    { tool: 'price_note', icon: 'priceNote', label: 'Nota de precio' },
                    { tool: 'table', icon: 'table', label: 'Tabla' },
                    { tool: 'callout', icon: 'callout', label: 'Leyenda' },
                    { tool: 'comment', icon: 'comment', label: 'Comentarios' },
                    { tool: 'price_label', icon: 'priceLabel', label: 'Etiqueta de precio' },
                    { tool: 'signpost', icon: 'signpost', label: 'Señal' },
                    { tool: 'flag', icon: 'flag', label: 'Marca con bandera' },
                ],
            },
        ],
    },
];

/** Flyout genérico anclado a la derecha de un botón de la barra. */
function Flyout({
    anchor,
    onClose,
    children,
    width = 320,
}: {
    anchor: HTMLElement;
    onClose: () => void;
    children: ReactNode;
    width?: number;
}) {
    const ref = useRef<HTMLDivElement>(null);
    const [mounted, setMounted] = useState(false);
    useEffect(() => setMounted(true), []);

    // Exclusividad + cierre por clic fuera (incl. iframes). El ESC lo gestiona
    // el flujo de la barra (cerrar flyout / volver al cursor), no el hook.
    useTVPopover(
        true,
        onClose,
        (t) => (ref.current?.contains(t) ?? false) || anchor.contains(t),
        { escape: false },
    );

    if (!mounted) return null;
    const r = anchor.getBoundingClientRect();
    const maxH = Math.min(560, window.innerHeight - 24);
    const top = Math.max(8, Math.min(r.top, window.innerHeight - maxH - 8));
    return createPortal(
        <div
            ref={ref}
            className="overflow-y-auto rounded-lg border py-1.5 shadow-xl"
            style={{
                position: 'fixed',
                top,
                left: r.right + 6,
                width,
                maxHeight: maxH,
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                background: 'var(--color-bg, #fff)',
                borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
            }}
        >
            {children}
        </div>,
        getOverlayRoot(),
    );
}

function FlyoutItem({
    icon,
    label,
    selected,
    onClick,
}: {
    icon: string;
    label: string;
    selected?: boolean;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[13px] hover:bg-black/5 dark:hover:bg-white/10 ${
                selected ? 'bg-black/5 font-semibold dark:bg-white/10' : ''
            }`}
        >
            <Icon name={icon} />
            <span className="min-w-0 flex-1 truncate">{label}</span>
        </button>
    );
}

const SectionHeader = ({ children }: { children: ReactNode }) => (
    <div className="px-3 pb-1 pt-3 text-[11px] font-medium tracking-wide opacity-50">{children}</div>
);

export function TVDrawingBar({ getActiveCell, getCells, getCellById, readyCell, drawingsSync, onDrawingsSyncChange, escSignal = 0 }: TVDrawingBarProps) {
    /** Herramienta "actual" de cada grupo (el icono del botón la refleja). */
    const [groupTool, setGroupTool] = useState<Record<string, ToolItem>>({});
    const [selectedTool, setSelectedTool] = useState('cursor');
    const [openFlyout, setOpenFlyout] = useState<string | null>(null);
    const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});

    /** Aplicar una acción a TODAS las celdas (estado global del layout). */
    const forEachCell = (fn: (api: TVChartCellApi) => void) => {
        for (const api of getCells()) fn(api);
    };

    // ESC (flujo TV): con flyout abierto lo cierra; si no, vuelve al cursor.
    const escapeToNormal = () => {
        setOpenFlyout((open) => {
            if (open !== null) return null;
            setSelectedTool('cursor');
            forEachCell((api) => api.selectTool('cursor'));
            return null;
        });
    };
    const escapeRef = useRef(escapeToNormal);
    escapeRef.current = escapeToNormal;

    // ESC fuera de los iframes (el Flyout ya gestiona su propio ESC al cerrar,
    // por eso aquí solo actuamos si NO hay flyout abierto).
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') escapeRef.current();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    // ESC dentro de los iframes de las celdas (señal del contenedor).
    const prevEscRef = useRef(escSignal);
    useEffect(() => {
        if (escSignal !== prevEscRef.current) {
            prevEscRef.current = escSignal;
            escapeRef.current();
        }
    }, [escSignal]);

    const [magnetMode, setMagnetMode] = useState<'off' | 'weak' | 'strong'>('off');
    const [drawLockOn, setDrawLockOn] = useState(false);
    const [lockAllOn, setLockAllOn] = useState(false);
    const [hiddenState, setHiddenState] = useState<'none' | 'drawings' | 'indicators' | 'all'>('none');

    const pick = (item: ToolItem, groupId: string) => {
        setGroupTool((prev) => ({ ...prev, [groupId]: item }));
        setSelectedTool(item.tool);
        setOpenFlyout(null);
        // Como en TV: la herramienta queda armada en TODO el layout y se
        // dibuja en la celda sobre la que se haga clic.
        forEachCell((api) => api.selectTool(item.tool));
    };

    const btnClass = (active: boolean) =>
        `grid h-8 w-8 shrink-0 place-items-center rounded hover:bg-black/10 dark:hover:bg-white/10 ${
            active ? 'bg-black/10 dark:bg-white/15' : ''
        }`;

    const applyMagnet = (mode: 'off' | 'weak' | 'strong') => {
        setMagnetMode(mode);
        setOpenFlyout(null);
        forEachCell((api) => {
            api.setMagnet(mode !== 'off');
            if (mode !== 'off') api.setMagnetMode(mode);
        });
    };

    const applyHide = (what: 'drawings' | 'indicators' | 'all') => {
        setOpenFlyout(null);
        const next = hiddenState === what ? 'none' : what;
        setHiddenState(next);
        const on = next !== 'none';
        forEachCell((api) => {
            if (what === 'drawings' || what === 'all') api.setHideAllDrawings(on);
            if (what === 'indicators' || what === 'all') api.setHideAllStudies(on);
        });
    };

    // Celda nueva lista (cambio de layout, recreación por watchdog…): hereda
    // el estado GLOBAL de la barra — sin esto nacía con los defaults aunque
    // la barra marcase imán/candado/herramienta activos.
    const barStateRef = useRef({ selectedTool, magnetMode, drawLockOn, lockAllOn, hiddenState });
    barStateRef.current = { selectedTool, magnetMode, drawLockOn, lockAllOn, hiddenState };
    useEffect(() => {
        if (!readyCell?.id) return;
        const api = getCellById(readyCell.id);
        if (!api) return;
        const s = barStateRef.current;
        api.setMagnet(s.magnetMode !== 'off');
        if (s.magnetMode !== 'off') api.setMagnetMode(s.magnetMode);
        api.setLockAllDrawings(s.lockAllOn);
        api.setHideAllDrawings(s.hiddenState === 'drawings' || s.hiddenState === 'all');
        api.setHideAllStudies(s.hiddenState === 'indicators' || s.hiddenState === 'all');
        // La celda recién creada parte con drawLock OFF: un exec la alinea.
        if (s.drawLockOn) api.exec('stayInDrawingModeAction');
        if (s.selectedTool !== 'cursor') api.selectTool(s.selectedTool);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [readyCell?.seq]);

    return (
        <div
            className="flex shrink-0 flex-col items-center gap-px overflow-y-auto border-r py-1"
            style={{
                width: 44,
                borderColor: 'var(--color-border, rgba(128,128,128,0.25))',
                background: 'var(--color-bg, transparent)',
            }}
        >
            {/* Grupos con flyout */}
            {GROUPS.map((group) => {
                const current = groupTool[group.id] ?? group.defaultItem;
                const isActive = selectedTool === current.tool;
                return (
                    <div key={group.id} className="group relative shrink-0">
                        {/* Flujo TV: click selecciona el instrumento actual del
                            grupo; click sobre el ya seleccionado abre el panel. */}
                        <button
                            ref={(el) => {
                                buttonRefs.current[group.id] = el;
                            }}
                            title={current.label}
                            aria-label={current.label}
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={() => {
                                if (isActive) {
                                    setOpenFlyout((v) => (v === group.id ? null : group.id));
                                } else {
                                    setSelectedTool(current.tool);
                                    forEachCell((api) => api.selectTool(current.tool));
                                }
                            }}
                            className={btnClass(isActive || openFlyout === group.id)}
                        >
                            <Icon name={current.icon} />
                        </button>
                        {/* Flechita de abrir panel: solo visible al pasar por encima. */}
                        <button
                            title={group.title}
                            aria-label={`${group.title} — abrir panel`}
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                                e.stopPropagation();
                                setOpenFlyout((v) => (v === group.id ? null : group.id));
                            }}
                            className={`absolute right-0 top-1/2 hidden h-5 w-2.5 -translate-y-1/2 place-items-center rounded-sm group-hover:grid hover:bg-black/15 dark:hover:bg-white/20 ${
                                openFlyout === group.id ? 'grid' : ''
                            }`}
                        >
                            <svg width="6" height="8" viewBox="0 0 6 8" aria-hidden>
                                <path d="M1.5 1l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.2" />
                            </svg>
                        </button>
                        {openFlyout === group.id && buttonRefs.current[group.id] && (
                            <Flyout anchor={buttonRefs.current[group.id]!} onClose={() => setOpenFlyout(null)}>
                                <div className="px-3 pb-1 pt-1.5 text-[13px] font-semibold">{group.title}</div>
                                {group.sections.map((section, si) => (
                                    <div key={si}>
                                        {section.header && <SectionHeader>{section.header}</SectionHeader>}
                                        {si > 0 && !section.header && (
                                            <div className="my-1 h-px w-full" style={{ background: 'var(--color-border, rgba(128,128,128,0.2))' }} />
                                        )}
                                        {section.items.map((item) => (
                                            <FlyoutItem
                                                key={item.tool}
                                                icon={item.icon}
                                                label={item.label}
                                                selected={selectedTool === item.tool}
                                                onClick={() => pick(item, group.id)}
                                            />
                                        ))}
                                    </div>
                                ))}
                            </Flyout>
                        )}
                    </div>
                );
            })}

            {/* Emoji: abre el picker nativo de la CL al seleccionar la herramienta */}
            <button
                title="Emoji"
                aria-label="Emoji"
                onClick={() => {
                    setSelectedTool('emoji');
                    forEachCell((api) => api.selectTool('emoji'));
                }}
                className={btnClass(selectedTool === 'emoji')}
            >
                <Icon name="heart" />
            </button>

            <div className="my-1 h-px w-6 shrink-0" style={{ background: 'var(--color-border, rgba(128,128,128,0.3))' }} />

            {/* Directos: regla y zoom (como en TV, sin flyout) */}
            <button
                title="Medir"
                aria-label="Medir"
                onClick={() => {
                    setSelectedTool('measure');
                    forEachCell((api) => api.selectTool('measure'));
                }}
                className={btnClass(selectedTool === 'measure')}
            >
                <Icon name="ruler" />
            </button>
            <button
                title="Acercar"
                aria-label="Acercar"
                onClick={() => {
                    setSelectedTool('zoom');
                    forEachCell((api) => api.selectTool('zoom'));
                }}
                className={btnClass(selectedTool === 'zoom')}
            >
                <Icon name="zoomIn" />
            </button>
            <button
                title="Alejar"
                aria-label="Alejar"
                onClick={() => getActiveCell()?.zoomOut()}
                className={btnClass(false)}
            >
                <Icon name="zoomOut" />
            </button>

            <div className="my-1 h-px w-6 shrink-0" style={{ background: 'var(--color-border, rgba(128,128,128,0.3))' }} />

            {/* Imán: mini-menú débil/fuerte */}
            <button
                ref={(el) => { buttonRefs.current.magnet = el; }}
                title="Imán"
                aria-label="Imán"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpenFlyout((v) => (v === 'magnet' ? null : 'magnet'))}
                className={btnClass(magnetMode !== 'off')}
            >
                <Icon name={magnetMode === 'strong' ? 'magnetStrong' : 'magnet'} />
            </button>
            {openFlyout === 'magnet' && buttonRefs.current.magnet && (
                <Flyout anchor={buttonRefs.current.magnet} onClose={() => setOpenFlyout(null)} width={220}>
                    <FlyoutItem icon="magnet" label="Imán débil" selected={magnetMode === 'weak'}
                        onClick={() => applyMagnet(magnetMode === 'weak' ? 'off' : 'weak')} />
                    <FlyoutItem icon="magnetStrong" label="Imán fuerte" selected={magnetMode === 'strong'}
                        onClick={() => applyMagnet(magnetMode === 'strong' ? 'off' : 'strong')} />
                </Flyout>
            )}

            {/* Permanecer en modo dibujo (directo) */}
            <button
                title="Permanecer en modo dibujo"
                aria-label="Permanecer en modo dibujo"
                onClick={() => {
                    setDrawLockOn((v) => !v);
                    forEachCell((api) => api.exec('stayInDrawingModeAction'));
                }}
                className={btnClass(drawLockOn)}
            >
                <Icon name="drawLock" />
            </button>

            {/* Bloquear todos los dibujos (directo) */}
            <button
                title="Bloquear todos los dibujos"
                aria-label="Bloquear todos los dibujos"
                onClick={() => {
                    const next = !lockAllOn;
                    setLockAllOn(next);
                    forEachCell((api) => api.setLockAllDrawings(next));
                }}
                className={btnClass(lockAllOn)}
            >
                <Icon name={lockAllOn ? 'lockAll' : 'unlockAll'} />
            </button>

            {/* Ojo: ocultar dibujos/indicadores/todo */}
            <button
                ref={(el) => { buttonRefs.current.eye = el; }}
                title="Ocultar"
                aria-label="Ocultar"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpenFlyout((v) => (v === 'eye' ? null : 'eye'))}
                className={btnClass(hiddenState !== 'none')}
            >
                <Icon name={hiddenState === 'none' ? 'eye' : 'eyeOff'} />
            </button>
            {openFlyout === 'eye' && buttonRefs.current.eye && (
                <Flyout anchor={buttonRefs.current.eye} onClose={() => setOpenFlyout(null)} width={230}>
                    <FlyoutItem icon="eyeOff" label="Ocultar dibujos" selected={hiddenState === 'drawings'}
                        onClick={() => applyHide('drawings')} />
                    <FlyoutItem icon="eyeOff" label="Ocultar indicadores" selected={hiddenState === 'indicators'}
                        onClick={() => applyHide('indicators')} />
                    <FlyoutItem icon="eyeOff" label="Ocultar todo" selected={hiddenState === 'all'}
                        onClick={() => applyHide('all')} />
                </Flyout>
            )}

            {/* Globo: sincronizar dibujos nuevos entre celdas del layout */}
            <button
                ref={(el) => { buttonRefs.current.globe = el; }}
                title="Sincronizar dibujos"
                aria-label="Sincronizar dibujos"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpenFlyout((v) => (v === 'globe' ? null : 'globe'))}
                className={btnClass(drawingsSync !== 'off')}
            >
                {/* El botón muestra el icono del modo activo (flujo TV). */}
                <Icon name={drawingsSync === 'layout' ? 'linkSync' : 'globe'} />
            </button>
            {openFlyout === 'globe' && buttonRefs.current.globe && (
                <Flyout anchor={buttonRefs.current.globe} onClose={() => setOpenFlyout(null)} width={360}>
                    <FlyoutItem
                        icon="linkSync"
                        label="Los nuevos dibujos se sincronizan en el diseño"
                        selected={drawingsSync === 'layout'}
                        onClick={() => {
                            onDrawingsSyncChange(drawingsSync === 'layout' ? 'off' : 'layout');
                            setOpenFlyout(null);
                        }}
                    />
                    <FlyoutItem
                        icon="globe"
                        label="Los nuevos dibujos se sincronizan a nivel global"
                        selected={drawingsSync === 'global'}
                        onClick={() => {
                            onDrawingsSyncChange(drawingsSync === 'global' ? 'off' : 'global');
                            setOpenFlyout(null);
                        }}
                    />
                </Flyout>
            )}

            <div className="min-h-2 flex-1" />

            {/* Eliminar dibujos e indicadores del panel enfocado */}
            <button
                title="Eliminar dibujos e indicadores"
                aria-label="Eliminar dibujos e indicadores"
                onClick={() => getActiveCell()?.exec('paneRemoveAllStudiesDrawingTools')}
                className={btnClass(false)}
            >
                <Icon name="trash" />
            </button>
        </div>
    );
}
