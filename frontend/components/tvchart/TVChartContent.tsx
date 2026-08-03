'use client';

/**
 * TVChartContent — ventana "TradingView" del workspace (comando TVC).
 *
 * Réplica del multichart de tradingview.com sobre la Charting Library v31:
 *   • UNA toolbar superior y UNA barra de dibujo para toda la ventana; actúan
 *     sobre la celda enfocada (los diálogos nativos de la CL se abren en ella).
 *   • Rejilla de 1-8 celdas headless (plantillas compartidas con el chart
 *     propio) con picker de miniaturas y sync de símbolo/intervalo.
 *   • Persistencia COMPLETA por ventana: cada celda guarda su widget.save().
 *
 * El multichart nativo de la CL es exclusivo de Trading Platform, así que la
 * rejilla es nuestra: N instancias del widget orquestadas desde aquí.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { useLinkGroupSubscription } from '@/hooks/useLinkGroup';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { tvDesignsApi, tvDrawingsApi } from './tvDesignsApi';
import { DEFAULT_SYNC_FLAGS, type SyncFlags } from '@/components/chart/multichart/types';
import { TV_LAYOUTS } from './tvLayouts';
import { closeAllTVPopovers } from './tvPopovers';
import { TVLayoutGrid } from './TVLayoutGrid';
import { TVBottomBar } from './TVBottomBar';
import { drawTradeulLogoOnCanvas } from './TradeulLogo';
import { TVIndicatorsDialog, TVIntervalDialog, TVSymbolSearchDialog } from './TVCommandDialogs';
import { TVLayoutPicker } from './TVLayoutPicker';
import { TVChartCell, type TVChartCellApi, type TVCellSnapshot } from './TVChartCell';
import { TVDesignManager, type ActiveDesign } from './TVDesignManager';
import { TVToolbar, type TVToolbarActions } from './TVToolbar';
import { TVDrawingBar, type DrawingsSyncMode } from './TVDrawingBar';

const DEFAULT_SYMBOL = 'AAPL';
const DEFAULT_TV_INTERVAL = '5';
const DEFAULT_CHART_TYPE = 1; // velas

/** Estado persistido de una celda. */
interface TVCellPersisted {
    /** JSON de widget.save() — chart completo. */
    tvState?: object;
    symbol?: string;
    /** Resolución TV ('5', '1D'…) para re-crear la celda sin tvState. */
    interval?: string;
    chartType?: number;
}

/** Estado persistido de la ventana multichart (componentState). */
interface TVWindowState {
    layoutId?: string;
    cells?: Record<string, TVCellPersisted>;
    sync?: SyncFlags;
    drawingsSync?: DrawingsSyncMode;
    /** Diseño con nombre activo (gestor de diseños). */
    designId?: string;
    designName?: string;
    autoSaveDesign?: boolean;
    /** Legacy fase 1 (una sola celda): migrado a cells['cell-1']. */
    tvState?: object;
    symbol?: string;
}

/** Normaliza el estado guardado (incluida la migración del formato fase 1). */
function normalizeState(
    raw: TVWindowState | undefined,
    fallbackSymbol: string,
): { layoutId: string; cells: Record<string, TVCellPersisted>; sync: SyncFlags } {
    // Migración: la fase multichart previa usaba id 'single'; ahora es 's'.
    let layoutId = raw?.layoutId === 'single' ? 's' : raw?.layoutId;
    if (!layoutId || !(layoutId in TV_LAYOUTS)) layoutId = 's';
    let cells = raw?.cells ?? {};
    if (!raw?.cells && raw?.tvState) {
        cells = { 'cell-1': { tvState: raw.tvState, symbol: raw.symbol } };
    }
    if (!cells['cell-1']) {
        cells = { ...cells, 'cell-1': { symbol: fallbackSymbol } };
    }
    return {
        layoutId,
        cells,
        sync: raw?.sync ?? { ...DEFAULT_SYNC_FLAGS, symbol: false, interval: false },
    };
}

interface TVChartContentProps {
    initialSymbol?: string;
}

