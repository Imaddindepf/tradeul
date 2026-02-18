import type { Time, UTCTimestamp } from 'lightweight-charts';
import type { ChartBar } from './constants';

export function calculateSMA(data: ChartBar[], period: number): { time: Time; value: number }[] {
    const result: { time: Time; value: number }[] = [];

    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j].close;
        }
        result.push({
            time: data[i].time as UTCTimestamp,
            value: sum / period
        });
    }

    return result;
}

export function calculateEMA(data: ChartBar[], period: number): { time: Time; value: number }[] {
    const result: { time: Time; value: number }[] = [];
    const multiplier = 2 / (period + 1);

    let sum = 0;
    for (let i = 0; i < period && i < data.length; i++) {
        sum += data[i].close;
    }

    if (data.length < period) return result;

    let ema = sum / period;
    result.push({ time: data[period - 1].time as UTCTimestamp, value: ema });

    for (let i = period; i < data.length; i++) {
        ema = (data[i].close - ema) * multiplier + ema;
        result.push({ time: data[i].time as UTCTimestamp, value: ema });
    }

    return result;
}
