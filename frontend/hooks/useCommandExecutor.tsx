'use client';

import { useCallback } from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent, UserProfileContent, USER_PROFILE_WINDOW_CONFIG } from '@/components/floating-window';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';
import { NewsContent } from '@/components/news/NewsContent';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import { FinancialsContent } from '@/components/financials/FinancialsContent';
import { IPOContent } from '@/components/ipos/IPOContent';
import { ChartContent } from '@/components/chart/ChartContent';
import { TickerStrip } from '@/components/ticker/TickerStrip';

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

// Configuración de categorías del scanner
const SCANNER_CATEGORIES: Record<string, { name: string; description: string }> = {
    'gappers_up': { name: 'Gap Up', description: 'Gap up ≥ 2%' },
    'gappers_down': { name: 'Gap Down', description: 'Gap down ≤ -2%' },
    'momentum_up': { name: 'Momentum Alcista', description: 'Cambio ≥ 3%' },
    'momentum_down': { name: 'Momentum Bajista', description: 'Cambio ≤ -3%' },
    'winners': { name: 'Mayores Ganadores', description: 'Cambio ≥ 5%' },
    'losers': { name: 'Mayores Perdedores', description: 'Cambio ≤ -5%' },
    'new_highs': { name: 'Nuevos Máximos', description: 'Máximos del día' },
    'new_lows': { name: 'Nuevos Mínimos', description: 'Mínimos del día' },
    'anomalies': { name: 'Anomalías', description: 'RVOL ≥ 3.0' },
    'high_volume': { name: 'Alto Volumen', description: 'RVOL ≥ 2.0' },
    'reversals': { name: 'Reversals', description: 'Cambios de dirección' },
};

/**
 * Hook centralizado para ejecutar comandos
 * Usado por CommandPalette, PinnedCommands y para abrir tablas del scanner
 * UNA SOLA FUENTE DE VERDAD para tamaños y posiciones de ventanas
 */
export function useCommandExecutor() {
    const { openWindow, closeWindow, windows } = useFloatingWindow();

    /**
     * Abrir una tabla del scanner como ventana flotante
     */
    const openScannerTable = useCallback((categoryId: string, index: number = 0) => {
        const category = SCANNER_CATEGORIES[categoryId];
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

        return openWindow({
            title,
            content: (
                <ScannerTableContent
                    categoryId={categoryId}
                    categoryName={category.name}
                    onClose={() => {
                        // Encontrar y cerrar la ventana por título
                        const win = windows.find(w => w.title === title);
                        if (win) closeWindow(win.id);
                    }}
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
    }, [openWindow, closeWindow, windows]);

    /**
     * Cerrar una tabla del scanner
     */
    const closeScannerTable = useCallback((categoryId: string) => {
        const category = SCANNER_CATEGORIES[categoryId];
        if (!category) return;

        const title = `Scanner: ${category.name}`;
        const win = windows.find(w => w.title === title);
        if (win) {
            closeWindow(win.id);
        }
    }, [windows, closeWindow]);

    /**
     * Verificar si una tabla del scanner está abierta
     */
    const isScannerTableOpen = useCallback((categoryId: string): boolean => {
        const category = SCANNER_CATEGORIES[categoryId];
        if (!category) return false;

        const title = `Scanner: ${category.name}`;
        return windows.some(w => w.title === title);
    }, [windows]);

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

            case 'sc':
                // SC es especial - abre el command palette
                return 'sc';

            default:
                // Verificar si es una categoría del scanner
                if (SCANNER_CATEGORIES[commandId]) {
                    openScannerTable(commandId, 0);
                    return null;
                }

                console.warn(`Unknown command: ${commandId}`);
                return null;
        }
    }, [openWindow, openScannerTable]);

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

    return {
        executeCommand,
        executeTickerCommand,
        openScannerTable,
        closeScannerTable,
        isScannerTableOpen,
        SCANNER_CATEGORIES,
    };
}
