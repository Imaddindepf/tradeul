'use client';

/**
 * L2ReplayContent — ventana flotante "L2 Replay": montaje Level 2 por venue
 * reproducido desde histórico Databento (15 prop feeds), estilo profesional.
 *
 * Anatomía (referencia IBKR Market Depth, con nuestro chrome):
 *   1. Toolbar: símbolo · fecha · hora ET · bloque · fidelidad · paleta · Cargar · coste
 *   2. Strip de cotización: last, bid/ask/spread consolidados, venues vivos
 *   3. Curva de profundidad acumulada (canvas, bid izquierda / ask derecha)
 *   4. Montaje: una fila por venue y lado, bandas por NIVEL DE PRECIO
 *   5. Tape lateral virtualizado (@tanstack/react-virtual, buffer acotado)
 *   6. Transporte: play/pausa · reloj ET · scrub · velocidad
 *
 * Ingeniería de render (lección de tablas de alta frecuencia: CONFLACIÓN):
 *   - El payload (frames + tape) vive en refs, NUNCA en estado React.
 *   - Un rAF avanza el reloj virtual y aplica frames sobre bookRef (mutable).
 *   - React solo se entera a ≤20 fps: un único bump de versión por commit.
 *   - El montaje son ≤15 filas/lado (no necesita virtualizador); el tape sí
 *     va virtualizado con fila fija de 20 px y buffer circular de 250.
 *   - Pestaña oculta ⇒ el navegador pausa el rAF: se muestra chip de pausa y
 *     el dt se acota a 250 ms para que nunca haya saltos de cientos de frames.
 *
 * Color: la profundidad es dato ORDENADO ⇒ un tono por lado con escalones de
 * luminosidad (rampas validadas), nunca arcoíris por nivel. La paleta por
 * defecto es neutra (el lado ya lo da la posición); azul/ámbar para tinte
 * CVD-safe; verde/rojo clásica opt-in. Verde/rojo pleno se reserva al tape,
 * donde sí tiene significado consensuado (agresor al ask / al bid).
 */

import React, {
    memo,
    useCallback,
    useEffect,
    useMemo,
    useReducer,
    useRef,
    useState,
    type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Play, Pause, Coins, EyeOff, Settings2 } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { useLinkGroupSubscription } from '@/hooks/useLinkGroup';
import { useReplayClockStore } from '@/stores/useReplayClockStore';
import { useAuthFetch } from '@/hooks/useAuthFetch';

// ============================================================================
// Tipos del payload (contrato de /api/v1/l2replay/result)
// ============================================================================

type Frame = [number, Array<[number, number | null, number, number | null, number]>];
type TapePrint = [number, number, number, number]; // [ms, price, size, venueIdx]

interface ReplayPayload {
    ok: boolean;
    error?: string;
    symbol: string;
    schema: string;
    venues: string[];
    startUtc: string;
    durationMs: number;
    conflateMs: number;
    initial: Array<[number, number | null, number, number | null, number]>;
    frames: Frame[];
    tape: TapePrint[];
    cached: boolean;
    errors: Record<string, string>;
}

interface L2Settings {
    symbol?: string;
    minutes?: number;
    schema?: 'mbp-1' | 'bbo-1s';
    palette?: PaletteKey;
    speed?: number;
    date?: string;
    time?: string;
    [key: string]: unknown;
}

// ============================================================================
// Paletas (rampas ordinales VALIDADAS: monotonía, ΔL≥0.06, extremo ≥2:1)
// ============================================================================

type PaletteKey = 'neutral' | 'safe' | 'classic';

interface Palette {
    bid: string[];   // nivel 0 (toque) → 2; del 3 en adelante sin banda
    ask: string[];
    deepBid: string; // color del precio fuera de banda
    deepAsk: string;
    curveBid: string; // curva de profundidad
    curveAsk: string;
}

const PALETTES: Record<PaletteKey, Palette> = {
    neutral: {
        bid: ['#6b7681', '#57626d', '#444e59'],
        ask: ['#6b7681', '#57626d', '#444e59'],
        deepBid: '#9aa6b3', deepAsk: '#9aa6b3',
        curveBid: '#7f96ad', curveAsk: '#ad9a7f',
    },
    safe: {
        bid: ['#4078b0', '#2b6399', '#144f84'],
        ask: ['#996a06', '#835600', '#6e4200'],
        deepBid: '#7fb0e0', deepAsk: '#d0a03a',
        curveBid: '#4078b0', curveAsk: '#c08b1e',
    },
    classic: {
        bid: ['#2a8858', '#057345', '#005f32'],
        ask: ['#ba5b55', '#a24541', '#8a2f2d'],
        deepBid: '#5fcf9a', deepAsk: '#e08b85',
        curveBid: '#2a8858', curveAsk: '#ba5b55',
    },
};

// ============================================================================
// Constantes de motor
// ============================================================================

const COMMIT_MS = 50;          // conflación de UI: ≤20 commits/s hacia React
const FLASH_PX_MS = 450;       // destello de cambio de precio (aclara su banda)
const FLASH_SZ_MS = 300;       // tinte del texto del size
const STALE_MS = 8000;         // venue sin cotizar ⇒ fila atenuada
const TAPE_BUFFER = 250;       // buffer circular del tape visible
const TAPE_ROW_H = 20;         // fila fija (estándar de ventanas: datos 20px)
const FIRST_BLOCK_SEC = 30;    // primer bloque corto: primer pintado antes
// Precarga por COLCHÓN DE PARED, no por tiempo de mercado restante. 90 s de
// mercado dan 90 s reales para pedir a 1×, pero solo 18 s a 5×: un umbral fijo
// en ms de mercado dispara tarde justo cuando menos margen hay. Se pide cuando
// el tiempo real que queda baja de lo que tarda una petición, medido.
const PREFETCH_K = 2.5;        // factor sobre la latencia medida
const PREFETCH_FLOOR_MS = 8000; // suelo: nunca esperar a tener menos que esto
const HIST_START = '2018-05-01';

