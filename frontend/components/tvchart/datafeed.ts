/**
 * TradeulDatafeed — adaptador entre la TradingView Charting Library (v31) y
 * el pipeline de datos de Tradeul.
 *
 *  - Histórico:    GET /api/v1/chart/{symbol}?interval=X&limit=N[&before=T]
 *  - Tiempo real:  WS compartido (AuthWebSocketContext) → subscribe_chart;
 *                  mensajes chart_aggregate (intrabar) y chart_bar_sealed
 *                  (vela consolidada de bar_builder), misma semántica que
 *                  useLiveChartData: merge/new-bar/gap-backfill vía
 *                  lib/barAggregation.
 *  - Símbolos:     GET /api/v1/ticker/{symbol}/metadata + /metadata/search
 *
 * La librería vive en public/charting_library/ y se carga por script tag
 * (ver TVChartContent). Este módulo no importa nada de ella en runtime.
 */

import {
    applyAggregate,
    mergeAuthoritativeBar,
    sealedToChartBar,
    type AggregatePayload,
    type ChartBar,
} from '@/lib/barAggregation';
import { acquireStream, releaseStream, resubscribeAllStreams } from '@/lib/chartStreams';
import { useReplayClockStore } from '@/stores/useReplayClockStore';

// ---------------------------------------------------------------------------
// Tipos mínimos de la Datafeed API (subset de datafeed-api.d.ts v31).
// Estructurales a propósito: el widget solo llama estos métodos.
// ---------------------------------------------------------------------------

export interface TVBar {
    time: number; // Unix ms
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
}

interface TVPeriodParams {
    from: number;      // Unix s
    to: number;        // Unix s (no inclusivo)
    countBack: number;
    firstDataRequest: boolean;
}

interface TVSymbolInfo {
    name: string;
    ticker?: string;
    full_name: string;
    description: string;
    type: string;
    session: string;
    session_display?: string;
    subsession_id?: string;
    subsessions?: Array<{ description: string; id: string; session: string }>;
    timezone: string;
    exchange: string;
    listed_exchange: string;
    format: 'price' | 'volume';
    pricescale: number;
    minmov: number;
    has_intraday: boolean;
    intraday_multipliers: string[];
    has_daily: boolean;
    daily_multipliers: string[];
    has_weekly_and_monthly: boolean;
    weekly_multipliers: string[];
    monthly_multipliers: string[];
    supported_resolutions: string[];
    volume_precision: number;
    data_status: 'streaming' | 'endofday' | 'pulsed' | 'delayed_streaming';
    sector?: string;
    industry?: string;
}

/** TimescaleMark de la CL v31 (subset estructural de charting_library.d.ts). */
interface TVTimescaleMark {
    id: string | number;
    time: number; // Unix s
    color: string;
    label: string;
    labelFontColor?: string;
    tooltip: string[];
    /** v31: shapes nativos de earnings (TimeScaleMarkShape). */
    shape?: 'circle' | 'earningUp' | 'earningDown' | 'earning';
}

/** Puente hacia el WebSocket compartido de la app (AuthWebSocketContext). */
export interface TVWsBridge {
    send: (msg: Record<string, unknown>) => void;
    messages$: {
        subscribe: (observer: {
            next: (msg: any) => void;
            error?: (err: unknown) => void;
        }) => { unsubscribe: () => void };
    };
}

interface LiveSubscription {
    symbol: string;
    resolution: string;
    intervalSecs: number;
    isDailyOrAbove: boolean;
    lastBar: ChartBar | null;
    onTick: (bar: TVBar) => void;
    onResetCacheNeeded: () => void;
    rxSub: { unsubscribe: () => void };
    /**
     * Descongela los ticks de reproducción tras un salto hacia atrás. Entre el
     * salto y la re-petición de historia la librería aún enseña la serie
     * VIEJA: cualquier tick del instante nuevo sería "hacia atrás" para ella
     * (time violation, serie corrupta). getBars lo llama al servir historia
     * fresca en modo replay.
     */
    thawReplay?: () => void;
}

// ---------------------------------------------------------------------------
// Mapeo de resoluciones TV → intervalos del endpoint /api/v1/chart
// ---------------------------------------------------------------------------

const RESOLUTION_TO_INTERVAL: Record<string, string> = {
    '1': '1min',
    '2': '2min',
    '5': '5min',
    '15': '15min',
    '30': '30min',
    '60': '1hour',
    '240': '4hour',
    '720': '12hour',
    '1D': '1day',
    '1W': '1week',
    '1M': '1month',
    '3M': '3month',
    '12M': '1year',
};

const SUPPORTED_RESOLUTIONS = Object.keys(RESOLUTION_TO_INTERVAL);

/** Sesiones US equities (hora de Nueva York) para el selector Session de la CL. */
const SUBSESSIONS = [
    { description: 'Regular Trading Hours', id: 'regular', session: '0930-1600' },
    { description: 'Extended Trading Hours', id: 'extended', session: '0400-2000' },
    { description: 'Premarket', id: 'premarket', session: '0400-0930' },
    { description: 'Postmarket', id: 'postmarket', session: '1600-2000' },
];

