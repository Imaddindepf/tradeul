/**
 * marketTime — helpers puros de tiempo de mercado US (America/New_York).
 *
 * Única fuente de verdad en el frontend para:
 *   - minuto del día en ET (sesiones pre/regular/post)
 *   - fecha de calendario ET (rollover de día, VWAP, velas diarias)
 *   - timestamp de la vela diaria a partir de un tick
 *
 * Todo es determinista y sin estado de React → testeable en aislamiento.
 *
 * CALENDARIO (festivos/half-days): por defecto los helpers describen el
 * horario ESTÁNDAR del mercado US e ignoran festivos. Llamando a
 * setMarketCalendar() con los datos de market_session (/api/holidays),
 * getSessionKind/isRegularHours pasan a respetar cierres totales y cierres
 * anticipados (13:00 ET). useMarketClockSync carga el calendario al arrancar.
 * Limitación conocida: el backend solo expone festivos FUTUROS (Polygon
 * "upcoming"), así que velas históricas de half-days pasados se pintan con
 * horario estándar — aceptable para shading; la sesión ACTUAL siempre es
 * correcta porque además la valida el servidor.
 */

// Formatters cacheados: crear Intl.DateTimeFormat es caro (~100µs);
// format() sobre uno existente es barato (~1-5µs).
const ET_TIME_FMT = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: 'numeric',
    hour12: false,
});

// en-CA produce YYYY-MM-DD directamente.
const ET_DATE_FMT = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
});

// La fecha ET solo puede cambiar cuando cambia la hora UTC, así que cacheamos
// por bucket de hora. Los datos de velas llegan ordenados → hit rate ~100%.
let _lastDateBucket = -1;
let _lastDateString = '';

/** Fecha de calendario ET como 'YYYY-MM-DD'. */
export function etDateString(unixSecs: number): string {
    const bucket = Math.floor(unixSecs / 3600);
    if (bucket === _lastDateBucket) return _lastDateString;
    const s = ET_DATE_FMT.format(new Date(unixSecs * 1000));
    _lastDateBucket = bucket;
    _lastDateString = s;
    return s;
}

/** Minutos transcurridos desde medianoche ET (0–1439). */
export function getETMinuteOfDay(unixSecs: number): number {
    const parts = ET_TIME_FMT.format(new Date(unixSecs * 1000));
    const [h, m] = parts.split(':').map(Number);
    // Intl puede devolver "24" para medianoche en hourCycle h24.
    return ((h === 24 ? 0 : h) * 60 + m) % 1440;
}

const ET_WEEKDAY_FMT = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
});

/** ¿Es sábado o domingo en ET? */
export function isETWeekend(unixSecs: number): boolean {
    const wd = ET_WEEKDAY_FMT.format(new Date(unixSecs * 1000));
    return wd === 'Sat' || wd === 'Sun';
}

// ── Calendario de festivos/half-days ─────────────────────────────────────────

export interface CalendarDay {
    /** true = mercado cerrado todo el día */
    closed: boolean;
    /** minuto ET de cierre de la sesión regular (p.ej. 780 = 13:00 en half-day) */
    regularCloseMin: number;
}

// 'YYYY-MM-DD' → info del día. Vacío = todo horario estándar.
const _calendar = new Map<string, CalendarDay>();

/**
 * Instala el calendario de mercado. `holidays` en el formato del backend
 * (/api/holidays): { date, is_early_close, early_close_time }.
 */
export function setMarketCalendar(
    holidays: Array<{ date: string; is_early_close: boolean; early_close_time?: string | null }>
): void {
    _calendar.clear();
    for (const h of holidays) {
        if (!h?.date) continue;
        if (h.is_early_close && h.early_close_time) {
            const [hh, mm] = h.early_close_time.split(':').map(Number);
            const closeMin = (hh || 13) * 60 + (mm || 0);
            _calendar.set(h.date, { closed: false, regularCloseMin: closeMin });
        } else {
            _calendar.set(h.date, { closed: true, regularCloseMin: 0 });
        }
    }
}

/** Info de calendario para un instante (o null si es día estándar). */
export function getCalendarDay(unixSecs: number): CalendarDay | null {
    return _calendar.get(etDateString(unixSecs)) ?? null;
}

/** ¿Día hábil de mercado? (ni fin de semana ni festivo de cierre total) */
export function isTradingDay(unixSecs: number): boolean {
    if (isETWeekend(unixSecs)) return false;
    const cal = getCalendarDay(unixSecs);
    return !(cal?.closed);
}

/** Minuto ET de cierre regular del día del instante (960 estándar, 780 half-day). */
export function getRegularCloseMin(unixSecs: number): number {
    const cal = getCalendarDay(unixSecs);
    return cal && !cal.closed ? cal.regularCloseMin : 960;
}

