/**
 * Tests de lib/barAggregation — el corazón de la agregación de ticks WS.
 *
 * Cubre: merge en la vela actual, apertura de vela contigua, huecos
 * (backfill en vez de velas interpoladas), ticks reordenados, comportamiento
 * de diario+ fuera de sesión regular, merge de velas autoritativas (selladas)
 * y conversión del formato de bar_builder.
 */

import { describe, it, expect } from 'vitest';
import {
    applyAggregate,
    mergeAuthoritativeBar,
    sealedToChartBar,
    type ChartBar,
    type AggregatePayload,
} from '../barAggregation';

const utc = (iso: string): number => Date.parse(iso) / 1000;

// Lunes 2026-07-13, 10:00:00 ET = 14:00Z (EDT)
const T0 = utc('2026-07-13T14:00:00Z');

const bar = (time: number, overrides: Partial<ChartBar> = {}): ChartBar => ({
    time, open: 10, high: 11, low: 9, close: 10.5, volume: 1000, ...overrides,
});

const agg = (tSecs: number, overrides: Partial<AggregatePayload> = {}): AggregatePayload => ({
    o: 10.6, h: 10.8, l: 10.4, c: 10.7, v: 250, t: tSecs * 1000, ...overrides,
});

describe('applyAggregate — intradía (1min)', () => {
    it('tick del mismo bucket → merge: open se conserva, extremos se extienden, volumen suma', () => {
        const last = bar(T0);
        const action = applyAggregate(last, agg(T0 + 30, { h: 12, l: 8.5, c: 11.5, v: 300 }), 60, false);
        expect(action).toEqual({
            kind: 'merge',
            bar: { time: T0, open: 10, high: 12, low: 8.5, close: 11.5, volume: 1300 },
        });
    });

    it('tick del bucket contiguo siguiente → new-bar con los datos del tick', () => {
        const last = bar(T0);
        const action = applyAggregate(last, agg(T0 + 65), 60, false);
        expect(action.kind).toBe('new-bar');
        if (action.kind === 'new-bar') {
            expect(action.bar.time).toBe(T0 + 60);
            expect(action.bar.open).toBe(10.6);
            expect(action.bar.volume).toBe(250);
        }
    });

    it('hueco de ≥1 vela → gap-backfill, nunca velas inventadas', () => {
        const last = bar(T0);
        // Tick 3 minutos después: faltan las velas de T0+60 y T0+120
        const action = applyAggregate(last, agg(T0 + 185), 60, false);
        expect(action).toEqual({ kind: 'gap-backfill' });
    });

    it('tick anterior a la vela actual (reordenado/duplicado) → ignore', () => {
        const last = bar(T0 + 120);
        const action = applyAggregate(last, agg(T0 + 30), 60, false);
        expect(action).toEqual({ kind: 'ignore' });
    });

    it('sin vela de referencia → ignore', () => {
        expect(applyAggregate(null, agg(T0), 60, false)).toEqual({ kind: 'ignore' });
    });

    it('alineación de bucket para 5min', () => {
        const fiveMin = 300;
        const barStart = Math.floor(T0 / fiveMin) * fiveMin;
        const last = bar(barStart);
        // Tick a 4:59 del bucket → merge; a 5:01 → new-bar
        expect(applyAggregate(last, agg(barStart + 299), fiveMin, false).kind).toBe('merge');
        const next = applyAggregate(last, agg(barStart + 301), fiveMin, false);
        expect(next.kind).toBe('new-bar');
        if (next.kind === 'new-bar') expect(next.bar.time).toBe(barStart + fiveMin);
    });
});

describe('applyAggregate — diario', () => {
    const dayBar = utc('2026-07-13T04:00:00Z'); // vela diaria del lunes (medianoche ET)

    it('tick en sesión regular del mismo día ET → merge sobre la vela diaria', () => {
        const last = bar(dayBar);
        const action = applyAggregate(last, agg(T0), 86400, true);
        expect(action.kind).toBe('merge');
        if (action.kind === 'merge') expect(action.bar.time).toBe(dayBar);
    });

    it('tick de pre-market → extended-hours (no toca la vela diaria)', () => {
        const preMarketTick = utc('2026-07-13T12:00:00Z'); // 8:00 ET
        const action = applyAggregate(bar(dayBar), agg(preMarketTick, { c: 99.9 }), 86400, true);
        expect(action).toEqual({ kind: 'extended-hours', price: 99.9 });
    });

    it('lunes tras la vela del viernes → new-bar en el LUNES (sin gap falso de fin de semana)', () => {
        const fridayBar = utc('2026-07-10T04:00:00Z');
        const mondayOpenTick = utc('2026-07-13T13:30:00Z'); // 9:30 ET lunes
        const action = applyAggregate(bar(fridayBar), agg(mondayOpenTick), 86400, true);
        expect(action.kind).toBe('new-bar');
        if (action.kind === 'new-bar') {
            expect(action.bar.time).toBe(utc('2026-07-13T04:00:00Z'));
        }
    });
});

describe('mergeAuthoritativeBar', () => {
    it('open/close/volumen del backend mandan; extremos locales se conservan si son mayores', () => {
        const local = bar(T0, { open: 10.1, high: 12.5, low: 8.9, close: 10.4, volume: 900 });
        const authoritative = bar(T0, { open: 10.0, high: 11.8, low: 9.1, close: 10.45, volume: 1050 });
        expect(mergeAuthoritativeBar(local, authoritative)).toEqual({
            time: T0,
            open: 10.0,      // open real del backend
            high: 12.5,      // extremo local visto en vivo
            low: 8.9,        // extremo local visto en vivo
            close: 10.45,    // close consolidado
            volume: 1050,    // volumen exacto, NO suma
        });
    });
});

describe('mergeAuthoritativeBar — volumen 0 defensivo', () => {
    it('si el backend reporta volume=0 (pipeline roto), conserva el volumen local', () => {
        const local = bar(T0, { volume: 900 });
        const authoritative = bar(T0, { volume: 0 });
        expect(mergeAuthoritativeBar(local, authoritative).volume).toBe(900);
    });
});

describe('sealedToChartBar', () => {
    it('convierte el formato bar_builder (ms) al del chart (segundos)', () => {
        const sealed = {
            bar_start: T0 * 1000, open: 10, high: 11, low: 9, close: 10.5, volume: 5000,
        };
        expect(sealedToChartBar(sealed)).toEqual({
            time: T0, open: 10, high: 11, low: 9, close: 10.5, volume: 5000,
        });
    });

    it('payload inválido → null', () => {
        expect(sealedToChartBar({ bar_start: NaN, open: 10, high: 11, low: 9, close: 10, volume: 0 })).toBeNull();
        expect(sealedToChartBar({ bar_start: T0 * 1000, open: 0, high: 0, low: 0, close: 0, volume: 0 })).toBeNull();
    });
});