const fmtPx = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(2));
const fmtSz = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v));

/** Último día hábil cerrado (histórico = T+1). */
function lastTradingDay(): string {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
}

/** UTC ms → 'HH:MM:SS' en ET (formatter cacheado: crearlo por fila es carísimo). */
const etFmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hour12: false,
    hour: '2-digit', minute: '2-digit', second: '2-digit',
});
const etDateFmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
});

// ============================================================================
// Estado mutable del motor (fuera de React)
// ============================================================================

interface VenueState {
    bp: number | null; bs: number;
    ap: number | null; as: number;
    tBid: number; tAsk: number;          // reloj virtual del último cambio por lado
    dirBid: 'px' | 'up' | 'dn' | null;   // para destellos
    dirAsk: 'px' | 'up' | 'dn' | null;
}

interface Engine {
    payload: ReplayPayload | null;
    book: VenueState[];
    cursor: number;        // próximo frame
    tapeCursor: number;
    clock: number;         // ms virtuales desde startUtc
    startUtcMs: number;
    durationMs: number;    // crece al encadenar bloques
    tape: TapePrint[];     // buffer circular más-reciente-primero
    lastPx: number | null;
    prevPx: number | null;
    exhausted: boolean;
    extending: boolean;
}

const freshEngine = (): Engine => ({
    payload: null, book: [], cursor: 0, tapeCursor: 0, clock: 0,
    startUtcMs: 0, durationMs: 0, tape: [], lastPx: null, prevPx: null,
    exhausted: false, extending: false,
});

// ============================================================================
// Filas del montaje (derivadas en cada commit; ≤15 por lado)
// ============================================================================

interface BookRow {
    vi: number; px: number; sz: number;
    level: number; newLevel: boolean; stale: boolean;
    flash: 'px' | 'up' | 'dn' | null; flashAge: number;
}

function deriveSide(book: VenueState[], clock: number, side: 'bid' | 'ask'): BookRow[] {
    const rows: BookRow[] = [];
    for (let vi = 0; vi < book.length; vi++) {
        const v = book[vi];
        if (!v) continue;
        const px = side === 'bid' ? v.bp : v.ap;
        if (px == null) continue;
        const t = side === 'bid' ? v.tBid : v.tAsk;
        const dir = side === 'bid' ? v.dirBid : v.dirAsk;
        const age = clock - t;
        rows.push({
            vi, px, sz: side === 'bid' ? v.bs : v.as,
            level: 0, newLevel: false, stale: age > STALE_MS,
            flash: dir && age >= 0 && age < (dir === 'px' ? FLASH_PX_MS : FLASH_SZ_MS) ? dir : null,
            flashAge: age,
        });
    }
    rows.sort((a, b) => (side === 'bid' ? b.px - a.px : a.px - b.px) || a.vi - b.vi);
    let lvl = -1; let lastPx = NaN;
    for (const r of rows) {
        if (r.px !== lastPx) { lvl++; lastPx = r.px; r.newLevel = lvl > 0; }
        r.level = lvl;
    }
    return rows;
}

// ============================================================================
// Fila del montaje (memoizada: solo repinta si cambian sus datos)
// ============================================================================

const BandRow = memo(function BandRow({
    row, venue, side, pal, maxSz,
}: {
    row: BookRow; venue: string; side: 'bid' | 'ask'; pal: Palette; maxSz: number;
}) {
    const ramp = side === 'bid' ? pal.bid : pal.ask;
    const inBand = row.level < ramp.length;

    let bg = inBand ? ramp[row.level] : 'transparent';
    if (row.flash === 'px') {
        // Aclarado del propio color de nivel: el destello nunca borra la banda
        const k = 0.30 * (1 - row.flashAge / FLASH_PX_MS);
        bg = inBand
            ? `color-mix(in srgb, ${ramp[row.level]} ${100 - k * 100}%, white ${k * 100}%)`
            : `rgba(148,163,184,${(k * 0.6).toFixed(3)})`;
    }

    let szColor: string | undefined;
    if (row.flash === 'up' || row.flash === 'dn') {
        szColor = row.flash === 'up' ? 'var(--color-chart-up)' : 'var(--color-chart-down)';
    }

    const priceStyle: CSSProperties = inBand
        ? { color: '#f2f6fb', fontWeight: row.level === 0 ? 700 : 600 }
        : { color: side === 'bid' ? pal.deepBid : pal.deepAsk, fontWeight: 500 };

    const barW = maxSz > 0 ? Math.min(100, (row.sz / maxSz) * 100) : 0;

    const cells = [
        <td key="v" className="px-2 text-left text-[10px] tracking-wide"
            style={{ color: inBand ? '#dfe6ef' : 'var(--color-muted-fg)', width: 52 }}>
            {venue}{row.stale ? <span style={{ color: 'var(--color-warning)' }}> ·</span> : null}
        </td>,
        <td key="s" className="px-2 text-right font-mono text-[10px]"
            style={{ color: szColor ?? (inBand ? '#eaf0f8' : 'var(--color-muted-fg)'), fontWeight: szColor ? 700 : 400 }}>
            {fmtSz(row.sz)}
        </td>,
        <td key="p" className="px-2 text-right font-mono text-[11px] relative overflow-hidden" style={priceStyle}>
            <span className="absolute inset-y-[3px] rounded-[2px] pointer-events-none"
                style={{
                    [side === 'bid' ? 'right' : 'left']: 0,
                    width: `${barW.toFixed(1)}%`,
                    background: side === 'bid' ? pal.curveBid : pal.curveAsk,
                    opacity: 0.16,
                } as CSSProperties} />
            <span className="relative">{fmtPx(row.px)}</span>
        </td>,
    ];

    return (
        <tr style={{
            height: TAPE_ROW_H,
            background: bg,
            opacity: row.stale ? 0.38 : 1,
            borderTop: row.newLevel ? '1px solid rgba(148,163,184,0.25)' : undefined,
        }}>
            {side === 'bid' ? cells : [cells[2], cells[1], cells[0]]}
        </tr>
    );
});

