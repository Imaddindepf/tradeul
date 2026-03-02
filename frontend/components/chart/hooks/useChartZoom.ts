import { useCallback, useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, UTCTimestamp } from 'lightweight-charts';
import { TIME_RANGES, type ChartBar, type Interval, type TimeRange } from '../constants';

export function useChartZoom(
    chartRef: MutableRefObject<IChartApi | null>,
    data: ChartBar[],
    currentTicker: string,
    selectedInterval: Interval,
    selectedRange: TimeRange,
    setSelectedInterval: (i: Interval) => void,
    setSelectedRange: (r: TimeRange) => void,
    isReplayActive?: boolean,
) {
    const applyTimeRange = useCallback((range: TimeRange) => {
        if (!chartRef.current || data.length === 0) return;
        const timeScale = chartRef.current.timeScale();
        const rangeConfig = TIME_RANGES.find(r => r.id === range);
        if (!rangeConfig) return;

        if (range === 'ALL' || rangeConfig.days === 0) {
            timeScale.fitContent();
            return;
        }

        const lastBar = data[data.length - 1];
        const fromTimestamp = lastBar.time - (rangeConfig.days * 86400);

        let fromIndex = 0;
        for (let i = 0; i < data.length; i++) {
            if (data[i].time >= fromTimestamp) {
                fromIndex = i;
                break;
            }
        }

        if (fromIndex === 0 && data[0].time > fromTimestamp) {
            timeScale.fitContent();
            return;
        }

        timeScale.setVisibleRange({
            from: data[fromIndex].time as UTCTimestamp,
            to: lastBar.time as UTCTimestamp,
        });
    }, [data]);

    const zoomIn = useCallback(() => {
        if (!chartRef.current) return;
        const timeScale = chartRef.current.timeScale();
        const currentBarSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.min(currentBarSpacing * 1.5, 50) });
    }, []);

    const zoomOut = useCallback(() => {
        if (!chartRef.current) return;
        const timeScale = chartRef.current.timeScale();
        const currentBarSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.max(currentBarSpacing / 1.5, 1) });
    }, []);

    const handleRangeChange = useCallback((range: TimeRange) => {
        setSelectedRange(range);

        const rangeConfig = TIME_RANGES.find(r => r.id === range);
        if (rangeConfig && rangeConfig.days >= 730 && !['1week', '1month', '3month', '1year'].includes(selectedInterval)) {
            setSelectedInterval('1week');
            return;
        }
        if (rangeConfig && rangeConfig.days >= 180 && !['1day', '1week', '1month', '3month', '1year'].includes(selectedInterval)) {
            setSelectedInterval('1day');
            return;
        }
        if (rangeConfig && rangeConfig.days >= 30 && ['1min', '2min', '5min', '15min', '30min'].includes(selectedInterval)) {
            setSelectedInterval('1hour');
            return;
        }

        applyTimeRange(range);
    }, [applyTimeRange, selectedInterval, setSelectedInterval, setSelectedRange]);

    // Apply time range when data/ticker/interval/range changes
    const lastAppliedKeyRef = useRef<string>('');
    const applyRangeTimerRef = useRef<ReturnType<typeof setTimeout>>();

    const isReplayActiveRef = useRef(isReplayActive);
    isReplayActiveRef.current = isReplayActive;

    useEffect(() => {
        if (!data || data.length === 0) return;
        if (isReplayActive) {
            clearTimeout(applyRangeTimerRef.current);
            return;
        }
        const key = `${currentTicker}-${selectedInterval}-${selectedRange}`;
        if (lastAppliedKeyRef.current !== key) {
            lastAppliedKeyRef.current = key;
            clearTimeout(applyRangeTimerRef.current);
            applyRangeTimerRef.current = setTimeout(() => {
                if (isReplayActiveRef.current) return;
                applyTimeRange(selectedRange);
            }, 50);
        }
        return () => { clearTimeout(applyRangeTimerRef.current); };
    }, [data, currentTicker, selectedInterval, selectedRange, applyTimeRange, isReplayActive]);

    return { applyTimeRange, zoomIn, zoomOut, handleRangeChange };
}
