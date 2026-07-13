import { useEffect } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { ChartBar } from '../constants';
import { getSessionKind } from '@/lib/marketTime';

function getSessionColors() {
    const isDark = typeof document !== 'undefined' &&
        document.documentElement.classList.contains('dark');
    return {
        preMarket: isDark ? 'rgba(251, 191, 36, 0.06)' : 'rgba(255, 247, 235, 0.85)',
        postMarket: isDark ? 'rgba(96, 165, 250, 0.06)' : 'rgba(238, 243, 255, 0.85)',
        regular: 'rgba(0, 0, 0, 0)',
    };
}

export function getSessionColor(barTimeSeconds: number): string {
    const SESSION_COLORS = getSessionColors();
    const kind = getSessionKind(barTimeSeconds);
    if (kind === 'pre') return SESSION_COLORS.preMarket;
    if (kind === 'post') return SESSION_COLORS.postMarket;
    return SESSION_COLORS.regular;
}

function applySessionData(
    series: ISeriesApi<any>,
    data: ChartBar[],
) {
    const sessionData = data.map(bar => ({
        time: bar.time as UTCTimestamp,
        value: 1,
        color: getSessionColor(bar.time),
    }));
    series.setData(sessionData);
}

export function useSessionBackground(
    sessionBgSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    data: ChartBar[],
    selectedInterval: string,
    replayControlsDataRef?: MutableRefObject<boolean>,
) {
    useEffect(() => {
        if (!sessionBgSeriesRef.current || !data || data.length === 0) return;
        if (replayControlsDataRef?.current) return;
        applySessionData(sessionBgSeriesRef.current, data);
    }, [data, selectedInterval]);

    // Re-apply session colors when theme changes
    useEffect(() => {
        const observer = new MutationObserver(() => {
            if (!sessionBgSeriesRef.current || !data || data.length === 0) return;
            applySessionData(sessionBgSeriesRef.current, data);
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, [data]);
}
