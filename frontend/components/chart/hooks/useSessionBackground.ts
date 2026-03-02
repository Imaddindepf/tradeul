import { useEffect } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { ChartBar } from '../constants';

const SESSION_COLORS = {
    preMarket: 'rgba(255, 247, 235, 0.85)',
    postMarket: 'rgba(238, 243, 255, 0.85)',
    regular: 'rgba(0, 0, 0, 0)',
};

export function getSessionColor(barTimeSeconds: number): string {
    const date = new Date(barTimeSeconds * 1000);
    const etParts = date.toLocaleString('en-US', {
        timeZone: 'America/New_York',
        hour: 'numeric',
        minute: 'numeric',
        hour12: false,
    });
    const [hStr, mStr] = etParts.split(':');
    const totalMinutes = parseInt(hStr) * 60 + parseInt(mStr);

    if (totalMinutes >= 240 && totalMinutes < 570) return SESSION_COLORS.preMarket;
    if (totalMinutes >= 960 && totalMinutes < 1200) return SESSION_COLORS.postMarket;
    return SESSION_COLORS.regular;
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

        const sessionData = data.map(bar => ({
            time: bar.time as UTCTimestamp,
            value: 1,
            color: getSessionColor(bar.time),
        }));

        sessionBgSeriesRef.current.setData(sessionData);
    }, [data, selectedInterval]);
}
