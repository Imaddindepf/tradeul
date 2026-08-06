/**
 * Replay Clock Store — ÚNICA fuente de verdad del tiempo en reproducción.
 *
 * Todas las ventanas que participan en un replay (gráfico, libro, cinta) leen
 * de aquí. La sincronía entre ellas no se programa: emana de que comparten
 * reloj. Ninguna ventana debe llevar su propio contador.
 *
 * ---------------------------------------------------------------------------
 * DOS RELOJES, A PROPÓSITO
 *
 *   · `now()`  — continuo y fraccionario. Es el que se lee para pintar, y da
 *                fluidez porque avanza en cada frame.
 *   · `tick`   — el mismo reloj CUANTIZADO. Es el único que dispara peticiones
 *                de datos, porque esas quieren pasos discretos, repetibles y
 *                cacheables. Con un solo reloj habría que elegir entre una
 *                interfaz a tirones o machacar al backend en cada frame.
 *
 * ---------------------------------------------------------------------------
 * ANCLADO A LA PARED, NO ACUMULADO
 *
 *   t = anclaSim + (pared − anclaPared) × velocidad
 *
 * Un acumulador (`t += dt × vel`) pierde tiempo sin remedio en cuanto el hilo
 * se congela, y el navegador congela mucho: con la pestaña en segundo plano
 * estrangula los temporizadores a uno por segundo, y tras unos minutos a uno
 * por minuto. Anclando a la pared, una congelación se recupera exacta al
 * despertar: el reloj no sabe que estuvo dormido, solo mira qué hora es.
 *
 * Se reancla al reanudar, al buscar y al cambiar de velocidad — nunca en un
 * frame normal, o volveríamos a acumular error.
 *
 * ---------------------------------------------------------------------------
 * EL METRÓNOMO VIVE EN UN WORKER
 *
 * `requestAnimationFrame` se para del todo con la pestaña oculta, y los
 * temporizadores de la página se estrangulan. Los de un Worker no. Por eso el
 * latido de respaldo vive ahí: despierta al reloj cuando el rAF lleva demasiado
 * sin disparar. Con la ventana visible el rAF va a 60 fps y el worker no llega
 * a entrar nunca.
 *
 * ---------------------------------------------------------------------------
 * EL RELOJ ES ESCLAVO DEL DATO
 *
 * Si quien sirve los datos no tiene el siguiente tramo, marca `stalled` y el
 * reloj SE PARA. Jamás avanza sobre un hueco: preferimos un indicador de espera
 * a que las ventanas se desincronicen entre sí o enseñen un vacío.
 */

import { create } from 'zustand';

// ============================================================================
// TIPOS
// ============================================================================

/** Suscriptor por frame. Recibe el tiempo continuo en ms. */
type FrameSub = (tMs: number) => void;

/** Suscriptor al tick cuantizado. Recibe el tiempo redondeado en ms. */
type TickSub = (tQuantMs: number) => void;

/**
 * Impresión reproducida: `[ms relativos al origen, precio, tamaño]`.
 *
 * Es el mismo flujo que alimenta la cinta y el libro. El gráfico forma su vela
 * viva de aquí y no de otro sitio: si cada ventana construyera la suya por su
 * cuenta podrían contar historias distintas del mismo instante.
 */
export type ReplayPrint = [number, number, number];
type PrintSub = (p: ReplayPrint) => void;

/**
 * Aviso de salto: instante nuevo e instante en el que estaba el reloj. La
 * dirección importa: hacia delante las impresiones de alcance son ticks
 * válidos y el gráfico avanza sin re-pedir; hacia atrás hay que rehacer la
 * historia (una serie de velas no puede retroceder por ticks).
 */
type SeekSub = (tMs: number, prevTMs: number) => void;

/**
 * Instante pedido DESDE EL GRÁFICO, señalando una vela.
 *
 * Manda el gráfico, no el libro: es donde se ve el contexto y donde se decide
 * "quiero estar aquí". El libro y la cinta son el detalle, y siguen.
 */
