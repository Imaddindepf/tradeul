'use client';

import { useCallback } from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import { FinancialsContent } from '@/components/financials/FinancialsContent';

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

    return {
        executeCommand,
        openScannerTable,
        closeScannerTable,
        isScannerTableOpen,
        SCANNER_CATEGORIES,
    };
}