/** Sesión regular US: 9:30 hasta el cierre del día (16:00, o 13:00 half-day). */
export function isRegularHours(unixSecs: number): boolean {
    if (!isTradingDay(unixSecs)) return false;
    const min = getETMinuteOfDay(unixSecs);
    return min >= 570 && min < getRegularCloseMin(unixSecs);
}

export type SessionKind = 'pre' | 'regular' | 'post' | 'closed';

/**
 * Sesión por hora ET, respetando calendario si está instalado
 * (fin de semana y festivos → 'closed'; half-days → regular termina antes
 * y el post-market arranca en el cierre anticipado).
 */
export function getSessionKind(unixSecs: number): SessionKind {
    if (!isTradingDay(unixSecs)) return 'closed';
    const min = getETMinuteOfDay(unixSecs);
    const closeMin = getRegularCloseMin(unixSecs);
    if (min >= 240 && min < 570) return 'pre';
    if (min >= 570 && min < closeMin) return 'regular';
    if (min >= closeMin && min < 1200) return 'post';
    return 'closed';
}

/**
 * Próximo instante (UTC, segundos) en el que cambiará la sesión de mercado.
 * Útil para programar un refetch justo en los boundaries (p.ej. 16:00 ET),
 * evitando depender de un polling de 60s que puede introducir ~55s de lag.
 *
 * Devuelve null si no puede determinarse (caso extremo).
 */
export function nextSessionTransitionUtcSeconds(nowUnixSecs: number): number | null {
    const now = Math.floor(nowUnixSecs);
    const today = etDateString(now);
    const todayMidnightUtc = etMidnightUtcSeconds(today);

    const minute = getETMinuteOfDay(now);
    const closeMin = getRegularCloseMin(now);

    const boundaryMinsToday = [240, 570, closeMin, 1200]; // pre start, market open, regular close, post end
    for (const m of boundaryMinsToday) {
        const t = todayMidnightUtc + m * 60;
        if (t > now) return t;
    }

    // Si ya pasó 20:00 ET, buscamos el próximo día hábil.
    // Iteramos hasta 14 días por seguridad (cubrir festivos encadenados).
    for (let i = 1; i <= 14; i++) {
        const candidateMidnightUtc = todayMidnightUtc + i * 86400;
        const candidateNoonUtc = candidateMidnightUtc + 12 * 3600;
        if (!isTradingDay(candidateNoonUtc)) continue;
        // Próxima sesión arranca en premarket (04:00 ET = 240).
        return candidateMidnightUtc + 240 * 60;
    }

    // Fallback: si no encontramos, programamos un refetch en 60s.
    return now + 60;
}

/**
 * Epoch (segundos) de la medianoche ET de una fecha 'YYYY-MM-DD' — la
 * convención de timestamp de las velas diarias de Polygon (04:00Z en EDT,
 * 05:00Z en EST). Sin dependencias de timezone: probamos los dos offsets
 * posibles de ET y verificamos contra Intl.
 */
export function etMidnightUtcSeconds(dateStr: string): number {
    const utcMidnight = Date.parse(`${dateStr}T00:00:00Z`) / 1000;
    for (const offMin of [240, 300]) { // EDT (UTC-4), EST (UTC-5)
        const guess = utcMidnight + offMin * 60;
        if (etDateString(guess) === dateStr && getETMinuteOfDay(guess) === 0) {
            return guess;
        }
    }
    // Inalcanzable para fechas US válidas; EST como último recurso.
    return utcMidnight + 300 * 60;
}

/**
 * Timestamp de la vela diaria a la que pertenece un tick.
 *
 * Mismo día ET que la última vela → reutiliza su timestamp. Día ET nuevo →
 * medianoche ET de la fecha del tick (convención exacta de Polygon).
 *
 * El código anterior sumaba 86400 fijo al detectar día distinto: colocaba la
 * primera vela del lunes en el sábado, fallaba tras festivos y derivaba una
 * hora en los cambios de DST (creando velas duplicadas del mismo día).
 */
export function dailyBarTime(tickUnixSecs: number, lastBarTime: number): number {
    const tickDate = etDateString(tickUnixSecs);
    if (tickDate === etDateString(lastBarTime)) return lastBarTime;
    return etMidnightUtcSeconds(tickDate);
}

/** ¿Pertenecen dos timestamps a fechas de calendario ET distintas? */
export function isDifferentETDay(unixSecsA: number, unixSecsB: number): boolean {
    return etDateString(unixSecsA) !== etDateString(unixSecsB);
}
