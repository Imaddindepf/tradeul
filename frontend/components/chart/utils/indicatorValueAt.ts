/**
 * Resolve the current values of every indicator at a given time. Used by the
 * indicator legend to display live numbers without re-querying the chart API.
 *
 * Each returned entry has:
 *   - `label`: e.g. "SMA 20", "MACD 12,26,9"
 *   - `mainColor`: the canonical color for the indicator instance
 *   - `values`: ordered list of { name, value, color } pairs for display
 */
import type { IndicatorResults } from '@/hooks/useIndicatorWorker';
import type { IndicatorInstance } from '../constants';
import { getInstanceLabel } from '../constants';

export interface IndicatorLiveValue {
    name: string;
    value: number | null;
    color: string;
}

export interface IndicatorLiveLine {
    id: string;
    label: string;
    mainColor: string;
    values: IndicatorLiveValue[];
}

function findValueAt(arr: any[] | undefined, time: number): number | null {
    if (!arr || arr.length === 0) return null;
    // The result arrays are time-ordered. Binary search for the latest sample
    // whose time <= target (so hovering an old bar shows the value AT that bar,
    // not the latest).
    let lo = 0;
    let hi = arr.length - 1;
    let best = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const t = arr[mid].time as number;
        if (t <= time) {
            best = mid;
            lo = mid + 1;
        } else {
            hi = mid - 1;
        }
    }
    if (best < 0) return null;
    const v = arr[best].value;
    return typeof v === 'number' ? v : null;
}

export function computeIndicatorLiveLines(
    indicators: IndicatorInstance[],
    indicatorResults: IndicatorResults | null,
    referenceTime: number | null,
): IndicatorLiveLine[] {
    if (!indicatorResults || referenceTime == null) {
        // No data yet — still emit headers so the legend isn't empty mid-load.
        return indicators
            .filter(i => i.visible)
            .map(inst => ({
                id: inst.id,
                label: getInstanceLabel(inst),
                mainColor: mainColorOf(inst),
                values: [],
            }));
    }

    const out: IndicatorLiveLine[] = [];
    for (const inst of indicators) {
        if (!inst.visible) continue;
        const r: any = (indicatorResults as any)[inst.id];
        const mainColor = mainColorOf(inst);
        const label = getInstanceLabel(inst);
        const values: IndicatorLiveValue[] = [];

        if (!r) {
            out.push({ id: inst.id, label, mainColor, values });
            continue;
        }

        switch (r.type ?? inst.type) {
            case 'sma':
            case 'ema':
            case 'vwap':
            case 'rsi':
            case 'atr':
            case 'obv':
                values.push({ name: '', value: findValueAt(r.data, referenceTime), color: mainColor });
                break;
            case 'bb':
            case 'keltner':
                values.push(
                    { name: 'U', value: findValueAt(r.data?.upper, referenceTime), color: (inst.styles.upperColor as string) || mainColor },
                    { name: 'B', value: findValueAt(r.data?.middle, referenceTime), color: (inst.styles.middleColor as string) || mainColor },
                    { name: 'L', value: findValueAt(r.data?.lower, referenceTime), color: (inst.styles.lowerColor as string) || mainColor },
                );
                break;
            case 'macd':
                values.push(
                    { name: 'MACD', value: findValueAt(r.data?.macd, referenceTime), color: (inst.styles.macdColor as string) || '#3b82f6' },
                    { name: 'Sig', value: findValueAt(r.data?.signal, referenceTime), color: (inst.styles.signalColor as string) || '#f97316' },
                    { name: 'Hist', value: findValueAt(r.data?.histogram, referenceTime), color: '#64748b' },
                );
                break;
            case 'stoch':
                values.push(
                    { name: '%K', value: findValueAt(r.data?.k, referenceTime), color: (inst.styles.kColor as string) || '#3b82f6' },
                    { name: '%D', value: findValueAt(r.data?.d, referenceTime), color: (inst.styles.dColor as string) || '#f97316' },
                );
                break;
            case 'adx':
                values.push(
                    { name: 'ADX', value: findValueAt(r.data?.adx, referenceTime), color: (inst.styles.adxColor as string) || '#8b5cf6' },
                    { name: '+DI', value: findValueAt(r.data?.pdi, referenceTime), color: (inst.styles.pdiColor as string) || '#10b981' },
                    { name: '-DI', value: findValueAt(r.data?.mdi, referenceTime), color: (inst.styles.mdiColor as string) || '#ef4444' },
                );
                break;
            case 'squeeze':
            case 'rvol':
                values.push({ name: '', value: findValueAt(r.data, referenceTime), color: mainColor });
                break;
            default:
                break;
        }
        out.push({ id: inst.id, label, mainColor, values });
    }
    return out;
}

function mainColorOf(inst: IndicatorInstance): string {
    return (
        (inst.styles.color as string) ||
        (inst.styles.upperColor as string) ||
        (inst.styles.macdColor as string) ||
        (inst.styles.kColor as string) ||
        (inst.styles.adxColor as string) ||
        (inst.styles.onColor as string) ||
        '#888'
    );
}
