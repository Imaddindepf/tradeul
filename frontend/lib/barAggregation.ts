/**
 * barAggregation — lógica PURA de agregación de ticks WS sobre la serie de
 * velas del chart. Sin React, sin red: entrada → decisión determinista.
 *
 * Usada por useLiveChartData; testeada en lib/__tests__/barAggregation.test.ts.
 */

import { dailyBarTime, isRegularHours } from './marketTime';

export interface ChartBar {
    time: number;      // Unix segundos (inicio del bucket)
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

/** Payload data de un mensaje WS chart_aggregate. */
export interface AggregatePayload {
    o: number;
    h: number;
    l: number;
    c: number;
    v: number;
    t: number; // Unix ms
}

export type AggregateAction =
    /** Tick fuera de sesión regular en velas diarias: solo actualizar overlay extendido. */
    | { kind: 'extended-hours'; price: number }
    /** El tick cae en la vela actual → reemplazarla por `bar` (merge OHLC + suma volumen). */
    | { kind: 'merge'; bar: ChartBar }
    /** El tick abre la vela contigua siguiente → añadir `bar` (open provisional). */
    | { kind: 'new-bar'; bar: ChartBar }
    /** Hay hueco de ≥1 vela: NO pintar nada, pedir backfill al backend. */
    | { kind: 'gap-backfill' }
    /** Tick viejo o sin vela de referencia: descartar. */
    | { kind: 'ignore' };

/**
 * Decide cómo aplicar un aggregate WS sobre la última vela conocida.
 *
 * Reglas:
 *  - Diario+: los ticks fuera de 9:30–close ET no tocan la vela (solo overlay).
 *  - Mismo bucket → merge (open se conserva, high/low se extienden, volumen suma).
 *  - Bucket contiguo siguiente → vela nueva provisional.
 *  - Hueco de más de un bucket → gap-backfill (interpolar velas falsas rompe
 *    los indicadores y pinta líneas que no existieron).
 *  - Tick anterior a la vela actual → ignore (mensaje reordenado/duplicado).
 */
export function applyAggregate(
    lastBar: ChartBar | null,
    agg: AggregatePayload,
    intervalSecs: number,
    isDailyOrAbove: boolean,
): AggregateAction {
    const timeSecs = Math.floor(agg.t / 1000);

    if (isDailyOrAbove && !isRegularHours(timeSecs)) {
        return { kind: 'extended-hours', price: agg.c };
    }

    if (!lastBar) return { kind: 'ignore' };

    const barTime = isDailyOrAbove
        ? dailyBarTime(timeSecs, lastBar.time)
        : Math.floor(timeSecs / intervalSecs) * intervalSecs;

    if (barTime === lastBar.time) {
        return {
            kind: 'merge',
            bar: {
                time: barTime,
                open: lastBar.open,
                high: Math.max(lastBar.high, agg.h),
                low: Math.min(lastBar.low, agg.l),
                close: agg.c,
                volume: lastBar.volume + agg.v,
            },
        };
    }

    if (barTime > lastBar.time) {
        const gapBars = isDailyOrAbove
            ? 0 // dailyBarTime ya salta fines de semana/festivos: contiguo por construcción
            : Math.floor((barTime - lastBar.time) / intervalSecs) - 1;
        if (gapBars > 0) return { kind: 'gap-backfill' };

        return {
            kind: 'new-bar',
            bar: { time: barTime, open: agg.o, high: agg.h, low: agg.l, close: agg.c, volume: agg.v },
        };
    }

    return { kind: 'ignore' };
}

/**
 * Merge de una vela AUTORITATIVA (backfill REST o vela sellada del backend)
 * sobre la última vela local del mismo bucket. A diferencia del merge de
 * ticks, el volumen NO se suma: el backend ya lo trae consolidado.
 */
export function mergeAuthoritativeBar(local: ChartBar, authoritative: ChartBar): ChartBar {
    return {
        time: authoritative.time,
        open: authoritative.open,
        high: Math.max(local.high, authoritative.high),
        low: Math.min(local.low, authoritative.low),
        close: authoritative.close,
        // Un volumen 0 "autoritativo" es imposible en una vela con trades
        // (si no hubo trades no habría vela): señal de pipeline roto aguas
        // arriba → conservar el volumen local acumulado en vivo.
        volume: authoritative.volume > 0 ? authoritative.volume : local.volume,
    };
}

/**
 * Convierte una vela sellada del backend (formato bar_builder: ms + campos
 * largos) al formato del chart. Devuelve null si el payload es inválido.
 */
export function sealedToChartBar(sealed: {
    bar_start: number; open: number; high: number; low: number; close: number; volume: number;
}): ChartBar | null {
    if (!sealed || !Number.isFinite(sealed.bar_start) || !(sealed.open > 0)) return null;
    return {
        time: Math.floor(sealed.bar_start / 1000),
        open: sealed.open,
        high: sealed.high,
        low: sealed.low,
        close: sealed.close,
        volume: sealed.volume,
    };
}
