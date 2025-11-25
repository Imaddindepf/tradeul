'use client';

import { useCallback } from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';

/**
 * Hook centralizado para ejecutar comandos
 * Usado por CommandPalette y PinnedCommands
 * UNA SOLA FUENTE DE VERDAD para tamaños y posiciones de ventanas
 */
export function useCommandExecutor() {
    const { openWindow } = useFloatingWindow();

    const executeCommand = useCallback((commandId: string): string | null => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
        const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

        switch (commandId) {
            case 'settings':
                openWindow({
                    title: 'Settings',
                    content: <SettingsContent />,
                    width: 280,
                    height: 240,
                    x: screenWidth - 300,
                    y: 80,
                    minWidth: 260,
                    minHeight: 200,
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

            // Scanner commands - retornar ID para manejo externo
            case 'sc':
            case 'gappers_up':
            case 'gappers_down':
            case 'halts':
            case 'momentum':
            case 'volume':
            case 'ipo':
            case 'spac':
            case 'low_float':
            case 'high_short':
                return commandId;

            default:
                console.warn(`Unknown command: ${commandId}`);
                return null;
        }
    }, [openWindow]);

    return { executeCommand };
}