// ============================================================================
// Curva de profundidad acumulada (canvas, estilo IBKR)
// ============================================================================

function drawDepth(
    canvas: HTMLCanvasElement, bids: BookRow[], asks: BookRow[], pal: Palette,
) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr; canvas.height = h * dpr;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!bids.length && !asks.length) return;

    const mid = bids.length && asks.length
        ? (bids[0].px + asks[0].px) / 2
        : (bids[0]?.px ?? asks[0]?.px ?? 0);
    const span = Math.max(
        mid - (bids[bids.length - 1]?.px ?? mid),
        (asks[asks.length - 1]?.px ?? mid) - mid,
        0.01,
    );
    const x = (px: number) => ((px - (mid - span)) / (2 * span)) * w;

    let maxCum = 1;
    { let c = 0; for (const r of bids) { c += r.sz; if (c > maxCum) maxCum = c; } }
    { let c = 0; for (const r of asks) { c += r.sz; if (c > maxCum) maxCum = c; } }
    const y = (cum: number) => h - (cum / maxCum) * (h - 6);

    const paint = (rows: BookRow[], color: string, dir: 1 | -1) => {
        if (!rows.length) return;
        ctx.beginPath();
        let cum = 0;
        ctx.moveTo(x(rows[0].px), h);
        for (const r of rows) {
            const px0 = x(r.px);
            ctx.lineTo(px0, y(cum));      // escalón: sube en el precio del venue
            cum += r.sz;
            ctx.lineTo(px0, y(cum));
        }
        const edge = dir === -1 ? 0 : w;
        ctx.lineTo(edge, y(cum));
        ctx.lineTo(edge, h);
        ctx.closePath();
        ctx.globalAlpha = 0.22; ctx.fillStyle = color; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = color; ctx.lineWidth = 1.25;
        // repetir el contorno sin la base
        ctx.beginPath();
        cum = 0; ctx.moveTo(x(rows[0].px), h);
        for (const r of rows) {
            const px0 = x(r.px);
            ctx.lineTo(px0, y(cum)); cum += r.sz; ctx.lineTo(px0, y(cum));
        }
        ctx.lineTo(edge, y(cum));
        ctx.stroke();
    };
    paint(bids, pal.curveBid, -1);
    paint(asks, pal.curveAsk, 1);

    // línea del mid
    ctx.strokeStyle = 'rgba(148,163,184,0.35)';
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(x(mid), 2); ctx.lineTo(x(mid), h); ctx.stroke();
    ctx.setLineDash([]);
}

// ============================================================================
// Componente
// ============================================================================

interface L2ReplayContentProps {
    initialSymbol?: string;
}

