/**
 * wsContracts — contrato TIPADO y VALIDADO de los mensajes WebSocket que
 * consume el motor de gráficos y el reloj de mercado.
 *
 * Regla: ningún consumidor lee `message.data.loquesea` a pelo. Se valida en
 * el borde con estos guards y a partir de ahí el tipo es de fiar. Un mensaje
 * malformado se descarta aquí (con contador de rechazos para diagnóstico) en
 * vez de propagar NaN/undefined a las velas.
 *
 * Espejo server-side: services/websocket_server/src/index.js
 *   - chart_aggregate  → broadcastChartAggregate() y handler chart:trades:*
 *   - chart_bar_sealed → handler chart:sealed:* (velas de bar_builder)
 *   - connected        → welcome message en la conexión
 *   - market_session_change / trading_day_changed → subscribeToSessionChangeEvents
 * Si cambias un campo aquí, cámbialo allí (y viceversa).
 */

import type { MarketSessionType } from './types';

// ============================================================================
// Tipos de mensaje
// ============================================================================

/** Payload OHLCV de un tick de chart (ambos feeds: trades y A.*). */
export interface ChartAggregateData {
    o: number;
    h: number;
    l: number;
    c: number;
    v: number;
    t: number;      // Unix ms
    av?: number;    // volumen acumulado del día (solo feed A.*)
}

export interface ChartAggregateMsg {
    type: 'chart_aggregate';
    symbol: string;
    data: ChartAggregateData;
    seq?: number;
    source?: 'trades';
    timestamp?: string;
}

/** Vela sellada de bar_builder (formato completo del builder, tiempos en ms). */
export interface SealedBarData {
    symbol: string;
    timeframe: number;   // minutos
    bar_start: number;   // Unix ms
    bar_end: number;     // Unix ms
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    trades?: number;
    vwap?: number;
}

export interface ChartBarSealedMsg {
    type: 'chart_bar_sealed';
    symbol: string;
    data: SealedBarData;
    seq?: number;
    timestamp?: string;
}

export interface ConnectedMsg {
    type: 'connected';
    connection_id?: string;
    trading_date?: string;
    current_session?: MarketSessionType;
    timestamp?: string;
    authenticated?: boolean;
}

export interface MarketSessionChangeMsg {
    type: 'market_session_change';
    data: {
        current_session: MarketSessionType;
        trading_date?: string;
        timestamp?: string;
        is_new_day?: boolean;
        // Ojo: en mensajes con is_new_day=true el servidor pone
        // from_session === to_session (no refleja la sesión anterior real).
        from_session?: MarketSessionType;
        to_session?: MarketSessionType;
    };
}

export interface TradingDayChangedMsg {
    type: 'trading_day_changed';
    data: {
        previousDate?: string | null;
        newDate?: string | null;
        session?: string;
        timestamp?: string;
    };
}

// ============================================================================
// Guards (validación en el borde)
// ============================================================================

const isFiniteNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);

// Contadores de mensajes rechazados por tipo — diagnósticos baratos para
// detectar la próxima ruptura de contrato sin abrir el debugger.
const _rejected = new Map<string, number>();

function reject(kind: string): false {
    _rejected.set(kind, (_rejected.get(kind) || 0) + 1);
    const count = _rejected.get(kind)!;
    // Log muestreado: el primero y luego 1 de cada 100, para no inundar.
    if (count === 1 || count % 100 === 0) {
        console.warn(`[wsContracts] Rejected malformed '${kind}' message (x${count})`);
    }
    return false;
}

/** Snapshot de rechazos acumulados (para debug/telemetría). */
export function getRejectedCounts(): Record<string, number> {
    return Object.fromEntries(_rejected);
}

export function isChartAggregateMsg(msg: any): msg is ChartAggregateMsg {
    if (msg?.type !== 'chart_aggregate') return false;
    const d = msg.data;
    const ok = typeof msg.symbol === 'string'
        && d != null
        && isFiniteNum(d.o) && isFiniteNum(d.h) && isFiniteNum(d.l) && isFiniteNum(d.c)
        && isFiniteNum(d.v) && isFiniteNum(d.t) && d.t > 0
        && d.c > 0;
    return ok || reject('chart_aggregate');
}

export function isChartBarSealedMsg(msg: any): msg is ChartBarSealedMsg {
    if (msg?.type !== 'chart_bar_sealed') return false;
    const d = msg.data;
    const ok = typeof msg.symbol === 'string'
        && d != null
        && isFiniteNum(d.timeframe) && d.timeframe > 0
        && isFiniteNum(d.bar_start) && d.bar_start > 0
        && isFiniteNum(d.open) && isFiniteNum(d.high) && isFiniteNum(d.low) && isFiniteNum(d.close)
        && isFiniteNum(d.volume)
        && d.open > 0;
    return ok || reject('chart_bar_sealed');
}

const SESSIONS: ReadonlySet<string> = new Set(['PRE_MARKET', 'MARKET_OPEN', 'POST_MARKET', 'CLOSED']);

export function isConnectedWithSessionMsg(msg: any): msg is ConnectedMsg & { current_session: MarketSessionType } {
    return msg?.type === 'connected'
        && typeof msg.current_session === 'string'
        && SESSIONS.has(msg.current_session);
}

export function isMarketSessionChangeMsg(msg: any): msg is MarketSessionChangeMsg {
    if (msg?.type !== 'market_session_change') return false;
    const ok = msg.data != null
        && typeof msg.data.current_session === 'string'
        && SESSIONS.has(msg.data.current_session);
    return ok || reject('market_session_change');
}

export function isTradingDayChangedMsg(msg: any): msg is TradingDayChangedMsg {
    return msg?.type === 'trading_day_changed';
}
