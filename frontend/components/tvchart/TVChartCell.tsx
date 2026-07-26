'use client';

/**
 * TVChartCell — una celda del multichart TradingView: monta UNA instancia de
 * la Charting Library v31 conectada al pipeline de Tradeul.
 *
 * Las celdas son "headless" (sin header, sin barra de dibujo, sin toolbar
 * inferior propios): igual que en tradingview.com, la ventana tiene UNA sola
 * toolbar y una sola barra de dibujo (TVToolbar / TVDrawingBar) que gobiernan
 * la celda enfocada a través de la API imperativa de esta celda.
 */

import {
    forwardRef,
    useEffect,
    useImperativeHandle,
    useRef,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { TradeulDatafeed } from './datafeed';

// En dev el gateway no permite CORS desde el puerto 3002: pasar por el
// rewrite same-origin /tvproxy (ver next.config.mjs). En prod, directo.
const API_URL =
    process.env.NODE_ENV === 'development'
        ? '/tvproxy'
        : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const LIBRARY_PATH = '/charting_library/';
const SCRIPT_SRC = `${LIBRARY_PATH}charting_library.standalone.js`;

declare global {
    interface Window {
        TradingView?: any;
    }
}

/** Carga única del bundle standalone (compartida entre todas las celdas). */
let tvLibraryPromise: Promise<void> | null = null;
function loadTradingViewLibrary(): Promise<void> {
    if (typeof window === 'undefined') return Promise.resolve();
    if (window.TradingView?.widget) return Promise.resolve();
    if (tvLibraryPromise) return tvLibraryPromise;
    tvLibraryPromise = new Promise<void>((resolve, reject) => {
        const script = document.createElement('script');
        script.src = SCRIPT_SRC;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => {
            tvLibraryPromise = null;
            reject(new Error(`No se pudo cargar ${SCRIPT_SRC}`));
        };
        document.head.appendChild(script);
    });
    return tvLibraryPromise;
}

/** Tema del widget a partir del tema activo de la app (CSS var --color-bg). */
function detectTheme(): { theme: 'dark' | 'light'; background: string } {
    const fallback = { theme: 'dark' as const, background: '#0d1117' };
    if (typeof window === 'undefined') return fallback;
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim();
    const m = /^#?([0-9a-f]{6})$/i.exec(bg.replace('#', ''));
    if (!m) return fallback;
    const n = parseInt(m[1], 16);
    const luminance =
        (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
    return { theme: luminance < 0.5 ? 'dark' : 'light', background: `#${m[1]}` };
}

/** Snapshot de la celda que sube al contenedor en cada persistencia. */
export interface TVCellSnapshot {
    state: object;
    symbol?: string;
    interval?: string;
    chartType?: number;
}

/** API imperativa que la toolbar/barra de dibujo usan sobre la celda enfocada. */
export interface TVChartCellApi {
    setSymbol: (symbol: string) => void;
    setInterval: (resolution: string) => void;
    setChartType: (type: number) => void;
    /** Ejecuta una acción nativa de la CL (abre sus diálogos: indicadores…). */
    exec: (actionId: string) => void;
    /** Selecciona una herramienta de dibujo nativa. */
    selectTool: (tool: string) => void;
    /** Imán on/off (snap de dibujos a OHLC). */
    setMagnet: (on: boolean) => void;
    /** Modo del imán: débil o fuerte. */
    setMagnetMode: (mode: 'weak' | 'strong') => void;
    /** Bloquear todos los dibujos. */
    setLockAllDrawings: (on: boolean) => void;
    /** Ocultar todos los dibujos. */
    setHideAllDrawings: (on: boolean) => void;
    /** Ocultar todos los indicadores (best-effort sobre cada study). */
    setHideAllStudies: (on: boolean) => void;
    /** Alejar el zoom del chart. */
    zoomOut: () => void;
    /** Estado de los dibujos (v31) para sincronización entre celdas. */
    getDrawingsState: () => Promise<object | null>;
    applyDrawingsState: (state: object) => Promise<void>;
    undo: () => void;
    redo: () => void;
    /** Screenshot del chart → descarga PNG. */
    screenshot: () => void;
    /** Serializa el estado del chart (para guardado bajo demanda). */
    save: () => Promise<TVCellSnapshot | null>;
}

export interface TVChartCellProps {
    cellId: string;
    initialSymbol: string;
    /** interval TV ('5', '1D'…) con el que arranca la celda si no hay saved_data. */
    initialInterval?: string;
    /** JSON de widget.save() para restaurar el chart completo. */
    savedState?: object;
    /** El chart cambió (dibujos, estudios, símbolo, intervalo…): persistir. */
    onPersist: (cellId: string, snapshot: TVCellSnapshot) => void;
    /** El usuario cambió el símbolo dentro de la celda. */
    onSymbolChanged?: (cellId: string, symbol: string) => void;
    /** El usuario cambió el intervalo dentro de la celda. */
    onIntervalChanged?: (cellId: string, resolution: string) => void;
    /** La celda recibió foco (click) → celda activa del layout. */
    onActivate?: (cellId: string) => void;
    /** El usuario creó/movió/borró un dibujo (para sync entre celdas). */
    onDrawingEvent?: (cellId: string) => void;
    /** ESC pulsado dentro del iframe (flujo TV: volver a cursor / cerrar flyout). */
    onEscape?: (cellId: string) => void;
}

export const TVChartCell = forwardRef<TVChartCellApi, TVChartCellProps>(function TVChartCell(
    {
        cellId,
        initialSymbol,
        initialInterval = '5',
        savedState,
        onPersist,
        onSymbolChanged,
        onIntervalChanged,
        onActivate,
        onDrawingEvent,
        onEscape,
    },
    ref,
) {
    const containerRef = useRef<HTMLDivElement>(null);
    const widgetRef = useRef<any>(null);
    const readyRef = useRef(false);
    const datafeedRef = useRef<TradeulDatafeed | null>(null);
    /** true mientras el contenedor aplica un cambio de sync → no re-propagar. */
    const applyingSyncRef = useRef(false);
    /** true mientras se aplican dibujos sincronizados → no re-emitir evento. */
    const applyingDrawingsRef = useRef(false);

    const { i18n } = useTranslation();
    const { messages$, send, isConnected } = useWebSocket();

    const sendRef = useRef(send);
    sendRef.current = send;
    const messagesRef = useRef(messages$);
    messagesRef.current = messages$;

    // Callbacks vía refs: el widget se monta una sola vez.
    const onPersistRef = useRef(onPersist);
    onPersistRef.current = onPersist;
    const onSymbolChangedRef = useRef(onSymbolChanged);
    onSymbolChangedRef.current = onSymbolChanged;
    const onIntervalChangedRef = useRef(onIntervalChanged);
    onIntervalChangedRef.current = onIntervalChanged;
    const onActivateRef = useRef(onActivate);
    onActivateRef.current = onActivate;
    const onDrawingEventRef = useRef(onDrawingEvent);
    onDrawingEventRef.current = onDrawingEvent;
    const onEscapeRef = useRef(onEscape);
    onEscapeRef.current = onEscape;

    /** Lee símbolo/intervalo/tipo del chart activo (best-effort). */
    const readChartMeta = () => {
        const w = widgetRef.current;
        const meta: { symbol?: string; interval?: string; chartType?: number } = {};
        try {
            const chart = w.activeChart();
            meta.symbol = chart.symbol();
            meta.interval = chart.resolution();
            meta.chartType = chart.chartType();
        } catch { /* aún cargando */ }
        return meta;
    };

    const buildSnapshot = (): Promise<TVCellSnapshot | null> =>
        new Promise((resolve) => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return resolve(null);
            try {
                w.save((state: object) => resolve({ state, ...readChartMeta() }));
            } catch {
                resolve(null);
            }
        });

    useImperativeHandle(ref, (): TVChartCellApi => ({
        setSymbol: (symbol: string) => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                if (w.activeChart().symbol() === symbol) return;
                applyingSyncRef.current = true;
                w.activeChart().setSymbol(symbol, () => {
                    applyingSyncRef.current = false;
                });
            } catch {
                applyingSyncRef.current = false;
            }
        },
        setInterval: (resolution: string) => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                if (w.activeChart().resolution() === resolution) return;
                applyingSyncRef.current = true;
                w.activeChart().setResolution(resolution, () => {
                    applyingSyncRef.current = false;
                });
            } catch {
                applyingSyncRef.current = false;
            }
        },
        setChartType: (type: number) => {
            try {
                widgetRef.current?.activeChart().setChartType(type);
            } catch { /* no listo */ }
        },
        exec: (actionId: string) => {
            try {
                widgetRef.current?.activeChart().executeActionById(actionId);
            } catch { /* acción no disponible */ }
        },
        selectTool: (tool: string) => {
            try {
                widgetRef.current?.selectLineTool(tool);
            } catch { /* no listo */ }
        },
        setMagnet: (on: boolean) => {
            try {
                widgetRef.current?.magnetEnabled().setValue(on);
            } catch { /* no listo */ }
        },
        setMagnetMode: (mode: 'weak' | 'strong') => {
            try {
                // MagnetMode enum de la CL: 0 = débil, 1 = fuerte.
                widgetRef.current?.magnetMode().setValue(mode === 'strong' ? 1 : 0);
            } catch { /* no listo */ }
        },
        setLockAllDrawings: (on: boolean) => {
            try {
                widgetRef.current?.lockAllDrawingTools().setValue(on);
            } catch { /* no listo */ }
        },
        setHideAllDrawings: (on: boolean) => {
            try {
                widgetRef.current?.hideAllDrawingTools().setValue(on);
            } catch { /* no listo */ }
        },
        setHideAllStudies: (on: boolean) => {
            try {
                const chart = widgetRef.current?.activeChart();
                for (const study of chart?.getAllStudies() ?? []) {
                    try {
                        chart.getStudyById(study.id).setVisible(!on);
                    } catch { /* study sin API de visibilidad */ }
                }
            } catch { /* no listo */ }
        },
        zoomOut: () => {
            try {
                widgetRef.current?.activeChart().zoomOut();
            } catch { /* no listo */ }
        },
        getDrawingsState: async () => {
            try {
                return await widgetRef.current?.activeChart().getLineToolsState();
            } catch {
                return null;
            }
        },
        applyDrawingsState: async (state: object) => {
            try {
                applyingDrawingsRef.current = true;
                await widgetRef.current?.activeChart().applyLineToolsState(state);
            } catch { /* estado incompatible */ } finally {
                setTimeout(() => { applyingDrawingsRef.current = false; }, 400);
            }
        },
        undo: () => {
            try { widgetRef.current?.undo(); } catch { /* sin historial */ }
        },
        redo: () => {
            try { widgetRef.current?.redo(); } catch { /* sin historial */ }
        },
        screenshot: () => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                w.takeClientScreenshot().then((canvas: HTMLCanvasElement) => {
                    canvas.toBlob((blob) => {
                        if (!blob) return;
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        let symbol = 'chart';
                        try { symbol = w.activeChart().symbol(); } catch { /* default */ }
                        a.href = url;
                        a.download = `tradeul_${symbol}_${Date.now()}.png`;
                        a.click();
                        setTimeout(() => URL.revokeObjectURL(url), 5000);
                    });
                });
            } catch { /* screenshot no disponible */ }
        },
        save: buildSnapshot,
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }), []);

    useEffect(() => {
        let disposed = false;

        const persistNow = () => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                w.save((state: object) => {
                    onPersistRef.current(cellId, { state, ...readChartMeta() });
                });
            } catch { /* save no disponible */ }
        };

        loadTradingViewLibrary()
            .then(() => {
                if (disposed || !containerRef.current || !window.TradingView?.widget) return;

                const datafeed = new TradeulDatafeed({
                    apiUrl: API_URL,
                    ws: {
                        send: (msg) => sendRef.current(msg),
                        messages$: {
                            subscribe: (observer) => messagesRef.current.subscribe(observer),
                        },
                    },
                });
                datafeedRef.current = datafeed;

                const { theme, background } = detectTheme();

                const options: Record<string, unknown> = {
                    container: containerRef.current,
                    library_path: LIBRARY_PATH,
                    symbol: initialSymbol.toUpperCase(),
                    interval: initialInterval,
                    datafeed,
                    locale: i18n.language?.toLowerCase().startsWith('es') ? 'es' : 'en',
                    theme,
                    autosize: true,
                    timezone: 'America/New_York',
                    loading_screen: { backgroundColor: background },
                    overrides: {
                        'paneProperties.background': background,
                        'paneProperties.backgroundType': 'solid',
                    },
                    auto_save_delay: 1,
                    // Celda headless: la ventana aporta SU toolbar y SU barra de
                    // dibujo únicas (estilo tradingview.com multichart).
                    disabled_features: [
                        'header_widget',
                        'left_toolbar',
                        'timeframes_toolbar',
                        'header_saveload',
                        'use_localstorage_for_settings',
                        'save_chart_properties_to_local_storage',
                        'popup_hints',
                        // Dígito/letra los cableamos nosotros vía executeActionById
                        // (los hotkeys nativos van ligados al header, aquí headless);
                        // desactivar el de letra evita un posible diálogo doble.
                        'symbol_search_hot_key',
                        // Marca de agua / logo de TradingView.
                        'widget_logo',
                        'library_branding',
                    ],
                    enabled_features: [
                        'items_favoriting',
                        'library_custom_no_powered_branding',
                        // Horario extendido: sin esto el menú Session no filtra
                        // pre/postmarket aunque el símbolo declare subsessions.
                        'pre_post_market_sessions',
                    ],
                };
                if (savedState) options.saved_data = savedState;

                const widget = new window.TradingView.widget(options);
                widgetRef.current = widget;

                widget.onChartReady(() => {
                    if (disposed) return;
                    readyRef.current = true;

                    try {
                        widget.subscribe('onAutoSaveNeeded', persistNow);
                    } catch { /* sin autosave */ }

                    // Click/foco dentro del iframe → celda activa.
                    try {
                        widget.subscribe('mouse_down', () => onActivateRef.current?.(cellId));
                    } catch { /* opcional */ }

                    // Eventos de dibujo → sync entre celdas (si está activado).
                    try {
                        widget.subscribe('drawing_event', () => {
                            if (!applyingDrawingsRef.current) {
                                onDrawingEventRef.current?.(cellId);
                            }
                        });
                    } catch { /* opcional */ }

                    // Teclas dentro del iframe (flujo TV). Los hotkeys nativos de
                    // dígito/letra van ligados al header (aquí headless), así que
                    // abrimos los diálogos NATIVOS vía executeActionById — mismo
                    // diálogo que en tradingview.com, cero UI propia.
                    try {
                        const doc = containerRef.current?.querySelector('iframe')?.contentWindow?.document;
                        doc?.addEventListener('keydown', (e: KeyboardEvent) => {
                            const target = e.target as HTMLElement | null;
                            if (target?.closest?.('input, textarea, [contenteditable]')) return;
                            if (e.key === 'Escape') {
                                onEscapeRef.current?.(cellId);
                                return;
                            }
                            if (e.ctrlKey || e.metaKey || e.altKey) return;
                            if (/^[0-9]$/.test(e.key)) {
                                widget.activeChart().executeActionById('changeInterval');
                            } else if (/^[a-zA-Z]$/.test(e.key)) {
                                widget.activeChart().executeActionById('symbolSearch');
                            }
                        });
                    } catch { /* iframe inaccesible */ }

                    try {
                        widget
                            .activeChart()
                            .onSymbolChanged()
                            .subscribe(null, () => {
                                const symbol = widget.activeChart().symbol();
                                if (!applyingSyncRef.current) {
                                    onSymbolChangedRef.current?.(cellId, symbol);
                                }
                                persistNow();
                            });
                        widget
                            .activeChart()
                            .onIntervalChanged()
                            .subscribe(null, (resolution: string) => {
                                if (!applyingSyncRef.current) {
                                    onIntervalChangedRef.current?.(cellId, resolution);
                                }
                                persistNow();
                            });
                    } catch { /* API parcial */ }
                });
            })
            .catch((err) => {
                if (!disposed) console.error('[TVChartCell] error cargando la librería:', err);
            });

        return () => {
            disposed = true;
            // Guardado final best-effort antes de destruir el widget.
            persistNow();
            readyRef.current = false;
            try {
                widgetRef.current?.remove();
            } catch { /* iframe ya retirado */ }
            widgetRef.current = null;
            datafeedRef.current?.destroy();
            datafeedRef.current = null;
        };
        // Montaje único por celda: cambiar de layout recrea las celdas por key.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Tras una reconexión del WS compartido, reemitir las suscripciones.
    useEffect(() => {
        if (isConnected) datafeedRef.current?.resubscribeAll();
    }, [isConnected]);

    return (
        <div
            ref={containerRef}
            className="h-full w-full"
            onMouseDownCapture={() => onActivateRef.current?.(cellId)}
        />
    );
});
