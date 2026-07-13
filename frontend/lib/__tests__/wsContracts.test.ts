/**
 * Tests de lib/wsContracts — validación en el borde de los mensajes WS.
 *
 * El objetivo de estos guards es que una ruptura de contrato en el servidor
 * (campo renombrado, payload malformado) se traduzca en mensajes DESCARTADOS
 * y contados, nunca en velas con NaN/undefined.
 */

import { describe, it, expect } from 'vitest';
import {
    isChartAggregateMsg,
    isChartBarSealedMsg,
    isConnectedWithSessionMsg,
    isMarketSessionChangeMsg,
    getRejectedCounts,
} from '../wsContracts';

const validAggregate = () => ({
    type: 'chart_aggregate',
    symbol: 'AAPL',
    data: { o: 10, h: 11, l: 9, c: 10.5, v: 1000, t: 1783962780000 },
    seq: 42,
});

const validSealed = () => ({
    type: 'chart_bar_sealed',
    symbol: 'AAPL',
    data: {
        symbol: 'AAPL', timeframe: 1,
        bar_start: 1783962780000, bar_end: 1783962840000,
        open: 10, high: 11, low: 9, close: 10.5, volume: 5000,
    },
    seq: 43,
});

describe('isChartAggregateMsg', () => {
    it('acepta un aggregate válido (con y sin campos opcionales)', () => {
        expect(isChartAggregateMsg(validAggregate())).toBe(true);
        expect(isChartAggregateMsg({ ...validAggregate(), source: 'trades', av: 99999 })).toBe(true);
    });

    it('rechaza tipos ajenos sin contarlos como malformados', () => {
        const before = getRejectedCounts()['chart_aggregate'] || 0;
        expect(isChartAggregateMsg({ type: 'snapshot' })).toBe(false);
        expect(getRejectedCounts()['chart_aggregate'] || 0).toBe(before);
    });

    it('rechaza y CUENTA payloads malformados (la clase de bug v/volume)', () => {
        const before = getRejectedCounts()['chart_aggregate'] || 0;
        const noVolume = validAggregate() as any;
        delete noVolume.data.v; // el servidor renombró el campo → v undefined
        expect(isChartAggregateMsg(noVolume)).toBe(false);

        const nanPrice = validAggregate() as any;
        nanPrice.data.c = NaN;
        expect(isChartAggregateMsg(nanPrice)).toBe(false);

        const zeroPrice = validAggregate() as any;
        zeroPrice.data.c = 0; // close=0 no es un tick real
        expect(isChartAggregateMsg(zeroPrice)).toBe(false);

        const noData = { type: 'chart_aggregate', symbol: 'AAPL' };
        expect(isChartAggregateMsg(noData)).toBe(false);

        expect(getRejectedCounts()['chart_aggregate']).toBe(before + 4);
    });
});

describe('isChartBarSealedMsg', () => {
    it('acepta una vela sellada válida de bar_builder', () => {
        expect(isChartBarSealedMsg(validSealed())).toBe(true);
    });

    it('rechaza velas sin timeframe, sin bar_start o con open<=0', () => {
        const noTf = validSealed() as any;
        delete noTf.data.timeframe;
        expect(isChartBarSealedMsg(noTf)).toBe(false);

        const badStart = validSealed() as any;
        badStart.data.bar_start = 0;
        expect(isChartBarSealedMsg(badStart)).toBe(false);

        const zeroOpen = validSealed() as any;
        zeroOpen.data.open = 0;
        expect(isChartBarSealedMsg(zeroOpen)).toBe(false);
    });
});

describe('mensajes de sesión', () => {
    it('connected solo cuenta como snapshot de sesión si trae current_session válida', () => {
        expect(isConnectedWithSessionMsg({ type: 'connected', current_session: 'PRE_MARKET' })).toBe(true);
        expect(isConnectedWithSessionMsg({ type: 'connected' })).toBe(false);
        expect(isConnectedWithSessionMsg({ type: 'connected', current_session: 'INVALID' })).toBe(false);
    });

    it('market_session_change exige data.current_session del enum', () => {
        expect(isMarketSessionChangeMsg({
            type: 'market_session_change',
            data: { current_session: 'MARKET_OPEN', trading_date: '2026-07-13' },
        })).toBe(true);
        expect(isMarketSessionChangeMsg({ type: 'market_session_change', data: {} })).toBe(false);
        expect(isMarketSessionChangeMsg({ type: 'market_session_change' })).toBe(false);
    });
});
