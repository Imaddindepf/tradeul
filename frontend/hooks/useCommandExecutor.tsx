'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useFloatingWindow, useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent, UserProfileContent, USER_PROFILE_WINDOW_CONFIG, PredictionMarketsContent } from '@/components/floating-window';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';
import { NewsContent } from '@/components/news/NewsContent';
import { CatalystAlertsConfig } from '@/components/catalyst-alerts';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import { TickersWithNewsContent } from '@/components/scanner/TickersWithNewsContent';
import { FinancialsContent } from '@/components/financials/FinancialsContent';
import { IPOContent } from '@/components/ipos/IPOContent';
import { EarningsCalendarContent } from '@/components/floating-window/EarningsCalendarContent';
import { ChartContent } from '@/components/chart/ChartContent';
import { TickerStrip } from '@/components/ticker/TickerStrip';
// DescriptionContent removed - now using FinancialAnalystContent
import { QuoteMonitor as QuoteMonitorContent } from '@/components/quote-monitor/QuoteMonitor';
import { ChatContent } from '@/components/chat';
import { NotesContent } from '@/components/notes/NotesContent';
import { GlossaryContent } from '@/components/glossary';
import { PatternMatchingContent } from '@/components/pattern-matching';
import { PatternRealtimeContent } from '@/components/pattern-realtime';
import { RatioAnalysisContent } from '@/components/ratio-analysis';
import { ScreenerContent } from '@/components/screener';
import { HistoricalMultipleSecurityContent } from '@/components/historical-multiple-security';
import { InsiderTradingContent, InsiderGlossaryContent } from '@/components/insider-trading';
import { FinancialAnalystContent } from '@/components/financial-analyst';
import { AIAgentContent } from '@/components/ai-agent';
import { InsightsPanel } from '@/components/insights';
import { HeatmapContent } from '@/components/heatmap';
import { MarketPulseContent } from '@/components/market-pulse';
import { UserScanTableContent } from '@/components/scanner/UserScanTableContent';
import { InstitutionalHoldingsContent } from '@/components/institutional-holdings';
import { EventTableContent } from '@/components/events/EventTableContent';
import { ConfigWindow, type AlertWindowConfig } from '@/components/config/ConfigWindow';
import { useEventFiltersStore } from '@/stores/useEventFiltersStore';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { SYSTEM_EVENT_CATEGORIES } from '@/lib/commands';
import type { UserFilter } from '@/lib/types/scannerFilters';

// Wrapper para TickerStrip - usa useCloseCurrentWindow automáticamente
function TickerStripWrapper({ symbol, exchange }: { symbol: string; exchange: string }) {
    const closeCurrentWindow = useCloseCurrentWindow();
    return <TickerStrip symbol={symbol} exchange={exchange} onClose={closeCurrentWindow} />;
}

/**
 * Hook centralizado para ejecutar comandos
 * Usado por CommandPalette, PinnedCommands y para abrir tablas del scanner
 * UNA SOLA FUENTE DE VERDAD para tamaños y posiciones de ventanas
 */
