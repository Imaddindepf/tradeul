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
import { useTranslation } from 'react-i18next';
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

/**
 * Texto bilingüe: nombres OFICIALES de TradingView en ambos idiomas (los ES
 * salen de los bundles de traducción de la CL; los EN son los nativos de
 * tradingview.com). La barra muestra el idioma de la app (react-i18next).
 */
interface Bi {
    en: string;
    es: string;
}
const bi = (en: string, es: string): Bi => ({ en, es });

interface ToolItem {
    tool: string;
    icon: string;
    label: Bi;
}
interface ToolSection {
    header?: Bi;
    items: ToolItem[];
}
interface ToolGroup {
    id: string;
    title: Bi;
    /** Herramienta por defecto (icono del botón hasta que se elige otra). */
    defaultItem: ToolItem;
    sections: ToolSection[];
}

const GROUPS: ToolGroup[] = [
    {
        id: 'cursors',
        title: bi('Cursors', 'Cursores'),
        defaultItem: { tool: 'cursor', icon: 'cursorCross', label: bi('Cross', 'Cruz') },
        sections: [
            {
                items: [
                    { tool: 'cursor', icon: 'cursorCross', label: bi('Cross', 'Cruz') },
                    { tool: 'dot', icon: 'cursorDot', label: bi('Dot', 'Punto') },
                    { tool: 'arrow_cursor', icon: 'cursorArrow', label: bi('Arrow', 'Flecha') },
                    { tool: 'eraser', icon: 'trash', label: bi('Eraser', 'Borrador') },
                ],
            },
        ],
    },
    {
        id: 'trend',
        title: bi('Trend line tools', 'Herramientas de tendencia'),
        defaultItem: { tool: 'trend_line', icon: 'trendLine', label: bi('Trend Line', 'Línea de tendencia') },
        sections: [
            {
                items: [
                    { tool: 'trend_line', icon: 'trendLine', label: bi('Trend Line', 'Línea de tendencia') },
                    { tool: 'ray', icon: 'ray', label: bi('Ray', 'Rayo') },
                    { tool: 'info_line', icon: 'infoLine', label: bi('Info Line', 'Línea de información') },
                    { tool: 'extended', icon: 'extended', label: bi('Extended Line', 'Línea extendida') },
                    { tool: 'trend_angle', icon: 'trendAngle', label: bi('Trend Angle', 'Ángulo de tendencia') },
                    { tool: 'horizontal_line', icon: 'horzLine', label: bi('Horizontal Line', 'Línea horizontal') },
                    { tool: 'horizontal_ray', icon: 'horzRay', label: bi('Horizontal Ray', 'Rayo horizontal') },
                    { tool: 'vertical_line', icon: 'vertLine', label: bi('Vertical Line', 'Línea vertical') },
                    { tool: 'cross_line', icon: 'crossLine', label: bi('Cross Line', 'Cruce de líneas') },
                ],
            },
            {
                header: bi('CHANNELS', 'CANALES'),
                items: [
                    { tool: 'parallel_channel', icon: 'parallelChannel', label: bi('Parallel Channel', 'Canal paralelo') },
                    { tool: 'regression_trend', icon: 'regressionTrend', label: bi('Regression Trend', 'Tendencia de regresión') },
                    { tool: 'flat_bottom', icon: 'flatBottom', label: bi('Flat Top/Bottom', 'Plano superior/inferior') },
                    { tool: 'disjoint_angle', icon: 'disjointAngle', label: bi('Disjoint Channel', 'Canal desconectado') },
                ],
            },
            {
                header: bi('PITCHFORKS', 'TRIDENTES'),
                items: [
                    { tool: 'pitchfork', icon: 'pitchfork', label: bi('Pitchfork', 'Herramienta tridente') },
                    { tool: 'schiff_pitchfork', icon: 'schiffPitchfork', label: bi('Schiff Pitchfork', 'Tridente de Schiff') },
                    { tool: 'schiff_pitchfork_modified', icon: 'schiffPitchfork2', label: bi('Modified Schiff Pitchfork', 'Tridente de Schiff modificado') },
                    { tool: 'inside_pitchfork', icon: 'insidePitchfork', label: bi('Inside Pitchfork', 'Tridente interno') },
                ],
            },
        ],
    },
    {
        id: 'fib',
        title: bi('Fibonacci and Gann', 'Fibonacci y Gann'),
        defaultItem: { tool: 'fib_retracement', icon: 'fibRetracement', label: bi('Fib Retracement', 'Retroceso de Fibonacci') },
        sections: [
            {
                header: bi('FIBONACCI', 'FIBONACCI'),
                items: [
                    { tool: 'fib_retracement', icon: 'fibRetracement', label: bi('Fib Retracement', 'Retroceso de Fibonacci') },
                    { tool: 'fib_trend_ext', icon: 'fibTrendExt', label: bi('Trend-Based Fib Extension', 'Extensión de Fibonacci en función de las tendencias') },
                    { tool: 'fib_channel', icon: 'fibChannel', label: bi('Fib Channel', 'Canal de Fibonacci') },
                    { tool: 'fib_timezone', icon: 'fibTimezone', label: bi('Fib Time Zone', 'Zona horaria de Fibonacci') },
                    { tool: 'fib_speed_resist_fan', icon: 'fibSpeedFan', label: bi('Fib Speed Resistance Fan', 'Abanico de Fibonacci de resistencia de velocidad') },
                    { tool: 'fib_trend_time', icon: 'fibTrendTime', label: bi('Trend-Based Fib Time', 'Proyección temporal de Fibonacci') },
                    { tool: 'fib_circles', icon: 'fibCircles', label: bi('Fib Circles', 'Círculos de Fibonacci') },
                    { tool: 'fib_spiral', icon: 'fibSpiral', label: bi('Fib Spiral', 'Espiral de Fibonacci') },
                    { tool: 'fib_speed_resist_arcs', icon: 'fibArcs', label: bi('Fib Speed Resistance Arcs', 'Arcos de Fibonacci de resistencia de velocidad') },
                    { tool: 'fib_wedge', icon: 'fibWedge', label: bi('Fib Wedge', 'Cuña de Fibonacci') },
                    { tool: 'pitchfan', icon: 'pitchfan', label: bi('Pitchfan', 'Herramienta abanico') },
                ],
            },
            {
                header: bi('GANN', 'GANN'),
                items: [
                    { tool: 'gannbox', icon: 'gannbox', label: bi('Gann Box', 'Cuadrícula de Gann') },
                    { tool: 'gannbox_fixed', icon: 'gannSquareFixed', label: bi('Gann Square Fixed', 'Cuadrado de Gann fijo') },
                    { tool: 'gannbox_square', icon: 'gannSquare', label: bi('Gann Square', 'Cuadrado de Gann') },
                    { tool: 'gannbox_fan', icon: 'gannFan', label: bi('Gann Fan', 'Abanico de Gann') },
                ],
            },
        ],
    },
    {
        id: 'patterns',
        title: bi('Patterns', 'Patrones'),
        defaultItem: { tool: 'xabcd_pattern', icon: 'xabcd', label: bi('XABCD Pattern', 'Patrón XABCD') },
        sections: [
            {
                header: bi('PATTERNS', 'PATRONES'),
                items: [
                    { tool: 'xabcd_pattern', icon: 'xabcd', label: bi('XABCD Pattern', 'Patrón XABCD') },
                    { tool: 'cypher_pattern', icon: 'cypher', label: bi('Cypher Pattern', 'Patrón Cypher') },
                    { tool: 'abcd_pattern', icon: 'abcd', label: bi('ABCD Pattern', 'Patrón ABCD') },
                    { tool: 'triangle_pattern', icon: 'trianglePattern', label: bi('Triangle Pattern', 'Patrón de triángulo') },
                    { tool: '3divers_pattern', icon: 'threeDrivers', label: bi('Three Drives Pattern', 'Patrón Three Drives') },
                    { tool: 'head_and_shoulders', icon: 'headShoulders', label: bi('Head and Shoulders', 'Hombro cabeza hombro') },
                ],
            },
            {
                header: bi('ELLIOTT WAVES', 'ONDAS DE ELLIOTT'),
                items: [
                    { tool: 'elliott_impulse_wave', icon: 'elliottImpulse', label: bi('Elliott Impulse Wave (12345)', 'Onda de impulso de Elliott (12345)') },
                    { tool: 'elliott_correction', icon: 'elliottCorrection', label: bi('Elliott Correction Wave (ABC)', 'Corrección de Elliott (ABC)') },
                    { tool: 'elliott_triangle_wave', icon: 'elliottTriangle', label: bi('Elliott Triangle Wave (ABCDE)', 'Triángulo de Elliott (ABCDE)') },
                    { tool: 'elliott_double_combo', icon: 'elliottDouble', label: bi('Elliott Double Combo Wave (WXY)', 'Combo doble de Elliott (WXY)') },
                    { tool: 'elliott_triple_combo', icon: 'elliottTriple', label: bi('Elliott Triple Combo Wave (WXYXZ)', 'Combo triple de Elliott (WXYXZ)') },
                ],
            },
            {
                header: bi('CYCLES', 'CICLOS'),
                items: [
                    { tool: 'cyclic_lines', icon: 'cyclicLines', label: bi('Cyclic Lines', 'Líneas cíclicas') },
                    { tool: 'time_cycles', icon: 'timeCycles', label: bi('Time Cycles', 'Ciclos temporales') },
                    { tool: 'sine_line', icon: 'sineLine', label: bi('Sine Line', 'Línea sinusoidal') },
                ],
            },
        ],
    },
    {
        id: 'forecast',
        title: bi('Prediction and measurement tools', 'Previsión y medición'),
        defaultItem: { tool: 'long_position', icon: 'longPosition', label: bi('Long Position', 'Posición larga') },
        sections: [
            {
                header: bi('PROJECTION', 'PREVISIÓN'),
                items: [
                    { tool: 'long_position', icon: 'longPosition', label: bi('Long Position', 'Posición larga') },
                    { tool: 'short_position', icon: 'shortPosition', label: bi('Short Position', 'Posición corta') },
                    { tool: 'forecast', icon: 'forecast', label: bi('Forecast', 'Previsión de la posición') },
                    { tool: 'bars_pattern', icon: 'barsPattern', label: bi('Bars Pattern', 'Patrón de barras') },
                    { tool: 'ghost_feed', icon: 'ghostFeed', label: bi('Ghost Feed', 'Ghost feed') },
                    { tool: 'projection', icon: 'sector', label: bi('Projection', 'Sector') },
                ],
            },
            {
                header: bi('VOLUME-BASED', 'EN FUNCIÓN DEL VOLUMEN'),
                items: [
                    { tool: 'anchored_vwap', icon: 'anchoredVwap', label: bi('Anchored VWAP', 'VWAP anclado') },
                    { tool: 'fixed_range_volume_profile', icon: 'fixedRangeVP', label: bi('Fixed Range Volume Profile', 'Perfil de volumen de rango fijo') },
                ],
            },
            {
                header: bi('MEASURER', 'MEDIDORES'),
                items: [
                    { tool: 'price_range', icon: 'priceRange', label: bi('Price Range', 'Rango de precios') },
                    { tool: 'date_range', icon: 'dateRange', label: bi('Date Range', 'Rango de fechas') },
                    { tool: 'date_and_price_range', icon: 'datePriceRange', label: bi('Date and Price Range', 'Rango de fecha y precio') },
                ],
            },
        ],
    },
    {
        id: 'shapes',
        title: bi('Geometric shapes', 'Figuras y pinceles'),
        defaultItem: { tool: 'brush', icon: 'brush', label: bi('Brush', 'Pincel') },
        sections: [
            {
                header: bi('BRUSHES', 'PINCELES'),
                items: [
                    { tool: 'brush', icon: 'brush', label: bi('Brush', 'Pincel') },
                    { tool: 'highlighter', icon: 'highlighter', label: bi('Highlighter', 'Resaltador') },
                ],
            },
            {
                header: bi('ARROWS', 'FLECHAS'),
                items: [
                    { tool: 'arrow_marker', icon: 'arrowMarker', label: bi('Arrow Marker', 'Marcador de flecha') },
                    { tool: 'arrow', icon: 'arrow', label: bi('Arrow', 'Flecha') },
                    { tool: 'arrow_up', icon: 'arrowUp', label: bi('Arrow Mark Up', 'Marca de flecha hacia arriba') },
                    { tool: 'arrow_down', icon: 'arrowDown', label: bi('Arrow Mark Down', 'Marca de flecha hacia abajo') },
                ],
            },
            {
                header: bi('SHAPES', 'FIGURAS'),
                items: [
                    { tool: 'rectangle', icon: 'rectangle', label: bi('Rectangle', 'Rectángulo') },
                    { tool: 'rotated_rectangle', icon: 'rotatedRectangle', label: bi('Rotated Rectangle', 'Rectángulo rotado') },
                    { tool: 'path', icon: 'path', label: bi('Path', 'Ruta') },
                    { tool: 'circle', icon: 'circle', label: bi('Circle', 'Círculo') },
                    { tool: 'ellipse', icon: 'ellipse', label: bi('Ellipse', 'Elipse') },
                    { tool: 'polyline', icon: 'polyline', label: bi('Polyline', 'Polilínea') },
                    { tool: 'triangle', icon: 'triangle', label: bi('Triangle', 'Triángulo') },
                    { tool: 'arc', icon: 'arc', label: bi('Arc', 'Arco') },
                    { tool: 'curve', icon: 'curve', label: bi('Curve', 'Curva') },
                    { tool: 'double_curve', icon: 'doubleCurve', label: bi('Double Curve', 'Doble curva') },
                ],
            },
        ],
    },
    {
        id: 'text',
        title: bi('Annotation tools', 'Texto y notas'),
        defaultItem: { tool: 'text', icon: 'text', label: bi('Text', 'Texto') },
        sections: [
            {
                header: bi('TEXT & NOTES', 'TEXTO Y NOTAS'),
                items: [
                    { tool: 'text', icon: 'text', label: bi('Text', 'Texto') },
                    { tool: 'note', icon: 'note', label: bi('Note', 'Nota') },
                    { tool: 'price_note', icon: 'priceNote', label: bi('Price Note', 'Nota de precio') },
                    { tool: 'table', icon: 'table', label: bi('Table', 'Tabla') },
                    { tool: 'callout', icon: 'callout', label: bi('Callout', 'Leyenda') },
                    { tool: 'comment', icon: 'comment', label: bi('Comment', 'Comentarios') },
                    { tool: 'price_label', icon: 'priceLabel', label: bi('Price Label', 'Etiqueta de precio') },
                    { tool: 'signpost', icon: 'signpost', label: bi('Signpost', 'Señal') },
                    { tool: 'flag', icon: 'flag', label: bi('Flag Mark', 'Marca con bandera') },
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
    // Idioma de la app → labels EN o ES (nombres oficiales de TV en ambos).
    const { i18n } = useTranslation();
    const lang: keyof Bi = i18n.language?.toLowerCase().startsWith('es') ? 'es' : 'en';
    const L = (b: Bi) => b[lang];

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
                            title={L(current.label)}
                            aria-label={L(current.label)}
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
                            title={L(group.title)}
                            aria-label={`${L(group.title)} — ${lang === 'es' ? 'abrir panel' : 'open panel'}`}
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
                                <div className="px-3 pb-1 pt-1.5 text-[13px] font-semibold">{L(group.title)}</div>
                                {group.sections.map((section, si) => (
                                    <div key={si}>
                                        {section.header && <SectionHeader>{L(section.header)}</SectionHeader>}
                                        {si > 0 && !section.header && (
                                            <div className="my-1 h-px w-full" style={{ background: 'var(--color-border, rgba(128,128,128,0.2))' }} />
                                        )}
                                        {section.items.map((item) => (
                                            <FlyoutItem
                                                key={item.tool}
                                                icon={item.icon}
                                                label={L(item.label)}
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
                title={L(bi('Measure', 'Medir'))}
                aria-label={L(bi('Measure', 'Medir'))}
                onClick={() => {
                    setSelectedTool('measure');
                    forEachCell((api) => api.selectTool('measure'));
                }}
                className={btnClass(selectedTool === 'measure')}
            >
                <Icon name="ruler" />
            </button>
            <button
                title={L(bi('Zoom In', 'Acercar'))}
                aria-label={L(bi('Zoom In', 'Acercar'))}
                onClick={() => {
                    setSelectedTool('zoom');
                    forEachCell((api) => api.selectTool('zoom'));
                }}
                className={btnClass(selectedTool === 'zoom')}
            >
                <Icon name="zoomIn" />
            </button>
            <button
                title={L(bi('Zoom Out', 'Alejar'))}
                aria-label={L(bi('Zoom Out', 'Alejar'))}
                onClick={() => getActiveCell()?.zoomOut()}
                className={btnClass(false)}
            >
                <Icon name="zoomOut" />
            </button>

            <div className="my-1 h-px w-6 shrink-0" style={{ background: 'var(--color-border, rgba(128,128,128,0.3))' }} />

            {/* Imán: mini-menú débil/fuerte */}
            <button
                ref={(el) => { buttonRefs.current.magnet = el; }}
                title={L(bi('Magnet', 'Imán'))}
                aria-label={L(bi('Magnet', 'Imán'))}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpenFlyout((v) => (v === 'magnet' ? null : 'magnet'))}
                className={btnClass(magnetMode !== 'off')}
            >
                <Icon name={magnetMode === 'strong' ? 'magnetStrong' : 'magnet'} />
            </button>
            {openFlyout === 'magnet' && buttonRefs.current.magnet && (
                <Flyout anchor={buttonRefs.current.magnet} onClose={() => setOpenFlyout(null)} width={220}>
                    <FlyoutItem icon="magnet" label={L(bi('Weak Magnet', 'Imán débil'))} selected={magnetMode === 'weak'}
                        onClick={() => applyMagnet(magnetMode === 'weak' ? 'off' : 'weak')} />
                    <FlyoutItem icon="magnetStrong" label={L(bi('Strong Magnet', 'Imán fuerte'))} selected={magnetMode === 'strong'}
                        onClick={() => applyMagnet(magnetMode === 'strong' ? 'off' : 'strong')} />
                </Flyout>
            )}

            {/* Permanecer en modo dibujo (directo) */}
            <button
                title={L(bi('Stay in Drawing Mode', 'Permanecer en modo dibujo'))}
                aria-label={L(bi('Stay in Drawing Mode', 'Permanecer en modo dibujo'))}
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
                title={L(bi('Lock All Drawings', 'Bloquear todos los dibujos'))}
                aria-label={L(bi('Lock All Drawings', 'Bloquear todos los dibujos'))}
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
                title={L(bi('Hide', 'Ocultar'))}
                aria-label={L(bi('Hide', 'Ocultar'))}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpenFlyout((v) => (v === 'eye' ? null : 'eye'))}
                className={btnClass(hiddenState !== 'none')}
            >
                <Icon name={hiddenState === 'none' ? 'eye' : 'eyeOff'} />
            </button>
            {openFlyout === 'eye' && buttonRefs.current.eye && (
                <Flyout anchor={buttonRefs.current.eye} onClose={() => setOpenFlyout(null)} width={230}>
                    <FlyoutItem icon="eyeOff" label={L(bi('Hide Drawings', 'Ocultar dibujos'))} selected={hiddenState === 'drawings'}
                        onClick={() => applyHide('drawings')} />
                    <FlyoutItem icon="eyeOff" label={L(bi('Hide Indicators', 'Ocultar indicadores'))} selected={hiddenState === 'indicators'}
                        onClick={() => applyHide('indicators')} />
                    <FlyoutItem icon="eyeOff" label={L(bi('Hide All', 'Ocultar todo'))} selected={hiddenState === 'all'}
                        onClick={() => applyHide('all')} />
                </Flyout>
            )}

            {/* Globo: sincronizar dibujos nuevos entre celdas del layout */}
            <button
                ref={(el) => { buttonRefs.current.globe = el; }}
                title={L(bi('Sync Drawings', 'Sincronizar dibujos'))}
                aria-label={L(bi('Sync Drawings', 'Sincronizar dibujos'))}
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
                        label={L(bi('New drawings are synced across the layout', 'Los nuevos dibujos se sincronizan en el diseño'))}
                        selected={drawingsSync === 'layout'}
                        onClick={() => {
                            onDrawingsSyncChange(drawingsSync === 'layout' ? 'off' : 'layout');
                            setOpenFlyout(null);
                        }}
                    />
                    <FlyoutItem
                        icon="globe"
                        label={L(bi('New drawings are synced globally', 'Los nuevos dibujos se sincronizan a nivel global'))}
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
                title={L(bi('Remove Drawings & Indicators', 'Eliminar dibujos e indicadores'))}
                aria-label={L(bi('Remove Drawings & Indicators', 'Eliminar dibujos e indicadores'))}
                onClick={() => getActiveCell()?.exec('paneRemoveAllStudiesDrawingTools')}
                className={btnClass(false)}
            >
                <Icon name="trash" />
            </button>
        </div>
    );
}
