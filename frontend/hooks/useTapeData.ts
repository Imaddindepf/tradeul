'use client';

/**
 * useTapeData — flujo de prints (Time & Sales) de un ticker.
 *
 * Fuentes:
 *  1. Backfill REST al abrir/cambiar símbolo: /api/v1/tape/{sym}/backfill
 *  2. Tiempo real: subscribe_tape por el WebSocket compartido; el servidor
 *     manda lotes tape_trades (~100ms) con prints crudos de Polygon.
 *
 * Los prints se guardan más-reciente-primero, con dirección de tick calculada
 * cronológicamente (uptick/downtick vs el print anterior) y clave estable por
 * fila para que el flash de fila nueva solo se dispare al montar.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { isTapeTradesMsg, type TapePrint } from '@/lib/wsContracts';
import { acquireStream, releaseStream } from '@/lib/chartStreams';
import { useAuthFetch } from '@/hooks/useAuthFetch';

export type TickDirection = 'up' | 'down' | 'flat';

export interface TapeRow extends TapePrint {
    /** Clave estable de fila (para React y para dedupe backfill/live). */
    key: string;
    /** Dirección vs el print anterior en orden cronológico. */
    dir: TickDirection;
    /** true solo para prints llegados por WS después del render inicial. */
    live: boolean;
}

interface UseTapeDataOptions {
    symbol: string;
    /** Máximo de filas retenidas en memoria (buffer circular). */
    maxRows?: number;
    /** Prints a pedir en el backfill inicial. */
    backfillLimit?: number;
    enabled?: boolean;
}

interface UseTapeDataReturn {
    rows: TapeRow[];
    /** Páginas históricas del día cargadas al hacer scroll (más antiguas que rows). */
    olderRows: TapeRow[];
    loading: boolean;
    /** true mientras se carga una página más antigua. */
    loadingOlder: boolean;
    /** false cuando ya se llegó al inicio del día. */
    hasMore: boolean;
    /** Pide la siguiente página de prints más antiguos (scroll infinito). */
    loadOlder: () => void;
    error: string | null;
    isConnected: boolean;
    /** true cuando ya llegó al menos un lote en vivo del símbolo actual. */
    isLive: boolean;
    /** prints/segundo aproximados (ventana móvil de 5s). */
    printsPerSecond: number;
    clear: () => void;
}

const DEFAULT_MAX_ROWS = 2000;
const DEFAULT_BACKFILL = 300;

function printKey(p: TapePrint): string {
    // id de trade + exchange es único por día; fallback a t/q/p/s.
    return `${p.i ?? ''}|${p.x ?? ''}|${p.t}|${p.q ?? ''}|${p.p}|${p.s}`;
}