export function useCommandExecutor() {
    const { t } = useTranslation();
    const { openWindow, closeWindow, windows } = useFloatingWindow();

    // Obtener categorías del scanner con traducciones
    const getScannerCategory = useCallback((categoryId: string) => {
        const categoryMap: Record<string, { nameKey: string; descriptionKey: string }> = {
            'gappers_up': { nameKey: 'scanner.gapUp', descriptionKey: 'scanner.gapUpDescription' },
            'gappers_down': { nameKey: 'scanner.gapDown', descriptionKey: 'scanner.gapDownDescription' },
            'momentum_up': { nameKey: 'scanner.momentumUp', descriptionKey: 'scanner.momentumUpDescription' },
            'momentum_down': { nameKey: 'scanner.momentumDown', descriptionKey: 'scanner.momentumDownDescription' },
            'winners': { nameKey: 'scanner.topGainers', descriptionKey: 'scanner.topGainersDescription' },
            'losers': { nameKey: 'scanner.topLosers', descriptionKey: 'scanner.topLosersDescription' },
            'new_highs': { nameKey: 'scanner.newHighs', descriptionKey: 'scanner.newHighsDescription' },
            'new_lows': { nameKey: 'scanner.newLows', descriptionKey: 'scanner.newLowsDescription' },
            'anomalies': { nameKey: 'scanner.anomalies', descriptionKey: 'scanner.anomaliesDescription' },
            'high_volume': { nameKey: 'scanner.highVolume', descriptionKey: 'scanner.highVolumeDescription' },
            'reversals': { nameKey: 'scanner.reversals', descriptionKey: 'scanner.reversalsDescription' },
            'post_market': { nameKey: 'scanner.postMarket', descriptionKey: 'scanner.postMarketDescription' },
            'with_news': { nameKey: 'scanner.withNews', descriptionKey: 'scanner.withNewsDescription' },
        };

        const category = categoryMap[categoryId];
        if (!category) return null;

        return {
            name: t(category.nameKey),
            description: t(category.descriptionKey),
        };
    }, [t]);

    // Obtener categorías de eventos
    const getEventCategory = useCallback((categoryId: string) => {
        const category = SYSTEM_EVENT_CATEGORIES.find(c => c.id === categoryId);
        if (!category) return null;

        return {
            id: category.id,
            name: category.label,
            description: category.description,
            eventTypes: category.eventTypes,
            icon: category.icon,
            defaultFilters: category.defaultFilters,
        };
    }, []);

    /**
     * Abrir una tabla de eventos como ventana flotante
     */
    const openEventTable = useCallback((categoryId: string, index: number = 0) => {
        const category = getEventCategory(categoryId);
        if (!category) {
            console.warn(`Unknown event category: ${categoryId}`);
            return null;
        }

        const title = `Events: ${category.name}`;

        // Calcular posición escalonada
        const baseX = 150;
        const baseY = 120;
        const offsetX = (index % 5) * 50;
        const offsetY = (index % 5) * 40;

        const cs = {
            restoreType: 'event_table',
            categoryId,
            categoryName: category.name,
            eventTypes: category.eventTypes,
            defaultFilters: category.defaultFilters,
        };
        const winId = openWindow({
            title,
            content: (
                <EventTableContent
                    categoryId={categoryId}
                    categoryName={category.name}
                    eventTypes={category.eventTypes}
                    defaultFilters={category.defaultFilters}
                />
            ),
            width: 750,
            height: 450,
            x: baseX + offsetX,
            y: baseY + offsetY,
            minWidth: 500,
            minHeight: 300,
            hideHeader: true,
            componentState: cs,
        });
        useUserPreferencesStore.getState().updateWindowComponentState(winId, cs);
        return winId;
    }, [openWindow, getEventCategory]);

    /**
     * Abrir una tabla del scanner como ventana flotante
     */
    const openScannerTable = useCallback((categoryId: string, index: number = 0) => {
        const category = getScannerCategory(categoryId);
        if (!category) {
            console.warn(`Unknown scanner category: ${categoryId}`);
            return null;
        }

        const title = `Scanner: ${category.name}`;

        // Calcular posición escalonada
        const baseX = 100;
        const baseY = 100;
        const offsetX = (index % 5) * 50;
        const offsetY = (index % 5) * 40;

        // Caso especial: tabla de "Tickers with News" (intersección scanner + news)
        if (categoryId === 'with_news') {
            return openWindow({
                title,
                content: <TickersWithNewsContent title={category.name} />,
                width: 900,
                height: 500,
                x: baseX + offsetX,
                y: baseY + offsetY,
                minWidth: 600,
                minHeight: 300,
                hideHeader: true,
            });
        }

        // Halts ahora usa ScannerTableContent como las demás categorías
        // con columnas enriquecidas (rvol, market_cap, free_float, etc.)

        return openWindow({
            title,
            content: (
                <ScannerTableContent
                    categoryId={categoryId}
                    categoryName={category.name}
                />
            ),
            width: 850,
            height: 500,
            x: baseX + offsetX,
            y: baseY + offsetY,
            minWidth: 500,
            minHeight: 300,
            hideHeader: true,
        });
    }, [openWindow, getScannerCategory]);

    /**
     * Cerrar una tabla del scanner
     */
    const closeScannerTable = useCallback((categoryId: string) => {
        const category = getScannerCategory(categoryId);
        if (!category) return;

        const title = `Scanner: ${category.name}`;
        const win = windows.find(w => w.title === title);
        if (win) {
            closeWindow(win.id);
        }
    }, [windows, closeWindow, getScannerCategory]);

    /**
     * Verificar si una tabla del scanner está abierta
     */
    const isScannerTableOpen = useCallback((categoryId: string): boolean => {
        const category = getScannerCategory(categoryId);
        if (!category) return false;

        const title = `Scanner: ${category.name}`;
        return windows.some(w => w.title === title);
    }, [windows, getScannerCategory]);

    /**
     * Ejecutar un comando
     */
    const executeCommand = useCallback((commandId: string): string | null => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        // Comandos de ventanas flotantes
        switch (commandId) {
            case 'settings':
                openWindow({
                    title: 'Settings',
                    content: <SettingsContent />,
                    width: 280,
                    height: 260,
                    x: screenWidth - 300,
                    y: 80,
                    minWidth: 260,
                    minHeight: 220,
                });
                return null;

            case 'build':
            case 'new':
            case 'create': {

                // Track categoryId across multiple onCreateAlertWindow calls
                let activeCategoryId: string | null = null;
                openWindow({
                    title: 'Strategy Builder',
                    content: (
                        <ConfigWindow
                            onCreateAlertWindow={(config: AlertWindowConfig) => {
                                const filterStore = useEventFiltersStore.getState();
                                const prefStore = useUserPreferencesStore.getState();
                                if (activeCategoryId) {
                                    filterStore.setAllFilters(activeCategoryId, {
                                        ...config.filters,
                                        event_types: config.eventTypes,
                                    });
                                } else {
                                    activeCategoryId = `evt_custom_${Date.now()}`;
                                    filterStore.setAllFilters(activeCategoryId, {
                                        ...config.filters,
                                        event_types: config.eventTypes,
                                    });
                                    const evtCs = {
                                        restoreType: 'event_table',
                                        categoryId: activeCategoryId,
                                        categoryName: config.name,
                                        eventTypes: config.eventTypes,
                                    };
                                    const winId = openWindow({
                                        title: `Events: ${config.name}`,
                                        content: (
                                            <EventTableContent
                                                categoryId={activeCategoryId}
                                                categoryName={config.name}
                                                eventTypes={config.eventTypes}
                                            />
                                        ),
                                        width: 800,
                                        height: 500,
                                        x: 220,
                                        y: 170,
                                        minWidth: 500,
                                        minHeight: 300,
                                        hideHeader: true,
                                        componentState: evtCs,
                                    });
                                    prefStore.updateWindowComponentState(winId, evtCs);
                                }
                            }}
                            onCreateScannerWindow={(savedFilter: UserFilter) => {
                                const prefStore = useUserPreferencesStore.getState();
                                const categoryId = `uscan_${savedFilter.id}`;
                                const scanCs = {
                                    restoreType: 'user_scan',
                                    categoryId,
                                    categoryName: savedFilter.name,
                                    scanId: savedFilter.id,
                                };
                                const winId = openWindow({
                                    title: `Scanner: ${savedFilter.name}`,
                                    content: (
                                        <ScannerTableContent
                                            categoryId={categoryId}
                                            categoryName={savedFilter.name}
                                        />
                                    ),
                                    width: 850,
                                    height: 500,
                                    x: Math.max(50, screenWidth / 2 - 425),
                                    y: Math.max(80, screenHeight / 2 - 250),
                                    minWidth: 500,
                                    minHeight: 300,
                                    hideHeader: true,
                                    componentState: scanCs,
                                });
                                prefStore.updateWindowComponentState(winId, scanCs);
                            }}
                        />
                    ),
                    width: 700,
                    height: 550,
                    x: screenWidth / 2 - 350,
                    y: screenHeight / 2 - 275,
                    minWidth: 550,
                    minHeight: 450,
                });
                return null;
            }

            case 'dt':
                openWindow({
                    title: 'Dilution Tracker',
                    content: <DilutionTrackerContent />,
                    width: 900,
                    height: 600,
                    x: screenWidth / 2 - 450,
                    y: screenHeight / 2 - 300,
                    minWidth: 600,
                    minHeight: 400,
                });
                return null;

            case 'sec':
                openWindow({
                    title: 'SEC Filings',
                    content: <SECFilingsContent />,
                    width: 1000,
                    height: 650,
                    x: screenWidth / 2 - 500,
                    y: screenHeight / 2 - 325,
                    minWidth: 800,
                    minHeight: 500,
                });
                return null;

            case 'news':
                openWindow({
                    title: 'News',
                    content: <NewsContent />,
                    width: 900,
                    height: 600,
                    x: screenWidth / 2 - 450,
                    y: screenHeight / 2 - 300,
                    minWidth: 700,
                    minHeight: 450,
                });
                return null;

            case 'ins':
                openWindow({
                    title: 'Insights',
                    content: <InsightsPanel />,
                    width: 700,
                    height: 600,
                    x: Math.max(100, screenWidth / 2 - 350),
                    y: Math.max(50, screenHeight / 2 - 300),
                    minWidth: 500,
                    minHeight: 400,
                });
                return null;

            case 'alerts':
                openWindow({
                    title: 'Catalyst Alerts',
                    content: <CatalystAlertsConfig />,
                    width: 420,
                    height: 520,
                    x: screenWidth - 450,
                    y: 80,
                    minWidth: 380,
                    minHeight: 450,
                });
                return null;

            case 'fa':
                openWindow({
                    title: 'Financial Analysis',
                    content: <FinancialsContent />,
                    width: 700,
                    height: 550,
                    x: Math.max(50, screenWidth / 2 - 350),
                    y: Math.max(80, (screenHeight - 64) / 2 - 275 + 64), // 64px = navbar height
                    minWidth: 500,
                    minHeight: 400,
                });
                return null;

            case 'profile':
                openWindow({
                    title: USER_PROFILE_WINDOW_CONFIG.title,
                    content: <UserProfileContent />,
                    width: USER_PROFILE_WINDOW_CONFIG.width,
                    height: USER_PROFILE_WINDOW_CONFIG.height,
                    x: Math.max(100, screenWidth / 2 - USER_PROFILE_WINDOW_CONFIG.width / 2),
                    y: Math.max(80, screenHeight / 2 - USER_PROFILE_WINDOW_CONFIG.height / 2),
                    minWidth: USER_PROFILE_WINDOW_CONFIG.minWidth,
                    minHeight: USER_PROFILE_WINDOW_CONFIG.minHeight,
                    maxWidth: USER_PROFILE_WINDOW_CONFIG.maxWidth,
                    maxHeight: USER_PROFILE_WINDOW_CONFIG.maxHeight,
                });
                return null;

            case 'ipo':
                openWindow({
                    title: 'IPOs',
                    content: <IPOContent />,
                    width: 850,
                    height: 500,
                    x: Math.max(50, screenWidth / 2 - 425),
                    y: Math.max(80, screenHeight / 2 - 250),
                    minWidth: 600,
                    minHeight: 350,
                });
                return null;

            case 'earnings':
                openWindow({
                    title: 'Earnings Calendar',
                    content: <EarningsCalendarContent />,
                    width: 900,
                    height: 450,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 225),
                    minWidth: 700,
                    minHeight: 300,
                });
                return null;

            case 'predict':
                openWindow({
                    title: 'Prediction Markets',
                    content: <PredictionMarketsContent />,
                    width: 650,
                    height: 550,
                    x: Math.max(50, screenWidth / 2 - 325),
                    y: Math.max(80, screenHeight / 2 - 275),
                    minWidth: 500,
                    minHeight: 400,
                });
                return null;

            case 'heatmap':
            case 'hm':
                openWindow({
                    title: 'Market Heatmap',
                    content: <HeatmapContent />,
                    width: 1100,
                    height: 750,
                    x: Math.max(50, screenWidth / 2 - 550),
                    y: Math.max(70, screenHeight / 2 - 375),
                    minWidth: 800,
                    minHeight: 500,
                });
                return null;

            case 'watchlist':
                openWindow({
                    title: 'Quote Monitor',
                    content: <QuoteMonitorContent />,
                    width: 900,
                    height: 500,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 250),
                    minWidth: 700,
                    minHeight: 350,
                });
                return null;

            case 'chat':
                openWindow({
                    title: 'Community Chat',
                    content: <ChatContent />,
                    width: 700,
                    height: 500,
                    x: Math.max(50, screenWidth - 750),
                    y: Math.max(80, screenHeight / 2 - 250),
                    minWidth: 500,
                    minHeight: 400,
                });
                return null;

            case 'notes':
                openWindow({
                    title: 'Notes',
                    content: <NotesContent />,
                    width: 500,
                    height: 450,
                    x: Math.max(50, screenWidth - 550),
                    y: Math.max(80, screenHeight / 2 - 225),
                    minWidth: 350,
                    minHeight: 300,
                });
                return null;

            case 'glossary':
            case 'indicators':
                openWindow({
                    title: 'Indicators',
                    content: <GlossaryContent />,
                    width: 280,
                    height: 400,
                    x: Math.max(50, screenWidth - 330),
                    y: Math.max(80, screenHeight / 2 - 200),
                    minWidth: 220,
                    minHeight: 280,
                });
                return null;

            case 'patterns':
            case 'pm':
                openWindow({
                    title: 'Pattern Matching',
                    content: <PatternMatchingContent />,
                    width: 700,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 350),
                    y: Math.max(80, screenHeight / 2 - 325),
                    minWidth: 550,
                    minHeight: 500,
                });
                return null;

            case 'prt':
            case 'pattern-realtime':
            case 'patternscan':
                openWindow({
                    title: 'Pattern Real-Time',
                    content: <PatternRealtimeContent />,
                    width: 900,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 325),
                    minWidth: 700,
                    minHeight: 500,
                });
                return null;

            case 'ratio':
            case 'gr':
                openWindow({
                    title: 'Ratio Analysis',
                    content: <RatioAnalysisContent />,
                    width: 800,
                    height: 750,
                    x: Math.max(50, screenWidth / 2 - 400),
                    y: Math.max(70, screenHeight / 2 - 375),
                    minWidth: 650,
                    minHeight: 600,
                });
                return null;

            case 'screener':
            case 'screen':
                openWindow({
                    title: 'Stock Screener',
                    content: <ScreenerContent />,
                    width: 900,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(70, screenHeight / 2 - 325),
                    minWidth: 700,
                    minHeight: 500,
                });
                return null;

            case 'mp':
            case 'compare':
            case 'multiple':
                openWindow({
                    title: 'Historical Multiple Security',
                    content: <HistoricalMultipleSecurityContent />,
                    width: 950,
                    height: 600,
                    x: Math.max(50, screenWidth / 2 - 475),
                    y: Math.max(70, screenHeight / 2 - 300),
                    minWidth: 700,
                    minHeight: 450,
                });
                return null;

            case 'insider':
            case 'insiders':
            case 'form4':
                openWindow({
                    title: 'Insider Trading',
                    content: <InsiderTradingContent />,
                    width: 700,
                    height: 500,
                    x: Math.max(50, screenWidth / 2 - 350),
                    y: Math.max(70, screenHeight / 2 - 250),
                    minWidth: 500,
                    minHeight: 350,
                });
                return null;

            case 'insider-glossary':
            case 'insider-help':
                openWindow({
                    title: 'Insider Trading Guide',
                    content: <InsiderGlossaryContent />,
                    width: 380,
                    height: 450,
                    x: Math.max(50, screenWidth / 2 + 100),
                    y: Math.max(70, screenHeight / 2 - 200),
                    minWidth: 300,
                    minHeight: 350,
                });
                return null;

            case 'fan':
                openWindow({
                    title: 'Financial Analyst',
                    content: <FinancialAnalystContent />,
                    width: 500,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 250),
                    y: Math.max(70, screenHeight / 2 - 325),
                    minWidth: 400,
                    minHeight: 500,
                });
                return null;

            case 'ai':
                openWindow({
                    title: 'AI Agent',
                    content: <AIAgentContent />,
                    width: 1100,
                    height: 700,
                    x: Math.max(50, screenWidth / 2 - 550),
                    y: Math.max(70, screenHeight / 2 - 350),
                    minWidth: 800,
                    minHeight: 500,
                });
                return null;

            case 'hds':
            case 'holders':
                openWindow({
                    title: 'Institutional Holdings',
                    content: <InstitutionalHoldingsContent />,
                    width: 850,
                    height: 550,
                    x: Math.max(50, screenWidth / 2 - 425),
                    y: Math.max(70, screenHeight / 2 - 275),
                    minWidth: 650,
                    minHeight: 400,
                });
                return null;

            case 'pulse':
            case 'market-pulse':
                openWindow({
                    title: 'Market Pulse',
                    content: <MarketPulseContent />,
                    width: 520,
                    height: 580,
                    x: Math.max(50, screenWidth - 570),
                    y: Math.max(70, 90),
                    minWidth: 420,
                    minHeight: 400,
                    hideHeader: true,
                });
                return null;

            default:
                break;
        }

        // SC es especial - abre el command palette
        if (commandId === 'sc') {
            return 'sc';
        }

        // EVN es especial - abre el command palette con eventos
        if (commandId === 'evn') {
            return 'evn';
        }

        // Verificar si es una categoría del scanner
        if (getScannerCategory(commandId)) {
            openScannerTable(commandId, 0);
            return null;
        }

        // Verificar si es una categoría de eventos
        if (getEventCategory(commandId)) {
            openEventTable(commandId, 0);
            return null;
        }

        console.warn(`Unknown command: ${commandId}`);
        return null;
    }, [openWindow, openScannerTable, getScannerCategory, openEventTable, getEventCategory]);

    /**
     * Ejecutar un comando con ticker específico
     * Usado por el TerminalPalette para comandos tipo "AAPL DT"
     * @param ticker - Símbolo del ticker
     * @param commandId - ID del comando a ejecutar
     * @param exchange - Exchange opcional (para TradingView)
     */
    const executeTickerCommand = useCallback((ticker: string, commandId: string, exchange?: string) => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        const normalizedTicker = ticker.toUpperCase();

        switch (commandId) {
            case 'graph':
            case 'chart': // Alias para graph
                openWindow({
                    title: 'Chart',
                    content: <ChartContent ticker={normalizedTicker} exchange={exchange} />,
                    width: 900,
                    height: 600,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 300),
                    minWidth: 600,
                    minHeight: 400,
                });
                break;

            case 'description': // Legacy: redirect to FAN
            case 'des': // Alias
                openWindow({
                    title: 'Financial Analyst',
                    content: <FinancialAnalystContent initialTicker={normalizedTicker} />,
                    width: 500,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 250),
                    y: Math.max(70, screenHeight / 2 - 325),
                    minWidth: 400,
                    minHeight: 500,
                });
                break;

            case 'dilution-tracker':
                openWindow({
                    title: 'Dilution Tracker',
                    content: <DilutionTrackerContent initialTicker={normalizedTicker} />,
                    width: 900,
                    height: 600,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 300),
                    minWidth: 600,
                    minHeight: 400,
                });
                break;

            case 'financials':
                openWindow({
                    title: 'Financials',
                    content: <FinancialsContent initialTicker={normalizedTicker} />,
                    width: 700,
                    height: 550,
                    x: Math.max(50, screenWidth / 2 - 350),
                    y: Math.max(80, (screenHeight - 64) / 2 - 275 + 64),
                    minWidth: 500,
                    minHeight: 400,
                });
                break;

            case 'sec-filings':
                openWindow({
                    title: 'SEC Filings',
                    content: <SECFilingsContent initialTicker={normalizedTicker} />,
                    width: 1000,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 500),
                    y: Math.max(80, screenHeight / 2 - 325),
                    minWidth: 800,
                    minHeight: 500,
                });
                break;

            case 'news':
                openWindow({
                    title: 'News',
                    content: <NewsContent initialTicker={normalizedTicker} />,
                    width: 900,
                    height: 600,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 300),
                    minWidth: 700,
                    minHeight: 450,
                });
                break;

            case 'quote':
            case 'span':
                // Mostrar precio real-time del ticker en tira compacta
                openWindow({
                    title: 'Quote',
                    content: (
                        <TickerStripWrapper
                            symbol={normalizedTicker}
                            exchange={exchange || 'US'}
                        />
                    ),
                    width: 560,
                    height: 48,
                    x: Math.max(50, screenWidth / 2 - 280),
                    y: 70,
                    minWidth: 450,
                    minHeight: 48,
                    maxHeight: 48,
                    hideHeader: true,
                });
                break;

            case 'patterns':
            case 'pm':
                // Pattern Matching con ticker específico
                openWindow({
                    title: 'Pattern Matching',
                    content: <PatternMatchingContent initialTicker={normalizedTicker} />,
                    width: 700,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 350),
                    y: Math.max(80, screenHeight / 2 - 325),
                    minWidth: 550,
                    minHeight: 500,
                });
                break;

            case 'fan':
                // Financial Analyst con ticker específico
                openWindow({
                    title: 'Financial Analyst',
                    content: <FinancialAnalystContent initialTicker={normalizedTicker} />,
                    width: 500,
                    height: 650,
                    x: Math.max(50, screenWidth / 2 - 250),
                    y: Math.max(70, screenHeight / 2 - 325),
                    minWidth: 400,
                    minHeight: 500,
                });
                break;

            case 'hds':
            case 'holders':
                // Institutional Holdings con ticker específico
                openWindow({
                    title: 'Institutional Holdings',
                    content: <InstitutionalHoldingsContent initialTicker={normalizedTicker} />,
                    width: 850,
                    height: 550,
                    x: Math.max(50, screenWidth / 2 - 425),
                    y: Math.max(70, screenHeight / 2 - 275),
                    minWidth: 650,
                    minHeight: 400,
                });
                break;

            default:
                console.warn(`Unknown ticker command: ${commandId}`);
        }
    }, [openWindow]);

    /**
     * Abrir la ventana de News con un artículo específico destacado
     * @param articleId - ID del artículo (benzinga_id o combinación con ticker)
     * @param ticker - Opcional: filtrar por ticker
     */
    const openNewsWithArticle = useCallback((articleId: string, ticker?: string) => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        openWindow({
            title: 'News',  // Siempre "News" - el ticker se persiste en componentState
            content: <NewsContent initialTicker={ticker} highlightArticleId={articleId} />,
            width: 900,
            height: 600,
            x: Math.max(50, screenWidth / 2 - 450),
            y: Math.max(80, screenHeight / 2 - 300),
            minWidth: 700,
            minHeight: 450,
        });
    }, [openWindow]);

    /**
     * Abrir tabla de resultados de un scan personalizado del usuario.
     * Usa ScannerTableContent (igual que categorías del sistema) para WebSocket real-time.
     * El categoryId es "uscan_{filterId}" que coincide con la key en Redis.
     */
    const openUserScanTable = useCallback((scan: UserFilter) => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        const categoryId = `uscan_${scan.id}`;
        const cs = {
            restoreType: 'user_scan',
            categoryId,
            categoryName: scan.name,
            scanId: scan.id,
        };
        const winId = openWindow({
            title: `Scanner: ${scan.name}`,
            content: (
                <ScannerTableContent
                    categoryId={categoryId}
                    categoryName={scan.name}
                />
            ),
            width: 850,
            height: 500,
            x: Math.max(50, screenWidth / 2 - 425),
            y: Math.max(80, screenHeight / 2 - 250),
            minWidth: 500,
            minHeight: 300,
            hideHeader: true,
            componentState: cs,
        });
        useUserPreferencesStore.getState().updateWindowComponentState(winId, cs);
    }, [openWindow]);

    /**
     * Abrir una tabla de eventos desde una estrategia guardada del usuario
     */
    const openUserStrategyTable = useCallback((strategy: { id: number; name: string; eventTypes: string[]; filters: Record<string, any> }, index: number = 0) => {
        const categoryId = `user_strategy_${strategy.id}`;

        // Pre-cargar filtros en el store
        useEventFiltersStore.getState().setAllFilters(categoryId, strategy.filters);

        const baseX = 150;
        const baseY = 120;
        const offsetX = (index % 5) * 50;
        const offsetY = (index % 5) * 40;

        const cs = {
            restoreType: 'user_strategy',
            categoryId,
            categoryName: strategy.name,
            eventTypes: strategy.eventTypes,
            strategyId: strategy.id,
            filters: strategy.filters,
        };
        const winId = openWindow({
            title: `Events: ${strategy.name}`,
            content: (
                <EventTableContent
                    categoryId={categoryId}
                    categoryName={strategy.name}
                    eventTypes={strategy.eventTypes}
                />
            ),
            width: 750,
            height: 450,
            x: baseX + offsetX,
            y: baseY + offsetY,
            minWidth: 500,
            minHeight: 300,
            hideHeader: true,
            componentState: cs,
        });
        useUserPreferencesStore.getState().updateWindowComponentState(winId, cs);
        return winId;
    }, [openWindow]);

    return {
        executeCommand,
        executeTickerCommand,
        openNewsWithArticle,
        openScannerTable,
        closeScannerTable,
        isScannerTableOpen,
        getScannerCategory,
        openUserScanTable,
        // Event functions
        openEventTable,
        getEventCategory,
        openUserStrategyTable,
    };
}