export function L2ReplayContent({ initialSymbol }: L2ReplayContentProps) {
    const { t } = useTranslation();
    const { authFetch } = useAuthFetch();
    const { state, updateState } = useWindowState<L2Settings>();
    const broadcast = useLinkGroupSubscription();

    // ---- ajustes persistidos por ventana --------------------------------
    const symbol = (initialSymbol ?? state.symbol ?? 'NVDA').toUpperCase();
    const minutes = state.minutes ?? 5;
    const schema = state.schema ?? 'mbp-1';
    const paletteKey: PaletteKey = state.palette ?? 'neutral';
    const speed = state.speed ?? 1;
    const dateStr = state.date ?? lastTradingDay();
    const timeStr = state.time ?? '09:35:00';
    const pal = PALETTES[paletteKey];

    const [symbolInput, setSymbolInput] = useState(symbol);
    useEffect(() => { setSymbolInput(symbol); }, [symbol]);

    // Ticker linkado desde otra ventana del grupo
    useEffect(() => {
        if (broadcast?.ticker && broadcast.ticker.toUpperCase() !== symbol) {
            updateState({ symbol: broadcast.ticker.toUpperCase() });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [broadcast]);

    // ---- motor ----------------------------------------------------------
    const eng = useRef<Engine>(freshEngine());
    const [, bump] = useReducer((x: number) => x + 1, 0);
    const lastCommit = useRef(0);
    const genRef = useRef(0);            // invalida fetches al recargar/cerrar
    const latencyRef = useRef(1500);     // EMA de lo que tarda un bloque

    // El tiempo NO vive aquí: lo lleva el reloj compartido, para que esta
    // ventana pueda ir sincronizada con el gráfico y la cinta. Aquí solo se
    // reacciona a él. El trampolín por ref sigue haciendo falta porque el
    // suscriptor se registra una vez y capturaría el primer cierre.
    const clock = useReplayClockStore;
    const playing = useReplayClockStore((s) => s.playing);
    const stalled = useReplayClockStore((s) => s.stalled);
    const onFrameRef = useRef<(t: number) => void>(() => { });
    const [status, setStatus] = useState<{ kind: 'idle' | 'loading' | 'ready' | 'error'; msg: string }>(
        { kind: 'idle', msg: '' });
    const [progress, setProgress] = useState(0);        // 0..1 mientras prepara
    const [cost, setCost] = useState<string | null>(null);
    const [hidden, setHidden] = useState(false);
    const [showPrefs, setShowPrefs] = useState(false);

    const setPlay = useCallback((on: boolean) => {
        if (on) clock.getState().play(); else clock.getState().pause();
    }, [clock]);

    // Un único suscriptor al reloj compartido: aplica los frames pendientes y
    // deja que React repinte conflado. Se registra una vez y llama siempre a
    // la versión más reciente del handler.
    useEffect(() => {
        const off = clock.getState().onFrame((t) => onFrameRef.current(t));
        return off;
    }, [clock]);

    // ---- avance del reloj + aplicación de frames (fuera de React) -------
    const advance = useCallback(() => {
        const e = eng.current;
        const p = e.payload;
        if (!p) return;
        while (e.cursor < p.frames.length && p.frames[e.cursor][0] <= e.clock) {
            for (const [vi, bp, bs, ap, asz] of p.frames[e.cursor][1]) {
                const v = e.book[vi] ?? (e.book[vi] = {
                    bp: null, bs: 0, ap: null, as: 0, tBid: -1, tAsk: -1, dirBid: null, dirAsk: null,
                });
                if (v.bp !== bp || v.bs !== bs) {
                    v.dirBid = v.bp !== bp ? 'px' : bs > v.bs ? 'up' : 'dn';
                    v.tBid = e.clock;
                }
                if (v.ap !== ap || v.as !== asz) {
                    v.dirAsk = v.ap !== ap ? 'px' : asz > v.as ? 'up' : 'dn';
                    v.tAsk = e.clock;
                }
                v.bp = bp; v.bs = bs; v.ap = ap; v.as = asz;
            }
            e.cursor++;
        }
        const emit = clock.getState().emitPrint;
        while (e.tapeCursor < p.tape.length && p.tape[e.tapeCursor][0] <= e.clock) {
            const pr = p.tape[e.tapeCursor];
            e.prevPx = e.lastPx; e.lastPx = pr[1];
            e.tape.unshift(pr);
            if (e.tape.length > TAPE_BUFFER) e.tape.pop();
            // Se publica al reloj compartido: el gráfico forma su vela viva con
            // ESTAS impresiones, las mismas que ve la cinta. Así no pueden
            // contar historias distintas del mismo instante.
            emit([pr[0], pr[1], pr[2]]);
            e.tapeCursor++;
        }
    }, [clock]);

    // ---- encadenado del siguiente bloque --------------------------------
    const fetchBlock = useCallback(async (
        dISO: string, tISO: string, gen: number, mins: number, secs?: number,
        onProgress?: (d: number, tot: number) => void,
    ): Promise<ReplayPayload | null> => {
        const qs = new URLSearchParams({
            symbol, date: dISO, time: tISO,
            minutes: String(mins), schema,
            ...(secs ? { seconds: String(secs) } : {}),
        });
        const sr = await authFetch(`/api/v1/l2replay/start?${qs}`);
        const sj = await sr.json();
        if (!sj.ok) throw new Error(sj.error || sj.detail || 'start failed');
        for (; ;) {
            if (gen !== genRef.current) return null;
            await new Promise(r => setTimeout(r, 450));
            const pr = await authFetch(`/api/v1/l2replay/progress?job=${sj.job}`);
            const pj = await pr.json();
            if (!pj.ok) throw new Error(pj.error || 'progress lost');
            if (pj.total > 0) setProgress(Math.min(0.99, pj.done / pj.total));
            if (pj.error) throw new Error(pj.error);
            if (pj.ready) break;
        }
        const rr = await authFetch(`/api/v1/l2replay/result?job=${sj.job}`);
        const rj: ReplayPayload = await rr.json();
        if (!rj.ok) throw new Error(rj.error || 'result failed');
        return rj;
    }, [authFetch, symbol, schema]);

    const extend = useCallback(async () => {
        const e = eng.current;
        if (e.extending || e.exhausted || !e.payload) return;
        e.extending = true;
        const gen = genRef.current;
        try {
            const nextUtc = new Date(e.startUtcMs + e.durationMs);
            const parts = etDateFmt.formatToParts(nextUtc)
                .reduce<Record<string, string>>((a, x) => (a[x.type] = x.value, a), {});
            const t0 = performance.now();
            const p = await fetchBlock(
                `${parts.year}-${parts.month}-${parts.day}`,
                `${parts.hour}:${parts.minute}:${parts.second}`, gen, minutes);
            // Media móvil de la latencia real: es la que dimensiona el colchón.
            latencyRef.current = latencyRef.current * 0.7 + (performance.now() - t0) * 0.3;
            if (!p || gen !== genRef.current) return;
            if (!p.frames.length && !p.tape.length) { e.exhausted = true; return; }
            const off = e.durationMs;
            for (const f of p.frames) e.payload.frames.push([f[0] + off, f[1]]);
            for (const tp of p.tape) e.payload.tape.push([tp[0] + off, tp[1], tp[2], tp[3]]);
            e.durationMs += p.durationMs;
            clock.getState().setLoaded(e.durationMs);   // reanuda si esperaba
        } catch {
            e.exhausted = true;
        } finally {
            e.extending = false;
        }
    }, [fetchBlock, minutes]);

    // ---- bucle rAF (cuerpo reasignado en cada render: cierres frescos) --
    onFrameRef.current = (t: number) => {
        const e2 = eng.current;
        e2.clock = t;               // el tiempo lo dicta el reloj compartido
        advance();

        // Se pide cuando el colchón de PARED baja del que cuesta una petición.
        // Así, a 10× dispara diez veces antes que a 1× sin tocar constantes, y
        // si la red se degrada la latencia medida sube y pide todavía antes.
        if (!e2.exhausted) {
            const umbral = Math.max(PREFETCH_FLOOR_MS, latencyRef.current * PREFETCH_K);
            if (clock.getState().bufferWallMs() < umbral) void extend();
        }

        const now = performance.now();
        if (now - lastCommit.current >= COMMIT_MS) {
            lastCommit.current = now;
            bump();
        }
    };

    // ---- carga inicial --------------------------------------------------
    const load = useCallback(async () => {
        const gen = ++genRef.current;
        setPlay(false);
        setCost(null);
        setProgress(0);
        // El libro histórico llega con un día de retraso: la sesión en curso no
        // existe todavía. Sin esta guarda, señalar una vela de hoy en el gráfico
        // —que es lo natural, porque abre mostrando lo más reciente— acababa en
        // un error genérico que no explicaba nada.
        const tope = lastTradingDay();
        if (dateStr > tope) {
            setStatus({ kind: 'error', msg: t('l2replay.noBookYet', { date: tope }) });
            return;
        }
        setStatus({ kind: 'loading', msg: t('l2replay.preparing') });
        try {
            const p = await fetchBlock(dateStr, timeStr, gen, 1, FIRST_BLOCK_SEC);
            if (!p || gen !== genRef.current) return;
            const e = eng.current = freshEngine();
            e.payload = p;
            e.startUtcMs = new Date(p.startUtc).getTime();
            e.durationMs = p.durationMs;
            e.book = p.venues.map(() => ({
                bp: null, bs: 0, ap: null, as: 0, tBid: -1e12, tAsk: -1e12, dirBid: null, dirAsk: null,
            }));
            for (const [vi, bp, bs, ap, asz] of p.initial) {
                e.book[vi] = { bp, bs, ap, as: asz, tBid: -1e12, tAsk: -1e12, dirBid: null, dirAsk: null };
            }
            // Si el gráfico ya abrió la sesión al señalar la vela, aquí SOLO se
            // amplía el horizonte: reabrirla movería el instante cero y el
            // gráfico daría un salto. Solo se abre si nadie lo hizo antes (la
            // ventana usada por su cuenta, sin pasar por el gráfico).
            const cs = clock.getState();
            if (cs.active && Math.abs(cs.originMs - e.startUtcMs) < 60_000) {
                cs.setLoaded(e.durationMs);
            } else {
                cs.open({ sessionDate: dateStr, originMs: e.startUtcMs, loadedMs: e.durationMs });
            }
            clock.getState().setSpeed(speed);   // la guardada en la ventana
            setProgress(1);
            setStatus({ kind: 'ready', msg: '' });
            bump();
            setPlay(true);
            void extend();          // empezar a rellenar el buffer ya
        } catch (err) {
            if (gen !== genRef.current) return;
            // El detalle técnico va a la consola; al usuario, una frase útil.
            console.warn('[L2 Replay]', err);
            setProgress(0);
            // "bloque incompleto" con TODAS las plazas = no hay libro ese día.
            // Decirlo, en vez de mandar a reintentar algo que nunca funcionará.
            const txt = String((err as Error)?.message ?? '');
            const sinLibro = /bloque incompleto/i.test(txt) && txt.split(',').length >= 10;
            setStatus({
                kind: 'error',
                msg: sinLibro ? t('l2replay.noBookDay') : t('l2replay.loadError'),
            });
        }
    }, [dateStr, timeStr, fetchBlock, extend, setPlay, t, clock]);

    // ---- petición del gráfico: señalar una vela manda aquí ---------------
    // Manda el gráfico. Cuando el usuario señala una vela, esta ventana adopta
    // ese día y esa hora (y su símbolo) y carga sola, sin que haya que tocar
    // los campos de arriba. El nonce distingue dos clics en la misma vela.
    const request = useReplayClockStore((s) => s.request);
    const lastNonce = useRef(0);
    useEffect(() => {
        if (!request || request.nonce === lastNonce.current) return;
        lastNonce.current = request.nonce;
        updateState({
            symbol: request.symbol || symbol,
            date: request.date,
            time: request.time,
        });
    }, [request, symbol, updateState]);

    // Cargar en cuanto los campos reflejan la vela pedida.
    const pendingLoad = useRef(false);
    useEffect(() => {
        if (!request || lastNonce.current !== request.nonce) return;
        if (dateStr !== request.date || timeStr !== request.time) return;
        if (pendingLoad.current) return;
        pendingLoad.current = true;
        void load().finally(() => { pendingLoad.current = false; });
    }, [request, dateStr, timeStr, load]);

    const queryCost = useCallback(async () => {
        setCost('…');
        try {
            const qs = new URLSearchParams({
                symbol, date: dateStr, time: timeStr, minutes: String(minutes), schema,
            });
            const r = await authFetch(`/api/v1/l2replay/cost?${qs}`);
            const j = await r.json();
            setCost(j.ok ? `$${Number(j.usd).toFixed(4)}` : 'n/d');
        } catch { setCost('n/d'); }
    }, [authFetch, symbol, dateStr, timeStr, minutes, schema]);

    // ---- ciclo de vida --------------------------------------------------
    useEffect(() => {
        const onVis = () => setHidden(document.visibilityState === 'hidden');
        document.addEventListener('visibilitychange', onVis);
        return () => {
            document.removeEventListener('visibilitychange', onVis);
            genRef.current++;                       // aborta sondeos en vuelo
            clock.getState().close();               // para el reloj compartido
        };
    }, [clock]);

    // fin de semana: saltar al viernes anterior
    const onDateChange = useCallback((v: string) => {
        if (!v) return;
        const d = new Date(`${v}T12:00:00`);
        if (d.getDay() === 0 || d.getDay() === 6) {
            d.setDate(d.getDate() - (d.getDay() === 6 ? 1 : 2));
            updateState({ date: d.toISOString().slice(0, 10) });
            setStatus({ kind: 'idle', msg: t('l2replay.weekend') });
            return;
        }
        updateState({ date: v });
    }, [updateState, t]);

    // ---- derivar filas del commit actual --------------------------------
    const e = eng.current;
    const bids = useMemo(() => deriveSide(e.book, e.clock, 'bid'),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [e.book, e.clock, e.payload]);
    const asks = useMemo(() => deriveSide(e.book, e.clock, 'ask'),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [e.book, e.clock, e.payload]);
    const maxBidSz = Math.max(1, ...bids.map(r => r.sz));
    const maxAskSz = Math.max(1, ...asks.map(r => r.sz));
    const bestBid = bids[0] ?? null;
    const bestAsk = asks[0] ?? null;
    const liveVenues = new Set([
        ...bids.filter(r => !r.stale).map(r => r.vi),
        ...asks.filter(r => !r.stale).map(r => r.vi),
    ]).size;
    const venues = e.payload?.venues ?? [];

    // curva de profundidad
    const canvasRef = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
        if (canvasRef.current) drawDepth(canvasRef.current, bids, asks, pal);
    });

    // ---- tape virtualizado ----------------------------------------------
    const tapeScrollRef = useRef<HTMLDivElement>(null);
    const rowVirtualizer = useVirtualizer({
        count: e.tape.length,
        getScrollElement: () => tapeScrollRef.current,
        estimateSize: () => TAPE_ROW_H,
        overscan: 10,
    });

    const clockAbs = e.startUtcMs ? e.startUtcMs + e.clock : null;

    // ---- estilos base ---------------------------------------------------
    const lbl = 'text-[9px] uppercase tracking-wider';
    const sel = 'bg-surface-inset border border-border rounded px-1.5 py-1 text-[11px] outline-none focus:border-primary';

    return (
        <div className="flex flex-col h-full min-h-0 text-[11px]" style={{ color: 'var(--color-fg)' }}>

            {/* ── 1 · Toolbar ─────────────────────────────────────────── */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border bg-surface-inset/60 shrink-0 flex-wrap">
                <TickerSearch
                    value={symbolInput}
                    onChange={setSymbolInput}
                    onSelect={(tk) => {
                        const next = tk.symbol.toUpperCase();
                        setSymbolInput(next);
                        if (next !== symbol) updateState({ symbol: next });
                    }}
                    placeholder={t('l2replay.symbol')}
                    className="w-[110px]"
                    autoFocus={false}
                />
                <span className="font-mono font-bold text-sm text-primary shrink-0">{symbol}</span>

                <input type="date" value={dateStr} min={HIST_START} max={lastTradingDay()}
                    onChange={ev => onDateChange(ev.target.value)} className={sel} />
                <input type="time" step={1} value={timeStr}
                    onChange={ev => updateState({ time: ev.target.value })} className={`${sel} w-[92px]`} />

                <select value={minutes} onChange={ev => updateState({ minutes: Number(ev.target.value) })} className={sel}>
                    {[1, 5, 15, 30, 60].map(m => <option key={m} value={m}>{m}m</option>)}
                </select>
                <select value={schema} onChange={ev => updateState({ schema: ev.target.value as L2Settings['schema'] })} className={sel}>
                    <option value="mbp-1">{t('l2replay.tick')}</option>
                    <option value="bbo-1s">{t('l2replay.sec1')}</option>
                </select>
                <button onClick={() => void load()}
                    disabled={status.kind === 'loading'}
                    className="px-2.5 py-1 rounded text-[11px] font-semibold disabled:opacity-40"
                    style={{ background: 'var(--color-primary)', color: '#fff' }}>
                    {t('l2replay.load')}
                </button>
                <button onClick={() => void queryCost()} title={t('l2replay.costTip')}
                    className="px-1.5 py-1 rounded border border-border hover:text-primary" style={{ color: 'var(--color-muted-fg)' }}>
                    <Coins size={12} />
                </button>
                {cost && <span className="font-mono text-[10px]" style={{ color: 'var(--color-muted-fg)' }}>{cost}</span>}

                {/* El estado solo se manifiesta cuando aporta algo: mientras
                    prepara (con %) o si algo ha fallado. En reposo, nada. */}
                {status.kind === 'loading' && (
                    <span className="ml-auto text-[10px] font-mono" style={{ color: 'var(--color-muted-fg)' }}>
                        {t('l2replay.preparing')} {Math.round(progress * 100)}%
                    </span>
                )}
                {status.kind === 'error' && (
                    <span className="ml-auto text-[10px] max-w-[260px] truncate" style={{ color: 'var(--color-danger)' }}>
                        {status.msg}
                    </span>
                )}

                <button onClick={() => setShowPrefs(v => !v)} title={t('l2replay.prefs')}
                    className={`${status.kind === 'loading' || status.kind === 'error' ? '' : 'ml-auto '}p-1 rounded hover:bg-surface-hover`}
                    style={{ color: showPrefs ? 'var(--color-primary)' : 'var(--color-muted-fg)' }}>
                    <Settings2 size={14} />
                </button>
            </div>

            {/* ── Preferencias de la ventana ──────────────────────────── */}
            {showPrefs && (
                <div className="px-3 py-2 border-b border-border bg-surface-inset/40 text-[11px] shrink-0
                                flex flex-wrap items-center gap-x-5 gap-y-2">
                    <label className="flex items-center gap-2">
                        <span style={{ color: 'var(--color-muted-fg)' }}>{t('l2replay.palette')}</span>
                        <select value={paletteKey} className={sel}
                            onChange={ev => updateState({ palette: ev.target.value as PaletteKey })}>
                            <option value="neutral">{t('l2replay.palNeutral')}</option>
                            <option value="safe">{t('l2replay.palSafe')}</option>
                            <option value="classic">{t('l2replay.palClassic')}</option>
                        </select>
                    </label>
                    <span className="text-[10px]" style={{ color: 'var(--color-muted-fg)' }}>
                        {t('l2replay.depthHint')}
                    </span>
                </div>
            )}

            {/* Barra de preparación: el libro se pinta cuando están los 15
                venues, así que mientras tanto se informa con honestidad. */}
            {status.kind === 'loading' && (
                <div className="h-[2px] w-full shrink-0" style={{ background: 'var(--color-surface-inset)' }}>
                    <div className="h-full transition-[width] duration-300"
                        style={{ width: `${Math.round(progress * 100)}%`, background: 'var(--color-primary)' }} />
                </div>
            )}

            {/* ── 2 · Strip de cotización ─────────────────────────────── */}
            <div className="flex items-baseline gap-4 px-3 py-1.5 border-b border-border shrink-0 flex-wrap">
                <span className="font-mono text-[16px] font-bold"
                    style={{
                        color: e.lastPx == null || e.prevPx == null || e.lastPx === e.prevPx
                            ? 'var(--color-fg)'
                            : e.lastPx > e.prevPx ? 'var(--color-chart-up)' : 'var(--color-chart-down)',
                    }}>
                    {fmtPx(e.lastPx)}
                </span>
                <span className="flex flex-col"><i className={lbl} style={{ color: 'var(--color-muted-fg)', fontStyle: 'normal' }}>Bid</i>
                    <b className="font-mono text-[11px]">{bestBid ? `${fmtPx(bestBid.px)} ×${fmtSz(bestBid.sz)}` : '—'}</b></span>
                <span className="flex flex-col"><i className={lbl} style={{ color: 'var(--color-muted-fg)', fontStyle: 'normal' }}>Ask</i>
                    <b className="font-mono text-[11px]">{bestAsk ? `${fmtPx(bestAsk.px)} ×${fmtSz(bestAsk.sz)}` : '—'}</b></span>
                <span className="flex flex-col"><i className={lbl} style={{ color: 'var(--color-muted-fg)', fontStyle: 'normal' }}>{t('l2replay.spread')}</i>
                    <b className="font-mono text-[11px]">{bestBid && bestAsk ? (bestAsk.px - bestBid.px).toFixed(2) : '—'}</b></span>
                <span className="flex flex-col"><i className={lbl} style={{ color: 'var(--color-muted-fg)', fontStyle: 'normal' }}>{t('l2replay.venuesLive')}</i>
                    <b className="font-mono text-[11px]">{venues.length ? `${liveVenues}/${venues.length}` : '—'}</b></span>
                {e.extending && (
                    <span className="text-[10px]" style={{ color: 'var(--color-muted-fg)' }}>
                        {t('l2replay.buffering')}
                    </span>
                )}
                {hidden && playing && (
                    <span className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--color-warning)' }}>
                        <EyeOff size={11} /> {t('l2replay.hiddenPaused')}
                    </span>
                )}
            </div>

            {/* ── 3+4+5 · Curva, montaje y tape ───────────────────────── */}
            <div className="flex flex-1 min-h-0">
                <div className="flex flex-col flex-1 min-w-0">
                    <canvas ref={canvasRef} className="w-full shrink-0 border-b border-border"
                        style={{ height: 72 }} />
                    <div className="flex flex-1 min-h-0 overflow-y-auto">
                        {/* bids */}
                        <table className="flex-1 border-collapse self-start" style={{ tableLayout: 'fixed' }}>
                            <thead>
                                <tr className={lbl} style={{ color: 'var(--color-muted-fg)' }}>
                                    <th className="px-2 py-1 text-left font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>{t('l2replay.venue')}</th>
                                    <th className="px-2 py-1 text-right font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>{t('l2replay.size')}</th>
                                    <th className="px-2 py-1 text-right font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>Bid</th>
                                </tr>
                            </thead>
                            <tbody>
                                {bids.map(r => (
                                    <BandRow key={venues[r.vi] ?? r.vi} row={r} venue={venues[r.vi] ?? '?'}
                                        side="bid" pal={pal} maxSz={maxBidSz} />
                                ))}
                                {!bids.length && (
                                    <tr><td colSpan={3} className="px-2 py-6 text-center text-[10px]"
                                        style={{ color: 'var(--color-muted-fg)' }}>{t('l2replay.noData')}</td></tr>
                                )}
                            </tbody>
                        </table>
                        {/* asks */}
                        <table className="flex-1 border-collapse self-start border-l border-border" style={{ tableLayout: 'fixed' }}>
                            <thead>
                                <tr className={lbl} style={{ color: 'var(--color-muted-fg)' }}>
                                    <th className="px-2 py-1 text-right font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>Ask</th>
                                    <th className="px-2 py-1 text-right font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>{t('l2replay.size')}</th>
                                    <th className="px-2 py-1 text-right font-medium sticky top-0" style={{ background: 'var(--color-surface)' }}>{t('l2replay.venue')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {asks.map(r => (
                                    <BandRow key={venues[r.vi] ?? r.vi} row={r} venue={venues[r.vi] ?? '?'}
                                        side="ask" pal={pal} maxSz={maxAskSz} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* tape virtualizado */}
                <div className="w-[210px] shrink-0 border-l border-border flex flex-col min-h-0">
                    <div className={`px-2 py-1 border-b border-border shrink-0 ${lbl}`}
                        style={{ color: 'var(--color-muted-fg)' }}>
                        {t('l2replay.tape')} · {e.tape.length}
                    </div>
                    <div ref={tapeScrollRef} className="flex-1 overflow-y-auto min-h-0">
                        <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
                            {rowVirtualizer.getVirtualItems().map(vi => {
                                const pr = e.tape[vi.index];
                                if (!pr) return null;
                                const [ms, px, sz, vidx] = pr;
                                const cls = bestAsk && px >= bestAsk.px ? 'var(--color-chart-up)'
                                    : bestBid && px <= bestBid.px ? 'var(--color-chart-down)'
                                        : 'var(--color-muted-fg)';
                                return (
                                    <div key={`${ms}-${vi.index}`}
                                        className="absolute left-0 right-0 flex items-center gap-1 px-2 font-mono text-[10px]"
                                        style={{ top: vi.start, height: TAPE_ROW_H }}>
                                        <span style={{ color: 'var(--color-muted-fg)' }}>
                                            {e.startUtcMs ? etFmt.format(e.startUtcMs + ms) : '—'}
                                        </span>
                                        <span className="ml-auto" style={{ color: cls }}>{fmtPx(px)}</span>
                                        <span className="w-[34px] text-right">{fmtSz(sz)}</span>
                                        <span className="w-[34px] text-right text-[9px]" style={{ color: 'var(--color-muted-fg)' }}>
                                            {venues[vidx] ?? ''}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                        {!e.tape.length && (
                            <div className="px-2 py-6 text-center text-[10px]" style={{ color: 'var(--color-muted-fg)' }}>
                                {t('l2replay.noData')}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* ── 6 · Transporte ──────────────────────────────────────── */}
            <div className="flex items-center gap-2.5 px-2 py-1.5 border-t border-border bg-surface-inset/60 shrink-0">
                <button onClick={() => setPlay(!playing)} disabled={!e.payload}
                    className="p-1 rounded border border-border disabled:opacity-40 hover:border-primary">
                    {playing ? <Pause size={12} /> : <Play size={12} />}
                </button>
                <span className="font-mono text-[12px] font-semibold min-w-[64px]">
                    {clockAbs ? etFmt.format(clockAbs) : '--:--:--'}
                </span>
                <input type="range" min={0} max={1000}
                    value={e.durationMs ? Math.round((e.clock / e.durationMs) * 1000) : 0}
                    onChange={ev => {
                        const target = e.durationMs * (Number(ev.target.value) / 1000);
                        if (target < e.clock && e.payload) {
                            // rebobinar = reponer estado inicial y reaplicar (barato: ≤20k frames)
                            const p = e.payload;
                            e.book = p.venues.map(() => ({
                                bp: null, bs: 0, ap: null, as: 0, tBid: -1e12, tAsk: -1e12, dirBid: null, dirAsk: null,
                            }));
                            for (const [vi2, bp, bs, ap, asz] of p.initial) {
                                e.book[vi2] = { bp, bs, ap, as: asz, tBid: -1e12, tAsk: -1e12, dirBid: null, dirAsk: null };
                            }
                            e.cursor = 0; e.tapeCursor = 0; e.tape = []; e.lastPx = null; e.prevPx = null;
                        }
                        // El salto lo publica el reloj compartido, que reancla
                        // y avisa a todas las ventanas: el gráfico y la cinta
                        // saltan con el libro, no cada uno por su cuenta.
                        clock.getState().seek(target);
                        advance();
                        bump();
                    }}
                    disabled={!e.payload}
                    className="flex-1" style={{ accentColor: 'var(--color-primary)' }} />
                {stalled && (
                    <span className="text-[9px] font-semibold tracking-wider text-warning animate-pulse">
                        {t('l2replay.buffering')}
                    </span>
                )}
                <select value={speed}
                    onChange={ev => {
                        const v = Number(ev.target.value);
                        updateState({ speed: v });
                        clock.getState().setSpeed(v);
                    }} className={sel}>
                    {[0.5, 1, 2, 5, 10, 30].map(s => <option key={s} value={s}>{s}×</option>)}
                </select>
            </div>
        </div>
    );
}