function resolutionToSeconds(resolution: string): number {
    if (/^\d+$/.test(resolution)) return parseInt(resolution, 10) * 60;
    const n = parseInt(resolution, 10) || 1;
    if (resolution.endsWith('D')) return n * 86400;
    if (resolution.endsWith('W')) return n * 604800;
    if (resolution.endsWith('M')) return n * 2592000;
    return 86400;
}

function isDailyOrAboveResolution(resolution: string): boolean {
    return /[DWM]/.test(resolution);
}

function toTVBar(bar: ChartBar, dailyOrAbove = false): TVBar {
    // Contrato de la CL: en velas diarias o superiores el time debe ser las
    // 00:00:00 UTC del día de trading (el backend las sirve a medianoche ET =
    // 04:00/05:00 UTC). Sin normalizar, la librería las desplaza y los charts
    // japoneses (Heikin Ashi/Renko) salen con horas corruptas.
    const time = dailyOrAbove ? bar.time - (bar.time % 86400) : bar.time;
    return {
        time: time * 1000,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
    };
}

/** pricescale según precio: los small caps sub-$1 necesitan 4 decimales. */
function priceScaleFor(lastPrice: number | null): number {
    if (lastPrice == null || !isFinite(lastPrice)) return 100;
    if (lastPrice < 1) return 10000;
    if (lastPrice < 10) return 1000;
    return 100;
}

// ---------------------------------------------------------------------------
// Caché compartida de resolución de símbolos (a nivel de módulo, entre TODAS
// las celdas/ventanas): 6 celdas con el mismo símbolo = 1 petición, no 6.
// Se cachea la Promise (dedup de peticiones en vuelo incluida).
// ---------------------------------------------------------------------------

/** Metadata (exchange, nombre, sector…): estática → cache de sesión. */
const metadataCache = new Map<string, Promise<any>>();
/** Snapshot (solo afina pricescale): TTL corto es suficiente. */
const snapshotCache = new Map<string, { at: number; promise: Promise<any> }>();
const SNAPSHOT_TTL_MS = 30_000;

function fetchMetadataShared(apiUrl: string, symbol: string): Promise<any> {
    const key = `${apiUrl}|${symbol}`;
    let p = metadataCache.get(key);
    if (!p) {
        p = fetch(`${apiUrl}/api/v1/ticker/${encodeURIComponent(symbol)}/metadata`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`metadata ${r.status}`))));
        // Los fallos no se cachean: el siguiente intento vuelve a pedir.
        p.catch(() => metadataCache.delete(key));
        metadataCache.set(key, p);
    }
    return p;
}

