'use client';

/**
 * TimeAndSalesContent — ventana flotante de Time & Sales (el tape).
 *
 * Columnas: Ticker · Time · Price · Size · Mkt · Cond (configurables).
 * - Color por dirección de tick (uptick verde / downtick rojo / flat neutro).
 * - Flash de fila nueva (toggle), milisegundos (toggle).
 * - Decodificación de conditions y market centers con tooltips
 *   (IDs numéricos de Polygon → letras SIP + nombre, vía tapeReference).
 * - Badges: DP (dark pool / FINRA TRF), subasta (open/close prints),
 *   extended hours; prints que no actualizan el last van atenuados.
 * - Filtros: size mínimo, ocultar odd lots, solo dark pool.
 * - Pausa automática al hacer scroll (chip para volver al directo).
 *
 * El estado (símbolo, columnas, filtros) persiste por ventana vía
 * useWindowState (se restaura al reabrir el workspace).
 */

import React, { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Settings2, Pause, ArrowUpToLine, CircleDot } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { useLinkGroupSubscription } from '@/hooks/useLinkGroup';
import { useTapeData, type TapeRow } from '@/hooks/useTapeData';
import { getTapeDecoder, TapeDecoder } from '@/lib/tapeReference';

// ============================================================================
// Settings (persistidos por ventana)
// ============================================================================

type ColumnKey = 'ticker' | 'time' | 'price' | 'size' | 'market' | 'condition';

interface TapeSettings {
    symbol?: string;
    flash?: boolean;
    showMs?: boolean;
    columns?: Partial<Record<ColumnKey, boolean>>;
    minSize?: number;
    hideOddLots?: boolean;
    darkPoolOnly?: boolean;
    dimNoUpdate?: boolean;
    // WindowComponentState exige index signature (estado serializable genérico)
    [key: string]: unknown;
}

const DEFAULT_COLUMNS: Record<ColumnKey, boolean> = {
    ticker: false,
    time: true,
    price: true,
    size: true,
    market: true,
    condition: true,
};

/**
 * Alto exacto de fila (px). Es fijo, así que el virtualizador no necesita medir:
 * estimateSize devuelve el valor real y no hay reflow de corrección.
 */
const ROW_H = 22;
/** Filas extra fuera del viewport que se pre-renderizan. */
const OVERSCAN = 12;
/** Antigüedad máxima de un print para que su fila haga flash (ms). */
const FLASH_WINDOW_MS = 500;

// ============================================================================
// Formateo
// ============================================================================

// Formatters de hora NY cacheados (crearlos por fila es carísimo)
const timeFmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
});

function formatTime(ms: number, showMs: boolean): string {
    const base = timeFmt.format(ms);
    if (!showMs) return base;
    return `${base}.${String(ms % 1000).padStart(3, '0')}`;
}

function formatPrice(p: number): string {
    return p.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: p < 1 ? 4 : 2,
    });
}

function formatSize(s: number): string {
    return s.toLocaleString('en-US');
}

// ============================================================================
// Fila
// ============================================================================

interface RowProps {
    row: TapeRow;
    symbol: string;
    decoder: TapeDecoder;
    columns: Record<ColumnKey, boolean>;
    gridTemplate: string;
    flash: boolean;
    showMs: boolean;
    dimNoUpdate: boolean;
    /** Posicionamiento absoluto que inyecta el virtualizador. */
    virtualStyle: CSSProperties;
}

