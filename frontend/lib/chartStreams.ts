/**
 * chartStreams — refcount GLOBAL de suscripciones realtime por (canal, símbolo)
 * sobre el WebSocket compartido de la app (AuthWebSocketContext).
 *
 * El servidor lleva las suscripciones por (conexión, símbolo) SIN contador
 * (websocket_server: subscribeClientToChart / unsubscribeClientFromChart): un
 * solo `unsubscribe_chart X` de CUALQUIER consumidor corta el stream de X para
 * toda la conexión. Con varias vistas del mismo símbolo a la vez — celdas del
 * multichart TVC (que además heredan el símbolo de la celda activa al crearse),
 * el chart propio, varias ventanas — destruir una dejaba sin realtime a las
 * supervivientes hasta la siguiente reconexión.
 *
 * Contrato de este módulo: `subscribe_<canal>` se emite solo para el PRIMER
 * consumidor de un símbolo y `unsubscribe_<canal>` solo cuando se va el ÚLTIMO.
 * TODO consumidor de chart/tape realtime debe pasar por aquí — nunca emitir
 * subscribe_chart/unsubscribe_chart directamente al WS.
 */

type SendFn = (msg: Record<string, unknown>) => void;

export type StreamChannel = 'chart' | 'tape';

const refs = new Map<string, number>();

const keyOf = (channel: StreamChannel, symbol: string) => `${channel}:${symbol}`;

/** Registrar un consumidor del stream; emite subscribe solo si es el primero. */
export function acquireStream(send: SendFn, channel: StreamChannel, symbol: string): void {
    const s = symbol.toUpperCase();
    const k = keyOf(channel, s);
    const n = refs.get(k) ?? 0;
    refs.set(k, n + 1);
    if (n === 0) send({ action: `subscribe_${channel}`, symbol: s });
}

/** Liberar un consumidor; emite unsubscribe solo cuando se va el último. */
export function releaseStream(send: SendFn, channel: StreamChannel, symbol: string): void {
    const s = symbol.toUpperCase();
    const k = keyOf(channel, s);
    const n = (refs.get(k) ?? 1) - 1;
    if (n <= 0) {
        refs.delete(k);
        send({ action: `unsubscribe_${channel}`, symbol: s });
    } else {
        refs.set(k, n);
    }
}

/**
 * Reemitir todas las suscripciones vivas (tras una reconexión del WS).
 * Coalescido a UNA emisión por microtask aunque lo invoquen N consumidores
 * a la vez (cada celda del multichart reacciona al mismo isConnected).
 */
let resubscribePending = false;
export function resubscribeAllStreams(send: SendFn): void {
    if (resubscribePending) return;
    resubscribePending = true;
    queueMicrotask(() => {
        resubscribePending = false;
        for (const k of refs.keys()) {
            const i = k.indexOf(':');
            send({ action: `subscribe_${k.slice(0, i)}`, symbol: k.slice(i + 1) });
        }
    });
}
