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

    constructor(opts: { apiUrl: string; ws: TVWsBridge }) {
        this.apiUrl = opts.apiUrl;
        this.ws = opts.ws;
    }

    // -- IExternalDatafeed ---------------------------------------------------

    onReady(callback: (config: unknown) => void): void {
        setTimeout(() => {
            callback({
                supported_resolutions: SUPPORTED_RESOLUTIONS,
                supports_marks: false,
                supports_timescale_marks: false,
                supports_time: false,
                exchanges: [],
                symbols_types: [],
            });
        }, 0);
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

        const metadataReq = fetch(`${this.apiUrl}/api/v1/ticker/${encodeURIComponent(symbol)}/metadata`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`metadata ${r.status}`))));

        // Best-effort: el snapshot solo afina pricescale; si falla, default.
        const snapshotReq = fetch(`${this.apiUrl}/api/v1/ticker/${encodeURIComponent(symbol)}/snapshot`)
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null);

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
        if (!periodParams.firstDataRequest) {
            url += `&before=${periodParams.to}`;
        }

        fetch(url)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`chart ${r.status}`))))
            .then((json) => {
                const raw: ChartBar[] = Array.isArray(json?.data) ? json.data : [];
                if (raw.length === 0) {
                    onResult([], { noData: json?.has_more !== true });
                    return;
                }
                // El endpoint devuelve ascendente; garantizarlo por contrato TV.
                raw.sort((a, b) => a.time - b.time);

                if (periodParams.firstDataRequest) {
                    this.lastHistoryBars.set(`${symbol}#${resolution}`, raw[raw.length - 1]);
                }
                // El estado interno (lastHistoryBars/lastBar) conserva la base
                // de tiempos del backend; la normalización diaria se aplica
                // solo en la frontera hacia la librería.
                const dailyOrAbove = isDailyOrAboveResolution(resolution);
                onResult(raw.map((b) => toTVBar(b, dailyOrAbove)), { noData: false });
            })
            .catch((err) => onError(String(err?.message ?? err)));
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

        // Refcount GLOBAL (lib/chartStreams): el WS es compartido por toda la
        // app y el servidor no lleva contador por símbolo — un unsubscribe
        // local mataría el stream de las demás celdas/ventanas con el símbolo.
        acquireStream(this.ws.send, 'chart', symbol);
    }

    unsubscribeBars(listenerGuid: string): void {
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

    /** Liberar todo al desmontar la ventana. */
    destroy(): void {
        for (const guid of Array.from(this.subs.keys())) {
            this.unsubscribeBars(guid);
        }
        this.lastHistoryBars.clear();
    }

    // -- Interno -----------------------------------------------------------------

    private handleWsMessage(listenerGuid: string, msg: any): void {
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
