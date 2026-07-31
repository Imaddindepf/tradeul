/**
 * Tests de lib/utils/numberFormat — parseo/formato de números abreviados.
 *
 * parseCellNumber es el parser unificado de CELDAS de tabla del agente
 * (AutoChart, InteractiveTable, StructuredTable): sufijos K/M/B/T, %, x,
 * moneda, negrita markdown, negativos contables y placeholders de "sin
 * dato". parseHumanNumber (entrada de filtros) NO debe cambiar: aquí se
 * fija su semántica para que ningún refactor la cruce con la de celdas.
 */

import { describe, it, expect } from 'vitest';
import { parseCellNumber, parseHumanNumber, formatCompact } from '../utils/numberFormat';

describe('parseCellNumber', () => {
    it('sufijos K/M/B/T con moneda', () => {
        expect(parseCellNumber('$2.28B')).toBe(2.28e9);
        expect(parseCellNumber('666.1M')).toBe(666.1e6);
        expect(parseCellNumber('500K')).toBe(500e3);
        expect(parseCellNumber('1.5T')).toBe(1.5e12);
    });

    it('sufijos case-insensitive', () => {
        expect(parseCellNumber('2.28b')).toBe(2.28e9);
        expect(parseCellNumber('666.1m')).toBe(666.1e6);
    });

    it('porcentajes con signo (el % no escala)', () => {
        expect(parseCellNumber('+69.01%')).toBe(69.01);
        expect(parseCellNumber('-5.3%')).toBe(-5.3);
    });

    it('múltiplos "x" (RVOL, ratios)', () => {
        expect(parseCellNumber('2.62x')).toBe(2.62);
        expect(parseCellNumber('0.85X')).toBe(0.85);
    });

    it('ignora markers de negrita markdown', () => {
        expect(parseCellNumber('**$1.2B**')).toBe(1.2e9);
        expect(parseCellNumber('**+3.4%**')).toBe(3.4);
    });

    it('separadores de miles', () => {
        expect(parseCellNumber('1,234.5')).toBe(1234.5);
        expect(parseCellNumber('$1,000,000')).toBe(1e6);
    });

    it('negativo contable entre paréntesis', () => {
        expect(parseCellNumber('(2.3M)')).toBe(-2.3e6);
        expect(parseCellNumber('($450K)')).toBe(-450e3);
    });

    it('placeholders de "sin dato" → null', () => {
        expect(parseCellNumber('N/A')).toBeNull();
        expect(parseCellNumber('n/a')).toBeNull();
        expect(parseCellNumber('—')).toBeNull();
        expect(parseCellNumber('-')).toBeNull();
        expect(parseCellNumber('')).toBeNull();
        expect(parseCellNumber('   ')).toBeNull();
        expect(parseCellNumber(null)).toBeNull();
        expect(parseCellNumber(undefined)).toBeNull();
    });

    it('rangos y texto → null', () => {
        expect(parseCellNumber('$1.02 - $2.28')).toBeNull();
        expect(parseCellNumber('Very Bullish')).toBeNull();
        expect(parseCellNumber('Q2 2026')).toBeNull();
    });

    it('números simples con signo', () => {
        expect(parseCellNumber('42')).toBe(42);
        expect(parseCellNumber('-0.5')).toBe(-0.5);
        expect(parseCellNumber('+12.75')).toBe(12.75);
    });
});

describe('formatCompact', () => {
    it('elige la unidad más legible y recorta ceros', () => {
        expect(formatCompact(2.28e9)).toBe('2.28B');
        expect(formatCompact(666.1e6)).toBe('666.1M');
        expect(formatCompact(1500)).toBe('1.5K');
        expect(formatCompact(-2e6)).toBe('-2M');
        expect(formatCompact(999)).toBe('999');
    });
});

describe('parseHumanNumber (sin cambios: FilterNumInput depende de esta semántica)', () => {
    it("'100m' sigue siendo 1e8 y '2x' sigue siendo null", () => {
        expect(parseHumanNumber('100m')).toBe(1e8);
        expect(parseHumanNumber('2x')).toBeNull();
        expect(parseHumanNumber('5,000,000')).toBe(5000000);
        expect(parseHumanNumber('$12.50')).toBe(12.5);
    });
});
