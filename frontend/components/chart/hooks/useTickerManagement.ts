import { useEffect, useRef, useState, useCallback } from 'react';
import type { MutableRefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { useFloatingWindowActions, useWindowState, useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { useLinkGroupSubscription } from '@/hooks/useLinkGroup';
import { useMarketSessionStore, selectSession, selectIsTrading } from '@/stores/useMarketSessionStore';
import type { TickerSearchRef } from '@/components/common/TickerSearch';
import type { ChartWindowState, Interval, TimeRange } from '../constants';
import type { IndicatorInstance } from '../constants';

export interface TickerMeta {
    company_name: string;
    exchange: string;
    icon_url: string;
}

export function useTickerManagement(
    initialTicker: string,
    tickerSearchRef: MutableRefObject<TickerSearchRef | null>,
    onTickerChange?: (ticker: string) => void,
    options?: { inLayoutMode?: boolean },
) {
    const inLayoutMode = options?.inLayoutMode ?? false;
    const { t } = useTranslation();
    const { state: windowState, updateState: updateWindowState } = useWindowState<ChartWindowState>();
    const windowId = useCurrentWindowId?.();
    const { openWindow, updateWindow } = useFloatingWindowActions();
    const linkBroadcast = useLinkGroupSubscription();

    // In layout mode the parent (ChartCell) owns the ticker. We always seed
    // from `initialTicker` and ignore `windowState.ticker` (which is shared
    // by all cells and would clobber each other otherwise).
    const seedTicker = inLayoutMode ? initialTicker : (windowState.ticker || initialTicker);
    const [currentTicker, setCurrentTicker] = useState(seedTicker);
    const [inputValue, setInputValue] = useState(seedTicker);
    const [tickerMeta, setTickerMeta] = useState<TickerMeta | null>(null);

    // Sesión de mercado desde el store global único (sincronizado por
    // useMarketClockSync: eventos WS + snapshot 'connected' + refetch en
    // visibility/reconexión). Antes cada chart mantenía su propia copia que
    // quedaba obsoleta si la pestaña dormía durante una transición de sesión
    // (la línea de pre-market no aparecía hasta el siguiente evento).
    const marketSession = useMarketSessionStore(selectSession);
    const isMarketOpen = useMarketSessionStore(selectIsTrading);

    // Fetch ticker metadata
    useEffect(() => {
        if (!currentTicker) return;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        fetch(`${apiUrl}/api/v1/ticker/${currentTicker.toUpperCase()}/metadata`)
            .then(res => res.ok ? res.json() : null)
            .then(d => {
                if (d) {
                    const MIC: Record<string, string> = {
                        XNAS: 'NASDAQ', XNYS: 'NYSE', XASE: 'AMEX',
                        ARCX: 'NYSE ARCA', BATS: 'CBOE', IEXG: 'IEX',
                        XNMS: 'NASDAQ', XNGS: 'NASDAQ', XNCM: 'NASDAQ',
                        OTC: 'OTC', OTCM: 'OTC', OOTC: 'OTC',
                    };
                    setTickerMeta({
                        company_name: d.company_name || currentTicker,
                        exchange: MIC[d.exchange] || d.exchange || '',
                        icon_url: d.icon_url || '',
                    });
                }
            })
            .catch(() => setTickerMeta(null));
    }, [currentTicker]);

    // Update floating window title
    useEffect(() => {
        if (windowId) {
            updateWindow(windowId, { title: t('chart.title') });
        }
    }, [windowId, updateWindow, t]);

    // Sync when windowState.ticker arrives late (store hydration race condition).
    // Disabled in layout mode.
    const hasAppliedWindowState = useRef(inLayoutMode ? true : !!windowState.ticker);

    useEffect(() => {
        if (inLayoutMode) return;
        if (windowState.ticker && windowState.ticker !== currentTicker && !hasAppliedWindowState.current) {
            hasAppliedWindowState.current = true;
            setCurrentTicker(windowState.ticker);
            setInputValue(windowState.ticker);
        } else if (windowState.ticker) {
            hasAppliedWindowState.current = true;
        }
    }, [windowState.ticker, inLayoutMode]);

    // Update when external ticker prop changes. In layout mode we *always*
    // honour initialTicker (the parent is the source of truth).
    useEffect(() => {
        if (!inLayoutMode && hasAppliedWindowState.current) {
            hasAppliedWindowState.current = false;
            return;
        }
        tickerSearchRef.current?.suppressSearch();
        tickerSearchRef.current?.close();
        setCurrentTicker(initialTicker);
        setInputValue(initialTicker);
    }, [initialTicker, inLayoutMode]);

    // Link group: subscribe to ticker broadcasts
    useEffect(() => {
        if (linkBroadcast?.ticker) {
            tickerSearchRef.current?.suppressSearch();
            setCurrentTicker(linkBroadcast.ticker.toUpperCase());
            setInputValue(linkBroadcast.ticker.toUpperCase());
        }
    }, [linkBroadcast]);

    // Persist window state
    const persistState = useCallback((
        selectedInterval: Interval,
        selectedRange: TimeRange,
        showVolume: boolean,
        indicators: IndicatorInstance[],
        nextInstanceId: number,
    ) => {
        updateWindowState({
            ticker: currentTicker,
            interval: selectedInterval,
            range: selectedRange,
            showVolume,
            indicators,
            nextInstanceId,
        });
    }, [currentTicker, updateWindowState]);

    // Ticker change handlers
    const handleTickerChange = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        const newTicker = inputValue.trim().toUpperCase();
        if (newTicker && newTicker !== currentTicker) {
            setCurrentTicker(newTicker);
            onTickerChange?.(newTicker);
        }
        tickerSearchRef.current?.close();
    }, [inputValue, currentTicker, onTickerChange]);

    const handleTickerSelect = useCallback((selected: { symbol: string }) => {
        const newTicker = selected.symbol.toUpperCase();
        setInputValue(newTicker);
        if (newTicker !== currentTicker) {
            setCurrentTicker(newTicker);
            onTickerChange?.(newTicker);
        }
        tickerSearchRef.current?.close();
    }, [currentTicker, onTickerChange]);

    return {
        currentTicker,
        setCurrentTicker,
        inputValue,
        setInputValue,
        marketSession,
        isMarketOpen,
        tickerMeta,
        windowId,
        windowState,
        openWindow,
        persistState,
        handleTickerChange,
        handleTickerSelect,
    };
}