export function TVChartContent({ initialSymbol }: TVChartContentProps) {
    const windowId = useCurrentWindowId();
    const updateWindowComponentState = useUserPreferencesStore((s) => s.updateWindowComponentState);
    const getWindowComponentState = useUserPreferencesStore((s) => s.getWindowComponentState);

    const fallbackSymbol = (initialSymbol || DEFAULT_SYMBOL).toUpperCase();
    const { getToken } = useAuth();
    const getTokenRef = useRef(getToken);
    getTokenRef.current = getToken;
    /** Indirection: lo usan callbacks declarados antes que su definición. */
    const applyGlobalDrawingsRef = useRef<(cellId: string) => void>(() => {});

    // Estado inicial: una sola lectura al montar la ventana. Si la ventana es
    // NUEVA (sin componentState: se cerró y se reabre, u otro dispositivo),
    // se restaura el último estado del usuario desde el backend (/last).
    const initialRef = useRef<ReturnType<typeof normalizeState> | null>(null);
    const freshWindowRef = useRef(false);
    const initialDrawingsSyncRef = useRef<DrawingsSyncMode>('off');
    if (initialRef.current === null) {
        const raw = (windowId ? getWindowComponentState(windowId) : undefined) as
            | TVWindowState
            | undefined;
        freshWindowRef.current = !raw || (!raw.cells && !raw.tvState && !raw.designId);
        initialDrawingsSyncRef.current = raw?.drawingsSync ?? 'off';
        initialRef.current = normalizeState(raw, fallbackSymbol);
    }

    const [layoutId, setLayoutId] = useState<string>(initialRef.current.layoutId);
    const [sync, setSync] = useState<SyncFlags>(initialRef.current.sync);
    const [drawingsSync, setDrawingsSync] = useState<DrawingsSyncMode>(
        () => initialDrawingsSyncRef.current,
    );
    const [activeCellId, setActiveCellId] = useState('cell-1');
    const [pickerOpen, setPickerOpen] = useState(false);
    const pickerButtonRef = useRef<HTMLButtonElement>(null);
    /** Raíz de la rejilla — geometría para componer la captura del layout. */
    const gridRootRef = useRef<HTMLDivElement>(null);
    /**
     * Restauración de ventana nueva: mientras se consulta /last no se montan
     * celdas (evita crear widgets por defecto y tirarlos al aplicar el estado).
     */
    const [restoring, setRestoring] = useState(() => freshWindowRef.current);
    /** Símbolo pedido explícitamente (comando `TICKER TVC`) a aplicar tras restaurar. */
    const pendingSymbolRef = useRef<string | null>(null);
    /** Símbolo del link group pendiente hasta que la celda activa esté lista. */
    const linkPendingRef = useRef<string | null>(null);
    const linkBroadcast = useLinkGroupSubscription();
    /** Última celda que llegó a ready (la barra de dibujo re-aplica su estado). */
    const [readyCell, setReadyCell] = useState<{ id: string; seq: number }>({ id: '', seq: 0 });

    // ESC desde los iframes → cerrar popovers y la barra de dibujo vuelve al
    // cursor (flujo TV).
    const [escSignal, setEscSignal] = useState(0);
    const handleCellEscape = useCallback(() => {
        closeAllTVPopovers();
        setEscSignal((s) => s + 1);
    }, []);

    // Gestor de diseños: diseño activo, dirty (versión vs guardada) y ⌘S.
    const initialRaw = (windowId ? getWindowComponentState(windowId) : undefined) as
        | TVWindowState
        | undefined;
    const [activeDesign, setActiveDesign] = useState<ActiveDesign | null>(
        initialRaw?.designId && initialRaw?.designName
            ? { id: initialRaw.designId, name: initialRaw.designName }
            : null,
    );
    const [autoSaveDesign, setAutoSaveDesign] = useState(initialRaw?.autoSaveDesign ?? true);
    const [stateVersion, setStateVersion] = useState(0);
    const [savedVersion, setSavedVersion] = useState(0);
    const [saveSignal, setSaveSignal] = useState(0);
    const [designEpoch, setDesignEpoch] = useState(0);
    const activeDesignRef = useRef(activeDesign);
    activeDesignRef.current = activeDesign;
    const autoSaveDesignRef = useRef(autoSaveDesign);
    autoSaveDesignRef.current = autoSaveDesign;
    const handleCellSaveShortcut = useCallback(() => setSaveSignal((s) => s + 1), []);


    // Info de la celda enfocada que pinta la toolbar.
    const initialCell1 = initialRef.current.cells['cell-1'];
    const [activeInfo, setActiveInfo] = useState({
        symbol: initialCell1?.symbol ?? fallbackSymbol,
        interval: initialCell1?.interval ?? DEFAULT_TV_INTERVAL,
        chartType: initialCell1?.chartType ?? DEFAULT_CHART_TYPE,
    });

    // Datos persistidos por celda: viven en un ref (las celdas son dueñas del
    // estado vivo; esto es solo el snapshot para persistir/recrear).
    const cellsRef = useRef<Record<string, TVCellPersisted>>(initialRef.current.cells);
    // API imperativa de cada celda montada (para sync y toolbar).
    const cellApisRef = useRef<Record<string, TVChartCellApi | null>>({});

    const windowIdRef = useRef(windowId);
    windowIdRef.current = windowId;
    const layoutIdRef = useRef(layoutId);
    layoutIdRef.current = layoutId;
    const syncRef = useRef(sync);
    syncRef.current = sync;
    const activeCellIdRef = useRef(activeCellId);
    activeCellIdRef.current = activeCellId;

    const cellCount = (TV_LAYOUTS[layoutId] ?? TV_LAYOUTS.s).count;
    const cellIds = useMemo(
        () => Array.from({ length: cellCount }, (_, i) => `cell-${i + 1}`),
        [cellCount],
    );

    // ── Celda maximizada ──────────────────────────────────────────────────
    // Estado de vista puro y a propósito efímero: TradingView lo guarda en un
    // único valor de su colección de charts, NO lo escribe en el layout
    // guardado y al recargar vuelve la rejilla entera. Dejarlo fuera del
    // diseño persistido reproduce eso exactamente.
    const [maximizedCellId, setMaximizedCellId] = useState<string | null>(null);

    // Cambiar de layout desmaximiza — igual que TradingView, donde `setLayout`
    // pasa por `_recalculateMaximizedChartDef` y resuelve a null en escritorio.
    // Cargar un diseño (designEpoch) cuenta como cambio de layout. El guard de
    // cellCount cubre encoger por debajo de la celda maximizada, que si no
    // dejaría TODAS las celdas ocultas a la vez.
    useEffect(() => {
        setMaximizedCellId(null);
    }, [layoutId, designEpoch]);

    const maximizedIndex = useMemo(() => {
        if (maximizedCellId === null) return null;
        const n = Number(maximizedCellId.split('-')[1]);
        if (!Number.isFinite(n) || n < 1 || n > cellCount) return null;
        return n - 1;
    }, [maximizedCellId, cellCount]);

    // Maximizar apunta SIEMPRE a la celda enfocada: el `requestFullscreen` por
    // chart de TradingView maximiza y activa en la misma llamada, así que la
    // maximizada es por definición la activa.
    const handleToggleMaximize = useCallback(() => {
        setMaximizedCellId((cur) => (cur !== null ? null : activeCellIdRef.current));
    }, []);

    // ── Montaje ESCALONADO de celdas ──────────────────────────────────────
    // Los iframes same-origin comparten el hilo principal de la página:
    // montar 6 widgets a la vez encola 6 inicializaciones de la CL en serie
    // y congela la UI varios segundos. mountedIds va admitiendo celdas de una
    // en una (la primera al instante); entre celda y celda el hilo respira y
    // la ventana sigue respondiendo. Las celdas aún no admitidas pintan un
    // placeholder con el fondo del chart.
    const STAGGER_MS = 200;
    const [mountedIds, setMountedIds] = useState<Set<string>>(() => new Set());
    useEffect(() => {
        // Mientras se restaura /last la rejilla no existe: no admitir celdas
        // (se montarían todas de golpe al aparecer).
        if (restoring) return;
        const missing = cellIds.filter((id) => !mountedIds.has(id));
        const stale = [...mountedIds].some((id) => !cellIds.includes(id));
        if (stale) {
            // Layout más pequeño: soltar las celdas sobrantes ya.
            setMountedIds(new Set(cellIds.filter((id) => mountedIds.has(id))));
            return;
        }
        if (missing.length === 0) return;
        const t = setTimeout(
            () => setMountedIds((prev) => new Set([...prev, missing[0]])),
            mountedIds.size === 0 ? 0 : STAGGER_MS,
        );
        return () => clearTimeout(t);
    }, [cellIds, mountedIds, restoring]);

    /** Escribir el componentState de la ventana (sin tocar el dirty). */
    const writeWindowState = useCallback(() => {
        const id = windowIdRef.current;
        if (!id) return;
        updateWindowComponentState(id, {
            layoutId: layoutIdRef.current,
            cells: cellsRef.current,
            sync: syncRef.current,
            drawingsSync: drawingsSyncRef.current,
            designId: activeDesignRef.current?.id,
            designName: activeDesignRef.current?.name,
            autoSaveDesign: autoSaveDesignRef.current,
        });
    }, [updateWindowComponentState]);

    /**
     * Throttle del volcado al store (leading + trailing): cada writeWindowState
     * acaba en un JSON.stringify del store COMPLETO de preferencias hacia
     * localStorage (síncrono, en el hilo principal) — con 6 celdas son cientos
     * de KB por golpe. El autosave de cada celda dispara persistWindow
     * constantemente mientras se usa el chart; escribir como mucho una vez
     * cada 2 s elimina el jank sin perder estado (siempre queda un trailing
     * write con el último snapshot, y al desmontar se hace flush).
     */
    const WRITE_THROTTLE_MS = 2000;
    const writeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastWriteRef = useRef(0);
    const scheduleWriteWindowState = useCallback(() => {
        if (writeTimerRef.current) return; // trailing ya programado
        const elapsed = Date.now() - lastWriteRef.current;
        if (elapsed >= WRITE_THROTTLE_MS) {
            lastWriteRef.current = Date.now();
            writeWindowState();
            return;
        }
        writeTimerRef.current = setTimeout(() => {
            writeTimerRef.current = null;
            lastWriteRef.current = Date.now();
            writeWindowState();
        }, WRITE_THROTTLE_MS - elapsed);
    }, [writeWindowState]);

    // Flush del trailing write pendiente al desmontar la ventana.
    useEffect(() => () => {
        if (writeTimerRef.current) {
            clearTimeout(writeTimerRef.current);
            writeTimerRef.current = null;
            writeWindowState();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /** Persistir el estado completo de la ventana y marcar cambios sin guardar. */
    const persistWindow = useCallback(() => {
        scheduleWriteWindowState();
        setStateVersion((v) => v + 1);
    }, [scheduleWriteWindowState]);

    // Ventana de gracia tras montar o cargar un diseño: los persists que
    // disparan las celdas al inicializarse (widget ready) no son cambios del
    // usuario y no deben dejar el chip en "Guardar".
    const cleanUntilRef = useRef(Date.now() + 6000);
    useEffect(() => {
        if (Date.now() < cleanUntilRef.current) setSavedVersion(stateVersion);
    }, [stateVersion]);

    // Persistir cuando cambian layout o sync (los cambios de celda persisten solos).
    useEffect(() => {
        persistWindow();
    }, [layoutId, sync, persistWindow]);

    // Diseño activo/autoguardado: persistir la asociación SIN marcar dirty
    // (renombrar o togglear autosave no ensucia el diseño). Sin esto, al
    // recargar la ventana se perdía el diseño activo y volvía "Sin nombre".
    useEffect(() => {
        writeWindowState();
    }, [activeDesign, autoSaveDesign, writeWindowState]);

    /** Refresca la toolbar si el cambio viene de la celda enfocada. */
    const refreshActiveInfo = useCallback((cellId: string) => {
        if (cellId !== activeCellIdRef.current) return;
        const snap = cellsRef.current[cellId];
        if (!snap) return;
        setActiveInfo({
            symbol: snap.symbol ?? DEFAULT_SYMBOL,
            interval: snap.interval ?? DEFAULT_TV_INTERVAL,
            chartType: snap.chartType ?? DEFAULT_CHART_TYPE,
        });
    }, []);

    const handleCellPersist = useCallback((cellId: string, snapshot: TVCellSnapshot) => {
        const prev = cellsRef.current[cellId] ?? {};
        cellsRef.current = {
            ...cellsRef.current,
            [cellId]: {
                tvState: snapshot.state,
                symbol: snapshot.symbol ?? prev.symbol,
                interval: snapshot.interval ?? prev.interval,
                chartType: snapshot.chartType ?? prev.chartType,
            },
        };
        refreshActiveInfo(cellId);
        persistWindow();
    }, [persistWindow, refreshActiveInfo]);

    const handleSymbolChanged = useCallback((cellId: string, symbol: string) => {
        const prev = cellsRef.current[cellId] ?? {};
        cellsRef.current = { ...cellsRef.current, [cellId]: { ...prev, symbol } };
        if (syncRef.current.symbol) {
            for (const [otherId, api] of Object.entries(cellApisRef.current)) {
                if (otherId !== cellId) api?.setSymbol(symbol);
            }
        }
        refreshActiveInfo(cellId);
        persistWindow();
        // Modo global: al cambiar de símbolo, traer sus dibujos globales
        // (pequeño margen para que el chart asiente el cambio).
        setTimeout(() => applyGlobalDrawingsRef.current(cellId), 500);
    }, [persistWindow, refreshActiveInfo]);

    const applyLinkedSymbol = useCallback((symbol: string) => {
        const cellId = activeCellIdRef.current;
        const api = cellApisRef.current[cellId];
        if (!api) {
            linkPendingRef.current = symbol;
            return;
        }
        linkPendingRef.current = null;
        api.setSymbol(symbol);
        handleSymbolChanged(cellId, symbol);
    }, [handleSymbolChanged]);

    // Link group → TC: clicks en SC / EVN / Screener cambian el símbolo activo.
    useEffect(() => {
        const ticker = linkBroadcast?.ticker;
        if (!ticker) return;
        applyLinkedSymbol(ticker.toUpperCase());
    }, [linkBroadcast, applyLinkedSymbol]);

    const handleCellReady = useCallback((cellId: string) => {
        setReadyCell((prev) => ({ id: cellId, seq: prev.seq + 1 }));
        // Modo global: la celda recién lista recibe los dibujos de su símbolo.
        applyGlobalDrawingsRef.current(cellId);
        // Comando `TICKER TVC` sobre estado restaurado: el layout vuelve tal
        // cual y la celda principal cambia al símbolo pedido.
        if (cellId === 'cell-1' && pendingSymbolRef.current) {
            const symbol = pendingSymbolRef.current;
            pendingSymbolRef.current = null;
            cellApisRef.current['cell-1']?.setSymbol(symbol);
            // setSymbol va con guard anti-eco: registrar el cambio a mano.
            handleSymbolChanged('cell-1', symbol);
        }
        // Link group pendiente (broadcast llegó antes de que la celda estuviera lista).
        if (linkPendingRef.current && cellId === activeCellIdRef.current) {
            const symbol = linkPendingRef.current;
            linkPendingRef.current = null;
            cellApisRef.current[cellId]?.setSymbol(symbol);
            handleSymbolChanged(cellId, symbol);
        }
    }, [handleSymbolChanged]);

    const handleIntervalChanged = useCallback((cellId: string, resolution: string) => {
        const prev = cellsRef.current[cellId] ?? {};
        cellsRef.current = { ...cellsRef.current, [cellId]: { ...prev, interval: resolution } };
        if (syncRef.current.interval) {
            for (const [otherId, api] of Object.entries(cellApisRef.current)) {
                if (otherId !== cellId) api?.setInterval(resolution);
            }
        }
        refreshActiveInfo(cellId);
        persistWindow();
    }, [persistWindow, refreshActiveInfo]);

    // ── Diálogos ÚNICOS de la ventana (flujo tradingview.com): búsqueda de
    // símbolo y cambio de intervalo salen UNA vez, centrados en la ventana,
    // y aplican a la celda enfocada ─────────────────────────────────────────
    const [cmdDialog, setCmdDialog] = useState<
        { kind: 'symbol' | 'interval' | 'indicators'; cellId: string; seed: string } | null
    >(null);
    /** Devolver el foco al contenedor al cerrar: la siguiente tecla reabre. */
    const contentRootRef = useRef<HTMLDivElement>(null);
    const closeCmdDialog = useCallback(() => {
        setCmdDialog(null);
        contentRootRef.current?.focus();
    }, []);
    const openCmdDialog = useCallback((kind: 'symbol' | 'interval' | 'indicators', cellId: string, seed: string) => {
        setActiveCellId(cellId);
        const snap = cellsRef.current[cellId];
        setActiveInfo({
            symbol: snap?.symbol ?? DEFAULT_SYMBOL,
            interval: snap?.interval ?? DEFAULT_TV_INTERVAL,
            chartType: snap?.chartType ?? DEFAULT_CHART_TYPE,
        });
        closeAllTVPopovers();
        // Si ya hay uno abierto, se conserva (no pisar lo que escribe el usuario).
        setCmdDialog((d) => d ?? { kind, cellId, seed });
    }, []);
    const applyCmdSymbol = useCallback((symbol: string) => {
        if (!cmdDialog) return;
        const cellId = cmdDialog.cellId;
        closeCmdDialog();
        cellApisRef.current[cellId]?.setSymbol(symbol);
        // setSymbol va con guard anti-eco: registrar el cambio a mano (mismo
        // patrón que el comando `TICKER TVC`).
        handleSymbolChanged(cellId, symbol);
    }, [cmdDialog, closeCmdDialog, handleSymbolChanged]);
    const applyCmdInterval = useCallback((resolution: string) => {
        if (!cmdDialog) return;
        const cellId = cmdDialog.cellId;
        closeCmdDialog();
        cellApisRef.current[cellId]?.setInterval(resolution);
        handleIntervalChanged(cellId, resolution);
    }, [cmdDialog, closeCmdDialog, handleIntervalChanged]);

    const handleActivate = useCallback((cellId: string) => {
        // Clic dentro de un gráfico (iframe): cerrar cualquier popover abierto
        // — los mousedown de los iframes no llegan al documento padre.
        closeAllTVPopovers();
        setActiveCellId(cellId);
        const snap = cellsRef.current[cellId];
        setActiveInfo({
            symbol: snap?.symbol ?? DEFAULT_SYMBOL,
            interval: snap?.interval ?? DEFAULT_TV_INTERVAL,
            chartType: snap?.chartType ?? DEFAULT_CHART_TYPE,
        });
    }, []);

    /**
     * Congelar en cellsRef el snapshot vivo de cada celda montada. Con timeout
     * por celda: una celda colgada no puede bloquear un guardado ni un cambio
     * de layout. (widget.save() tras desmontar el iframe nunca responde — por
     * eso SIEMPRE se congela antes de destruir celdas.)
     */
    const flushCellSnapshots = useCallback(async () => {
        await Promise.all(
            Object.entries(cellApisRef.current).map(async ([cellId, api]) => {
                if (!api) return;
                const snap = await Promise.race([
                    api.save(),
                    new Promise<null>((r) => setTimeout(() => r(null), 800)),
                ]);
                if (!snap) return;
                const prev = cellsRef.current[cellId] ?? {};
                cellsRef.current = {
                    ...cellsRef.current,
                    [cellId]: {
                        tvState: snap.state,
                        symbol: snap.symbol ?? prev.symbol,
                        interval: snap.interval ?? prev.interval,
                        chartType: snap.chartType ?? prev.chartType,
                    },
                };
            }),
        );
    }, []);

    const handlePickLayout = useCallback((id: string) => {
        setPickerOpen(false);
        // Congelar el estado vivo ANTES de desmontar: las celdas que
        // desaparecen conservan su último snapshot en cellsRef y, si el
        // usuario vuelve a un layout mayor, recuperan su chart tal cual
        // (dibujos de última hora incluidos).
        void flushCellSnapshots().then(() => setLayoutId(id));
    }, [flushCellSnapshots]);

    const handleToggleSync = useCallback((flag: keyof SyncFlags) => {
        setSync((prev) => {
            const next = { ...prev, [flag]: !prev[flag] };
            // Al activar, alinear el resto de celdas con la celda activa.
            if (next[flag]) {
                const source = cellsRef.current[activeCellIdRef.current];
                if (flag === 'symbol' && source?.symbol) {
                    for (const [otherId, api] of Object.entries(cellApisRef.current)) {
                        if (otherId !== activeCellIdRef.current) api?.setSymbol(source.symbol);
                    }
                }
                if (flag === 'interval' && source?.interval) {
                    for (const [otherId, api] of Object.entries(cellApisRef.current)) {
                        if (otherId !== activeCellIdRef.current) api?.setInterval(source.interval);
                    }
                }
            }
            return next;
        });
    }, []);

    // Ref-callbacks MEMOIZADOS por celda: si la identidad de la función
    // cambiara en cada render, React soltaría (null) y re-engancharía el api
    // de todas las celdas en cada re-render de la ventana.
    const cellApiRefFnsRef = useRef(new Map<string, (api: TVChartCellApi | null) => void>());
    const registerCellApi = useCallback((cellId: string) => {
        let fn = cellApiRefFnsRef.current.get(cellId);
        if (!fn) {
            fn = (api: TVChartCellApi | null) => {
                cellApisRef.current[cellId] = api;
            };
            cellApiRefFnsRef.current.set(cellId, fn);
        }
        return fn;
    }, []);

    // ── Sincronización de dibujos, semántica EXACTA de tradingview.com ────
    // Cada dibujo queda marcado con su ámbito AL CREARSE ("los NUEVOS dibujos
    // se sincronizan…"): los anteriores jamás se suben ni se pisan. Las
    // ediciones y borrados de un dibujo sincronizado siguen propagándose
    // aunque el modo cambie después (el ámbito pertenece al dibujo). Todos
    // los applies son PARCIALES (merge por id; null = tombstone).
    const drawingsSyncRef = useRef(drawingsSync);
    drawingsSyncRef.current = drawingsSync;
    /** Ámbito por (símbolo → id de dibujo). Solo entran los sincronizados. */
    const syncedDrawingsRef = useRef<Map<string, Map<string, 'layout' | 'global'>>>(new Map());
    /** Debounce por dibujo (ráfagas de points_changed al arrastrar). */
    const drawingTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
    /** Parches al servidor acumulados por símbolo. */
    const pendingPatchesRef = useRef<Map<string, Record<string, unknown | null>>>(new Map());
    const patchTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

    const scopeOf = (symbol: string, id: string) =>
        syncedDrawingsRef.current.get(symbol)?.get(id);
    const setScope = (symbol: string, id: string, scope: 'layout' | 'global') => {
        const bySymbol = syncedDrawingsRef.current.get(symbol) ?? new Map<string, 'layout' | 'global'>();
        bySymbol.set(id, scope);
        syncedDrawingsRef.current.set(symbol, bySymbol);
    };
    const dropScope = (symbol: string, id: string) => {
        syncedDrawingsRef.current.get(symbol)?.delete(id);
    };

    /** Replicar UN dibujo (o su borrado) en las demás celdas del símbolo. */
    const replicateEntry = useCallback((cellId: string, symbol: string, id: string, entry: unknown) => {
        for (const [otherId, api] of Object.entries(cellApisRef.current)) {
            if (otherId === cellId || !api) continue;
            if (cellsRef.current[otherId]?.symbol !== symbol) continue;
            void api.applyDrawingsState({ sources: new Map([[id, entry]]), groups: new Map() });
        }
    }, []);

    /** Acumular y enviar parches por símbolo (merge con tombstones). */
    const schedulePatch = useCallback((symbol: string, id: string, entry: unknown | null) => {
        const pending = pendingPatchesRef.current.get(symbol) ?? {};
        pending[id] = entry as Record<string, unknown> | null;
        pendingPatchesRef.current.set(symbol, pending);
        const prev = patchTimersRef.current.get(symbol);
        if (prev) clearTimeout(prev);
        patchTimersRef.current.set(symbol, setTimeout(() => {
            patchTimersRef.current.delete(symbol);
            const body = pendingPatchesRef.current.get(symbol);
            pendingPatchesRef.current.delete(symbol);
            if (!body) return;
            tvDrawingsApi.patch(getTokenRef.current, symbol, body).catch(() => { /* offline */ });
        }, 800));
    }, []);

    const handleDrawingEvent = useCallback((cellId: string, sourceId: string, eventType: string) => {
        if (!['create', 'remove', 'points_changed', 'properties_changed'].includes(eventType)) return;
        const symbol = cellsRef.current[cellId]?.symbol;
        if (!symbol) return;

        // ¿Participa este dibujo? Solo si nace AHORA con un modo activo, o si
        // ya estaba registrado como sincronizado. Los antiguos: intocables.
        let scope = scopeOf(symbol, sourceId);
        if (!scope) {
            const mode = drawingsSyncRef.current;
            if (eventType !== 'create' || mode === 'off') return;
            scope = mode;
            setScope(symbol, sourceId, scope);
        }

        if (eventType === 'remove') {
            dropScope(symbol, sourceId);
            replicateEntry(cellId, symbol, sourceId, null);
            if (scope === 'global') schedulePatch(symbol, sourceId, null);
            return;
        }

        // create / cambios: leer el estado de ESE dibujo, debounced por dibujo.
        const timerKey = `${cellId}:${sourceId}`;
        const prevTimer = drawingTimersRef.current.get(timerKey);
        if (prevTimer) clearTimeout(prevTimer);
        drawingTimersRef.current.set(timerKey, setTimeout(async () => {
            drawingTimersRef.current.delete(timerKey);
            const source = cellApisRef.current[cellId];
            if (!source) return;
            const state = await source.getDrawingsState();
            // sources viene del realm del iframe: acceso duck-typed, nunca instanceof.
            const sources = (state as { sources?: { get?: (k: string) => unknown } } | null)?.sources;
            const entry = typeof sources?.get === 'function'
                ? sources.get(sourceId)
                : (sources as Record<string, unknown> | undefined)?.[sourceId];
            if (entry === undefined || entry === null) return;
            replicateEntry(cellId, symbol, sourceId, entry);
            if (scope === 'global') schedulePatch(symbol, sourceId, entry);
        }, 400));
    }, [replicateEntry, schedulePatch]);

    /**
     * Traer los dibujos GLOBALES del símbolo de una celda y aplicarlos en
     * merge parcial. Se hace SIEMPRE (independiente del modo actual): un
     * dibujo global ya pertenece al símbolo — el toggle solo decide el ámbito
     * de los dibujos NUEVOS. Registra los ids para que sus ediciones y
     * borrados sigan propagándose.
     */
    const applyGlobalDrawings = useCallback(async (cellId: string) => {
        const symbol = cellsRef.current[cellId]?.symbol;
        const api = cellApisRef.current[cellId];
        if (!symbol || !api) return;
        try {
            const state = await tvDrawingsApi.get(getTokenRef.current, symbol);
            const sources = (state as { sources?: Map<string, unknown> } | null)?.sources;
            if (!sources || sources.size === 0) return;
            for (const id of sources.keys()) setScope(symbol, id, 'global');
            await api.applyDrawingsState({ sources, groups: new Map() });
        } catch { /* offline o sin sesión */ }
    }, []);

    applyGlobalDrawingsRef.current = (cellId: string) => void applyGlobalDrawings(cellId);

    /**
     * Cambio de modo (menú del globo). AJUSTE DE USUARIO (doc oficial:
     * independiente de los layouts): persiste por usuario y nunca viaja en
     * los diseños. Cambiarlo NO toca ningún dibujo existente — solo define el
     * ámbito de los que se creen a partir de ahora.
     */
    const handleDrawingsSyncChange = useCallback((mode: DrawingsSyncMode) => {
        setDrawingsSync(mode);
        drawingsSyncRef.current = mode;
        writeWindowState();
        tvDesignsApi.setSettings(getTokenRef.current, { drawingsSync: mode }).catch(() => { /* offline */ });
    }, [writeWindowState]);

    /** Símbolo con el que arranca una celda nueva (sin snapshot previo). */
    const symbolForNewCell = useCallback((cellId: string): string => {
        const snap = cellsRef.current[cellId];
        if (snap?.symbol) return snap.symbol;
        return cellsRef.current[activeCellIdRef.current]?.symbol ?? fallbackSymbol;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fallbackSymbol]);

    /**
     * Captura de TODO el layout (flujo TV multichart): compone los canvas de
     * cada celda según su geometría real en la rejilla y descarga un solo PNG.
     * La cámara NO es por-celda: un layout de 6 charts descarga los 6.
     */
    const screenshotLayout = useCallback(async () => {
        const root = gridRootRef.current;
        if (!root) return;
        const rootRect = root.getBoundingClientRect();
        if (rootRect.width === 0 || rootRect.height === 0) return;
        const shots: Array<{ rect: DOMRect; canvas: HTMLCanvasElement }> = [];
        for (const [cellId, api] of Object.entries(cellApisRef.current)) {
            if (!api) continue;
            const el = root.querySelector(`[data-cell-id="${cellId}"]`);
            if (!el) continue;
            // Con una celda maximizada el resto siguen en el DOM y conservan
            // su rect (así no se recargan los iframes), pero están ocultas: si
            // no las saltamos, la captura compondría la rejilla entera encima
            // de la maximizada.
            if (getComputedStyle(el).visibility === 'hidden') continue;
            const canvas = await api.captureCanvas();
            if (canvas) shots.push({ rect: el.getBoundingClientRect(), canvas });
        }
        if (shots.length === 0) return;
        const scale = window.devicePixelRatio || 1;
        const out = document.createElement('canvas');
        out.width = Math.round(rootRect.width * scale);
        out.height = Math.round(rootRect.height * scale);
        const ctx = out.getContext('2d');
        if (!ctx) return;
        const bg = getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim();
        ctx.fillStyle = bg || '#0d1117';
        ctx.fillRect(0, 0, out.width, out.height);
        for (const { rect, canvas } of shots) {
            ctx.drawImage(
                canvas,
                Math.round((rect.left - rootRect.left) * scale),
                Math.round((rect.top - rootRect.top) * scale),
                Math.round(rect.width * scale),
                Math.round(rect.height * scale),
            );
        }
        // Logo Tradeul en la descarga del layout (bottom-left del conjunto).
        await drawTradeulLogoOnCanvas(ctx, {
            x: 12 * scale,
            y: out.height - (34 + 20) * scale,
            height: 20 * scale,
        });
        const symbols = Array.from(
            new Set(
                Object.keys(cellApisRef.current)
                    .filter((id) => cellApisRef.current[id])
                    .map((id) => cellsRef.current[id]?.symbol)
                    .filter((s): s is string => Boolean(s)),
            ),
        );
        const name = symbols.length > 3 ? `${symbols[0]}_y_${symbols.length - 1}_mas` : symbols.join('-') || 'layout';
        out.toBlob((blob) => {
            if (!blob) return;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `tradeul_${name}_${Date.now()}.png`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
        });
    }, []);

    // Acciones de la toolbar → celda enfocada (la cámara, al layout entero).
    const toolbarActions: TVToolbarActions = useMemo(() => {
        const active = () => cellApisRef.current[activeCellIdRef.current];
        return {
            exec: (actionId) => {
                // Búsqueda/intervalo: diálogo único de la ventana, no el
                // nativo del iframe de la celda.
                if (actionId === 'symbolSearch') {
                    openCmdDialog('symbol', activeCellIdRef.current, '');
                    return;
                }
                if (actionId === 'changeInterval') {
                    openCmdDialog('interval', activeCellIdRef.current, '');
                    return;
                }
                if (actionId === 'insertIndicator') {
                    openCmdDialog('indicators', activeCellIdRef.current, '');
                    return;
                }
                active()?.exec(actionId);
            },
            setInterval: (resolution) => {
                active()?.setInterval(resolution);
                handleIntervalChanged(activeCellIdRef.current, resolution);
            },
            setChartType: (type) => {
                active()?.setChartType(type);
                const cellId = activeCellIdRef.current;
                const prev = cellsRef.current[cellId] ?? {};
                cellsRef.current = { ...cellsRef.current, [cellId]: { ...prev, chartType: type } };
                refreshActiveInfo(cellId);
                persistWindow();
            },
            undo: () => active()?.undo(),
            redo: () => active()?.redo(),
            screenshot: () => void screenshotLayout(),
        };
    }, [handleIntervalChanged, openCmdDialog, persistWindow, refreshActiveInfo, screenshotLayout]);

    /**
     * Teclas con el foco fuera de los iframes (toolbar, barra, bordes):
     * abrir el diálogo ÚNICO de la ventana para la celda enfocada
     * (dígito → cambio de intervalo; letra → búsqueda de símbolo).
     */
    const handleRootKeyDown = useCallback((e: React.KeyboardEvent) => {
        const target = e.target as HTMLElement;
        if (target.closest('input, textarea, [contenteditable]')) return;
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            setSaveSignal((s) => s + 1);
            return;
        }
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        if (/^[0-9]$/.test(e.key)) {
            e.preventDefault();
            openCmdDialog('interval', activeCellIdRef.current, e.key);
        } else if (/^[a-zA-Z]$/.test(e.key)) {
            e.preventDefault();
            openCmdDialog('symbol', activeCellIdRef.current, e.key.toUpperCase());
        }
    }, [openCmdDialog]);

    /**
     * Payload completo del diseño (mismo shape que el componentState), con los
     * snapshots recién congelados: el guardado incluye el último dibujo aunque
     * el autosave de la CL aún no haya saltado.
     */
    const getDesignPayload = useCallback(async () => {
        await flushCellSnapshots();
        return {
            layoutId: layoutIdRef.current,
            cells: cellsRef.current,
            sync: syncRef.current,
        };
    }, [flushCellSnapshots]);

    /** Payload por defecto para "Crear nuevo diseño" (1 celda, símbolo actual). */
    const getFreshPayload = useCallback(
        () => ({
            layoutId: 's',
            cells: {
                'cell-1': {
                    symbol: cellsRef.current[activeCellIdRef.current]?.symbol ?? fallbackSymbol,
                },
            },
            sync: { ...DEFAULT_SYNC_FLAGS, symbol: false, interval: false },
        }),
        [fallbackSymbol],
    );

    /** Cargar un diseño guardado (o estado sin nombre con meta=null):
     *  reemplaza layout+celdas y remonta la rejilla. */
    const applyDesign = useCallback((payload: object, meta: ActiveDesign | null) => {
        const p = payload as { layoutId?: string; cells?: Record<string, TVCellPersisted>; sync?: SyncFlags };
        cellsRef.current = p.cells ?? {};
        setLayoutId(p.layoutId && p.layoutId in TV_LAYOUTS ? p.layoutId : 's');
        if (p.sync) setSync(p.sync);
        setActiveDesign(meta);
        setActiveCellId('cell-1');
        setDesignEpoch((e) => e + 1);
        // El epoch remonta la rejilla entera: volver a escalonar el montaje.
        setMountedIds(new Set());
        // Recién cargado = sin cambios pendientes (ventana de gracia mientras
        // las celdas remontan y disparan sus persists de inicialización).
        cleanUntilRef.current = Date.now() + 6000;
        persistWindow();
    }, [persistWindow]);

    // ── Restauración por usuario al abrir ventana NUEVA (flujo TV: siempre
    // vuelves a donde estabas) ────────────────────────────────────────────
    useEffect(() => {
        if (!freshWindowRef.current) return;
        let finished = false;
        const finish = () => {
            if (!finished) {
                finished = true;
                setRestoring(false);
            }
        };
        // El backend no puede bloquear la ventana: tope de espera.
        const timeout = setTimeout(finish, 3500);
        void (async () => {
            try {
                const last = await tvDesignsApi.getLast(getTokenRef.current);
                if (finished) return;
                const explicit = initialSymbol?.toUpperCase() || null;
                if (last.designId && last.designName) {
                    const payload = await tvDesignsApi.getPayload(getTokenRef.current, last.designId);
                    if (finished) return;
                    if (explicit) pendingSymbolRef.current = explicit;
                    applyDesign(payload, { id: last.designId, name: last.designName });
                } else if (last.payload) {
                    if (explicit) pendingSymbolRef.current = explicit;
                    applyDesign(last.payload, null);
                }
            } catch { /* sin sesión o backend caído: estado por defecto */ }
            clearTimeout(timeout);
            finish();
        })();
        return () => {
            clearTimeout(timeout);
            finished = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Ajustes de usuario del chart: el modo de sync de dibujos se carga
    // del backend al montar (independiente del diseño; el componentState es
    // solo cache templada) ────────────────────────────────────────────────
    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const settings = await tvDesignsApi.getSettings(getTokenRef.current);
                const mode = settings?.drawingsSync as DrawingsSyncMode | undefined;
                if (cancelled || !mode || !['off', 'layout', 'global'].includes(mode)) return;
                if (mode !== drawingsSyncRef.current) {
                    setDrawingsSync(mode);
                    drawingsSyncRef.current = mode;
                }
                if (mode === 'global') {
                    for (const cellId of Object.keys(cellApisRef.current)) {
                        void applyGlobalDrawings(cellId);
                    }
                }
            } catch { /* offline o sin sesión: se queda el cache local */ }
        })();
        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Mantener /last al día (por usuario, en el backend) ────────────────
    // Habilitado solo tras la inicialización para no pisar el estado real.
    const initSyncRef = useRef(false);
    useEffect(() => {
        if (!restoring) initSyncRef.current = true;
    }, [restoring]);

    // Puntero al diseño activo. Con varias ventanas TVC gana la última en
    // escribir (mismo modelo que tradingview.com con su "último layout").
    useEffect(() => {
        if (!initSyncRef.current || !activeDesign) return;
        tvDesignsApi.setLast(getTokenRef.current, { designId: activeDesign.id }).catch(() => { /* offline */ });
    }, [activeDesign]);

    // Estado sin nombre: autosave del último estado con debounce.
    useEffect(() => {
        if (!initSyncRef.current || activeDesign) return;
        const t = setTimeout(() => {
            void (async () => {
                try {
                    await tvDesignsApi.setLast(getTokenRef.current, { payload: await getDesignPayload() });
                } catch { /* offline */ }
            })();
        }, 8000);
        return () => clearTimeout(t);
    }, [stateVersion, activeDesign, getDesignPayload]);

    // Al cerrar la ventana sin diseño activo: volcado final del estado sin
    // nombre (cellsRef está razonablemente fresco: los cambios de símbolo/
    // intervalo persisten al instante y el autosave de la CL corre cada 5 s).
    useEffect(() => () => {
        if (!initSyncRef.current || activeDesignRef.current) return;
        tvDesignsApi.setLast(getTokenRef.current, {
            payload: {
                layoutId: layoutIdRef.current,
                cells: cellsRef.current,
                sync: syncRef.current,
            },
        }).catch(() => { /* offline */ });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
        <div
            ref={contentRootRef}
            tabIndex={-1}
            className="relative flex h-full w-full flex-col outline-none"
            onKeyDown={handleRootKeyDown}
        >
            <TVToolbar
                symbol={activeInfo.symbol}
                interval={activeInfo.interval}
                chartType={activeInfo.chartType}
                actions={toolbarActions}
                layoutId={layoutId}
                layoutButtonRef={pickerButtonRef}
                onLayoutClick={() => setPickerOpen((v) => !v)}
                designManager={
                    <TVDesignManager
                        activeDesign={activeDesign}
                        dirty={stateVersion !== savedVersion}
                        autoSave={autoSaveDesign}
                        onAutoSaveChange={setAutoSaveDesign}
                        getPayload={getDesignPayload}
                        getFreshPayload={getFreshPayload}
                        applyDesign={applyDesign}
                        onActiveDesignChange={setActiveDesign}
                        onSaved={() => setSavedVersion(stateVersion)}
                        saveSignal={saveSignal}
                    />
                }
            />

            <TVLayoutPicker
                anchorEl={pickerButtonRef.current}
                isOpen={pickerOpen}
                onClose={() => setPickerOpen(false)}
                activeLayoutId={layoutId}
                onPick={handlePickLayout}
                sync={sync}
                onToggleSync={handleToggleSync}
                syncEnabled={cellCount > 1}
            />

            <div className="flex min-h-0 flex-1">
                <TVDrawingBar
                    getActiveCell={() => cellApisRef.current[activeCellIdRef.current] ?? null}
                    getCells={() =>
                        Object.values(cellApisRef.current).filter(
                            (api): api is TVChartCellApi => api != null,
                        )
                    }
                    getCellById={(id) => cellApisRef.current[id] ?? null}
                    readyCell={readyCell}
                    drawingsSync={drawingsSync}
                    onDrawingsSyncChange={handleDrawingsSyncChange}
                    escSignal={escSignal}
                />

                {/* Columna del chart: rejilla + barra inferior. La barra vive
                    AQUÍ dentro, no como pie de la ventana: en tradingview.com
                    la toolbar vertical ocupa toda la altura (x:0 → abajo del
                    todo) y la barra inferior arranca a su derecha (x:56, ya
                    dentro de `layout__area--center`). Colgarla del root la
                    haría cruzar por debajo de TVDrawingBar. */}
                <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                    {/* Rejilla PLANA de los 55 layouts TV (celdas absolutas con key
                        estable): cambiar de layout no remonta las supervivientes —
                        solo cambian estilos y se monta/desmonta el delta. La key
                        lleva SOLO el epoch: cargar un diseño sí remonta todo
                        (savedState nuevo); cambiar de layout, nunca.
                        Durante la restauración de /last no se montan celdas. */}
                    <div ref={gridRootRef} className="min-h-0 min-w-0 flex-1">
                        {!restoring && <TVLayoutGrid
                            key={`epoch-${designEpoch}`}
                            layoutId={layoutId}
                            maximizedIndex={maximizedIndex}
                            renderCell={(cellIndex) => {
                                const cellId = `cell-${cellIndex + 1}`;
                                const snap = cellsRef.current[cellId];
                                const isActive = cellCount > 1 && cellId === activeCellId;
                                if (!mountedIds.has(cellId)) {
                                    // Turno de montaje aún no llegó: placeholder.
                                    return (
                                        <div
                                            data-cell-id={cellId}
                                            style={{
                                                width: '100%',
                                                height: '100%',
                                                background: 'var(--color-bg, #0d1117)',
                                                outline: '1px solid transparent',
                                                outlineOffset: -1,
                                            }}
                                        />
                                    );
                                }
                                return (
                                    <div
                                        data-cell-id={cellId}
                                        style={{
                                            width: '100%',
                                            height: '100%',
                                            minWidth: 0,
                                            minHeight: 0,
                                            outline: isActive
                                                ? '1px solid var(--color-accent, #2962ff)'
                                                : '1px solid transparent',
                                            outlineOffset: -1,
                                        }}
                                    >
                                        <TVChartCell
                                            ref={registerCellApi(cellId)}
                                            cellId={cellId}
                                            initialSymbol={symbolForNewCell(cellId)}
                                            initialInterval={snap?.interval ?? DEFAULT_TV_INTERVAL}
                                            savedState={snap?.tvState}
                                            onPersist={handleCellPersist}
                                            onSymbolChanged={handleSymbolChanged}
                                            onIntervalChanged={handleIntervalChanged}
                                            onActivate={handleActivate}
                                            onDrawingEvent={handleDrawingEvent}
                                            onEscape={handleCellEscape}
                                            onSaveShortcut={handleCellSaveShortcut}
                                            onReady={handleCellReady}
                                            onOpenSymbolSearch={(id, seed) => openCmdDialog('symbol', id, seed)}
                                            onOpenIntervalDialog={(id, seed) => openCmdDialog('interval', id, seed)}
                                        />
                                    </div>
                                );
                            }}
                        />}
                    </div>

                    <TVBottomBar
                        cellCount={cellCount}
                        maximized={maximizedIndex !== null}
                        onToggleMaximize={handleToggleMaximize}
                    />
                </div>
            </div>

            {/* Diálogos únicos de la ventana (centrados sobre el conjunto). */}
            {cmdDialog?.kind === 'symbol' && (
                <TVSymbolSearchDialog
                    seed={cmdDialog.seed}
                    onClose={closeCmdDialog}
                    onPick={applyCmdSymbol}
                />
            )}
            {cmdDialog?.kind === 'interval' && (
                <TVIntervalDialog
                    seed={cmdDialog.seed}
                    onClose={closeCmdDialog}
                    onApply={applyCmdInterval}
                />
            )}
            {cmdDialog?.kind === 'indicators' && (
                <TVIndicatorsDialog
                    studies={Array.from(new Set([
                        // Custom de Tradeul primero (por si getStudiesList no
                        // los incluye en esta versión).
                        'RVOL Volumen Relativo',
                        ...(cellApisRef.current[cmdDialog.cellId]?.listStudies() ?? []),
                    ]))}
                    onClose={closeCmdDialog}
                    onAdd={(name) => cellApisRef.current[cmdDialog.cellId]?.addStudy(name)}
                />
            )}
        </div>
    );
}
