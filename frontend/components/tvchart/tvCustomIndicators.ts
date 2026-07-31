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
        ]);
}
