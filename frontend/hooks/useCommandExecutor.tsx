'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { FilterManagerContent } from '@/components/scanner/FilterManagerContent';
import { DilutionTrackerContent, UserProfileContent, USER_PROFILE_WINDOW_CONFIG } from '@/components/floating-window';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';
import { NewsContent } from '@/components/news/NewsContent';
import { CatalystAlertsConfig } from '@/components/catalyst-alerts';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import TickersWithNewsTable from '@/components/scanner/TickersWithNewsTable';
import { FinancialsContent } from '@/components/financials/FinancialsContent';
import { IPOContent } from '@/components/ipos/IPOContent';
import { ChartContent } from '@/components/chart/ChartContent';
import { TickerStrip } from '@/components/ticker/TickerStrip';
import { DescriptionContent } from '@/components/description/DescriptionContent';
import { QuoteMonitor as QuoteMonitorContent } from '@/components/quote-monitor/QuoteMonitor';
import { ChatContent } from '@/components/chat';

// Wrapper para TickerStrip que obtiene onClose del contexto de ventana
function TickerStripWrapper({ symbol, exchange }: { symbol: string; exchange: string }) {
    const { closeWindow, windows } = useFloatingWindow();

    // Encontrar el ID de esta ventana por el título
    const windowId = windows.find(w => w.title === `Quote: ${symbol}`)?.id;

    const handleClose = () => {
        if (windowId) {
            closeWindow(windowId);
        }
    };

    return <TickerStrip symbol={symbol} exchange={exchange} onClose={handleClose} />;
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
            'with_news': { nameKey: 'scanner.withNews', descriptionKey: 'scanner.withNewsDescription' },
        };

        const category = categoryMap[categoryId];
        if (!category) return null;

        return {
            name: t(category.nameKey),
            description: t(category.descriptionKey),
        };
    }, [t]);

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
                content: (
                    <TickersWithNewsTable
                        title={category.name}
                    />
                ),
                width: 900,
                height: 500,
                x: baseX + offsetX,
                y: baseY + offsetY,
                minWidth: 600,
                minHeight: 300,
                hideHeader: true,
            });
        }

        return openWindow({
            title,
            content: (
                <ScannerTableContent
                    categoryId={categoryId}
                    categoryName={category.name}
                // onClose se maneja internamente en ScannerTableContent
                // usando el contexto actualizado de windows
                />
            ),
            width: 850,
            height: 500,
            x: baseX + offsetX,
            y: baseY + offsetY,
            minWidth: 500,
            minHeight: 300,
            hideHeader: true, // La tabla del scanner tiene su propia cabecera
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

            case 'filters':
                openWindow({
                    title: 'Filter Manager',
                    content: <FilterManagerContent />,
                    width: 500,
                    height: 600,
                    x: screenWidth / 2 - 250,
                    y: screenHeight / 2 - 300,
                    minWidth: 400,
                    minHeight: 400,
                });
                return null;

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

            case 'sc':
                // SC es especial - abre el command palette
                return 'sc';

            default:
                // Verificar si es una categoría del scanner
                if (getScannerCategory(commandId)) {
                    openScannerTable(commandId, 0);
                    return null;
                }

                console.warn(`Unknown command: ${commandId}`);
                return null;
        }
    }, [openWindow, openScannerTable, getScannerCategory]);

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
                    title: `Chart: ${normalizedTicker}`,
                    content: <ChartContent ticker={normalizedTicker} exchange={exchange} />,
                    width: 900,
                    height: 600,
                    x: Math.max(50, screenWidth / 2 - 450),
                    y: Math.max(80, screenHeight / 2 - 300),
                    minWidth: 600,
                    minHeight: 400,
                });
                break;

            case 'description':
                openWindow({
                    title: `Description: ${normalizedTicker}`,
                    content: <DescriptionContent ticker={normalizedTicker} exchange={exchange} />,
                    width: 1100,
                    height: 700,
                    x: Math.max(50, screenWidth / 2 - 550),
                    y: Math.max(70, screenHeight / 2 - 350),
                    minWidth: 900,
                    minHeight: 550,
                });
                break;

            case 'dilution-tracker':
                openWindow({
                    title: `DT: ${normalizedTicker}`,
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
                    title: `FA: ${normalizedTicker}`,
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
                    title: `SEC: ${normalizedTicker}`,
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
                    title: `News: ${normalizedTicker}`,
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
                    title: `Quote: ${normalizedTicker}`,
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
            title: ticker ? `News: ${ticker.toUpperCase()}` : 'News',
            content: <NewsContent initialTicker={ticker} highlightArticleId={articleId} />,
            width: 900,
            height: 600,
            x: Math.max(50, screenWidth / 2 - 450),
            y: Math.max(80, screenHeight / 2 - 300),
            minWidth: 700,
            minHeight: 450,
        });
    }, [openWindow]);

    return {
        executeCommand,
        executeTickerCommand,
        openNewsWithArticle,
        openScannerTable,
        closeScannerTable,
        isScannerTableOpen,
        getScannerCategory,
    };
}
