import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import { EarningsMarkerPrimitive } from '../primitives/EarningsMarkerPrimitive';
import type { ChartBar, Interval } from '../constants';

export function useEarningsMarkers(
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>,
    data: ChartBar[],
    selectedInterval: Interval,
    currentTicker: string,
    showEarningsMarkers: boolean,
) {
    const [earningsDates, setEarningsDates] = useState<{ date: string; time_slot: string }[]>([]);
    const earningsPrimitiveRef = useRef<EarningsMarkerPrimitive | null>(null);

    useEffect(() => {
        if (!currentTicker) return;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${apiUrl}/api/v1/earnings/ticker/${currentTicker.toUpperCase()}/dates?limit=100`)
            .then(res => res.ok ? res.json() : null)
            .then(d => {
                if (d?.dates) setEarningsDates(d.dates);
            })
            .catch(() => setEarningsDates([]));
    }, [currentTicker]);

    useEffect(() => {
        if (!candleSeriesRef.current || !data || data.length === 0) return;

        if (!earningsPrimitiveRef.current) {
            earningsPrimitiveRef.current = new EarningsMarkerPrimitive();
            candleSeriesRef.current.attachPrimitive(earningsPrimitiveRef.current);
        }

        const primitive = earningsPrimitiveRef.current;
        primitive.setVisible(showEarningsMarkers);
        primitive.setInterval(selectedInterval);
        primitive.setDataTimes(data.map(b => b.time));
        primitive.setEarnings(earningsDates);

        return () => {
            earningsPrimitiveRef.current = null;
        };
    }, [showEarningsMarkers, earningsDates, data, selectedInterval]);

    return { earningsDates, earningsPrimitiveRef };
}
