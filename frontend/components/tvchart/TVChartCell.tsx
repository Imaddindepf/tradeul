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
    useCallback,
    useEffect,
    useImperativeHandle,
    useRef,
    useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { TradeulDatafeed } from './datafeed';
import { drawTradeulLogoOnCanvas, injectTradeulLogo } from './TradeulLogo';
import { buildCustomIndicatorsGetter } from './tvCustomIndicators';
import { useReplayClockStore } from '@/stores/useReplayClockStore';

// En dev el gateway no permite CORS desde el puerto 3002: pasar por el
// rewrite same-origin /tvproxy (ver next.config.mjs). En prod, directo.
// Exportada: los diálogos de ventana (TVCommandDialogs) buscan contra el
// mismo API que el datafeed.
export const API_URL =
    process.env.NODE_ENV === 'development'
        ? '/tvproxy'
        : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const LIBRARY_PATH = '/charting_library/';
const SCRIPT_SRC = `${LIBRARY_PATH}charting_library.standalone.js`;

/** Reintentos automáticos de una celda antes de mostrar el error con botón. */
const MAX_CELL_ATTEMPTS = 3;
/** Segundos VISIBLES sin onChartReady antes de recrear la celda. */
const READY_TIMEOUT_SECS = 20;
/** Segundos visibles antes de chequear si el CSS del iframe murió (celda blanca). */
const CSS_CHECK_SECS = 4;

/** Etiqueta de la vela apuntada al elegir el arranque de una reproducción. */
/** Segundos que abarca una vela de esa resolución (para encuadrar al entrar). */
function resolutionSpanSecs(res: string): number {
    if (/^\d+S$/.test(res)) return parseInt(res, 10);
    if (res === '1D' || res === 'D') return 86400;
    if (res === '1W' || res === 'W') return 604800;
    if (/^\d+M$/.test(res)) return parseInt(res, 10) * 2592000;
    const n = parseInt(res, 10);
    return Number.isFinite(n) && n > 0 ? n * 60 : 300;
}