function fetchSnapshotShared(apiUrl: string, symbol: string): Promise<any> {
    const key = `${apiUrl}|${symbol}`;
    const hit = snapshotCache.get(key);
    if (hit && Date.now() - hit.at < SNAPSHOT_TTL_MS) return hit.promise;
    const promise = fetch(`${apiUrl}/api/v1/ticker/${encodeURIComponent(symbol)}/snapshot`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
    snapshotCache.set(key, { at: Date.now(), promise });
    return promise;
}

// ---------------------------------------------------------------------------
// Earnings → timescale marks (iconos E en el eje de tiempo, estilo TV).
// Fuente: /api/v1/earnings/ticker/{symbol} (histórico + próximos). Caché a
// nivel de módulo compartida entre celdas, con TTL: la CL pide marks en cada
// cambio de rango visible y no queremos martillear el backend.
// ---------------------------------------------------------------------------

interface EarningsEvent {
    event_id?: number;
    report_date?: string;    // YYYY-MM-DD
    utc_time?: string;       // ISO
    time_slot?: string;      // BMO / AMC / TBD
    fiscal_year?: number;
    fiscal_period?: string;  // Q1…Q4
    eps_estimate?: number | null;
    eps_actual?: number | null;
    beat_eps?: boolean | null;
    revenue_estimate?: number | null;
    revenue_actual?: number | null;
    expected_move_pct?: number | null;      // fracción (0.036 = 3.6 %)
    post_earnings_move_1d?: number | null;  // fracción
    status?: string;         // scheduled / reported…
}

const earningsCache = new Map<string, { at: number; promise: Promise<EarningsEvent[]> }>();
const EARNINGS_TTL_MS = 10 * 60_000;

function fetchEarningsShared(apiUrl: string, symbol: string): Promise<EarningsEvent[]> {
    const key = `${apiUrl}|${symbol}`;
    const hit = earningsCache.get(key);
    if (hit && Date.now() - hit.at < EARNINGS_TTL_MS) return hit.promise;
    const promise = fetch(`${apiUrl}/api/v1/earnings/ticker/${encodeURIComponent(symbol)}?limit=100`)
        .then((r) => (r.ok ? r.json() : null))
        .then((json) => (Array.isArray(json?.earnings) ? (json.earnings as EarningsEvent[]) : []))
        .catch(() => []);
    earningsCache.set(key, { at: Date.now(), promise });
    return promise;
}

/** 108848200000 → "108.8B" (para tooltips compactos). */
function fmtMoney(n: number | null | undefined): string | null {
    if (n == null || !isFinite(n)) return null;
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    return `${n}`;
}

/** Fracción → "+3.6%" (con signo). */
function fmtPct(n: number | null | undefined): string | null {
    if (n == null || !isFinite(n)) return null;
    const v = n * 100;
    return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Datafeed
// ---------------------------------------------------------------------------

export class TradeulDatafeed {
    private readonly apiUrl: string;
    private readonly ws: TVWsBridge;

    /** Suscripciones realtime activas, por listenerGuid de la librería. */
    private readonly subs = new Map<string, LiveSubscription>();
    /**
     * Última vela del histórico por `symbol#resolution` — semilla de la
     * agregación realtime (getBars siempre corre antes de subscribeBars).
     */
    private readonly lastHistoryBars = new Map<string, ChartBar>();

    /**
     * Suscripciones al reloj de reproducción, por listenerGuid. En modo replay
     * la vela viva NO viene del socket: se forma con las mismas impresiones que
     * alimentan el libro y la cinta, para que las tres ventanas no puedan
     * contar historias distintas del mismo instante.
     */
    private readonly replaySubs = new Map<string, () => void>();

    /**
     * Barras ya vistas durante la reproducción, por `symbol#resolution`
     * (ASC por time). Es lo que permite que un rebobinado se sirva SÍNCRONO
     * desde memoria en vez de irse a red: el usuario tiene razón cuando dice
     * "está todo cargado, no debería parpadear". Se alimenta de cada
     * respuesta de getBars y de cada vela sellada por impresiones.
     */
    private readonly replayBars = new Map<string, ChartBar[]>();

    /**
     * true cuando el último salto exige rehacer la serie de la librería
     * (retroceso que cruza velas: una serie no puede encoger por ticks).
     * El dueño del widget lo consume y decide si llama a resetData; los
     * retrocesos DENTRO de la vela viva no lo levantan y salen gratis.
     */
    private replayResetRequired = false;

    /** Consume (y limpia) la señal de "hace falta resetData". */
    consumeReplayResetNeeded(): boolean {
        const v = this.replayResetRequired;
        this.replayResetRequired = false;
        return v;
    }

    private rememberReplayBars(key: string, bars: ChartBar[], overwrite: boolean): void {
        if (!bars.length) return;
        const cur = this.replayBars.get(key);
        if (!cur) {
            this.replayBars.set(key, [...bars].sort((a, b) => a.time - b.time));
            return;
        }
        const byTime = new Map<number, ChartBar>();
        for (const b of cur) byTime.set(b.time, b);
        for (const b of bars) {
            // Las barras del servidor pisan; las selladas por impresiones solo
            // rellenan huecos (pueden venir cortas de volumen tras un salto).
            if (overwrite || !byTime.has(b.time)) byTime.set(b.time, b);
        }
        let merged = [...byTime.values()].sort((a, b) => a.time - b.time);
        if (merged.length > 3000) merged = merged.slice(merged.length - 3000);
        this.replayBars.set(key, merged);
    }

    constructor(opts: { apiUrl: string; ws: TVWsBridge }) {
        this.apiUrl = opts.apiUrl;
        this.ws = opts.ws;
    }

    /** Instante de reproducción en segundos epoch, o null si no hay sesión. */
    private replayNowSec(): number | null {
        const s = useReplayClockStore.getState();
        if (!s.active) return null;
        return Math.floor((s.originMs + s.now()) / 1000);
    }

    // -- IExternalDatafeed ---------------------------------------------------

    onReady(callback: (config: unknown) => void): void {
        setTimeout(() => {
            callback({
                supported_resolutions: SUPPORTED_RESOLUTIONS,
                supports_marks: false,
                // Iconos de earnings en el eje de tiempo: la CL solo llama a
                // getTimescaleMarks si el datafeed lo declara aquí.
                supports_timescale_marks: true,
                // Countdown de cierre de vela en la escala de precios: con
                // esto la CL llama getServerTime y el contador no depende del
                // reloj (potencialmente desviado) del navegador.
                supports_time: true,
                exchanges: [],
                symbols_types: [],
            });
        }, 0);
    }

    /**
     * Hora del servidor (Unix s) para el countdown de la escala de precios.
     * Cualquier respuesta del dominio trae header Date (Caddy): un HEAD
     * barato basta. Fallback: reloj local (comportamiento sin supports_time).
     */
    getServerTime(callback: (serverTime: number) => void): void {
        fetch(`${this.apiUrl}/api/v1/health`, { method: 'HEAD' })
            .then((r) => {
                const d = r.headers.get('date');
                const t = d ? Date.parse(d) : NaN;
                callback(Math.round((isFinite(t) ? t : Date.now()) / 1000));
            })
            .catch(() => callback(Math.round(Date.now() / 1000)));
    }

    // -- Símbolos --------------------------------------------------------------

    searchSymbols(
        userInput: string,
        _exchange: string,
        _symbolType: string,
        onResult: (items: unknown[]) => void,
    ): void {
        const q = userInput.trim();
        if (!q) {
            onResult([]);
            return;
        }
        fetch(`${this.apiUrl}/api/v1/metadata/search?q=${encodeURIComponent(q)}&limit=30`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`search ${r.status}`))))
            .then((json) => {
                const results = Array.isArray(json?.results) ? json.results : [];
                onResult(
                    results.map((item: any) => ({
                        symbol: item.symbol,
                        ticker: item.symbol,
                        full_name: item.symbol,
                        description: item.name ?? '',
                        exchange: item.exchange ?? '',
                        type: item.asset_type === 'etf' ? 'fund' : 'stock',
                    })),
                );
            })
            .catch(() => onResult([]));
    }

    resolveSymbol(
        symbolName: string,
        onResolve: (info: TVSymbolInfo) => void,
        onError: (reason: string) => void,
        extension?: { session?: string },
    ): void {
        const symbol = symbolName.split(':').pop()!.trim().toUpperCase();
        if (!symbol) {
            onError('unknown_symbol');
            return;
        }

        // Horario extendido: al cambiar Session en el menú de la escala, la CL
        // re-resuelve el símbolo con extension.session ('extended', 'premarket',
        // 'postmarket') y espera que session/subsession_id reflejen esa sesión.
        const requestedSession =
            extension?.session && SUBSESSIONS.some((s) => s.id === extension.session)
                ? extension.session
                : 'regular';
        const activeSession = SUBSESSIONS.find((s) => s.id === requestedSession)!;

        const metadataReq = fetchMetadataShared(this.apiUrl, symbol);

        // Best-effort: el snapshot solo afina pricescale; si falla, default.
        const snapshotReq = fetchSnapshotShared(this.apiUrl, symbol);

        Promise.all([metadataReq, snapshotReq])
            .then(([meta, snap]) => {
                const lastPrice =
                    snap?.last_price ?? snap?.price ?? snap?.day?.c ?? snap?.lastTrade?.p ?? null;
                onResolve({
                    name: symbol,
                    ticker: symbol,
                    full_name: `${meta?.exchange ?? 'US'}:${symbol}`,
                    description: meta?.company_name ?? symbol,
                    type: 'stock',
                    session: activeSession.session,
                    subsession_id: activeSession.id,
                    subsessions: SUBSESSIONS,
                    timezone: 'America/New_York',
                    exchange: meta?.exchange ?? 'US',
                    listed_exchange: meta?.exchange ?? 'US',
                    format: 'price',
                    pricescale: priceScaleFor(typeof lastPrice === 'number' ? lastPrice : null),
                    minmov: 1,
                    has_intraday: true,
                    // SIN 60/240/720: el backend ancla la vela horaria a :00,
                    // pero la sesión regular 0930-1600 exige velas 09:30/10:30…
                    // ("Library shifts bar time"). Al no declararlas, la CL las
                    // CONSTRUYE desde las de 30m con el anclaje correcto para
                    // la sesión activa (regular o extendida). Siguen disponibles
                    // en la UI vía supported_resolutions.
                    intraday_multipliers: ['1', '2', '5', '15', '30'],
                    has_daily: true,
                    daily_multipliers: ['1'],
                    has_weekly_and_monthly: true,
                    weekly_multipliers: ['1'],
                    monthly_multipliers: ['1', '3', '12'],
                    supported_resolutions: SUPPORTED_RESOLUTIONS,
                    volume_precision: 0,
                    data_status: 'streaming',
                    sector: meta?.sector ?? undefined,
                    industry: meta?.industry ?? undefined,
                });
            })
            .catch(() => onError('unknown_symbol'));
    }

    // -- Timescale marks (earnings) --------------------------------------------

    /**
     * Iconos de earnings en el eje de tiempo (contrato v31): un shape nativo
     * por evento — earningUp (beat de EPS), earningDown (miss), earning
     * (programado / sin resultado aún). onDataCallback se llama EXACTAMENTE
     * una vez por petición (requisito de la CL), con [] ante cualquier fallo.
     */
    getTimescaleMarks(
        symbolInfo: TVSymbolInfo,
        from: number,
        to: number,
        onDataCallback: (marks: TVTimescaleMark[]) => void,
        resolution: string,
    ): void {
        const symbol = (symbolInfo.ticker ?? symbolInfo.name).toUpperCase();
        const dailyOrAbove = isDailyOrAboveResolution(resolution);
        fetchEarningsShared(this.apiUrl, symbol)
            .then((events) => {
                const marks: TVTimescaleMark[] = [];
                for (const ev of events) {
                    if (!ev.report_date) continue;
                    // Velas diarias+ van normalizadas a las 00:00 UTC del día
                    // (ver toTVBar): el mark debe caer en la misma marca de
                    // tiempo. En intradía, la hora real del evento.
                    const dayStart = Date.parse(`${ev.report_date}T00:00:00Z`) / 1000;
                    const utc = ev.utc_time ? Date.parse(ev.utc_time) / 1000 : NaN;
                    const time = dailyOrAbove || !isFinite(utc) ? dayStart : utc;
                    if (!isFinite(time) || time < from || time > to) continue;

                    const beat = ev.beat_eps;
                    const shape: TVTimescaleMark['shape'] =
                        beat === true ? 'earningUp' : beat === false ? 'earningDown' : 'earning';
                    const color = beat === true ? '#26a69a' : beat === false ? '#ef5350' : '#787b86';

                    const tooltip: string[] = [];
                    const fiscal = [ev.fiscal_period, ev.fiscal_year].filter(Boolean).join(' ');
                    tooltip.push(
                        `Earnings${fiscal ? ` ${fiscal}` : ''} · ${ev.report_date}${ev.time_slot && ev.time_slot !== 'TBD' ? ` (${ev.time_slot})` : ''}`,
                    );
                    if (ev.eps_actual != null) {
                        tooltip.push(`EPS: ${ev.eps_actual}${ev.eps_estimate != null ? ` (est ${ev.eps_estimate})` : ''}`);
                    } else if (ev.eps_estimate != null) {
                        tooltip.push(`EPS est: ${ev.eps_estimate}`);
                    }
                    const rev = fmtMoney(ev.revenue_actual);
                    const revEst = fmtMoney(ev.revenue_estimate);
                    if (rev) tooltip.push(`Ingresos: ${rev}${revEst ? ` (est ${revEst})` : ''}`);
                    else if (revEst) tooltip.push(`Ingresos est: ${revEst}`);
                    const move = fmtPct(ev.post_earnings_move_1d);
                    const expMove = fmtPct(ev.expected_move_pct);
                    if (move) tooltip.push(`Reacción 1D: ${move}`);
                    else if (expMove) tooltip.push(`Mov. esperado: ±${expMove.replace(/^[+-]/, '')}`);

                    marks.push({
                        id: ev.event_id ?? `${symbol}-${ev.report_date}`,
                        time,
                        color,
                        label: 'E',
                        labelFontColor: '#ffffff',
                        tooltip,
                        shape,
                    });
                }
                onDataCallback(marks);
            })
            .catch(() => onDataCallback([]));
    }

    // -- Histórico -------------------------------------------------------------

    getBars(
        symbolInfo: TVSymbolInfo,
        resolution: string,
        periodParams: TVPeriodParams,
        onResult: (bars: TVBar[], meta?: { noData?: boolean }) => void,
        onError: (reason: string) => void,
    ): void {
        const symbol = (symbolInfo.ticker ?? symbolInfo.name).toUpperCase();
        const interval = RESOLUTION_TO_INTERVAL[resolution];
        if (!interval) {
            onError(`unsupported resolution: ${resolution}`);
            return;
        }

        const limit = Math.min(Math.max(periodParams.countBack || 300, 100), 5000);
        let url = `${this.apiUrl}/api/v1/chart/${encodeURIComponent(symbol)}?interval=${interval}&limit=${limit}`;
        // En reproducción la historia se corta en el instante del reloj: para la
        // librería, el pasado del replay ES toda la historia que existe. El
        // backend devuelve las barras completas previas mas un colchon por
        // delante, que aqui se descarta — el futuro lo destapa el reloj.
        const replaySec = this.replayNowSec();
        if (replaySec !== null) url += `&to=${replaySec}`;

        // Rebobinar NO debería ir a red: todo lo que puede necesitar la
        // librería ya pasó por aquí (respuestas anteriores + velas selladas).
        // Servir de memoria hace el salto atrás síncrono — sin el blanco de
        // "resetData y a esperar el fetch", que era el parpadeo que se veía.
        // Solo la primera petición tras el reset: la paginación de historia
        // más antigua (scroll a la izquierda) sigue yendo a red.
        if (replaySec !== null && periodParams.firstDataRequest && !isDailyOrAboveResolution(resolution)) {
            const cached = this.replayBars.get(`${symbol}#${resolution}`);
            if (cached?.length) {
                const dur = resolutionToSeconds(resolution);
                let hi = -1;
                for (let i = cached.length - 1; i >= 0; i--) {
                    if (cached[i].time + dur <= replaySec) { hi = i; break; }
                }
                // Cobertura real: el corte tiene que caer dentro del tramo
                // cacheado O en la vela viva inmediatamente posterior a la
                // última sellada (esa la reconstruye el catch-up con las
                // impresiones). Si no, a red.
                const newest = cached[cached.length - 1];
                const cubierto = hi >= 0 && newest.time + dur * 2 > replaySec;
                if (cubierto) {
                    const slice = cached.slice(Math.max(0, hi + 1 - limit), hi + 1);
                    // CONTINUIDAD: la caché mezcla barras del servidor y
                    // selladas por impresiones, y esa unión puede tener
                    // agujeros. Servir un tramo agujereado lo perpetúa en
                    // pantalla (el hueco que "se curaba solo" al volver a la
                    // pestaña, cuando el resync de visibilidad iba a red). Ante
                    // la duda — hueco interno grande o tramo raquítico — a red,
                    // que es lenta pero completa.
                    let sano = slice.length >= Math.min(limit, 30);
                    for (let i = 1; sano && i < slice.length; i++) {
                        if (slice[i].time - slice[i - 1].time > dur * 3) sano = false;
                    }
                    if (sano) {
                        const newestBar = slice[slice.length - 1];
                        this.lastHistoryBars.set(`${symbol}#${resolution}`, newestBar);
                        for (const sub of this.subs.values()) {
                            if (sub.symbol === symbol && sub.resolution === resolution) {
                                sub.lastBar = newestBar;
                                sub.thawReplay?.();
                            }
                        }
                        onResult(slice.map((b) => toTVBar(b, false)), { noData: false });
                        return;
                    }
                }
            }
        }

        // El cursor de paginación se envía IGUAL en reproducción. Sin él, cada
        // petición de historia antigua devolvía la misma ventana y la librería
        // volvía a pedir sin avanzar nunca: 32 peticiones seguidas por un solo
        // corte. El recorte lo sigue haciendo `to`; esto solo dice por dónde va.
        if (!periodParams.firstDataRequest) url += `&before=${periodParams.to}`;

        fetch(url)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`chart ${r.status}`))))
            .then((json) => {
                // Descongelar SOLO con la respuesta que sigue al reset
                // (firstDataRequest). Las cargas que dispara el encuadre son
                // paginación: si su respuesta llega antes que la del reset y
                // deshiela, los ticks entran sobre una serie a medio limpiar.
                if (replaySec !== null && periodParams.firstDataRequest) {
                    for (const sub of this.subs.values()) {
                        if (sub.symbol === symbol && sub.resolution === resolution) sub.thawReplay?.();
                    }
                }
                const raw: ChartBar[] = Array.isArray(json?.data) ? json.data : [];
                if (raw.length === 0) {
                    onResult([], { noData: json?.has_more !== true });
                    return;
                }
                // El endpoint devuelve ascendente; garantizarlo por contrato TV.
                raw.sort((a, b) => a.time - b.time);

                // Colchón fuera: una barra solo entra si TERMINA en o antes del
                // instante. La que lo contiene se está formando y la construye
                // subscribeBars con las impresiones que va soltando el reloj.
                if (replaySec !== null) {
                    const dur = resolutionToSeconds(resolution);
                    for (let i = raw.length - 1; i >= 0; i--) {
                        if (raw[i].time + dur <= replaySec) { raw.length = i + 1; break; }
                        if (i === 0) raw.length = 0;
                    }
                    // OJO: aquí noData NO puede ser true a la ligera. Tras un
                    // salto atrás, la primera re-petición cubre el rango visible
                    // VIEJO (posterior al corte) y el recorte la vacía: con
                    // noData:true la librería da la serie por agotada y no
                    // vuelve a pedir — gráfico en blanco para siempre. Mientras
                    // el servidor tenga más historia, que siga preguntando.
                    if (raw.length === 0) { onResult([], { noData: json?.has_more === false }); return; }
                    // A memoria: el siguiente rebobinado hacia este tramo se
                    // servirá síncrono, sin blanco de red.
                    if (!isDailyOrAboveResolution(resolution)) {
                        this.rememberReplayBars(`${symbol}#${resolution}`, raw, true);
                    }
                }

                if (periodParams.firstDataRequest) {
                    const newest = raw[raw.length - 1];
                    this.lastHistoryBars.set(`${symbol}#${resolution}`, newest);
                    // Re-sembrar la base de agregación de las suscripciones YA
                    // vivas del mismo par: tras un reset (resyncAll/gap-backfill)
                    // la CL rellama getBars pero NO subscribeBars, y un lastBar
                    // obsoleto haría que cada aggregate posterior volviera a
                    // detectar hueco → bucle de resets.
                    for (const sub of this.subs.values()) {
                        if (sub.symbol === symbol && sub.resolution === resolution) {
                            sub.lastBar = newest;
                        }
                    }
                }
                // El estado interno (lastHistoryBars/lastBar) conserva la base
                // de tiempos del backend; la normalización diaria se aplica
                // solo en la frontera hacia la librería.
                const dailyOrAbove = isDailyOrAboveResolution(resolution);
                onResult(raw.map((b) => toTVBar(b, dailyOrAbove)), { noData: false });
            })
            .catch((err) => {
                // Descongelar también en error (solo el post-reset): mejor un
                // tick raro que un gráfico mudo hasta un fetch que quizá no
                // llegue.
                if (replaySec !== null && periodParams.firstDataRequest) {
                    for (const sub of this.subs.values()) {
                        if (sub.symbol === symbol && sub.resolution === resolution) sub.thawReplay?.();
                    }
                }
                onError(String(err?.message ?? err));
            });
    }

    // -- Tiempo real -------------------------------------------------------------

    subscribeBars(
        symbolInfo: TVSymbolInfo,
        resolution: string,
        onTick: (bar: TVBar) => void,
        listenerGuid: string,
        onResetCacheNeededCallback: () => void,
    ): void {
        const symbol = (symbolInfo.ticker ?? symbolInfo.name).toUpperCase();
        const intervalSecs = resolutionToSeconds(resolution);
        const isDailyOrAbove = isDailyOrAboveResolution(resolution);

        const sub: LiveSubscription = {
            symbol,
            resolution,
            intervalSecs,
            isDailyOrAbove,
            lastBar: this.lastHistoryBars.get(`${symbol}#${resolution}`) ?? null,
            onTick,
            onResetCacheNeeded: onResetCacheNeededCallback,
            rxSub: this.ws.messages$.subscribe({
                next: (msg) => this.handleWsMessage(listenerGuid, msg),
                error: () => {
                    /* la reconexión la gestiona AuthWebSocketContext */
                },
            }),
        };
        this.subs.set(listenerGuid, sub);

        // -- Reproducción -----------------------------------------------------
        // Se engancha SIEMPRE, no solo si ya hay sesión abierta: la ventana de
        // Level 2 puede abrirse después de que el gráfico se suscriba, y el
        // gráfico tiene que seguir al reloj sin depender del orden. Mientras no
        // haya sesión, el bus no emite nada y esto no cuesta.
        let rBar: TVBar | null = null;
        let rDirty = false;
        // true entre un salto HACIA ATRÁS y la historia fresca: la librería
        // aún enseña la serie vieja y un tick del instante nuevo sería
        // "hacia atrás" para ella (time violation → serie corrupta).
        let rFrozen = false;
        sub.thawReplay = () => {
            rFrozen = false;
            // La vela viva acumulada en silencio durante el catch-up sale
            // ahora, con la historia fresca ya en pantalla: mismo timestamp o
            // posterior al último sellado, tick válido.
            rDirty = rBar !== null;
        };

        const offPrint = useReplayClockStore.getState().onPrint(([tRel, px, size]) => {
            const rs = useReplayClockStore.getState();
            // VETO POR SÍMBOLO: el bus no lleva ticker. Un gráfico en otro
            // símbolo que se trague impresiones ajenas fabrica velas que no
            // existen — y las cachea, envenenando los rebobinados futuros.
            if (rs.sessionSymbol && rs.sessionSymbol !== symbol) return;
            const origin = rs.originMs;
            const t0 = Math.floor(Math.floor((origin + tRel) / 1000) / intervalSecs) * intervalSecs;
            if (!rBar || t0 * 1000 > rBar.time) {
                if (rBar) {
                    // Sellar la que cierra ANTES de abrir la nueva: a velocidad
                    // alta puede cruzarse más de una frontera en el mismo frame
                    // y, emitiendo solo la última, quedarían huecos. Congelado
                    // NO se emite (la librería aún enseña la serie vieja), pero
                    // la sellada sí se guarda: es una barra legítima que un
                    // rebobinado posterior servirá de memoria.
                    if (!rFrozen) onTick({ ...rBar });
                    if (!isDailyOrAbove) {
                        this.rememberReplayBars(`${symbol}#${resolution}`, [{
                            time: rBar.time / 1000, open: rBar.open, high: rBar.high,
                            low: rBar.low, close: rBar.close, volume: rBar.volume ?? 0,
                        } as ChartBar], false);
                    }
                }
                rBar = { time: t0 * 1000, open: px, high: px, low: px, close: px, volume: size };
            } else {
                rBar.high = Math.max(rBar.high, px);
                rBar.low = Math.min(rBar.low, px);
                rBar.close = px;
                rBar.volume = (rBar.volume ?? 0) + size;
            }
            // Congelado se ACUMULA pero no se publica: así, cuando el catch-up
            // de un salto reaplica las impresiones desde el principio, la vela
            // viva queda EXACTA (antes se descartaban y la vela salía más
            // pequeña unas veces sí y otras no, según qué prints pillara).
            if (!rFrozen) rDirty = true;
        });

        // Conflación: un onTick por frame, no uno por impresión.
        const offFrame = useReplayClockStore.getState().onFrame(() => {
            if (rDirty && rBar) { onTick({ ...rBar }); rDirty = false; }
        });

        // Dirección y alcance del salto deciden el coste:
        //   · delante → nada: las impresiones de alcance son ticks válidos y
        //     el gráfico avanza en el acto, sin re-petición ni parpadeo.
        //   · atrás DENTRO de la vela viva → la vela solo encoge, y un tick
        //     con el mismo timestamp es legal: se reconstruye en silencio con
        //     el catch-up y se publica al soltar el hilo. Cero resetData.
        //   · atrás cruzando velas → la serie tiene que perder barras, y eso
        //     solo lo hace un resetData: congelar, invalidar y avisar al
        //     dueño del widget (replayResetRequired).
        const offSeek = useReplayClockStore.getState().onSeek((tMs, prevTMs) => {
            if (tMs >= prevTMs) return;
            const absMs = useReplayClockStore.getState().originMs + tMs;
            const dentroDeVela = rBar !== null && absMs >= rBar.time;
            rBar = null;
            rDirty = false;
            rFrozen = true;
            if (dentroDeVela) {
                // El catch-up corre síncrono dentro de seek(); este timeout se
                // ejecuta justo después, con la vela ya reconstruida entera.
                setTimeout(() => { rFrozen = false; rDirty = rBar !== null; }, 0);
            } else {
                this.replayResetRequired = true;
                onResetCacheNeededCallback();
            }
        });

        this.replaySubs.set(listenerGuid, () => { offPrint(); offFrame(); offSeek(); });

        // Refcount GLOBAL (lib/chartStreams): el WS es compartido por toda la
        // app y el servidor no lleva contador por símbolo — un unsubscribe
        // local mataría el stream de las demás celdas/ventanas con el símbolo.
        acquireStream(this.ws.send, 'chart', symbol);
    }

    unsubscribeBars(listenerGuid: string): void {
        const offReplay = this.replaySubs.get(listenerGuid);
        if (offReplay) { this.replaySubs.delete(listenerGuid); offReplay(); }
        const sub = this.subs.get(listenerGuid);
        if (!sub) return;
        this.subs.delete(listenerGuid);
        sub.rxSub.unsubscribe();
        releaseStream(this.ws.send, 'chart', sub.symbol);
    }

    /** Reemitir las suscripciones vivas tras una reconexión del WS compartido. */
    resubscribeAll(): void {
        resubscribeAllStreams(this.ws.send);
    }

    /**
     * Resync tras reconexión o vuelta de background (mecanismo oficial CL:
     * onResetCacheNeeded + resetData, docs "Datafeed Issues → internet
     * connection issues"). Invalida la caché de barras de TODAS las
     * suscripciones vivas; el caller debe llamar después
     * widget.activeChart().resetData() para forzar el re-fetch inmediato.
     * Cierra los huecos de velas de forma determinista en vez de esperar al
     * siguiente aggregate (que en símbolos ilíquidos o diario puede no llegar).
     */
    resyncAll(): void {
        for (const sub of this.subs.values()) {
            sub.onResetCacheNeeded();
        }
    }

    /** Liberar todo al desmontar la ventana. */
    destroy(): void {
        for (const guid of Array.from(this.subs.keys())) {
            this.unsubscribeBars(guid);
        }
        this.lastHistoryBars.clear();
    }

    // -- Interno -----------------------------------------------------------------

    private handleWsMessage(listenerGuid: string, msg: any): void {
        // Durante una reproducción el presente se calla: la vela viva la forman
        // las impresiones del reloj. Colar un tick de ahora sobre un gráfico
        // parado en el pasado lo dispara al futuro y rompe la sincronía con el
        // libro y la cinta.
        if (useReplayClockStore.getState().active) return;
        const sub = this.subs.get(listenerGuid);
        if (!sub || !msg || msg.symbol !== sub.symbol) return;

        if (msg.type === 'chart_aggregate') {
            const payload = msg.data as AggregatePayload | undefined;
            if (!payload) return;
            const action = applyAggregate(sub.lastBar, payload, sub.intervalSecs, sub.isDailyOrAbove);
            switch (action.kind) {
                case 'merge':
                case 'new-bar':
                    sub.lastBar = action.bar;
                    sub.onTick(toTVBar(action.bar, sub.isDailyOrAbove));
                    return;
                case 'gap-backfill':
                    // La librería re-pide el histórico y llama getBars de nuevo.
                    sub.onResetCacheNeeded();
                    return;
                case 'extended-hours':
                case 'ignore':
                    return;
            }
        }

        if (msg.type === 'chart_bar_sealed') {
            const sealed = msg.data;
            // Solo aplica si el builder emite exactamente nuestra resolución.
            if (!sealed || sealed.timeframe * 60 !== sub.intervalSecs) return;
            const authoritative = sealedToChartBar(sealed);
            if (!authoritative || !sub.lastBar || authoritative.time !== sub.lastBar.time) return;
            const corrected = mergeAuthoritativeBar(sub.lastBar, authoritative);
            sub.lastBar = corrected;
            sub.onTick(toTVBar(corrected, sub.isDailyOrAbove));
        }
    }
}
