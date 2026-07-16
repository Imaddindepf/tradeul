'use client';

/**
 * useIndicatorHover — foco milimétrico de los indicadores overlay sobre el
 * canvas (BB, Keltner, SMA, EMA, VWAP).
 *
 * Hasta ahora los estudios NO tenían hit-testing: el ratón sobre una banda
 * de Bollinger nunca la "enfocaba" y solo se podían seleccionar desde la
 * leyenda. Este hook cierra ese hueco con las mismas reglas que los dibujos:
 *
 *   • el hit se calcula por DISTANCIA GEOMÉTRICA a cada línea del estudio
 *     (upper/middle/lower en bandas, la media en SMA/EMA…), nunca por el
 *     área entre bandas — estar "dentro" del canal de Bollinger no enfoca
 *     nada: el foco es del canvas;
 *   • tolerancia compartida con los dibujos (BODY_HIT_TOLERANCE);
 *   • si hay varias líneas candidatas gana la más cercana al cursor;
 *   • el indicador hovered/seleccionado se resalta engrosando su línea +1;
 *   • solo se evalúa el pane principal (los paneles RSI/MACD tienen su
 *     propia escala y coordenadas — fuera de alcance de este hover).
 *
 * La PRIORIDAD la orquesta useDrawingInteractions: dibujos del usuario >
 * indicadores > canvas. Este hook solo expone el hit-test y el estado.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import { INDICATOR_TYPE_DEFAULTS, type IndicatorInstance } from '../constants';
import { BODY_HIT_TOLERANCE, distToSegment } from '../primitives/hitTesting';

/** Tipos overlay con líneas hit-testeables en el pane principal. */
const HOVERABLE_OVERLAY_TYPES = new Set(['sma', 'ema', 'vwap', 'bb', 'keltner']);

interface LinePoints {
    indicatorId: string;
    points: { time: number; value: number }[];
}

/** Forma mínima del MouseEventParams del crosshair/click que consumimos. */
export interface IndicatorHitParam {
    point?: { x: number; y: number };
    time?: unknown;
    paneIndex?: number;
}

export interface UseIndicatorHoverResult {
    hoveredIndicatorId: string | null;
    setHoveredIndicator: (id: string | null) => void;
    /** Devuelve el indicador cuya línea pasa a < tolerancia del cursor (o null). */
    indicatorHitTest: (param: IndicatorHitParam) => { id: string } | null;
}