export interface ReplayRequest {
    symbol: string;
    /** Epoch ms de la vela señalada: es el instante cero de la reproducción. */
    originMs: number;
    /** Día de la vela señalada, ISO `YYYY-MM-DD` en hora de Nueva York. */
    date: string;
    /** Hora de la vela señalada, `HH:MM:SS` en hora de Nueva York. */
    time: string;
    /** Cambia en cada petición: distingue dos clics en la misma vela. */
    nonce: number;
}

export interface ReplayClockState {
    /** Hay una sesión de reproducción abierta. */
    active: boolean;

    /**
     * Última vela señalada en el gráfico. La ventana del libro la observa y
     * carga ese instante; el gráfico se queda esperando a que abra la sesión.
     */
    request: ReplayRequest | null;
    playing: boolean;
    /** Esperando datos: el reloj está detenido a propósito. */
    stalled: boolean;

    /**
     * Segundos de mercado por segundo de pared. Un único escalar cubre desde
     * cámara lenta hasta minutos por segundo: 0,5 · 1 · 2 · 5 · 10 y, por
     * encima, 60 = "1 min/s", 300 = "5 min/s"…
     */
    speed: number;

    /** Día de la sesión en curso, ISO `YYYY-MM-DD` en hora de Nueva York. */
    sessionDate: string | null;
    /**
     * Símbolo de la sesión en curso. El bus de impresiones no lleva símbolo,
     * así que quien construya velas con él DEBE comparar contra esto: un
     * gráfico en otro ticker que se trague impresiones ajenas fabrica velas
     * que no existen (y las cachea).
     */
    sessionSymbol: string | null;
    /** Epoch en ms del instante cero del replay. `now()` es relativo a él. */
    originMs: number;

    /** Fin de lo cargado, en ms relativos. El reloj no lo rebasa. */
    loadedMs: number;

    /**
     * Tiempo publicado para la interfaz. Se refresca conflado (ver COMMIT_MS),
     * no en cada frame: escribir en el store 60 veces por segundo repintaría
     * media aplicación. Para pintar fluido, suscribirse con `onFrame`.
     */
    tMs: number;

    // --- acciones ---
    /** El gráfico señala una vela: pide reproducir desde ese instante. */
    requestSession: (r: Omit<ReplayRequest, 'nonce'>) => void;
    open: (opts: { sessionDate: string; originMs: number; loadedMs?: number; symbol?: string }) => void;
    close: () => void;
    play: () => void;
    pause: () => void;
    toggle: () => void;
    setSpeed: (speed: number) => void;
    /** Salta a un instante (ms relativos al origen). Reancla. */
    seek: (tMs: number) => void;
    /** Amplía el horizonte cargado; si estaba esperando, reanuda. */
    setLoaded: (loadedMs: number) => void;
    /** Marca que falta dato. El reloj se detiene sin perder el anclaje. */
    setStalled: (stalled: boolean) => void;

    // --- lectura ---
    /** Tiempo continuo en ms. Derivado del ancla: no se guarda por frame. */
    now: () => number;
    /** Colchón restante en ms de PARED (no de mercado). Ver nota abajo. */
    bufferWallMs: () => number;

    // --- suscripción ---
    onFrame: (fn: FrameSub) => () => void;
    onTick: (fn: TickSub) => () => void;
    /** Publica una impresión reproducida a todas las ventanas. */
    emitPrint: (p: ReplayPrint) => void;
    onPrint: (fn: PrintSub) => () => void;
    onSeek: (fn: SeekSub) => () => void;
}

// ============================================================================
// CONSTANTES
// ============================================================================

/** Cuanto del tick que dispara datos. Fino para que la cinta no lata. */
const QUANTUM_MS = 250;

/** Cada cuánto se publica `tMs` al store (y por tanto se repinta la UI). */
const COMMIT_MS = 100;

/** Si el rAF lleva más de esto sin disparar, lo rescata el worker. */
const RAF_STALE_MS = 300;

/** Latido del worker. Solo entra cuando el rAF está estrangulado. */
const METRONOME_MS = 100;

// ============================================================================
// BUCLE (fuera de React: no provoca renders)
// ============================================================================

