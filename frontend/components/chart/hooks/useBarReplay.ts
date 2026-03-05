import { useCallback, useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import { CHART_COLORS, INTERVAL_SECONDS, WHITESPACE_BAR_COUNT, type ChartBar, type Interval, type IndicatorInstance } from '../constants';
import { getSessionColor } from './useSessionBackground';

export type ReplayMode = 'idle' | 'selecting' | 'playing' | 'paused';

const SPEED_OPTIONS = [0.5, 1, 2, 4, 8] as const;
export type ReplaySpeed = (typeof SPEED_OPTIONS)[number];

const BASE_TICK_MS = 400;

export interface ReplayState {
    mode: ReplayMode;
    currentIndex: number;
    startIndex: number;
    speed: ReplaySpeed;
    totalBars: number;
}

function findClosestBarIndex(bars: ChartBar[], targetTime: number): number {
    if (bars.length === 0) return -1;
    let best = 0;
    let bestDiff = Math.abs(bars[0].time - targetTime);
    for (let i = 1; i < bars.length; i++) {
        const diff = Math.abs(bars[i].time - targetTime);
        if (diff < bestDiff) { bestDiff = diff; best = i; }
        if (bars[i].time > targetTime && diff > bestDiff) break;
    }
    return best;
}

export function useBarReplay(
    chartRef: MutableRefObject<IChartApi | null>,
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    volumeSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    sessionBgSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    whitespaceSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    indicatorSeriesRef: MutableRefObject<Map<string, Map<string, ISeriesApi<any>>>>,
    lastPriceInfoRef: MutableRefObject<{ close: number; open: number }>,
    data: ChartBar[],
    selectedInterval: Interval,
    indicators: IndicatorInstance[],
    indicatorResults: any,
    replayControlsDataRef: MutableRefObject<boolean>,
    chartVersion: number,
    setReplayTimestamp: (ts: number | null) => void,
    replayTimeRef: MutableRefObject<number | null>,
    loadForward: () => Promise<boolean>,
) {
    const [mode, setMode] = useState<ReplayMode>('idle');
    const [currentIndex, setCurrentIndex] = useState(0);
    const [startIndex, setStartIndex] = useState(0);
    const [speed, setSpeed] = useState<ReplaySpeed>(1);

    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const currentIndexRef = useRef(0);
    const startIndexRef = useRef(0);
    const modeRef = useRef<ReplayMode>('idle');
    const dataRef = useRef(data);
    dataRef.current = data;
    const intervalRef = useRef(selectedInterval);
    intervalRef.current = selectedInterval;

    const clearTimer = useCallback(() => {
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    }, []);

    // ── Core: rebuild all series up to `idx` ─────────────────────────────

    const rebuildSeriesUpTo = useCallback((idx: number, chartData: ChartBar[], scrollToEnd = false) => {
        const candle = candleSeriesRef.current;
        const volume = volumeSeriesRef.current;
        const session = sessionBgSeriesRef.current;
        const chart = chartRef.current;
        if (!candle || !volume || !chart || !chartData.length || idx < 0) return;

        const slice = chartData.slice(0, idx + 1);

        candle.setData(slice.map(b => ({
            time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close,
        })));
        volume.setData(slice.map(b => ({
            time: b.time as UTCTimestamp,
            value: b.volume,
            color: b.close >= b.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        })));
        if (session) {
            session.setData(slice.map(b => ({
                time: b.time as UTCTimestamp, value: 1, color: getSessionColor(b.time),
            } as any)));
        }
        if (whitespaceSeriesRef.current) {
            const futureWs: { time: UTCTimestamp }[] = [];
            // Use real timestamps from bars we haven't revealed yet
            for (let i = idx + 1; i < chartData.length; i++) {
                futureWs.push({ time: chartData[i].time as UTCTimestamp });
            }
            // Extend beyond dataset with synthetic timestamps
            const gap = INTERVAL_SECONDS[intervalRef.current] || 60;
            const extraCount = WHITESPACE_BAR_COUNT[intervalRef.current] || 120;
            const lastWsTime = futureWs.length > 0
                ? futureWs[futureWs.length - 1].time as number
                : slice[slice.length - 1]?.time ?? 0;
            for (let i = 1; i <= extraCount; i++) {
                futureWs.push({ time: (lastWsTime + gap * i) as UTCTimestamp });
            }
            whitespaceSeriesRef.current.setData(futureWs);
        }

        const last = slice[slice.length - 1];
        if (last) lastPriceInfoRef.current = { close: last.close, open: last.open };

        if (scrollToEnd) {
            const ts = chart.timeScale();
            const barsToShow = 80;
            const from = Math.max(0, slice.length - barsToShow);
            const to = slice.length + 10;
            ts.setVisibleLogicalRange({ from, to });
        }
    }, []);

    const appendBar = useCallback((idx: number, chartData: ChartBar[]) => {
        const candle = candleSeriesRef.current;
        const volume = volumeSeriesRef.current;
        const session = sessionBgSeriesRef.current;
        const bar = chartData[idx];
        if (!candle || !volume || !bar) return;

        candle.update({
            time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
        });
        volume.update({
            time: bar.time as UTCTimestamp,
            value: bar.volume,
            color: bar.close >= bar.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
        } as any);
        if (session) {
            session.update({
                time: bar.time as UTCTimestamp, value: 1, color: getSessionColor(bar.time),
            } as any);
        }
        lastPriceInfoRef.current = { close: bar.close, open: bar.open };
    }, []);

    const syncIndicators = useCallback((cutoffTime: number) => {
        if (!indicatorResults) return;
        for (const inst of indicators) {
            if (!inst.visible) continue;
            const result = (indicatorResults as any)[inst.id];
            if (!result) continue;
            const seriesMap = indicatorSeriesRef.current.get(inst.id);
            if (!seriesMap) continue;
            const { type, data: rData } = result as any;
            try {
                const cut = (arr: any[]) => arr ? arr.filter((d: any) => d.time <= cutoffTime) : [];
                const tv = (arr: any[]) => cut(arr).map((d: any) => ({ time: d.time as UTCTimestamp, value: d.value }));
                const tvc = (arr: any[]) => cut(arr).map((d: any) => ({
                    time: d.time as UTCTimestamp, value: d.value,
                    color: d.color || (d.value >= 0 ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)'),
                }));
                if (['sma', 'ema', 'vwap', 'rsi', 'atr', 'obv'].includes(type)) {
                    seriesMap.get('main')?.setData(tv(rData));
                } else if (type === 'bb' || type === 'keltner') {
                    seriesMap.get('upper')?.setData(tv(rData?.upper));
                    seriesMap.get('middle')?.setData(tv(rData?.middle));
                    seriesMap.get('lower')?.setData(tv(rData?.lower));
                } else if (type === 'macd') {
                    seriesMap.get('histogram')?.setData(tvc(rData?.histogram));
                    seriesMap.get('macd')?.setData(tv(rData?.macd));
                    seriesMap.get('signal')?.setData(tv(rData?.signal));
                } else if (type === 'stoch') {
                    seriesMap.get('k')?.setData(tv(rData?.k));
                    seriesMap.get('d')?.setData(tv(rData?.d));
                } else if (type === 'adx') {
                    seriesMap.get('adx')?.setData(tv(rData?.adx));
                    seriesMap.get('pdi')?.setData(tv(rData?.pdi));
                    seriesMap.get('mdi')?.setData(tv(rData?.mdi));
                } else if (type === 'squeeze' || type === 'rvol') {
                    seriesMap.get('main')?.setData(cut(rData).map((d: any) => ({
                        time: d.time as UTCTimestamp, value: d.value, color: d.color,
                    })));
                }
            } catch { }
        }
    }, [indicators, indicatorResults]);

    // ── Actions ──────────────────────────────────────────────────────────

    const enterSelectingMode = useCallback(() => {
        if (data.length === 0) return;
        setMode('selecting');
        modeRef.current = 'selecting';
    }, [data.length]);

    const selectStartPoint = useCallback((barTime: number) => {
        const idx = findClosestBarIndex(data, barTime);
        if (idx < 0) return;
        replayControlsDataRef.current = true;
        replayTimeRef.current = data[idx].time;
        const visibleIdx = Math.max(idx - 1, 0);
        setStartIndex(visibleIdx); startIndexRef.current = visibleIdx;
        setCurrentIndex(visibleIdx); currentIndexRef.current = visibleIdx;
        rebuildSeriesUpTo(visibleIdx, data, true);
        if (data[visibleIdx]) syncIndicators(data[visibleIdx].time);
        setMode('paused'); modeRef.current = 'paused';
    }, [data, rebuildSeriesUpTo, syncIndicators]);

    const stepForward = useCallback((count = 1) => {
        if (modeRef.current === 'idle' || modeRef.current === 'selecting') return;
        const d = dataRef.current;
        const cur = currentIndexRef.current;
        if (cur >= d.length - 1) return;
        const target = Math.min(cur + count, d.length - 1);
        for (let i = cur + 1; i <= target; i++) appendBar(i, d);
        if (d[target]) syncIndicators(d[target].time);
        currentIndexRef.current = target;
        setCurrentIndex(target);
    }, [appendBar, syncIndicators]);

    const stepBackward = useCallback((count = 1) => {
        if (modeRef.current === 'idle' || modeRef.current === 'selecting') return;
        const d = dataRef.current;
        const cur = currentIndexRef.current;
        const minIdx = startIndexRef.current;
        if (cur <= minIdx) return;
        const target = Math.max(cur - count, minIdx);
        rebuildSeriesUpTo(target, d);
        if (d[target]) syncIndicators(d[target].time);
        currentIndexRef.current = target;
        setCurrentIndex(target);
    }, [rebuildSeriesUpTo, syncIndicators]);

    const play = useCallback(() => {
        if (modeRef.current === 'paused') { setMode('playing'); modeRef.current = 'playing'; }
    }, []);
    const pause = useCallback(() => {
        if (modeRef.current === 'playing') { clearTimer(); setMode('paused'); modeRef.current = 'paused'; }
    }, [clearTimer]);
    const togglePlay = useCallback(() => {
        if (modeRef.current === 'playing') pause(); else if (modeRef.current === 'paused') play();
    }, [play, pause]);
    const cycleSpeed = useCallback(() => {
        setSpeed(prev => SPEED_OPTIONS[(SPEED_OPTIONS.indexOf(prev) + 1) % SPEED_OPTIONS.length]);
    }, []);

    const exitReplay = useCallback(() => {
        clearTimer();
        replayControlsDataRef.current = false;
        replayTimeRef.current = null;
        modeRef.current = 'idle';
        setMode('idle');
        setReplayTimestamp(null);
        setCurrentIndex(0); currentIndexRef.current = 0;
        setStartIndex(0); startIndexRef.current = 0;

        const d = dataRef.current;
        const candle = candleSeriesRef.current;
        const volume = volumeSeriesRef.current;
        const session = sessionBgSeriesRef.current;
        if (candle && d.length > 0) {
            candle.setData(d.map(b => ({
                time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close,
            })));
        }
        if (volume && d.length > 0) {
            volume.setData(d.map(b => ({
                time: b.time as UTCTimestamp, value: b.volume,
                color: b.close >= b.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
            })));
        }
        if (session && d.length > 0) {
            session.setData(d.map(b => ({
                time: b.time as UTCTimestamp, value: 1, color: getSessionColor(b.time),
            } as any)));
        }
        if (d.length > 0) {
            const last = d[d.length - 1];
            lastPriceInfoRef.current = { close: last.close, open: last.open };
            if (indicatorResults) syncIndicators(last.time);
        }
        chartRef.current?.timeScale().scrollToRealTime();
    }, [clearTimer, syncIndicators, indicatorResults]);

    // ── Playback timer ───────────────────────────────────────────────────

    const appendBarRef = useRef(appendBar);
    appendBarRef.current = appendBar;
    const syncIndicatorsRef = useRef(syncIndicators);
    syncIndicatorsRef.current = syncIndicators;
    const loadForwardRef = useRef(loadForward);
    loadForwardRef.current = loadForward;
    const isLoadingForwardRef = useRef(false);

    useEffect(() => {
        clearTimer();
        if (mode !== 'playing') return;
        const ms = BASE_TICK_MS / speed;
        timerRef.current = setInterval(() => {
            const d = dataRef.current;
            const cur = currentIndexRef.current;

            if (cur >= d.length - 1) {
                if (isLoadingForwardRef.current) return;
                isLoadingForwardRef.current = true;
                loadForwardRef.current().then(loaded => {
                    isLoadingForwardRef.current = false;
                    if (!loaded) {
                        clearTimer();
                        setMode('paused'); modeRef.current = 'paused';
                    }
                });
                return;
            }

            if (!isLoadingForwardRef.current && d.length - 1 - cur < 200) {
                isLoadingForwardRef.current = true;
                loadForwardRef.current().finally(() => { isLoadingForwardRef.current = false; });
            }

            const next = cur + 1;
            appendBarRef.current(next, d);
            if (d[next]) syncIndicatorsRef.current(d[next].time);
            currentIndexRef.current = next;
            setCurrentIndex(next);
        }, ms);
        return clearTimer;
    }, [mode, speed, clearTimer]);

    // ── Pause on interval change ────────────────────────────────────────
    const prevIntervalRef = useRef(selectedInterval);
    useEffect(() => {
        if (prevIntervalRef.current === selectedInterval) return;
        prevIntervalRef.current = selectedInterval;
        if (modeRef.current === 'playing') {
            clearTimer();
            setMode('paused'); modeRef.current = 'paused';
        }
    }, [selectedInterval, clearTimer]);

    // ── Position replay when data changes ──────────────────────────────
    //
    // Three cases:
    // 1. loadMore prepended older bars → shift indices forward
    // 2. loadForward appended newer bars → no-op (indices stay)
    // 3. Fresh data (interval change) → find replay target, rebuild

    const prevDataRef = useRef(data);
    const prevChartVersionRef = useRef(chartVersion);
    const awaitingFreshDataRef = useRef(false);
    useEffect(() => {
        const prev = prevDataRef.current;
        const prevCV = prevChartVersionRef.current;
        prevDataRef.current = data;
        prevChartVersionRef.current = chartVersion;

        const mode = modeRef.current;
        if (mode === 'idle' || mode === 'selecting') return;
        if (!data.length) return;
        if (prev === data && prevCV === chartVersion) return;

        const isNewChart = prevCV !== chartVersion;
        const isNewData = prev !== data;

        if (isNewChart) {
            awaitingFreshDataRef.current = true;
            if (!isNewData) return;
        }

        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;

        if (!awaitingFreshDataRef.current && isNewData
            && prev.length > 0 && data.length > prev.length) {
            const delta = data.length - prev.length;

            // loadMore prepended older bars at the front
            if (prev[0].time === data[delta]?.time) {
                const newStart = startIndexRef.current + delta;
                const newCurrent = currentIndexRef.current + delta;
                setStartIndex(newStart); startIndexRef.current = newStart;
                setCurrentIndex(newCurrent); currentIndexRef.current = newCurrent;
                rebuildSeriesUpTo(newCurrent, data);
                return;
            }

            // loadForward appended newer bars at the end — indices stay the same
            const lastPrev = prev[prev.length - 1];
            if (lastPrev && data[prev.length - 1]?.time === lastPrev.time) {
                return;
            }
        }

        // Fresh data (interval change) — find the bar closest to the
        // replay target so playback resumes from the same point in time.
        awaitingFreshDataRef.current = false;
        const replayTarget = replayTimeRef.current;
        const rawIdx = replayTarget
            ? findClosestBarIndex(data, replayTarget)
            : data.length - 1;
        const targetIdx = Math.max(rawIdx - 1, 0);
        replayControlsDataRef.current = true;
        setStartIndex(0); startIndexRef.current = 0;
        setCurrentIndex(targetIdx); currentIndexRef.current = targetIdx;
        rebuildSeriesUpTo(targetIdx, data, true);
        if (data[targetIdx]) syncIndicators(data[targetIdx].time);
    }, [data, chartVersion, rebuildSeriesUpTo, syncIndicators]);

    return {
        replayState: { mode, currentIndex, startIndex, speed, totalBars: data.length } as ReplayState,
        replayControlsDataRef,
        enterSelectingMode,
        selectStartPoint,
        play, pause, togglePlay,
        stepForward, stepBackward,
        cycleSpeed, setSpeed,
        exitReplay,
        SPEED_OPTIONS,
    };
}