export function useIndicatorHover(
    chartRef: MutableRefObject<IChartApi | null>,
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    indicatorSeriesRef: MutableRefObject<Map<string, Map<string, ISeriesApi<any>>>>,
    indicators: IndicatorInstance[],
    indicatorResults: IndicatorResults | null,
    selectedIndicator: string | null,
    chartVersion: number,
): UseIndicatorHoverResult {
    const [hoveredIndicatorId, setHoveredIndicatorId] = useState<string | null>(null);

    // ── Polilíneas hit-testeables, derivadas de los resultados del worker ──
    const lines = useMemo((): LinePoints[] => {
        if (!indicatorResults) return [];
        const out: LinePoints[] = [];
        for (const inst of indicators) {
            if (!inst.visible || !HOVERABLE_OVERLAY_TYPES.has(inst.type)) continue;
            const result = (indicatorResults as any)[inst.id];
            if (!result) continue;
            const rData = result.data;
            if (inst.type === 'bb' || inst.type === 'keltner') {
                for (const key of ['upper', 'middle', 'lower'] as const) {
                    const pts = rData?.[key];
                    if (Array.isArray(pts) && pts.length >= 2) {
                        out.push({ indicatorId: inst.id, points: pts });
                    }
                }
            } else if (Array.isArray(rData) && rData.length >= 2) {
                out.push({ indicatorId: inst.id, points: rData });
            }
        }
        return out;
    }, [indicators, indicatorResults]);
    const linesRef = useRef(lines);
    linesRef.current = lines;

    // ── Hit-test: distancia a los segmentos vecinos del cursor ────────────
    const indicatorHitTest = useCallback((param: IndicatorHitParam): { id: string } | null => {
        const point = param?.point;
        if (!point) return null;
        // Solo pane principal: en paneles (RSI, MACD…) point.y es relativo a
        // OTRO pane y la conversión con la serie de velas daría falsos hits.
        if (param.paneIndex !== undefined && param.paneIndex !== 0) return null;
        const chart = chartRef.current;
        const series = candleSeriesRef.current;
        if (!chart || !series || linesRef.current.length === 0) return null;
        const ts = chart.timeScale();

        const cursorTime = typeof param.time === 'number'
            ? param.time
            : (ts.coordinateToTime(point.x) as number | null);
        if (cursorTime == null) return null;

        let best: { id: string; dist: number } | null = null;
        for (const line of linesRef.current) {
            const pts = line.points;
            // Búsqueda binaria del punto más cercano en tiempo…
            let lo = 0, hi = pts.length - 1;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (pts[mid].time < cursorTime) lo = mid + 1; else hi = mid;
            }
            // …y distancia real a los dos segmentos que lo rodean.
            const from = Math.max(0, lo - 1);
            const to = Math.min(pts.length - 2, lo);
            for (let i = from; i <= to; i++) {
                const a = pts[i], b = pts[i + 1];
                if (a.value == null || b.value == null) continue;
                const ax = ts.timeToCoordinate(a.time as any);
                const bx = ts.timeToCoordinate(b.time as any);
                const ay = series.priceToCoordinate(a.value);
                const by = series.priceToCoordinate(b.value);
                if (ax == null || bx == null || ay == null || by == null) continue;
                const d = distToSegment(point.x, point.y, ax as number, ay as number, bx as number, by as number);
                if (d < BODY_HIT_TOLERANCE && (!best || d < best.dist)) {
                    best = { id: line.indicatorId, dist: d };
                }
            }
        }
        return best ? { id: best.id } : null;
    }, [chartRef, candleSeriesRef]);

    // ── Si el indicador hovered desaparece / se oculta, soltar el foco ────
    useEffect(() => {
        if (!hoveredIndicatorId) return;
        const inst = indicators.find(i => i.id === hoveredIndicatorId);
        if (!inst || !inst.visible) setHoveredIndicatorId(null);
    }, [indicators, hoveredIndicatorId]);

    // ── Resaltado del estudio activo (hovered o seleccionado) ─────────────
    // Línea +1 de grosor y punto de crosshair visible. Las series se crean
    // con crosshairMarkerVisible=false (useIndicatorSeries); encenderlo solo
    // aquí es lo que hace que el círculo sobre la línea signifique "tiene el
    // foco" y no "hay un cursor en el chart".
    useEffect(() => {
        for (const inst of indicators) {
            if (!HOVERABLE_OVERLAY_TYPES.has(inst.type)) continue;
            const seriesMap = indicatorSeriesRef.current.get(inst.id);
            if (!seriesMap) continue;
            const baseLw = ((inst.styles.lineWidth as number)
                || (INDICATOR_TYPE_DEFAULTS[inst.type]?.defaultStyles.lineWidth as number)
                || 1);
            const active = inst.id === hoveredIndicatorId || inst.id === selectedIndicator;
            const lw = Math.min(4, active ? baseLw + 1 : baseLw) as 1 | 2 | 3 | 4;
            for (const [, s] of seriesMap) {
                try {
                    s.applyOptions({ lineWidth: lw, crosshairMarkerVisible: active });
                } catch { /* serie destruida */ }
            }
        }
    }, [hoveredIndicatorId, selectedIndicator, indicators, indicatorSeriesRef, chartVersion]);

    const setHoveredIndicator = useCallback((id: string | null) => {
        setHoveredIndicatorId(prev => (prev === id ? prev : id));
    }, []);

    return { hoveredIndicatorId, setHoveredIndicator, indicatorHitTest };
}