const frameSubs = new Set<FrameSub>();
const tickSubs = new Set<TickSub>();
const printSubs = new Set<PrintSub>();
const seekSubs = new Set<SeekSub>();

let anchorWall = 0;      // performance.now() del último anclaje
let anchorSim = 0;       // tiempo simulado en ese anclaje
let lastFrameAt = 0;     // último frame servido (para detectar rAF muerto)
let lastCommitAt = 0;
let lastTick = -1;
let rafId = 0;
let metronome: Worker | null = null;

/** El reloj, derivado. No hay estado por frame que pueda desincronizarse. */
function computeNow(playing: boolean, stalled: boolean, loadedMs: number): number {
    if (!playing || stalled) return anchorSim;
    const t = anchorSim + (performance.now() - anchorWall) * useReplayClockStore.getState().speed;
    return t > loadedMs ? loadedMs : t;
}

function anchor(tMs?: number) {
    anchorSim = tMs ?? computeNow(
        useReplayClockStore.getState().playing,
        useReplayClockStore.getState().stalled,
        useReplayClockStore.getState().loadedMs,
    );
    anchorWall = performance.now();
}

function frame(wall: number) {
    lastFrameAt = wall;
    const s = useReplayClockStore.getState();
    if (!s.active || !s.playing) return;

    const t = computeNow(s.playing, s.stalled, s.loadedMs);

    // Tope de lo cargado: el reloj espera al dato, nunca lo adelanta. Se
    // reancla mientras espera para no dar un salto al reanudar.
    if (!s.stalled && t >= s.loadedMs) {
        anchor(s.loadedMs);
        useReplayClockStore.setState({ stalled: true, tMs: s.loadedMs });
    }

    for (const fn of frameSubs) fn(t);

    const q = Math.floor(t / QUANTUM_MS) * QUANTUM_MS;
    if (q !== lastTick) {
        lastTick = q;
        for (const fn of tickSubs) fn(q);
    }

    if (wall - lastCommitAt >= COMMIT_MS) {
        lastCommitAt = wall;
        useReplayClockStore.setState({ tMs: t });
    }
}

function rafLoop(wall: number) {
    frame(wall);
    rafId = requestAnimationFrame(rafLoop);
}

function startLoop() {
    if (rafId) return;
    lastFrameAt = performance.now();
    rafId = requestAnimationFrame(rafLoop);

    // Metrónomo: los temporizadores de la página se estrangulan en segundo
    // plano, los de un Worker no. Se crea desde un Blob para no arrastrar un
    // fichero suelto solo por un setInterval.
    if (!metronome && typeof Worker !== 'undefined') {
        try {
            const src = `setInterval(() => postMessage(0), ${METRONOME_MS});`;
            metronome = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
            metronome.onmessage = () => {
                const wall = performance.now();
                // Solo rescata si el rAF está muerto. Y NO se re-encola: si lo
                // hiciera, cada rescate apilaría una cadena más y al volver a
                // primer plano habría varios bucles pintando a la vez.
                if (wall - lastFrameAt > RAF_STALE_MS) frame(wall);
            };
        } catch {
            /* sin worker se degrada a solo rAF: el replay se pausa de facto
               en segundo plano, que es preferible a desincronizarse. */
        }
    }
}

function stopLoop() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    if (metronome) { metronome.terminate(); metronome = null; }
}

// ============================================================================
// STORE
// ============================================================================

