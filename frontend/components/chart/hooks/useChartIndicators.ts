import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { MutableRefObject } from 'react';
import {
    LineSeries,
    HistogramSeries,
    LineStyle,
    type IChartApi,
    type ISeriesApi,
    type UTCTimestamp,
} from 'lightweight-charts';
import { useIndicatorWorker } from '@/hooks/useIndicatorWorker';
import type { WorkerIndicatorConfig, IndicatorResults } from '@/hooks/useIndicatorWorker';
import {
    INDICATOR_TYPE_DEFAULTS,
    OVERLAY_TYPES,
    PANEL_TYPES,
    getNextColor,
    migrateOldIndicatorState,
    type IndicatorInstance,
    type ChartBar,
    type Interval,
    type TimeRange,
    type ChartWindowState,
} from '../constants';

export function useChartIndicators(
    chartRef: MutableRefObject<IChartApi | null>,
    data: ChartBar[],
    currentTicker: string,
    selectedInterval: Interval,
    selectedRange: TimeRange,
    windowState: ChartWindowState,
) {
    const [indicators, setIndicators] = useState<IndicatorInstance[]>(() => {
        if (windowState.indicators && windowState.indicators.length > 0) return windowState.indicators;
        if (windowState.showMA || windowState.showEMA || windowState.activeOverlays?.length || windowState.activePanels?.length) {
            return migrateOldIndicatorState(windowState);
        }
        return [];
    });
    const nextInstanceIdRef = useRef(windowState.nextInstanceId || 1);
    const [showVolume, setShowVolume] = useState(windowState.showVolume ?? true);
    const [showNewsMarkers, setShowNewsMarkers] = useState(false);
    const [showEarningsMarkers, setShowEarningsMarkers] = useState(true);
    const [selectedIndicator, setSelectedIndicator] = useState<string | null>(null);
    const [legendExpanded, setLegendExpanded] = useState(true);
    const [indicatorSettingsOpen, setIndicatorSettingsOpen] = useState<string | null>(null);
    const [indicatorSettingsPos, setIndicatorSettingsPos] = useState<{ x: number; y: number } | undefined>();
    const [showIndicatorDropdown, setShowIndicatorDropdown] = useState(false);
    const indicatorDropdownRef = useRef<HTMLDivElement>(null);

    const { calculate, clearCache, results: indicatorResults, isCalculating: indicatorsLoading, isReady: workerReady } = useIndicatorWorker();
    const overlayInstances = useMemo(() => indicators.filter(i => i.visible && OVERLAY_TYPES.has(i.type)), [indicators]);
    const panelInstances = useMemo(() => indicators.filter(i => i.visible && PANEL_TYPES.has(i.type)), [indicators]);
    const indicatorSeriesRef = useRef<Map<string, Map<string, ISeriesApi<any>>>>(new Map());
    const panelPaneIndexRef = useRef<Map<string, number>>(new Map());

    useEffect(() => {
        if (!showIndicatorDropdown) return;
        const handleClick = (e: MouseEvent) => {
            if (indicatorDropdownRef.current && !indicatorDropdownRef.current.contains(e.target as Node)) {
                setShowIndicatorDropdown(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, [showIndicatorDropdown]);

    const addIndicator = useCallback((type: string) => {
        const id = `${type}_${nextInstanceIdRef.current++}`;
        const config = INDICATOR_TYPE_DEFAULTS[type];
        if (!config) return;
        const color = getNextColor(indicators);
        const newInst: IndicatorInstance = {
            id, type,
            params: { ...config.defaultParams },
            styles: { ...config.defaultStyles, color },
            visible: true,
        };
        setIndicators(prev => [...prev, newInst]);
        setShowIndicatorDropdown(false);
    }, [indicators]);

    const openIndicatorSettings = useCallback((indicatorId: string, event?: React.MouseEvent) => {
        const pos = event ? { x: Math.min(event.clientX, window.innerWidth - 340), y: Math.min(event.clientY, window.innerHeight - 460) } : undefined;
        setIndicatorSettingsPos(pos);
        setIndicatorSettingsOpen(indicatorId);
    }, []);

    const removeIndicator = useCallback((instanceId: string) => {
        if (instanceId === 'volume') { setShowVolume(false); return; }
        setIndicators(prev => prev.filter(i => i.id !== instanceId));
        setSelectedIndicator(null);
    }, []);

    const onApplyIndicatorSettings = useCallback((id: string, settings: { inputs: Record<string, number | string>; styles: Record<string, string | number>; visibility: string[] }) => {
        const { styles, inputs } = settings;
        setIndicators(prev => prev.map(inst => {
            if (inst.id !== id) return inst;
            return { ...inst, params: { ...inst.params, ...inputs }, styles: { ...inst.styles, ...styles } };
        }));
        const seriesMap = indicatorSeriesRef.current.get(id);
        if (!seriesMap) return;
        const inst = indicators.find(i => i.id === id);
        if (!inst) return;
        const color = styles.color as string;
        const lw = styles.lineWidth as number;
        const apply = (s: any, c?: string, w?: number) => {
            if (!s) return;
            const opts: any = {};
            if (c) opts.color = c;
            if (w) opts.lineWidth = w;
            try { s.applyOptions(opts); } catch {}
        };
        if (['sma', 'ema', 'vwap', 'atr', 'rsi', 'obv'].includes(inst.type)) {
            apply(seriesMap.get('main'), color, lw);
        } else if (inst.type === 'bb' || inst.type === 'keltner') {
            apply(seriesMap.get('upper'), styles.upperColor as string, lw);
            apply(seriesMap.get('middle'), styles.middleColor as string, lw);
            apply(seriesMap.get('lower'), styles.lowerColor as string, lw);
        } else if (inst.type === 'macd') {
            apply(seriesMap.get('macd'), styles.macdColor as string);
            apply(seriesMap.get('signal'), styles.signalColor as string);
        } else if (inst.type === 'stoch') {
            apply(seriesMap.get('k'), styles.kColor as string);
            apply(seriesMap.get('d'), styles.dColor as string);
        } else if (inst.type === 'adx') {
            apply(seriesMap.get('adx'), styles.adxColor as string);
            apply(seriesMap.get('pdi'), styles.pdiColor as string);
            apply(seriesMap.get('mdi'), styles.mdiColor as string);
        }
    }, [indicators]);

    return {
        indicators, setIndicators, nextInstanceIdRef,
        showVolume, setShowVolume,
        showNewsMarkers, setShowNewsMarkers,
        showEarningsMarkers, setShowEarningsMarkers,
        selectedIndicator, setSelectedIndicator,
        legendExpanded, setLegendExpanded,
        indicatorSettingsOpen, setIndicatorSettingsOpen, indicatorSettingsPos,
        showIndicatorDropdown, setShowIndicatorDropdown, indicatorDropdownRef,
        indicatorResults, indicatorsLoading, workerReady,
        overlayInstances, panelInstances,
        indicatorSeriesRef, panelPaneIndexRef,
        addIndicator, openIndicatorSettings, removeIndicator, onApplyIndicatorSettings,
        calculate, clearCache,
    };
}
