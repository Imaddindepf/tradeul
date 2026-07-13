/**
 * Tests de lib/marketTime — la base de tiempo del motor de gráficos.
 *
 * Cubre exactamente las clases de bug encontradas en la auditoría:
 *   - rollover de día ET vs UTC (20:00–23:59 ET)
 *   - vela diaria del lunes cayendo en sábado (fin de semana/festivos)
 *   - deriva de 1h en cambios de DST
 *   - límites de sesión pre/regular/post
 */

import { describe, it, expect, afterEach } from 'vitest';
import {
    etDateString,
    getETMinuteOfDay,
    isRegularHours,
    getSessionKind,
    dailyBarTime,
    etMidnightUtcSeconds,
    isDifferentETDay,
    isETWeekend,
    isTradingDay,
    setMarketCalendar,
} from '../marketTime';

// El calendario es estado de módulo: dejarlo limpio tras cada test.
afterEach(() => setMarketCalendar([]));

/** Epoch en segundos de un instante UTC ISO. */
const utc = (iso: string): number => Date.parse(iso) / 1000;

describe('etDateString', () => {
    it('mapea instantes UTC a la fecha de calendario ET', () => {
        // Julio = EDT (UTC-4). 03:59Z del día 13 son las 23:59 ET del día 12.
        expect(etDateString(utc('2026-07-13T03:59:00Z'))).toBe('2026-07-12');
        expect(etDateString(utc('2026-07-13T04:00:00Z'))).toBe('2026-07-13');
        // Enero = EST (UTC-5). 04:59Z del día 15 son las 23:59 ET del día 14.
        expect(etDateString(utc('2026-01-15T04:59:00Z'))).toBe('2026-01-14');
        expect(etDateString(utc('2026-01-15T05:00:00Z'))).toBe('2026-01-15');
    });

    it('post-market tardío (20:00–23:59 ET) sigue siendo "hoy" aunque UTC ya sea mañana', () => {
        // 2026-07-13 21:30 ET = 2026-07-14 01:30 UTC
        expect(etDateString(utc('2026-07-14T01:30:00Z'))).toBe('2026-07-13');
    });
});

describe('getETMinuteOfDay / isRegularHours / getSessionKind', () => {
    it('calcula el minuto ET correcto en EDT y EST', () => {
        expect(getETMinuteOfDay(utc('2026-07-13T13:30:00Z'))).toBe(570);  // 9:30 EDT
        expect(getETMinuteOfDay(utc('2026-01-15T14:30:00Z'))).toBe(570);  // 9:30 EST
        expect(getETMinuteOfDay(utc('2026-07-13T04:00:00Z'))).toBe(0);    // medianoche EDT
    });

    it('límites exactos de la sesión regular (9:30–16:00 ET)', () => {
        expect(isRegularHours(utc('2026-07-13T13:29:59Z'))).toBe(false); // 9:29:59
        expect(isRegularHours(utc('2026-07-13T13:30:00Z'))).toBe(true);  // 9:30:00
        expect(isRegularHours(utc('2026-07-13T19:59:59Z'))).toBe(true);  // 15:59:59
        expect(isRegularHours(utc('2026-07-13T20:00:00Z'))).toBe(false); // 16:00:00
    });

    it('límites de todas las sesiones', () => {
        expect(getSessionKind(utc('2026-07-13T07:59:00Z'))).toBe('closed');  // 3:59 ET
        expect(getSessionKind(utc('2026-07-13T08:00:00Z'))).toBe('pre');     // 4:00 ET
        expect(getSessionKind(utc('2026-07-13T13:29:00Z'))).toBe('pre');     // 9:29 ET
        expect(getSessionKind(utc('2026-07-13T13:30:00Z'))).toBe('regular'); // 9:30 ET
        expect(getSessionKind(utc('2026-07-13T20:00:00Z'))).toBe('post');    // 16:00 ET
        expect(getSessionKind(utc('2026-07-13T23:59:00Z'))).toBe('post');    // 19:59 ET
        expect(getSessionKind(utc('2026-07-14T00:00:00Z'))).toBe('closed');  // 20:00 ET
    });
});

describe('etMidnightUtcSeconds', () => {
    it('convención Polygon: medianoche ET en UTC (04:00Z EDT, 05:00Z EST)', () => {
        expect(etMidnightUtcSeconds('2026-07-13')).toBe(utc('2026-07-13T04:00:00Z'));
        expect(etMidnightUtcSeconds('2026-01-15')).toBe(utc('2026-01-15T05:00:00Z'));
    });
});