const pickLabelFmt = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'America/New_York',
    weekday: 'short', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', hour12: false,
});

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
    /**
     * Modo "elegir vela": el siguiente clic sobre el gráfico devuelve el
     * instante de esa vela. Es como se arranca una reproducción — señalando en
     * el gráfico, que es donde se ve el contexto y se decide dónde ir.
     * Devuelve una función para cancelar el modo.
     */
    pickBar: (onPick: (timeSec: number) => void) => () => void;
    /** Lista de estudios disponibles (nativos + custom) para el diálogo único. */
    listStudies: () => string[];
    /** Añade un indicador por nombre al chart de la celda. */
    addStudy: (name: string) => void;
    /** Estado de los dibujos (v31) para sincronización entre celdas. */
    getDrawingsState: () => Promise<object | null>;
    applyDrawingsState: (state: object) => Promise<void>;
    undo: () => void;
    redo: () => void;
    /** Screenshot del chart → descarga PNG (celda suelta). */
    screenshot: () => void;
    /** Canvas del chart para componer la captura de TODO el layout. */
    captureCanvas: () => Promise<HTMLCanvasElement | null>;
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
    /** El usuario creó/movió/borró un dibujo. Entrega el id del dibujo y el
     *  tipo de evento de la CL (create/remove/points_changed/…): la semántica
     *  TV de "solo los dibujos NUEVOS se sincronizan" exige saber QUÉ dibujo
     *  y CUÁNDO nació. */
    onDrawingEvent?: (cellId: string, sourceId: string, eventType: string) => void;
    /** ESC pulsado dentro del iframe (flujo TV: volver a cursor / cerrar flyout). */
    onEscape?: (cellId: string) => void;
    /** ⌘S/Ctrl+S dentro del iframe → guardar el diseño. */
    onSaveShortcut?: () => void;
    /** El widget llegó a ready — la barra de dibujo re-aplica su estado
     *  global (imán, candados, herramienta armada…) a la celda nueva. */
    onReady?: (cellId: string) => void;
    /** Letra tecleada en el iframe → abrir el buscador ÚNICO de la ventana. */
    onOpenSymbolSearch?: (cellId: string, seed: string) => void;
    /** Dígito tecleado en el iframe → abrir el diálogo ÚNICO de intervalo. */
    onOpenIntervalDialog?: (cellId: string, seed: string) => void;
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
        onSaveShortcut,
        onReady,
        onOpenSymbolSearch,
        onOpenIntervalDialog,
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

    // Auto-curación: si el widget no llega a ready (assets caídos, hipo de
    // red…), la celda se destruye y recrea sola en vez de quedarse blanca
    // para siempre. mountEpoch re-ejecuta el efecto de montaje; attempts
    // limita los reintentos automáticos; failed muestra la UI de error.
    const [mountEpoch, setMountEpoch] = useState(0);
    const [failed, setFailed] = useState(false);
    const attemptsRef = useRef(0);

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
    const onSaveShortcutRef = useRef(onSaveShortcut);
    onSaveShortcutRef.current = onSaveShortcut;
    const onReadyRef = useRef(onReady);
    onReadyRef.current = onReady;
    const onOpenSymbolSearchRef = useRef(onOpenSymbolSearch);
    onOpenSymbolSearchRef.current = onOpenSymbolSearch;
    const onOpenIntervalDialogRef = useRef(onOpenIntervalDialog);
    onOpenIntervalDialogRef.current = onOpenIntervalDialog;

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

    // Abrir o cerrar una reproducción cambia lo que significa "toda la
    // historia": el datafeed empieza (o deja) de cortar en el reloj. Hay que
    // obligar a la librería a repedir, o el gráfico se queda con las barras de
    // antes y no pasa nada visible — que era justo el sintoma.
    useEffect(() => {
        let prev = useReplayClockStore.getState().active;
        return useReplayClockStore.subscribe((s) => {
            if (s.active === prev) return;
            prev = s.active;
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                w.activeChart().resetData();
                // El viewport de la CL apunta al presente; al entrar en
                // reproducción las velas viven en el pasado y se veria vacio.
                if (s.active) {
                    const nowSec = (s.originMs + s.now()) / 1000;
                    const span = resolutionSpanSecs(w.activeChart().resolution()) * 120;
                    setTimeout(() => {
                        try {
                            w.activeChart().setVisibleRange(
                                { from: nowSec - span, to: nowSec + span * 0.15 },
                                { applyDefaultRightMargin: false },
                            );
                        } catch { /* aun sin barras */ }
                    }, 250);
                }
            } catch { /* widget no listo */ }
        });
    }, []);

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
        pickBar: (onPick: (timeSec: number) => void) => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return () => { };
            // `mouse_down` solo trae píxeles; el instante lo da la cruz. Se
            // combinan: la cruz mantiene la última vela apuntada y el clic la
            // confirma. Y mientras, se pinta una línea vertical con la fecha de
            // esa vela: sin ella no se sabe qué se está a punto de elegir.
            let hovered: number | null = null;
            let markId: unknown = null;
            let sub: { unsubscribe: (obj: unknown, cb: unknown) => void } | null = null;

            const borrarMarca = () => {
                if (markId == null) return;
                try { w.activeChart().removeEntity(markId as never); } catch { /* ya no está */ }
                markId = null;
            };

            const onCross = (p: { time?: number }) => {
                if (typeof p?.time !== 'number' || p.time === hovered) return;
                hovered = p.time;
                borrarMarca();
                try {
                    markId = w.activeChart().createShape(
                        { time: p.time },
                        {
                            shape: 'vertical_line',
                            lock: true,
                            disableSelection: true,
                            disableSave: true,
                            disableUndo: true,
                            text: pickLabelFmt.format(new Date(p.time * 1000)),
                            overrides: {
                                linecolor: '#2962FF',
                                linewidth: 2,
                                showTime: true,
                                textcolor: '#FFFFFF',
                            },
                        } as never,
                    );
                } catch { /* la CL aún no acepta formas */ }
            };

            const onDown = () => {
                if (hovered == null) return;
                const t = hovered;
                cancel();
                onPick(t);
            };

            const cancel = () => {
                borrarMarca();
                try { sub?.unsubscribe(null, onCross); } catch { /* ya suelto */ }
                try { w.unsubscribe('mouse_down', onDown); } catch { /* ya suelto */ }
            };

            try {
                sub = w.activeChart().crossHairMoved() as typeof sub;
                (sub as unknown as { subscribe: (o: unknown, c: unknown) => void })
                    .subscribe(null, onCross);
                w.subscribe('mouse_down', onDown);
            } catch {
                cancel();
                return () => { };
            }
            return cancel;
        },
        listStudies: () => {
            try {
                return widgetRef.current?.getStudiesList() ?? [];
            } catch {
                return [];
            }
        },
        addStudy: (name: string) => {
            try {
                widgetRef.current
                    ?.activeChart()
                    .createStudy(name)
                    ?.catch?.((err: unknown) => {
                        console.warn(`[TVChartCell] createStudy("${name}") falló:`, err);
                    });
            } catch (err) {
                console.warn(`[TVChartCell] createStudy("${name}") falló:`, err);
            }
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
                w.takeClientScreenshot().then(async (canvas: HTMLCanvasElement) => {
                    // Logo Tradeul en la descarga, mismo sitio que el overlay
                    // (bottom-left, por encima del eje de tiempo).
                    const ctx = canvas.getContext('2d');
                    if (ctx) {
                        const dpr = window.devicePixelRatio || 1;
                        const h = 20 * dpr;
                        await drawTradeulLogoOnCanvas(ctx, {
                            x: 12 * dpr,
                            y: canvas.height - 34 * dpr - h,
                            height: h,
                        });
                    }
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
        captureCanvas: async () => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return null;
            try {
                return await w.takeClientScreenshot();
            } catch {
                return null;
            }
        },
        save: buildSnapshot,
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }), []);

    useEffect(() => {
        let disposed = false;
        let watchdogIv: ReturnType<typeof setInterval> | null = null;
        let retryTimer: ReturnType<typeof setTimeout> | null = null;

        const persistNow = () => {
            const w = widgetRef.current;
            if (!w || !readyRef.current) return;
            try {
                w.save((state: object) => {
                    onPersistRef.current(cellId, { state, ...readChartMeta() });
                });
            } catch { /* save no disponible */ }
        };

        const stopWatchdog = () => {
            if (watchdogIv) {
                clearInterval(watchdogIv);
                watchdogIv = null;
            }
        };

        /** Recrear la celda (o rendirse con UI de error tras N intentos). */
        const scheduleRetry = (reason: string) => {
            if (disposed) return;
            stopWatchdog();
            attemptsRef.current += 1;
            if (attemptsRef.current > MAX_CELL_ATTEMPTS) {
                console.warn(`[TVChartCell] ${cellId}: sin gráfico tras ${MAX_CELL_ATTEMPTS} intentos (${reason})`);
                setFailed(true);
            } else {
                console.warn(`[TVChartCell] ${cellId}: recreando celda (${reason}, intento ${attemptsRef.current})`);
                setMountEpoch((e) => e + 1);
            }
        };

        /**
         * El documento del iframe de la CL nace BLANCO y solo pinta oscuro al
         * cargar su CSS: si alguna hoja falló (deploy, hipo de red), la celda
         * quedaría blanca para siempre. readyState 'complete' + link sin
         * .sheet = hoja fallida.
         */
        const cssDead = (): boolean => {
            try {
                const doc = containerRef.current?.querySelector('iframe')?.contentDocument;
                if (!doc || doc.readyState !== 'complete') return false;
                const links = Array.from(doc.querySelectorAll('link[rel="stylesheet"]'));
                return links.length > 0 && links.some((l) => !(l as HTMLLinkElement).sheet);
            } catch {
                return false;
            }
        };

        /**
         * Vigilar la inicialización contando solo segundos VISIBLES: en una
         * pestaña en segundo plano Chrome congela rAF/timers y la CL espera
         * legítimamente — eso no es un fallo y no debe disparar reintentos.
         */
        const startWatchdog = () => {
            stopWatchdog();
            let visibleSecs = 0;
            watchdogIv = setInterval(() => {
                if (readyRef.current) {
                    stopWatchdog();
                    return;
                }
                if (document.visibilityState !== 'visible') return;
                visibleSecs += 1;
                if (visibleSecs >= CSS_CHECK_SECS && cssDead()) scheduleRetry('css muerto');
                else if (visibleSecs >= READY_TIMEOUT_SECS) scheduleRetry('timeout de carga');
            }, 1000);
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
                        // Countdown de cierre de vela DENTRO de la etiqueta
                        // del precio actual (default false en la CL). Solo
                        // aplica en resoluciones intradía — limitación
                        // documentada de la librería, igual en tradingview.com.
                        'mainSeriesProperties.showCountdown': true,
                    },
                    // 5 s: cada autosave serializa el chart completo y dispara la
                    // persistencia de la ventana (localStorage síncrono). A 1 s,
                    // cualquier pan/zoom convertía el hilo principal en un
                    // festival de JSON.stringify. Los cambios críticos (símbolo,
                    // intervalo) persisten aparte vía persistNow inmediato, y los
                    // cambios de layout/guardados congelan snapshots explícitos
                    // (flushCellSnapshots), así que no se pierde nada relevante.
                    auto_save_delay: 5,
                    // La CL debouncea la búsqueda de símbolos: sin esto lanzaba
                    // una petición por pulsación.
                    symbol_search_request_delay: 300,
                    // Indicadores propios de Tradeul (RVOL…): vía oficial de la
                    // v31; la CL los lista y persiste como estudios normales.
                    custom_indicators_getter: buildCustomIndicatorsGetter(),
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
                        // REQUISITO del sync de dibujos: getLineToolsState /
                        // applyLineToolsState solo existen con este featureset
                        // (d.ts v31). Sin él, ambos modos de sincronización
                        // morían en silencio. widget.save() sigue incluyendo
                        // los dibujos (SaveChartOptions.includeDrawings
                        // default true) → los diseños no cambian.
                        'saveload_separate_drawings_storage',
                        // resetData() (resync tras reconexión/background) solo
                        // re-pide el rango visible: con 6-8 celdas evita una
                        // tormenta de peticiones de histórico completo por
                        // cada vuelta a la pestaña.
                        'request_only_visible_range_on_reset',
                    ],
                };
                if (savedState) options.saved_data = savedState;

                const widget = new window.TradingView.widget(options);
                widgetRef.current = widget;
                startWatchdog();

                widget.onChartReady(() => {
                    if (disposed) return;
                    readyRef.current = true;
                    attemptsRef.current = 0;
                    stopWatchdog();
                    setFailed(false);

                    // Logo Tradeul DENTRO del iframe, en la capa del logo de
                    // TV que ocultamos: sus paneles quedan por encima.
                    injectTradeulLogo(
                        containerRef.current?.querySelector('iframe')?.contentDocument,
                    );

                    // El estado guardado (saved_data) restaura sus propias
                    // propiedades y puede pisar los overrides del constructor:
                    // re-aplicar el countdown SIEMPRE tras cargar.
                    try {
                        widget.applyOverrides({ 'mainSeriesProperties.showCountdown': true });
                    } catch { /* opcional */ }

                    try {
                        widget.subscribe('onAutoSaveNeeded', persistNow);
                    } catch { /* sin autosave */ }

                    // Click/foco dentro del iframe → celda activa.
                    try {
                        widget.subscribe('mouse_down', () => onActivateRef.current?.(cellId));
                    } catch { /* opcional */ }

                    // Eventos de dibujo → sync entre celdas / global (si activo).
                    try {
                        widget.subscribe('drawing_event', (sourceId: unknown, eventType: unknown) => {
                            if (!applyingDrawingsRef.current) {
                                onDrawingEventRef.current?.(cellId, String(sourceId), String(eventType));
                            }
                        });
                    } catch { /* opcional */ }

                    // Teclas dentro del iframe (flujo TV). Los diálogos nativos
                    // viven DENTRO del iframe (saldrían centrados en la celda):
                    // se delega en los diálogos ÚNICOS de la ventana
                    // (TVCommandDialogs), centrados en el conjunto y aplicados
                    // a la celda enfocada — como en tradingview.com.
                    try {
                        const doc = containerRef.current?.querySelector('iframe')?.contentWindow?.document;
                        doc?.addEventListener('keydown', (e: KeyboardEvent) => {
                            const target = e.target as HTMLElement | null;
                            if (target?.closest?.('input, textarea, [contenteditable]')) return;
                            if (e.key === 'Escape') {
                                onEscapeRef.current?.(cellId);
                                return;
                            }
                            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
                                e.preventDefault();
                                onSaveShortcutRef.current?.();
                                return;
                            }
                            if (e.ctrlKey || e.metaKey || e.altKey) return;
                            if (/^[0-9]$/.test(e.key)) {
                                e.preventDefault();
                                onOpenIntervalDialogRef.current?.(cellId, e.key);
                            } else if (/^[a-zA-Z]$/.test(e.key)) {
                                e.preventDefault();
                                onOpenSymbolSearchRef.current?.(cellId, e.key.toUpperCase());
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

                    onReadyRef.current?.(cellId);
                });
            })
            .catch((err) => {
                if (disposed) return;
                console.error('[TVChartCell] error cargando la librería:', err);
                // El loader resetea su promesa al fallar: reintentar recarga el script.
                retryTimer = setTimeout(() => scheduleRetry('script de la librería'), 2000);
            });

        return () => {
            disposed = true;
            stopWatchdog();
            if (retryTimer) clearTimeout(retryTimer);
            // NOTA: no hay guardado final aquí — widget.save() es asíncrono y
            // su callback nunca llega con el iframe desmontado. El contenedor
            // congela los snapshots ANTES de desmontar celdas
            // (flushCellSnapshots) y el autosave de la CL (1 s) cubre el resto.
            readyRef.current = false;
            try {
                widgetRef.current?.remove();
            } catch { /* iframe ya retirado */ }
            widgetRef.current = null;
            // Un widget zombie puede dejar su iframe muerto colgando del
            // contenedor (hijos gestionados por la CL, no por React).
            if (containerRef.current) containerRef.current.innerHTML = '';
            datafeedRef.current?.destroy();
            datafeedRef.current = null;
        };
        // Montaje por celda: cambiar de layout recrea por key; mountEpoch
        // recrea la MISMA celda cuando el watchdog detecta un arranque muerto.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mountEpoch]);

    // ------------------------------------------------------------------
    // Resync de datos (mecanismo oficial CL para cortes de conexión):
    // invalidar la caché de barras del datafeed y forzar re-fetch con
    // resetData(). Cierra huecos de velas de forma determinista — sin esto,
    // la recuperación dependía de que el SIGUIENTE aggregate detectara gap,
    // que en símbolos ilíquidos o resolución diaria puede no llegar nunca.
    // ------------------------------------------------------------------
    const resyncData = useCallback(() => {
        if (!readyRef.current) return;
        datafeedRef.current?.resyncAll();
        try {
            widgetRef.current?.activeChart().resetData();
        } catch { /* widget en transición */ }
    }, []);

    // Tras una reconexión del WS compartido, reemitir las suscripciones y
    // resincronizar el histórico. Solo en transiciones reales false→true:
    // en el primer render el chart acaba de cargar y no hay hueco que cerrar.
    const prevConnectedRef = useRef<boolean | null>(null);
    useEffect(() => {
        const prev = prevConnectedRef.current;
        prevConnectedRef.current = isConnected;
        if (!isConnected) return;
        datafeedRef.current?.resubscribeAll();
        if (prev === false) resyncData();
    }, [isConnected, resyncData]);

    // Page Lifecycle: al volver de background (visibilitychange), de una
    // congelación de pestaña (freeze/resume, Chrome) o de un corte de red
    // (online), resincronizar si la ausencia superó el umbral. Mismo patrón
    // ya validado en useLiveChartData para el chart legacy.
    useEffect(() => {
        const MIN_AWAY_MS = 5000;
        let hiddenAt: number | null = null;

        const onVisibility = () => {
            if (document.visibilityState === 'hidden') {
                hiddenAt = Date.now();
                return;
            }
            const awayMs = hiddenAt ? Date.now() - hiddenAt : 0;
            hiddenAt = null;
            if (awayMs >= MIN_AWAY_MS) resyncData();
        };
        const onFreeze = () => {
            if (hiddenAt == null) hiddenAt = Date.now();
        };
        const onOnline = () => resyncData();

        document.addEventListener('visibilitychange', onVisibility);
        document.addEventListener('freeze', onFreeze);
        document.addEventListener('resume', onVisibility);
        window.addEventListener('online', onOnline);
        return () => {
            document.removeEventListener('visibilitychange', onVisibility);
            document.removeEventListener('freeze', onFreeze);
            document.removeEventListener('resume', onVisibility);
            window.removeEventListener('online', onOnline);
        };
    }, [resyncData]);

    return (
        <div
            className="relative h-full w-full"
            onMouseDownCapture={() => onActivateRef.current?.(cellId)}
        >
            <div ref={containerRef} className="h-full w-full" />
            {failed && (
                <div
                    className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3"
                    style={{ background: 'var(--color-bg, #0d1117)' }}
                >
                    <span className="text-[13px] opacity-70">No se pudo cargar el gráfico</span>
                    <button
                        onClick={() => {
                            attemptsRef.current = 0;
                            setFailed(false);
                            setMountEpoch((e) => e + 1);
                        }}
                        className="rounded-md border px-3 py-1.5 text-[13px] hover:bg-black/10 dark:hover:bg-white/10"
                        style={{ borderColor: 'var(--color-border, rgba(128,128,128,0.35))' }}
                    >
                        Reintentar
                    </button>
                </div>
            )}
        </div>
    );
});
