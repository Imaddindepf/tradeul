/**
 * useEventMarkers
 *
 * Single source of truth for "event" markers rendered inside the chart's
 * time-axis area (earnings, news, and any future event types). Combines all
 * provided event streams into one EventMarkerPrimitive attached to the candle
 * series, so all markers share the same visual language and z-order.
 *
 * Why centralize: previously earnings used a time-axis primitive while news
 * used `series.setMarkers()` (chart-pane). That produced two inconsistent
 * marker rendering paths and made hover/click handling hard to reason about.
 */
import { useEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import {
    EventMarkerPrimitive,
    type ChartEvent,
} from '../primitives/EventMarkerPrimitive';
import type { ChartBar } from '../constants';

interface UseEventMarkersOptions {
    candleSeriesRef: MutableRefObject<ISeriesApi<any> | null>;
    data: ChartBar[];
    /** Each stream contributes events to the merged marker layer. */
    streams: ChartEvent[][];
    /** Refresh palette when theme changes (light/dark toggle). */
    themeKey?: string;
    /** chartVersion bumps on chart re-init (ticker/interval change). */
    chartVersion: number;
}

export function useEventMarkers({
    candleSeriesRef,
    data,
    streams,
    themeKey,
    chartVersion,
}: UseEventMarkersOptions) {
    const primitiveRef = useRef<EventMarkerPrimitive | null>(null);

    const events = useMemo<ChartEvent[]>(() => {
        return streams.flat();
    }, [streams]);

    // Latest values exposed via refs so the [chartVersion] effect can seed a
    // newly-created primitive even when data/events haven't changed since the
    // chart was re-initialised (ticker/interval/style switch).
    const dataRef = useRef(data);
    dataRef.current = data;
    const eventsRef = useRef(events);
    eventsRef.current = events;

    // Create + attach primitive once per chart instance, and seed it with the
    // current data + events immediately so markers appear without waiting for
    // those refs to change later.
    useEffect(() => {
        const series = candleSeriesRef.current;
        if (!series) return;
        const primitive = new EventMarkerPrimitive();
        series.attachPrimitive(primitive);
        primitiveRef.current = primitive;
        primitive.setDataTimes(dataRef.current.map(b => b.time));
        primitive.setEvents(eventsRef.current);
        return () => {
            try { series.detachPrimitive(primitive); } catch { /* */ }
            primitiveRef.current = null;
        };
    }, [chartVersion, candleSeriesRef]);

    // Push data times whenever bars change.
    useEffect(() => {
        const primitive = primitiveRef.current;
        if (!primitive) return;
        primitive.setDataTimes(data.map(b => b.time));
    }, [data]);

    // Push events whenever any stream updates.
    useEffect(() => {
        const primitive = primitiveRef.current;
        if (!primitive) return;
        primitive.setEvents(events);
    }, [events]);

    // Refresh palette on theme change.
    useEffect(() => {
        primitiveRef.current?.refreshPalette();
    }, [themeKey]);

    return { primitiveRef };
}
