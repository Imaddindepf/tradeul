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
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { DEFAULT_SYNC_FLAGS, type SyncFlags } from '@/components/chart/multichart/types';
import { TV_LAYOUTS } from './tvLayouts';
import { TVLayoutGrid } from './TVLayoutGrid';
import { TVLayoutPicker } from './TVLayoutPicker';
import { TVChartCell, type TVChartCellApi, type TVCellSnapshot } from './TVChartCell';
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

    // Estado inicial: una sola lectura al montar la ventana.
    const initialRef = useRef<ReturnType<typeof normalizeState> | null>(null);
    if (initialRef.current === null) {
        const raw = (windowId ? getWindowComponentState(windowId) : undefined) as
            | TVWindowState
            | undefined;
        initialRef.current = normalizeState(raw, fallbackSymbol);
    }

    const [layoutId, setLayoutId] = useState<string>(initialRef.current.layoutId);
    const [sync, setSync] = useState<SyncFlags>(initialRef.current.sync);
    const [drawingsSync, setDrawingsSync] = useState<DrawingsSyncMode>('off');
    const [activeCellId, setActiveCellId] = useState('cell-1');
    const [pickerOpen, setPickerOpen] = useState(false);
    const pickerButtonRef = useRef<HTMLButtonElement>(null);

    // ESC desde los iframes → la barra de dibujo vuelve al cursor (flujo TV).
    const [escSignal, setEscSignal] = useState(0);
    const handleCellEscape = useCallback(() => setEscSignal((s) => s + 1), []);


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

    /** Persistir el estado completo de la ventana. */
    const persistWindow = useCallback(() => {
        const id = windowIdRef.current;
        if (!id) return;
        updateWindowComponentState(id, {
            layoutId: layoutIdRef.current,
            cells: cellsRef.current,
            sync: syncRef.current,
        });
    }, [updateWindowComponentState]);

    // Persistir cuando cambian layout o sync (los cambios de celda persisten solos).
    useEffect(() => {
        persistWindow();
    }, [layoutId, sync, persistWindow]);

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
    }, [persistWindow, refreshActiveInfo]);

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

    const handleActivate = useCallback((cellId: string) => {
        setActiveCellId(cellId);
        const snap = cellsRef.current[cellId];
        setActiveInfo({
            symbol: snap?.symbol ?? DEFAULT_SYMBOL,
            interval: snap?.interval ?? DEFAULT_TV_INTERVAL,
            chartType: snap?.chartType ?? DEFAULT_CHART_TYPE,
        });
    }, []);

    const handlePickLayout = useCallback((id: string) => {
        setPickerOpen(false);
        setLayoutId(id);
        // Las celdas que desaparecen conservan su snapshot en cellsRef: si el
        // usuario vuelve a un layout mayor, recupera su chart tal cual.
    }, []);

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

    const registerCellApi = useCallback((cellId: string) => (api: TVChartCellApi | null) => {
        cellApisRef.current[cellId] = api;
    }, []);

    // Sincronización de dibujos nuevos (globo): al dibujar en una celda,
    // replicar el estado de dibujos en las demás celdas del MISMO símbolo.
    const drawingsSyncRef = useRef(drawingsSync);
    drawingsSyncRef.current = drawingsSync;
    const drawingSyncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const handleDrawingEvent = useCallback((cellId: string) => {
        if (drawingsSyncRef.current === 'off') return;
        if (drawingSyncTimerRef.current) clearTimeout(drawingSyncTimerRef.current);
        drawingSyncTimerRef.current = setTimeout(async () => {
            const source = cellApisRef.current[cellId];
            const sourceSymbol = cellsRef.current[cellId]?.symbol;
            if (!source || !sourceSymbol) return;
            const state = await source.getDrawingsState();
            if (!state) return;
            for (const [otherId, api] of Object.entries(cellApisRef.current)) {
                if (otherId === cellId || !api) continue;
                if (cellsRef.current[otherId]?.symbol !== sourceSymbol) continue;
                void api.applyDrawingsState(state);
            }
        }, 350);
    }, []);

    /** Símbolo con el que arranca una celda nueva (sin snapshot previo). */
    const symbolForNewCell = useCallback((cellId: string): string => {
        const snap = cellsRef.current[cellId];
        if (snap?.symbol) return snap.symbol;
        return cellsRef.current[activeCellIdRef.current]?.symbol ?? fallbackSymbol;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fallbackSymbol]);

    // Acciones de la toolbar → celda enfocada.
    const toolbarActions: TVToolbarActions = useMemo(() => {
        const active = () => cellApisRef.current[activeCellIdRef.current];
        return {
            exec: (actionId) => active()?.exec(actionId),
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
            screenshot: () => active()?.screenshot(),
        };
    }, [handleIntervalChanged, persistWindow, refreshActiveInfo]);

    /**
     * Teclas con el foco fuera de los iframes (toolbar, barra, bordes):
     * abrir los diálogos NATIVOS de la librería en la celda enfocada
     * (dígito → cambio de intervalo; letra → búsqueda de símbolo).
     */
    const handleRootKeyDown = useCallback((e: React.KeyboardEvent) => {
        const target = e.target as HTMLElement;
        if (target.closest('input, textarea, [contenteditable]')) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        const api = cellApisRef.current[activeCellIdRef.current];
        if (/^[0-9]$/.test(e.key)) {
            e.preventDefault();
            api?.exec('changeInterval');
        } else if (/^[a-zA-Z]$/.test(e.key)) {
            e.preventDefault();
            api?.exec('symbolSearch');
        }
    }, []);

    return (
        <div className="relative flex h-full w-full flex-col" onKeyDown={handleRootKeyDown}>
            <TVToolbar
                symbol={activeInfo.symbol}
                interval={activeInfo.interval}
                chartType={activeInfo.chartType}
                actions={toolbarActions}
                layoutId={layoutId}
                layoutButtonRef={pickerButtonRef}
                onLayoutClick={() => setPickerOpen((v) => !v)}
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
                    drawingsSync={drawingsSync}
                    onDrawingsSyncChange={setDrawingsSync}
                    escSignal={escSignal}
                />

                {/* Rejilla recursiva (árbol de partición de los 55 layouts TV) */}
                <div className="min-h-0 min-w-0 flex-1">
                    <TVLayoutGrid
                        key={layoutId}
                        layoutId={layoutId}
                        renderCell={(cellIndex) => {
                            const cellId = `cell-${cellIndex + 1}`;
                            const snap = cellsRef.current[cellId];
                            const isActive = cellCount > 1 && cellId === activeCellId;
                            return (
                                <div
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
                                    />
                                </div>
                            );
                        }}
                    />
                </div>
            </div>
        </div>
    );
}