const TapeRowView = memo(function TapeRowView({
    row, symbol, decoder, columns, gridTemplate, flash, showMs, dimNoUpdate, virtualStyle,
}: RowProps) {
    const isDP = decoder.isDarkPool(row.x, row.trfi);
    const noLast = decoder.isDimmedPrint(row.c);
    const isExt = decoder.isExtendedHours(row.c);
    const isAuction = decoder.isAuction(row.c);
    const isBlock = row.s >= 10_000;
    const isBig = row.s >= 2_000 && !isBlock;

    const priceColor =
        row.dir === 'up'
            ? 'text-[color:var(--color-tick-up)]'
            : row.dir === 'down'
                ? 'text-[color:var(--color-tick-down)]'
                : 'text-foreground/80';

    // Con la lista virtualizada una fila se monta cada vez que vuelve al
    // viewport, así que "montar" ya no equivale a "recién llegada": el flash se
    // acota por antigüedad real del print.
    const animation = flash && row.live && Date.now() - row.at < FLASH_WINDOW_MS
        ? row.dir === 'down' ? 'tas-flash-down 0.5s ease-out' : 'tas-flash-up 0.5s ease-out'
        : undefined;

    return (
        <div
            className={`grid items-center gap-x-2 px-2 h-[22px] text-[11.5px] leading-none font-mono border-b border-border/30 ${
                noLast && dimNoUpdate ? 'opacity-60' : ''
            } ${isBlock ? 'bg-primary/10' : ''}`}
            // `contain: strict` aísla layout/paint de cada fila: el navegador deja
            // de recalcular el árbol entero al entrar un lote. Es seguro aquí
            // porque la fila tiene alto fijo y no contiene overlays flotantes
            // (los tooltips son atributos `title` nativos).
            style={{ ...virtualStyle, gridTemplateColumns: gridTemplate, animation, contain: 'strict' }}
        >
            {columns.ticker && (
                <span className="truncate font-semibold text-primary">{symbol}</span>
            )}
            {columns.time && (
                <span className={`tabular-nums ${isExt ? 'text-amber-500/90' : 'text-muted-fg'}`}>
                    {formatTime(row.t, showMs)}
                </span>
            )}
            {columns.price && (
                <span className={`tabular-nums text-right font-semibold ${priceColor}`}>
                    {formatPrice(row.p)}
                </span>
            )}
            {columns.size && (
                <span className={`tabular-nums text-right ${
                    isBlock ? 'font-bold text-foreground' : isBig ? 'font-semibold text-foreground/90' : 'text-foreground/70'
                }`}>
                    {formatSize(row.s)}
                </span>
            )}
            {columns.market && (
                <span
                    className="text-center"
                    title={decoder.exchangeName(row.x, row.trfi)}
                >
                    {isDP ? (
                        <span className="inline-flex items-center gap-0.5 text-violet-400 font-semibold">
                            D<span className="text-[8px] rounded-sm bg-violet-500/15 px-0.5">DP</span>
                        </span>
                    ) : (
                        <span className="text-foreground/70">{decoder.exchangeLetter(row.x)}</span>
                    )}
                </span>
            )}
            {columns.condition && (
                <span
                    className={`truncate text-right ${isAuction ? 'text-sky-400 font-semibold' : 'text-muted-fg'}`}
                    title={decoder.conditionNames(row.c)}
                >
                    {decoder.conditionLetters(row.c)}
                </span>
            )}
        </div>
    );
});

// ============================================================================
// Componente principal
// ============================================================================