export const useReplayClockStore = create<ReplayClockState>((set, get) => ({
    active: false,
    request: null,
    playing: false,
    stalled: false,
    speed: 1,
    sessionDate: null,
    sessionSymbol: null,
    originMs: 0,
    loadedMs: 0,
    tMs: 0,

    requestSession: (r) => {
        // El corte es INMEDIATO. La sesión se abre aquí, al señalar, no cuando
        // el libro termina de cargar: el gráfico debe recortarse en el acto y
        // el libro incorporarse cuando llegue. Esperar a los datos para mover
        // el gráfico deja al usuario mirando un panel que no reacciona.
        anchorSim = 0;
        anchorWall = performance.now();
        lastTick = -1;
        set({
            request: { ...r, nonce: Date.now() },
            active: true,
            playing: false,
            // Sin datos todavía: el reloj nace detenido. Puede cortar, no correr.
            stalled: true,
            sessionDate: r.date,
            sessionSymbol: r.symbol ? r.symbol.toUpperCase() : null,
            originMs: r.originMs,
            loadedMs: 0,
            tMs: 0,
        });
        startLoop();
    },

    open: ({ sessionDate, originMs, loadedMs = 0, symbol }) => {
        anchorSim = 0;
        anchorWall = performance.now();
        lastTick = -1;
        set({
            active: true, playing: false, stalled: false, sessionDate,
            sessionSymbol: symbol ? symbol.toUpperCase() : get().sessionSymbol,
            originMs, loadedMs, tMs: 0,
        });
        startLoop();
    },

    close: () => {
        stopLoop();
        // Las suscripciones NO se borran: pertenecen a quien las registró
        // (datafeed, gráfico, cinta) y viven más que la sesión. Borrarlas aquí
        // dejaba sordo al gráfico en la SIGUIENTE reproducción — el datafeed
        // solo se engancha en subscribeBars, que no vuelve a ejecutarse.
        set({
            active: false, request: null, playing: false, stalled: false,
            sessionDate: null, sessionSymbol: null, originMs: 0, loadedMs: 0, tMs: 0,
        });
    },

    play: () => {
        if (!get().active) return;
        anchor();                       // la pausa no cuenta como tiempo
        set({ playing: true });
    },

    pause: () => {
        anchor();
        set({ playing: false });
    },

    toggle: () => (get().playing ? get().pause() : get().play()),

    setSpeed: (speed) => {
        anchor();                       // reanclar ANTES de cambiar el factor
        set({ speed });
    },

    seek: (tMs) => {
        const s = get();
        const prevT = computeNow(s.playing, s.stalled, s.loadedMs);
        const clamped = Math.max(0, Math.min(s.loadedMs, tMs));
        anchor(clamped);
        lastTick = -1;                  // fuerza un tick tras el salto
        set({ tMs: clamped, stalled: false });
        // Primero el aviso de salto: quien acumule estado (velas, libro, cinta)
        // tiene que reconstruirlo ANTES de recibir el nuevo instante, o mezclaría
        // lo viejo con lo nuevo.
        for (const fn of seekSubs) fn(clamped, prevT);
        for (const fn of frameSubs) fn(clamped);
        for (const fn of tickSubs) fn(Math.floor(clamped / QUANTUM_MS) * QUANTUM_MS);
    },

    setLoaded: (loadedMs) => {
        const s = get();
        if (loadedMs <= s.loadedMs) return;
        // Al llegar dato nuevo se reancla: el tiempo que estuvo esperando no
        // debe convertirse en un salto hacia delante.
        if (s.stalled) anchor();
        set({ loadedMs, stalled: false });
    },

    setStalled: (stalled) => {
        if (stalled === get().stalled) return;
        anchor();
        set({ stalled });
    },

    now: () => {
        const s = get();
        return s.active ? computeNow(s.playing, s.stalled, s.loadedMs) : 0;
    },

    /**
     * Colchón en tiempo de PARED, que es el único que importa para decidir
     * cuándo pedir más. Lo que queda de mercado no dice nada por sí solo: a 5×
     * se consume cinco veces más rápido, y un umbral fijo en ms de mercado
     * dispara tarde justo cuando más margen hace falta.
     */
    bufferWallMs: () => {
        const s = get();
        if (!s.active) return 0;
        return (s.loadedMs - computeNow(s.playing, s.stalled, s.loadedMs)) / (s.speed || 1);
    },

    onFrame: (fn) => { frameSubs.add(fn); return () => { frameSubs.delete(fn); }; },
    onTick: (fn) => { tickSubs.add(fn); return () => { tickSubs.delete(fn); }; },
    emitPrint: (p) => { for (const fn of printSubs) fn(p); },
    onPrint: (fn) => { printSubs.add(fn); return () => { printSubs.delete(fn); }; },
    onSeek: (fn) => { seekSubs.add(fn); return () => { seekSubs.delete(fn); }; },
}));
