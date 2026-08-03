/**
 * tvCustomIndicators — indicadores PROPIOS de Tradeul para la Charting
 * Library v31, inyectados por la vía oficial `custom_indicators_getter`
 * (ChartingLibraryWidgetOptions): la librería los lista y gestiona como un
 * estudio más (diálogo, estilos, persistencia en widget.save()).
 *
 * RVOL — Volumen Relativo Intradía (port del Pine v5 del usuario, ©
 * LonesomeTheBlue, MPL 2.0): compara el volumen ACUMULADO de la sesión a la
 * altura del minuto actual contra la media del acumulado a ese mismo minuto
 * en los N días previos. Diferencias deliberadas con el Pine:
 *   - El "minuto de sesión" se mide desde el inicio de sesión detectado por
 *     hueco (>4 h sin barras), no por hora UTC: inmune a DST sin el input
 *     manual del script original, y válido para la sesión extendida 4:00-20:00.
 *   - La media divide entre los días CON datos (no entre N fijos): durante el
 *     warmup no infla el RVOL como hacía el original.
 */

/** Barra de estado que la CL empuja por main(); volumen puede faltar. */
type Ctx = any;

const SESSION_GAP_MS = 4 * 3600 * 1000;
/** 48 h de minutos por sesión (mismo colchón que el Pine original). */
const DAY_BUCKETS = 2880;

// ── VWAP autoanclado ────────────────────────────────────────────────────────
/**
 * Réplica del built-in "VWAP Auto Anchored" de TradingView (ES: "VWAP
 * autoanclado"). El estudio NO viene en el bundle de la Charting Library: su
 * nombre solo aparece en los ficheros de traducción.
 *
 * TradingView declara que este indicador NO está escrito en Pine y que no hay
 * forma de ver su código, así que esto es una reconstrucción a partir de:
 *   - La doc del anclaje "Auto" (soporte 43000652199), que es un mapeo
 *     determinista temporalidad→periodo, NO detección de pivotes.
 *   - El código Pine OFICIAL del VWAP incorporado (STD;VWAP), que sí es
 *     público: de ahí salen la varianza ponderada y el modo Porcentaje.
 */
const VWAP_ANCHORS = [
    'Automático', 'Sesión', 'Semana', 'Mes', 'Trimestre', 'Año', 'Década', 'Siglo',
    'Máximo más alto', 'Mínimo más bajo', 'Volumen más alto',
] as const;
/** Anclajes que consumen el input "Longitud" (los demás lo ignoran). */
const VWAP_LOOKBACK_ANCHORS = new Set(['Máximo más alto', 'Mínimo más bajo', 'Volumen más alto']);
/** Opciones de "Modo de cálculo de bandas". */
const VWAP_BAND_MODES = ['Desviación estándar', 'Porcentaje'] as const;

/**
 * Mapeo oficial del modo "Auto" (soporte 43000652199): el periodo depende de la
 * temporalidad del gráfico. `res` es PineJS.Std.period().
 */
function autoAnchorPeriod(res: string, isIntraday: boolean): string {
    if (isIntraday) return 'Sesión';
    const m = /^(\d+)([DWM]?)$/.exec(res.trim());
    if (!m) return 'Década';
    const n = parseInt(m[1], 10);
    const unit = m[2] || 'D';
    if (unit !== 'D') return 'Década'; // semanal y mensual
    if (n === 1) return 'Mes';
    if (n <= 10) return 'Trimestre';
    if (n <= 60) return 'Año';
    return 'Década';
}

/** Clave de periodo de calendario; al cambiar, se reancla. */
function periodKey(anchor: string, t: number): number {
    const d = new Date(t);
    const y = d.getUTCFullYear();
    switch (anchor) {
        case 'Semana': {
            const day = (d.getUTCDay() + 6) % 7; // lunes ISO
            return Math.floor((t - day * 86400000) / 86400000);
        }
        case 'Mes':
            return y * 12 + d.getUTCMonth();
        case 'Trimestre':
            return y * 4 + Math.floor(d.getUTCMonth() / 3);
        case 'Año':
            return y;
        case 'Década':
            return Math.floor(y / 10);
        case 'Siglo':
            return Math.floor(y / 100);
        default: // Sesión
            return Math.floor(t / 86400000);
    }
}