export function TimeAndSalesContent({ initialSymbol }: { initialSymbol?: string }) {
    const { t } = useTranslation();
    const { state, updateState } = useWindowState<TapeSettings>();

    const symbol = (state.symbol || initialSymbol || 'SPY').toUpperCase();
    const flash = state.flash ?? true;
    const showMs = state.showMs ?? false;
    const dimNoUpdate = state.dimNoUpdate ?? true;
    const minSize = state.minSize ?? 0;
    const hideOddLots = state.hideOddLots ?? false;
    const darkPoolOnly = state.darkPoolOnly ?? false;
    const columns = useMemo(
        () => ({ ...DEFAULT_COLUMNS, ...(state.columns || {}) }),
        [state.columns]
    );

    const [symbolInput, setSymbolInput] = useState(symbol);
    const [showSettings, setShowSettings] = useState(false);
    const [decoder, setDecoder] = useState<TapeDecoder>(() => new TapeDecoder(null));
    const [paused, setPaused] = useState(false);
    // Ancla de pausa: key de la fila superior al pausar. Las filas nuevas se
    // acumulan por encima del ancla (invisibles) y las páginas antiguas se
    // añaden por debajo, así el scroll no salta en ninguna dirección.
    const pauseAnchorRef = useRef<string | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);

    // Reference data (conditions/exchanges) — singleton compartido
    useEffect(() => {
        let mounted = true;
        getTapeDecoder().then((d) => { if (mounted) setDecoder(d); });
        return () => { mounted = false; };
    }, []);

    // Link groups: si la ventana está en un grupo, seguir el ticker difundido
    const broadcast = useLinkGroupSubscription();
    useEffect(() => {
        if (broadcast?.ticker && broadcast.ticker.toUpperCase() !== symbol) {
            const next = broadcast.ticker.toUpperCase();
            setSymbolInput(next);
            updateState({ symbol: next });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [broadcast]);

    useEffect(() => { setSymbolInput(symbol); }, [symbol]);

    const {
        rows, olderRows, atBufferCap, loading, loadingOlder, hasMore, loadOlder,
        error, isConnected, isLive, printsPerSecond,
    } = useTapeData({ symbol });

    // Buffer en vivo + páginas históricas del día (scroll infinito)
    const allRows = useMemo(
        () => (olderRows.length > 0 ? rows.concat(olderRows) : rows),
        [rows, olderRows]
    );

    // ── Filtros ──────────────────────────────────────────────────────────────
    const filteredRows = useMemo(() => {
        if (minSize <= 0 && !hideOddLots && !darkPoolOnly) return allRows;
        return allRows.filter((r) => {
            if (minSize > 0 && r.s < minSize) return false;
            if (hideOddLots && decoder.isOddLot(r.c, r.s)) return false;
            if (darkPoolOnly && !decoder.isDarkPool(r.x, r.trfi)) return false;
            return true;
        });
    }, [allRows, minSize, hideOddLots, darkPoolOnly, decoder]);

    // ── Pausa por scroll + carga de páginas antiguas al llegar al fondo ─────
    const handleScroll = useCallback(() => {
        const el = scrollRef.current;
        if (!el) return;
        const atTop = el.scrollTop < 8;
        if (!atTop && !pauseAnchorRef.current) {
            pauseAnchorRef.current = filteredRows[0]?.key ?? null;
            if (pauseAnchorRef.current) setPaused(true);
        } else if (atTop && pauseAnchorRef.current) {
            pauseAnchorRef.current = null;
            setPaused(false);
        }
        // Scroll infinito: a <300px del fondo, pedir la siguiente página del día
        if (hasMore && el.scrollHeight - el.scrollTop - el.clientHeight < 300) {
            loadOlder();
        }
    }, [filteredRows, hasMore, loadOlder]);

    const resumeLive = useCallback(() => {
        pauseAnchorRef.current = null;
        setPaused(false);
        scrollRef.current?.scrollTo({ top: 0 });
    }, []);

    // En pausa: recortar todo lo más nuevo que el ancla (se acumula arriba sin
    // mover el scroll). Si el ancla fue expulsada del buffer, volver al directo.
    let anchorIdx = 0;
    if (paused && pauseAnchorRef.current) {
        const idx = filteredRows.findIndex((r) => r.key === pauseAnchorRef.current);
        anchorIdx = idx > 0 ? idx : 0;
    }
    const displayRows = anchorIdx > 0 ? filteredRows.slice(anchorIdx) : filteredRows;
    const newSincePause = anchorIdx;

    // ── Virtualización ───────────────────────────────────────────────────────
    // Solo se montan las filas visibles (+OVERSCAN), como el resto de tablas del
    // terminal. Antes se pintaban 250 en vivo y hasta 3.000 en pausa: ~18.000
    // nodos DOM, un orden de magnitud por encima del umbral de error de
    // Lighthouse (~1.400) y del presupuesto de ~10 ms por frame.
    const rowVirtualizer = useVirtualizer({
        count: displayRows.length,
        getScrollElement: () => scrollRef.current,
        estimateSize: () => ROW_H,
        overscan: OVERSCAN,
        // Claves estables: sin esto, al anteponer filas el virtualizador
        // reutiliza por índice y las filas se ven "saltar" de contenido.
        getItemKey: (index) => displayRows[index]?.key ?? index,
    });
    const virtualItems = rowVirtualizer.getVirtualItems();

    // ── Grid template según columnas visibles ────────────────────────────────
    const gridTemplate = useMemo(() => {
        const parts: string[] = [];
        if (columns.ticker) parts.push('minmax(40px,0.7fr)');
        if (columns.time) parts.push(showMs ? 'minmax(86px,1.1fr)' : 'minmax(62px,0.9fr)');
        if (columns.price) parts.push('minmax(58px,1fr)');
        if (columns.size) parts.push('minmax(52px,0.9fr)');
        if (columns.market) parts.push('minmax(34px,0.5fr)');
        if (columns.condition) parts.push('minmax(44px,0.8fr)');
        return parts.join(' ');
    }, [columns, showMs]);

    const toggleColumn = useCallback((key: ColumnKey) => {
        updateState({ columns: { ...columns, [key]: !columns[key] } });
    }, [columns, updateState]);

    const COLUMN_LABELS: Record<ColumnKey, string> = {
        ticker: t('tape.colTicker'),
        time: t('tape.colTime'),
        price: t('tape.colPrice'),
        size: t('tape.colSize'),
        market: t('tape.colMarket'),
        condition: t('tape.colCondition'),
    };

    return (
        <div className="relative flex flex-col h-full bg-surface text-foreground select-none">
            {/* Keyframes del flash (autocontenidas en el componente) */}
            <style>{`
                @keyframes tas-flash-up { 0% { background-color: rgb(from var(--color-tick-up) r g b / 0.28); } 100% { background-color: transparent; } }
                @keyframes tas-flash-down { 0% { background-color: rgb(from var(--color-tick-down) r g b / 0.28); } 100% { background-color: transparent; } }
            `}</style>

            {/* ── Barra de búsqueda (la cabecera estándar de la ventana pone
                   cierre / pop-out / grupo de link) ───────────────────────── */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border bg-surface-inset/60 shrink-0">
                <TickerSearch
                    value={symbolInput}
                    onChange={setSymbolInput}
                    onSelect={(tk) => {
                        const next = tk.symbol.toUpperCase();
                        setSymbolInput(next);
                        if (next !== symbol) updateState({ symbol: next });
                    }}
                    placeholder={t('tape.symbol')}
                    className="flex-1"
                    autoFocus={false}
                />
                <span className="font-mono font-bold text-sm text-primary shrink-0">{symbol}</span>
                <span
                    className={`inline-flex items-center gap-1 text-[10px] ${
                        isLive ? 'text-[color:var(--color-tick-up)]' : isConnected ? 'text-amber-500' : 'text-muted-fg'
                    }`}
                    title={isLive ? t('tape.live') : isConnected ? t('tape.waiting') : t('tape.disconnected')}
                >
                    <CircleDot size={9} className={isLive ? 'animate-pulse' : ''} />
                    {isLive && printsPerSecond > 0 ? `${printsPerSecond}/s` : ''}
                </span>
                <div className="flex-1" />
                <button
                    onClick={() => setShowSettings((v) => !v)}
                    className={`p-1 rounded hover:bg-surface-hover ${showSettings ? 'text-primary' : 'text-muted-fg'}`}
                    title={t('tape.settings')}
                >
                    <Settings2 size={14} />
                </button>
            </div>

            {/* ── Panel de settings ───────────────────────────────────────── */}
            {showSettings && (
                <div className="px-3 py-2 border-b border-border bg-surface-inset/40 text-[11px] space-y-2 shrink-0">
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="checkbox" checked={flash} onChange={() => updateState({ flash: !flash })} />
                            {t('tape.flash')}
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="checkbox" checked={showMs} onChange={() => updateState({ showMs: !showMs })} />
                            {t('tape.showMs')}
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="checkbox" checked={dimNoUpdate} onChange={() => updateState({ dimNoUpdate: !dimNoUpdate })} />
                            {t('tape.dimNoUpdate')}
                        </label>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 items-center">
                        <label className="flex items-center gap-1.5">
                            {t('tape.minSize')}
                            <input
                                type="number"
                                min={0}
                                step={100}
                                value={minSize || ''}
                                placeholder="0"
                                onChange={(e) => updateState({ minSize: Math.max(0, Number(e.target.value) || 0) })}
                                className="w-16 bg-surface border border-border rounded px-1 py-0.5 font-mono text-right"
                            />
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="checkbox" checked={hideOddLots} onChange={() => updateState({ hideOddLots: !hideOddLots })} />
                            {t('tape.hideOddLots')}
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="checkbox" checked={darkPoolOnly} onChange={() => updateState({ darkPoolOnly: !darkPoolOnly })} />
                            {t('tape.darkPoolOnly')}
                        </label>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-border/50">
                        {(Object.keys(DEFAULT_COLUMNS) as ColumnKey[]).map((key) => (
                            <label key={key} className="flex items-center gap-1.5 cursor-pointer">
                                <input type="checkbox" checked={columns[key]} onChange={() => toggleColumn(key)} />
                                {COLUMN_LABELS[key]}
                            </label>
                        ))}
                    </div>
                </div>
            )}

            {/* ── Cabecera de columnas ────────────────────────────────────── */}
            <div
                className="grid gap-x-2 px-2 h-6 items-center text-[9.5px] font-semibold uppercase tracking-wider text-muted-fg border-b border-border bg-surface-inset/30 shrink-0"
                style={{ gridTemplateColumns: gridTemplate }}
            >
                {columns.ticker && <span>{COLUMN_LABELS.ticker}</span>}
                {columns.time && <span>{COLUMN_LABELS.time}</span>}
                {columns.price && <span className="text-right">{COLUMN_LABELS.price}</span>}
                {columns.size && <span className="text-right">{COLUMN_LABELS.size}</span>}
                {columns.market && <span className="text-center">{COLUMN_LABELS.market}</span>}
                {columns.condition && <span className="text-right">{COLUMN_LABELS.condition}</span>}
            </div>

            {/* ── Tape ────────────────────────────────────────────────────── */}
            <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto overflow-x-hidden relative">
                {loading && rows.length === 0 && (
                    <div className="flex items-center justify-center h-24 text-xs text-muted-fg">
                        {t('tape.loading')}
                    </div>
                )}
                {!loading && displayRows.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-24 gap-1 text-xs text-muted-fg">
                        <span>{t('tape.empty')}</span>
                        {error === 'backfill_failed' && <span className="text-[10px]">{t('tape.backfillFailed')}</span>}
                    </div>
                )}
                {displayRows.length > 0 && (
                    <div className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
                        {virtualItems.map((vi) => {
                            const row = displayRows[vi.index];
                            if (!row) return null;
                            return (
                                <TapeRowView
                                    key={row.key}
                                    row={row}
                                    symbol={symbol}
                                    decoder={decoder}
                                    columns={columns}
                                    gridTemplate={gridTemplate}
                                    flash={flash}
                                    showMs={showMs}
                                    dimNoUpdate={dimNoUpdate}
                                    virtualStyle={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        width: '100%',
                                        height: vi.size,
                                        transform: `translateY(${vi.start}px)`,
                                    }}
                                />
                            );
                        })}
                    </div>
                )}
                {displayRows.length > 0 && loadingOlder && (
                    <div className="flex items-center justify-center h-7 text-[10px] text-muted-fg animate-pulse">
                        {t('tape.loadingMore')}
                    </div>
                )}
                {displayRows.length > 0 && !loadingOlder && (atBufferCap || !hasMore) && (
                    <div className="flex items-center justify-center h-7 text-[10px] text-muted-fg/60">
                        — {atBufferCap ? t('tape.bufferCap') : t('tape.dayStart')} —
                    </div>
                )}
            </div>

            {/* ── Chip de pausa ───────────────────────────────────────────── */}
            {paused && (
                <button
                    onClick={resumeLive}
                    className="absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary text-white text-[11px] font-semibold shadow-lg hover:opacity-90"
                >
                    <ArrowUpToLine size={12} />
                    {newSincePause > 0 ? t('tape.resumeWithCount', { count: newSincePause }) : t('tape.resume')}
                </button>
            )}

            {/* ── Footer ──────────────────────────────────────────────────── */}
            <div className="flex items-center justify-between px-2 h-5 text-[9.5px] text-muted-fg border-t border-border bg-surface-inset/30 shrink-0">
                <span>
                    {paused ? (
                        <span className="inline-flex items-center gap-1 text-amber-500">
                            <Pause size={9} /> {t('tape.paused')}
                        </span>
                    ) : (
                        t('tape.printCount', { count: filteredRows.length })
                    )}
                </span>
                <span className="font-mono">{t('tape.timezone')}</span>
            </div>
        </div>
    );
}