describe('dailyBarTime', () => {
    it('mismo día ET → reutiliza el timestamp de la última vela', () => {
        const fridayBar = etMidnightUtcSeconds('2026-07-10');
        const fridayNoonTick = utc('2026-07-10T16:00:00Z'); // 12:00 ET viernes
        expect(dailyBarTime(fridayNoonTick, fridayBar)).toBe(fridayBar);
    });

    it('fin de semana: el primer tick del lunes crea la vela del LUNES, no del sábado', () => {
        const fridayBar = etMidnightUtcSeconds('2026-07-10');
        const mondayOpenTick = utc('2026-07-13T13:30:00Z'); // 9:30 ET lunes
        const result = dailyBarTime(mondayOpenTick, fridayBar);
        expect(result).toBe(etMidnightUtcSeconds('2026-07-13'));
        expect(etDateString(result)).toBe('2026-07-13');
        // El bug antiguo (+86400) habría dado sábado:
        expect(result).not.toBe(fridayBar + 86400);
    });

    it('festivo largo: salta los días no hábiles correctamente', () => {
        // Independence Day 2026 cae en sábado; viernes 3 festivo → último día
        // hábil jueves 2, siguiente lunes 6.
        const thursdayBar = etMidnightUtcSeconds('2026-07-02');
        const mondayTick = utc('2026-07-06T13:30:00Z');
        expect(dailyBarTime(mondayTick, thursdayBar)).toBe(etMidnightUtcSeconds('2026-07-06'));
    });

    it('cambio de DST (EST→EDT): sin deriva de 1 hora', () => {
        // DST 2026 empieza el domingo 8 de marzo. Viernes 6 = EST, lunes 9 = EDT.
        const fridayBar = etMidnightUtcSeconds('2026-03-06'); // 05:00Z
        const mondayTick = utc('2026-03-09T13:30:00Z'); // 9:30 EDT lunes
        const result = dailyBarTime(mondayTick, fridayBar);
        expect(result).toBe(utc('2026-03-09T04:00:00Z')); // 04:00Z, no 05:00Z
        expect(etDateString(result)).toBe('2026-03-09');
    });

    it('cambio de DST (EDT→EST): sin deriva de 1 hora', () => {
        // DST 2026 termina el domingo 1 de noviembre. Viernes 30-oct = EDT.
        const fridayBar = etMidnightUtcSeconds('2026-10-30'); // 04:00Z
        const mondayTick = utc('2026-11-02T14:30:00Z'); // 9:30 EST lunes
        const result = dailyBarTime(mondayTick, fridayBar);
        expect(result).toBe(utc('2026-11-02T05:00:00Z')); // 05:00Z, no 04:00Z
        expect(etDateString(result)).toBe('2026-11-02');
    });
});

describe('calendario (festivos y half-days)', () => {
    it('fin de semana ET → closed aunque la hora sea de mercado', () => {
        // Sábado 2026-07-11, 12:00 ET
        const saturdayNoon = utc('2026-07-11T16:00:00Z');
        expect(isETWeekend(saturdayNoon)).toBe(true);
        expect(isTradingDay(saturdayNoon)).toBe(false);
        expect(getSessionKind(saturdayNoon)).toBe('closed');
        expect(isRegularHours(saturdayNoon)).toBe(false);
    });

    it('festivo de cierre total → closed todo el día', () => {
        setMarketCalendar([
            { date: '2026-12-25', is_early_close: false, early_close_time: null },
        ]);
        const xmasNoon = utc('2026-12-25T17:00:00Z'); // 12:00 ET, viernes
        expect(isTradingDay(xmasNoon)).toBe(false);
        expect(getSessionKind(xmasNoon)).toBe('closed');
        expect(isRegularHours(xmasNoon)).toBe(false);
    });

    it('half-day (cierre 13:00 ET): regular termina antes y post arranca a las 13:00', () => {
        setMarketCalendar([
            { date: '2026-11-27', is_early_close: true, early_close_time: '13:00:00' },
        ]);
        // Black Friday 2026-11-27 (EST, UTC-5)
        const at1230 = utc('2026-11-27T17:30:00Z'); // 12:30 ET
        const at1301 = utc('2026-11-27T18:01:00Z'); // 13:01 ET
        const at1530 = utc('2026-11-27T20:30:00Z'); // 15:30 ET (sería regular en día normal)
        expect(getSessionKind(at1230)).toBe('regular');
        expect(isRegularHours(at1230)).toBe(true);
        expect(getSessionKind(at1301)).toBe('post');
        expect(isRegularHours(at1301)).toBe(false);
        expect(getSessionKind(at1530)).toBe('post');
    });

    it('sin calendario instalado, el comportamiento estándar se mantiene', () => {
        const monday1530 = utc('2026-07-13T19:30:00Z'); // 15:30 ET lunes
        expect(getSessionKind(monday1530)).toBe('regular');
        expect(isRegularHours(monday1530)).toBe(true);
    });
});

describe('isDifferentETDay', () => {
    it('frontera de VWAP: día ET, no día local ni UTC', () => {
        // 19:59 ET vs 20:01 ET del mismo día: mismo día ET aunque en UTC
        // cruzan medianoche (23:59Z vs 00:01Z).
        expect(isDifferentETDay(utc('2026-07-13T23:59:00Z'), utc('2026-07-14T00:01:00Z'))).toBe(false);
        // 23:59 ET vs 00:01 ET: día ET distinto.
        expect(isDifferentETDay(utc('2026-07-14T03:59:00Z'), utc('2026-07-14T04:01:00Z'))).toBe(true);
    });
});