export function buildCustomIndicatorsGetter() {
    return (PineJS: any) =>
        Promise.resolve([
            {
                name: 'RVOL Volumen Relativo',
                metainfo: {
                    _metainfoVersion: 53,
                    id: 'TradeulRVOL@tv-basicstudies-1',
                    name: 'RVOL Volumen Relativo',
                    // OJO: createStudy() resuelve los custom por la DESCRIPTION
                    // exacta — debe coincidir con lo que lista el diálogo.
                    description: 'RVOL Volumen Relativo',
                    shortDescription: 'RVOL',
                    is_price_study: false,
                    isCustomIndicator: true,
                    format: { type: 'price', precision: 2 },
                    plots: [
                        { id: 'plot_0', type: 'line' },
                        { id: 'plot_1', type: 'colorer', target: 'plot_0', palette: 'palette_0' },
                    ],
                    palettes: {
                        palette_0: {
                            colors: { 0: { name: 'Vela alcista' }, 1: { name: 'Vela bajista' } },
                            valToIndex: { 0: 0, 1: 1 },
                        },
                    },
                    defaults: {
                        palettes: {
                            palette_0: {
                                colors: {
                                    0: { color: '#26a69a', width: 1, style: 0 },
                                    1: { color: '#ef5350', width: 1, style: 0 },
                                },
                            },
                        },
                        styles: {
                            // plottype 5 = Columns (LineStudyPlotStyle.Columns).
                            plot_0: {
                                linestyle: 0,
                                linewidth: 1,
                                plottype: 5,
                                trackPrice: false,
                                transparency: 0,
                                visible: true,
                                color: '#26a69a',
                            },
                        },
                        inputs: { in_0: 5 },
                    },
                    styles: { plot_0: { title: 'RVOL', histogramBase: 0 } },
                    inputs: [
                        {
                            id: 'in_0',
                            name: 'Número de días',
                            defval: 5,
                            type: 'integer',
                            min: 1,
                            max: 55,
                        },
                    ],
                },
                constructor: function (this: any) {
                    this.init = function (this: any) {
                        // Estado de la pasada secuencial sobre las barras.
                        this._days = [] as Float64Array[]; // sesiones cerradas (más nueva al final)
                        this._cur = new Float64Array(DAY_BUCKETS); // acumulado por minuto de la sesión en curso
                        this._dayStart = NaN;
                        this._lastBarTime = NaN;
                        this._cum = 0; // acumulado al CIERRE de la barra actual
                        this._cumAtBarStart = 0; // acumulado antes de la barra actual (realtime re-entra en main)
                        this._lastBucket = 0;
                    };

                    this.main = function (this: any, context: Ctx, inputCallback: (i: number) => number) {
                        this._context = context;
                        const Std = PineJS.Std;
                        const period = Math.max(1, Math.floor(inputCallback(0) || 5));

                        const res = String(Std.period(this._context) ?? '');
                        // Como el Pine original: solo intradía de minutos.
                        if (!Std.isintraday(this._context) || res.endsWith('S')) {
                            return [NaN, NaN];
                        }

                        const t = Std.time(this._context);
                        const v = Std.volume(this._context);
                        if (!isFinite(t)) return [NaN, NaN];
                        const vol = isFinite(v) ? v : 0;

                        // La CL recalcula desde el principio al cargar más
                        // histórico: si el tiempo retrocede, reset completo.
                        if (isFinite(this._lastBarTime) && t < this._lastBarTime) {
                            this.init();
                        }

                        if (t !== this._lastBarTime) {
                            // Barra NUEVA (no un update realtime de la misma).
                            if (!isFinite(this._dayStart) || t - this._lastBarTime > SESSION_GAP_MS) {
                                // Sesión nueva: archivar la anterior.
                                if (isFinite(this._dayStart)) {
                                    this._days.push(this._cur);
                                    if (this._days.length > 55) this._days.shift();
                                    this._cur = new Float64Array(DAY_BUCKETS);
                                }
                                this._dayStart = t;
                                this._cum = 0;
                                this._lastBucket = 0;
                            }
                            this._cumAtBarStart = this._cum;
                            this._lastBarTime = t;
                        }

                        const bucket = Math.min(
                            Math.max(Math.floor((t - this._dayStart) / 60000), 0),
                            DAY_BUCKETS - 1,
                        );

                        // Update realtime: REEMPLAZAR el volumen de la barra en
                        // curso, no acumularlo otra vez.
                        this._cum = this._cumAtBarStart + vol;
                        // Rellenar huecos (minutos sin barra) con el acumulado
                        // previo para que el lookup por minuto nunca caiga en 0.
                        for (let b = this._lastBucket + 1; b < bucket; b++) {
                            this._cur[b] = this._cumAtBarStart;
                        }
                        this._cur[bucket] = this._cum;
                        this._lastBucket = bucket;

                        // Baseline: media del acumulado a este minuto en los
                        // últimos `period` días CON datos (backward-fill por día,
                        // como el fallback del Pine).
                        const from = Math.max(0, this._days.length - period);
                        let sum = 0;
                        let n = 0;
                        for (let d = from; d < this._days.length; d++) {
                            const day = this._days[d];
                            let s = day[bucket];
                            if (s === 0) {
                                for (let b = bucket - 1; b >= 0; b--) {
                                    if (day[b] !== 0) {
                                        s = day[b];
                                        break;
                                    }
                                }
                            }
                            if (s > 0) {
                                sum += s;
                                n++;
                            }
                        }

                        const rvol = n > 0 ? this._cum / (sum / n) : NaN;
                        const colorIndex =
                            Std.close(this._context) >= Std.open(this._context) ? 0 : 1;
                        return [rvol, colorIndex];
                    };
                },
            },
            {
                name: 'VWAP autoanclado',
                metainfo: {
                    _metainfoVersion: 53,
                    id: 'TradeulAutoVWAP@tv-basicstudies-1',
                    name: 'VWAP autoanclado',
                    // createStudy() resuelve los custom por DESCRIPTION exacta.
                    description: 'VWAP autoanclado',
                    shortDescription: 'VWAP AA',
                    is_price_study: true,
                    isCustomIndicator: true,
                    format: { type: 'inherit' },
                    plots: [
                        { id: 'plot_vwap', type: 'line' },
                        { id: 'plot_u1', type: 'line' },
                        { id: 'plot_l1', type: 'line' },
                        { id: 'plot_u2', type: 'line' },
                        { id: 'plot_l2', type: 'line' },
                        { id: 'plot_u3', type: 'line' },
                        { id: 'plot_l3', type: 'line' },
                    ],
                    // Forma copiada del propio bundle de la CL (linetoolanchoredvwap
                    // usa objAId/objBId + type 'plot_plot').
                    filledAreas: [
                        { id: 'fill_1', objAId: 'plot_u1', objBId: 'plot_l1', type: 'plot_plot', title: 'Fondo #1' },
                        { id: 'fill_2', objAId: 'plot_u2', objBId: 'plot_l2', type: 'plot_plot', title: 'Fondo #2' },
                        { id: 'fill_3', objAId: 'plot_u3', objBId: 'plot_l3', type: 'plot_plot', title: 'Fondo #3' },
                    ],
                    defaults: {
                        styles: {
                            plot_vwap: { linestyle: 0, linewidth: 2, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#2962FF' },
                            plot_u1: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#4CAF50' },
                            plot_l1: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#4CAF50' },
                            plot_u2: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#808000' },
                            plot_l2: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#808000' },
                            plot_u3: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#008080' },
                            plot_l3: { linestyle: 0, linewidth: 1, plottype: 0, trackPrice: false, transparency: 0, visible: true, color: '#008080' },
                        },
                        filledAreasStyle: {
                            fill_1: { color: '#4CAF50', transparency: 95, visible: true },
                            fill_2: { color: '#808000', transparency: 95, visible: true },
                            fill_3: { color: '#008080', transparency: 95, visible: true },
                        },
                        inputs: {
                            in_anchor: 'Automático',
                            in_length: 14,
                            in_source: 'hlc3',
                            in_mode: 'Desviación estándar',
                            in_show1: true,
                            in_mult1: 1,
                            in_show2: false,
                            in_mult2: 2,
                            in_show3: false,
                            in_mult3: 3,
                            in_offset: 0,
                        },
                    },
                    styles: {
                        plot_vwap: { title: 'VWAP' },
                        plot_u1: { title: 'Banda superior #1' },
                        plot_l1: { title: 'Banda inferior #1' },
                        plot_u2: { title: 'Banda superior #2' },
                        plot_l2: { title: 'Banda inferior #2' },
                        plot_u3: { title: 'Banda superior #3' },
                        plot_l3: { title: 'Banda inferior #3' },
                    },
                    inputs: [
                        { id: 'in_anchor', name: 'Periodo de referencia', defval: 'Automático', type: 'text', options: [...VWAP_ANCHORS] },
                        { id: 'in_length', name: 'Longitud', defval: 14, type: 'integer', min: 2, max: 5000 },
                        { id: 'in_source', name: 'Fuente', defval: 'hlc3', type: 'source', options: ['open', 'high', 'low', 'close', 'hl2', 'hlc3', 'ohlc4'] },
                        { id: 'in_mode', name: 'Modo de cálculo de bandas', defval: 'Desviación estándar', type: 'text', options: [...VWAP_BAND_MODES] },
                        { id: 'in_show1', name: 'Banda #1', defval: true, type: 'bool' },
                        { id: 'in_mult1', name: 'Multiplicador de bandas #1', defval: 1, type: 'float', min: 0, max: 100 },
                        { id: 'in_show2', name: 'Banda #2', defval: false, type: 'bool' },
                        { id: 'in_mult2', name: 'Multiplicador de bandas #2', defval: 2, type: 'float', min: 0, max: 100 },
                        { id: 'in_show3', name: 'Banda #3', defval: false, type: 'bool' },
                        { id: 'in_mult3', name: 'Multiplicador de bandas #3', defval: 3, type: 'float', min: 0, max: 100 },
                        { id: 'in_offset', name: 'Compensación', defval: 0, type: 'integer', min: 0, max: 500 },
                    ],
                },
                constructor: function (this: any) {
                    const EMPTY = [NaN, NaN, NaN, NaN, NaN, NaN, NaN];

                    this.init = function (this: any) {
                        // Acumuladores ponderados por volumen desde el ancla.
                        // `*C` = valor COMMITEADO (hasta la barra anterior): en
                        // realtime main() re-entra para la misma barra y hay que
                        // recalcular sobre él, nunca volver a sumar. Mismo patrón
                        // que el RVOL de arriba.
                        this._sumV = 0; this._sumPV = 0; this._sumPPV = 0;
                        this._sumVC = 0; this._sumPVC = 0; this._sumPPVC = 0;
                        this._anchorId = null;   // clave de periodo o time del pivote
                        this._lastBarTime = NaN;
                        this._ring = [];         // barras commiteadas (modo Pivote)
                        this._out = [];          // salidas pasadas (Compensación)
                    };

                    this.main = function (this: any, context: Ctx, inputCallback: (i: number) => any) {
                        this._context = context;
                        const Std = PineJS.Std;

                        const anchorMode = String(inputCallback(0) ?? 'Automático');
                        const length = Math.max(2, Math.floor(Number(inputCallback(1)) || 14));
                        const srcName = String(inputCallback(2) ?? 'hlc3');
                        const bandMode = String(inputCallback(3) ?? 'Desviación estándar');
                        const show1 = inputCallback(4) !== false;
                        const mult1 = Number(inputCallback(5)) || 0;
                        const show2 = inputCallback(6) === true;
                        const mult2 = Number(inputCallback(7)) || 0;
                        const show3 = inputCallback(8) === true;
                        const mult3 = Number(inputCallback(9)) || 0;
                        const offset = Math.max(0, Math.floor(Number(inputCallback(10)) || 0));

                        const t = Std.time(this._context);
                        if (!isFinite(t)) return EMPTY;

                        const srcFn = (Std as any)[srcName] || Std.hlc3;
                        const src = Number(srcFn(this._context));
                        if (!isFinite(src)) return EMPTY;

                        const rawVol = Number(Std.volume(this._context));
                        // nz(volume): tolera barras sueltas sin volumen. Si el
                        // acumulado acaba en 0 (índices, forex) no se pinta nada
                        // — el built-in de TradingView tampoco degrada a media
                        // simple, aborta con "No volume is provided".
                        const vol = isFinite(rawVol) && rawVol > 0 ? rawVol : 0;

                        // La CL recalcula desde cero al cargar más histórico.
                        if (isFinite(this._lastBarTime) && t < this._lastBarTime) this.init();

                        // ── Barra nueva: commitear y recolocar el ancla ──────
                        if (t !== this._lastBarTime) {
                            if (isFinite(this._lastBarTime)) {
                                this._sumVC = this._sumV;
                                this._sumPVC = this._sumPV;
                                this._sumPPVC = this._sumPPV;
                                this._ring.push({
                                    t: this._lastBarTime,
                                    src: this._lastSrc,
                                    vol: this._lastVol,
                                    high: this._lastHigh,
                                    low: this._lastLow,
                                });
                                if (this._ring.length > length) this._ring.shift();
                            }
                            this._lastBarTime = t;

                            let anchorId: number;
                            if (VWAP_LOOKBACK_ANCHORS.has(anchorMode)) {
                                // Ancla = barra del extremo dentro de las últimas
                                // `Longitud` barras. Al moverse se recalcula desde
                                // ahí (como mucho `Longitud` barras: irrelevante).
                                let best = -Infinity, bestI = 0;
                                for (let i = 0; i < this._ring.length; i++) {
                                    const b = this._ring[i];
                                    const val = anchorMode === 'Máximo más alto' ? b.high
                                        : anchorMode === 'Mínimo más bajo' ? -b.low
                                            : b.vol;
                                    if (val >= best) { best = val; bestI = i; }
                                }
                                anchorId = this._ring.length ? this._ring[bestI].t : t;
                                if (anchorId !== this._anchorId) {
                                    this._anchorId = anchorId;
                                    this._sumVC = 0; this._sumPVC = 0; this._sumPPVC = 0;
                                    for (let i = bestI; i < this._ring.length; i++) {
                                        const b = this._ring[i];
                                        this._sumVC += b.vol;
                                        this._sumPVC += b.src * b.vol;
                                        this._sumPPVC += b.src * b.src * b.vol;
                                    }
                                }
                            } else {
                                const period = anchorMode === 'Automático'
                                    ? autoAnchorPeriod(String(Std.period(this._context) ?? ''), !!Std.isintraday(this._context))
                                    : anchorMode;
                                anchorId = periodKey(period, t);
                                if (anchorId !== this._anchorId) {
                                    this._anchorId = anchorId;
                                    this._sumVC = 0; this._sumPVC = 0; this._sumPPVC = 0;
                                }
                            }
                        }

                        this._lastSrc = src;
                        this._lastVol = vol;
                        this._lastHigh = Number(Std.high(this._context));
                        this._lastLow = Number(Std.low(this._context));

                        // ── Acumulado = commiteado + barra en curso ──────────
                        this._sumV = this._sumVC + vol;
                        this._sumPV = this._sumPVC + src * vol;
                        this._sumPPV = this._sumPPVC + src * src * vol;

                        if (!(this._sumV > 0)) return EMPTY;
                        const vwap = this._sumPV / this._sumV;
                        if (!isFinite(vwap)) return EMPTY;

                        let dev: number;
                        if (bandMode === 'Porcentaje') {
                            dev = vwap / 100; // banda = vwap * (1 ± mult/100)
                        } else {
                            // Varianza ponderada por volumen, en la MISMA forma
                            // incremental que el Pine oficial de STD;VWAP:
                            //   variance = sumSrcSrcVol/sumVol - vwap^2
                            //   variance := variance < 0 ? 0 : variance
                            // El recorte a 0 no es defensivo de más: con precios
                            // grandes y varianza diminuta, E[x²]−E[x]² sufre
                            // cancelación catastrófica y sale negativa.
                            const variance = this._sumPPV / this._sumV - vwap * vwap;
                            dev = Math.sqrt(Math.max(variance, 0));
                        }

                        const band = (show: boolean, m: number, sign: number) =>
                            show && m > 0 ? vwap + sign * m * dev : NaN;

                        const out = [
                            vwap,
                            band(show1, mult1, 1), band(show1, mult1, -1),
                            band(show2, mult2, 1), band(show2, mult2, -1),
                            band(show3, mult3, 1), band(show3, mult3, -1),
                        ];

                        if (offset === 0) return out;
                        // Compensación: desplaza la serie a la derecha devolviendo
                        // la salida de `offset` barras atrás (hacia la izquierda
                        // exigiría lookahead, por eso el input es >= 0).
                        this._out.push(out);
                        if (this._out.length > offset + 1) this._out.shift();
                        return this._out.length > offset ? this._out[0] : EMPTY;
                    };
                },
            },
        ]);
}