export function useTapeData({
    symbol,
    maxRows = DEFAULT_MAX_ROWS,
    backfillLimit = DEFAULT_BACKFILL,
    enabled = true,
}: UseTapeDataOptions): UseTapeDataReturn {
    const { isConnected, messages$, send } = useWebSocket();
    const { authFetchJson } = useAuthFetch();

    const [rows, setRows] = useState<TapeRow[]>([]);
    const [olderRows, setOlderRows] = useState<TapeRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadingOlder, setLoadingOlder] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isLive, setIsLive] = useState(false);
    const [printsPerSecond, setPrintsPerSecond] = useState(0);
    const loadingOlderRef = useRef(false);

    const symbolRef = useRef(symbol);
    symbolRef.current = symbol;

    // Último precio en orden CRONOLÓGICO (para dirección del siguiente print)
    const lastPriceRef = useRef<number | null>(null);
    // Dedupe entre backfill y primeros lotes en vivo
    const seenKeysRef = useRef<Set<string>>(new Set());
    // Ventana móvil para prints/s
    const rateWindowRef = useRef<number[]>([]);

    const computeDir = useCallback((price: number): TickDirection => {
        const last = lastPriceRef.current;
        lastPriceRef.current = price;
        if (last == null || price === last) return 'flat';
        return price > last ? 'up' : 'down';
    }, []);

    const clear = useCallback(() => {
        setRows([]);
        setOlderRows([]);
        setHasMore(true);
        setLoadingOlder(false);
        loadingOlderRef.current = false;
        lastPriceRef.current = null;
        seenKeysRef.current = new Set();
        rateWindowRef.current = [];
        setIsLive(false);
        setPrintsPerSecond(0);
    }, []);

    /** Convierte una página desc de prints en TapeRows con dir local. */
    const buildRowsFromPage = useCallback((prints: TapePrint[], dedupe: boolean): TapeRow[] => {
        const built: TapeRow[] = [];
        let localLast: number | null = null;
        for (let idx = prints.length - 1; idx >= 0; idx--) {
            const p = prints[idx];
            const key = printKey(p);
            if (dedupe && seenKeysRef.current.has(key)) continue;
            seenKeysRef.current.add(key);
            const dir: TickDirection =
                localLast == null || p.p === localLast ? 'flat' : p.p > localLast ? 'up' : 'down';
            localLast = p.p;
            built.push({ ...p, key, dir, live: false });
        }
        built.reverse(); // asc → desc (más reciente primero)
        return built;
    }, []);

    // ── Backfill al abrir / cambiar símbolo ──────────────────────────────────
    useEffect(() => {
        if (!symbol || !enabled) return;
        let cancelled = false;

        clear();
        setLoading(true);
        setError(null);

        (async () => {
            try {
                const resp = await authFetchJson<{ prints: TapePrint[] }>(
                    `/api/v1/tape/${encodeURIComponent(symbol)}/backfill?limit=${backfillLimit}`
                );
                if (cancelled || symbolRef.current !== symbol) return;

                // El backfill llega desc (más reciente primero). La dirección
                // se calcula con una cadena LOCAL: si ya entraron prints en
                // vivo (más nuevos), su lastPrice no debe ser pisado por
                // precios antiguos del backfill.
                const prints = resp?.prints ?? [];
                const built = buildRowsFromPage(prints, true);
                if (lastPriceRef.current == null && built.length > 0) {
                    lastPriceRef.current = built[0].p;
                }
                setHasMore((resp as any)?.has_more ?? prints.length >= backfillLimit);
                // Los prints en vivo que llegaron antes que el backfill son más
                // recientes: van delante.
                setRows((prev) => (prev.length ? [...prev, ...built] : built));
            } catch (e) {
                if (!cancelled) {
                    // Sin backfill la ventana sigue sirviendo (solo tiempo real)
                    setError('backfill_failed');
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();

        return () => {
            cancelled = true;
        };
        // authFetchJson es estable (useCallback en useAuthFetch)
    }, [symbol, enabled, backfillLimit, authFetchJson, clear, computeDir]);

    // ── Scroll infinito: páginas más antiguas del día ────────────────────────
    const rowsRef = useRef(rows);
    rowsRef.current = rows;
    const olderRowsRef = useRef(olderRows);
    olderRowsRef.current = olderRows;

    const loadOlder = useCallback(() => {
        if (loadingOlderRef.current || !symbolRef.current) return;
        const older = olderRowsRef.current;
        const live = rowsRef.current;
        const oldest = older.length > 0 ? older[older.length - 1] : live[live.length - 1];
        if (!oldest) return;

        loadingOlderRef.current = true;
        setLoadingOlder(true);
        const requestedSymbol = symbolRef.current;

        (async () => {
            try {
                const resp = await authFetchJson<{ prints: TapePrint[]; has_more?: boolean }>(
                    `/api/v1/tape/${encodeURIComponent(requestedSymbol)}/backfill?limit=500&before=${oldest.t}`
                );
                if (symbolRef.current !== requestedSymbol) return; // cambió el símbolo
                const prints = resp?.prints ?? [];
                const built = buildRowsFromPage(prints, true);
                setHasMore(resp?.has_more ?? prints.length >= 500);
                if (built.length > 0) {
                    setOlderRows((prev) => [...prev, ...built]);
                }
            } catch {
                // Silencioso: el usuario puede reintentar con más scroll
            } finally {
                loadingOlderRef.current = false;
                setLoadingOlder(false);
            }
        })();
    }, [authFetchJson, buildRowsFromPage]);

    // ── Suscripción en tiempo real ───────────────────────────────────────────
    useEffect(() => {
        if (!symbol || !enabled || !isConnected) return;

        // Refcount global (lib/chartStreams): dos ventanas TAS del mismo
        // símbolo comparten conexión; un unsubscribe directo mataría el
        // stream de la otra (el servidor no lleva contador por símbolo).
        acquireStream(send, 'tape', symbol);

        const subscription = messages$.subscribe({
            next: (message: any) => {
                if (!isTapeTradesMsg(message)) return;
                if (message.symbol !== symbolRef.current) return;

                const batch = message.data; // orden cronológico (asc) dentro del lote
                const fresh: TapeRow[] = [];
                for (const p of batch) {
                    const key = printKey(p);
                    if (seenKeysRef.current.has(key)) continue;
                    seenKeysRef.current.add(key);
                    fresh.push({ ...p, key, dir: computeDir(p.p), live: true });
                }
                if (fresh.length === 0) return;

                // Cap del set de dedupe (solo necesita cubrir el solape
                // backfill ↔ primeros lotes; 5k llaves ≈ nada de memoria)
                if (seenKeysRef.current.size > 5000) {
                    seenKeysRef.current = new Set(Array.from(seenKeysRef.current).slice(-2000));
                }

                // prints/s: ventana móvil de 5s
                const now = Date.now();
                const win = rateWindowRef.current;
                for (const _ of fresh) win.push(now);
                while (win.length > 0 && win[0] < now - 5000) win.shift();
                setPrintsPerSecond(Math.round(win.length / 5));

                setIsLive(true);
                setRows((prev) => {
                    // fresh está asc → invertir para prepend (más reciente primero)
                    const next = fresh.slice().reverse().concat(prev);
                    return next.length > maxRows ? next.slice(0, maxRows) : next;
                });
            },
        });

        return () => {
            subscription.unsubscribe();
            releaseStream(send, 'tape', symbol);
            setIsLive(false);
        };
    }, [symbol, enabled, isConnected, messages$, send, maxRows, computeDir]);

    return { rows, olderRows, loading, loadingOlder, hasMore, loadOlder, error, isConnected, isLive, printsPerSecond, clear };
}
