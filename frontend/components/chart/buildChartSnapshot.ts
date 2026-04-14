import type { IChartApi } from 'lightweight-charts';
import { INDICATOR_TYPE_DEFAULTS, type ChartBar, type IndicatorInstance } from './constants';
import type { ChartSnapshot } from '@/components/ai-agent/types';
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { Drawing } from '@/hooks/useChartDrawings';

export function buildChartSnapshot(
    data: ChartBar[],
    indicatorResults: IndicatorResults | null,
    drawings: Drawing[],
    activeIndicators: IndicatorInstance[],
    chartApi: IChartApi | null,
): ChartSnapshot {
    const visibleRange = chartApi?.timeScale().getVisibleLogicalRange();
    const fromIdx = Math.max(0, Math.floor(visibleRange?.from ?? 0));
    const toIdx = Math.min(data.length - 1, Math.ceil(visibleRange?.to ?? data.length - 1));

    const visibleBars = data.slice(fromIdx, toIdx + 1);
    const recentBars = visibleBars;
    const rightEdge = toIdx;
    const rightTime = data[rightEdge]?.time;

    const findValue = (arr?: { time: number; value: number }[]) => {
        if (!arr?.length || !rightTime) return undefined;
        const pt = arr.find(p => p.time === rightTime);
        if (pt) return pt.value;
        return arr[arr.length - 1]?.value;
    };

    const trajectory = (arr?: { time: number; value: number }[], count = 5) => {
        if (!arr || !rightTime) return undefined;
        return arr.filter(p => p.time <= rightTime).slice(-count).map(d => d.value);
    };

    const indicators: ChartSnapshot['indicators'] = {};

    if (indicatorResults) {
        for (const [instId, result] of Object.entries(indicatorResults)) {
            const { type, data: rData } = result as any;
            const label = instId;
            if (type === 'sma' || type === 'ema' || type === 'vwap' || type === 'atr' || type === 'obv') {
                if (Array.isArray(rData)) indicators[label] = findValue(rData);
            } else if (type === 'bb' || type === 'keltner') {
                if (rData?.upper) indicators[label + '_upper'] = findValue(rData.upper);
                if (rData?.middle) indicators[label + '_mid'] = findValue(rData.middle);
                if (rData?.lower) indicators[label + '_lower'] = findValue(rData.lower);
            } else if (type === 'rsi') {
                if (Array.isArray(rData)) {
                    indicators[label] = findValue(rData);
                    indicators[label + '_trajectory'] = trajectory(rData);
                }
            } else if (type === 'macd') {
                if (rData?.macd) indicators[label + '_line'] = findValue(rData.macd);
                if (rData?.signal) indicators[label + '_signal'] = findValue(rData.signal);
                if (rData?.histogram) {
                    indicators[label + '_histogram'] = findValue(rData.histogram);
                    indicators[label + '_hist_trajectory'] = trajectory(rData.histogram);
                }
            } else if (type === 'stoch') {
                if (rData?.k) indicators[label + '_k'] = findValue(rData.k);
                if (rData?.d) indicators[label + '_d'] = findValue(rData.d);
            } else if (type === 'adx') {
                if (rData?.adx) indicators[label + '_adx'] = findValue(rData.adx);
                if (rData?.pdi) indicators[label + '_pdi'] = findValue(rData.pdi);
                if (rData?.mdi) indicators[label + '_mdi'] = findValue(rData.mdi);
            }
        }
    }

    const closePrices = visibleBars.map(b => b.close);
    const r2 = (v: number) => Math.round(v * 100) / 100;
    const calcSMA = (prices: number[], period: number) =>
        r2(prices.slice(-period).reduce((s, c) => s + c, 0) / period);
    const calcEMA = (prices: number[], period: number) => {
        const k = 2 / (period + 1);
        let ema = prices.slice(0, period).reduce((s, c) => s + c, 0) / period;
        for (let i = period; i < prices.length; i++) ema = prices[i] * k + ema * (1 - k);
        return r2(ema);
    };

    if (!indicators.sma20 && closePrices.length >= 20) indicators.sma20 = calcSMA(closePrices, 20);
    if (!indicators.sma50 && closePrices.length >= 50) indicators.sma50 = calcSMA(closePrices, 50);
    if (!indicators.ema12 && closePrices.length >= 12) indicators.ema12 = calcEMA(closePrices, 12);
    if (!indicators.ema26 && closePrices.length >= 26) indicators.ema26 = calcEMA(closePrices, 26);

    if (!indicators.macd_line && closePrices.length >= 26) {
        const allEma12: number[] = [];
        const allEma26: number[] = [];
        const k12 = 2 / 13, k26 = 2 / 27;
        let e12 = closePrices.slice(0, 12).reduce((s, c) => s + c, 0) / 12;
        let e26 = closePrices.slice(0, 26).reduce((s, c) => s + c, 0) / 26;
        for (let i = 0; i < closePrices.length; i++) {
            if (i >= 12) e12 = closePrices[i] * k12 + e12 * (1 - k12);
            if (i >= 26) e26 = closePrices[i] * k26 + e26 * (1 - k26);
            if (i >= 26) { allEma12.push(e12); allEma26.push(e26); }
        }
        const macdLine = allEma12.map((v, i) => v - allEma26[i]);
        if (macdLine.length >= 9) {
            const k9 = 2 / 10;
            let sig = macdLine.slice(0, 9).reduce((s, c) => s + c, 0) / 9;
            for (let i = 9; i < macdLine.length; i++) sig = macdLine[i] * k9 + sig * (1 - k9);
            indicators.macd_line = r2(macdLine[macdLine.length - 1]);
            indicators.macd_signal = r2(sig);
            indicators.macd_histogram = r2(macdLine[macdLine.length - 1] - sig);
            indicators.macd_hist_trajectory = macdLine.slice(-5).map((v, i, arr) => {
                const sigArr = macdLine.slice(0, -5 + i + 1);
                let s = sigArr.slice(0, 9).reduce((sum, c) => sum + c, 0) / 9;
                for (let j = 9; j < sigArr.length; j++) s = sigArr[j] * k9 + s * (1 - k9);
                return r2(v - s);
            });
        }
    }

    if (!indicators.bb_upper && closePrices.length >= 20) {
        const sma = (indicators.sma20 as number | undefined) ?? calcSMA(closePrices, 20);
        const last20 = closePrices.slice(-20);
        const variance = last20.reduce((s, c) => s + Math.pow(c - sma, 2), 0) / 20;
        const stddev = Math.sqrt(variance);
        indicators.bb_upper = r2(sma + 2 * stddev);
        indicators.bb_mid = r2(sma);
        indicators.bb_lower = r2(sma - 2 * stddev);
    }

    if (!indicators.rsi && closePrices.length >= 15) {
        const period = 14;
        const changes = closePrices.slice(-period - 1).map((c, i, arr) => i > 0 ? c - arr[i - 1] : 0).slice(1);
        const avgGain = changes.filter(c => c > 0).reduce((s, c) => s + c, 0) / period;
        const avgLoss = changes.filter(c => c < 0).reduce((s, c) => s + Math.abs(c), 0) / period;
        indicators.rsi = avgLoss === 0 ? 100 : r2(100 - 100 / (1 + avgGain / avgLoss));
    }

    if (!indicators.atr && visibleBars.length >= 15) {
        const last15 = visibleBars.slice(-15);
        const trs = last15.slice(1).map((b, i) => Math.max(b.high - b.low, Math.abs(b.high - last15[i].close), Math.abs(b.low - last15[i].close)));
        indicators.atr = r2(trs.reduce((s, t) => s + t, 0) / trs.length);
    }

    const cleanIndicators: ChartSnapshot['indicators'] = {};
    for (const [k, v] of Object.entries(indicators)) {
        if (v !== undefined && v !== null && (typeof v !== 'number' || !isNaN(v))) {
            (cleanIndicators as Record<string, unknown>)[k] = v;
        }
    }

    const levels = drawings
        .filter((d): d is Drawing & { type: 'horizontal_line' } => d.type === 'horizontal_line')
        .map(d => ({ price: d.price, label: d.label }));

    const isHistorical = toIdx < data.length - 3;

    return {
        recentBars: recentBars.map(b => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })),
        indicators: cleanIndicators,
        levels,
        visibleDateRange: { from: data[fromIdx]?.time ?? 0, to: rightTime ?? 0 },
        isHistorical,
    };
}
