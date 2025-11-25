'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Command } from 'cmdk';
import {
    ScanSearch,
    TrendingUp,
    TrendingDown,
    Zap,
    Trophy,
    AlertTriangle,
    BarChart3,
    Bell,
    Settings,
    X,
    Search,
    ArrowUp,
    ArrowDown,
    LayoutGrid,
    FileText,
} from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';

interface CommandPaletteProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelectCategory?: (categoryId: string) => void;
    activeCategories?: string[];
    searchValue?: string;
    onSearchChange?: (value: string) => void;
}

type CommandItem = {
    id: string;
    label: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    group: string;
    shortcut?: string;
    disabled?: boolean;
};

// Sistema de comandos con prefijos tipo terminal
// Comandos principales (sin prefijo)
const MAIN_COMMANDS: CommandItem[] = [
    { id: 'sc', label: 'SC', description: 'Scanner - Ver todas las tablas', icon: LayoutGrid, group: 'Comandos principales' },
    { id: 'dt', label: 'DT', description: 'Dilution Tracker - Análisis de dilución', icon: BarChart3, shortcut: 'Ctrl+D', group: 'Comandos principales' },
    { id: 'sec', label: 'SEC', description: 'SEC Filings - Filings de la SEC en tiempo real', icon: FileText, shortcut: 'Ctrl+F', group: 'Comandos principales' },
    { id: 'settings', label: 'SET', description: 'Settings - Configuración de la app', icon: Settings, shortcut: 'Ctrl+,', group: 'Comandos principales' },
];

// Comandos del scanner (prefijo SC)
const SCANNER_COMMANDS: CommandItem[] = [
    { id: 'gappers_up', label: 'SC Gap Up', description: 'Gap up ≥ 2%', icon: TrendingUp, shortcut: 'Ctrl+1', group: 'Scanner' },
    { id: 'gappers_down', label: 'SC Gap Down', description: 'Gap down ≤ -2%', icon: TrendingDown, shortcut: 'Ctrl+2', group: 'Scanner' },
    { id: 'momentum_up', label: 'SC Momentum Alcista', description: 'Cambio ≥ 3%', icon: ArrowUp, shortcut: 'Ctrl+3', group: 'Scanner' },
    { id: 'momentum_down', label: 'SC Momentum Bajista', description: 'Cambio ≤ -3%', icon: ArrowDown, shortcut: 'Ctrl+4', group: 'Scanner' },
    { id: 'winners', label: 'SC Mayores Ganadores', description: 'Cambio ≥ 5%', icon: Trophy, shortcut: 'Ctrl+5', group: 'Scanner' },
    { id: 'losers', label: 'SC Mayores Perdedores', description: 'Cambio ≤ -5%', icon: AlertTriangle, shortcut: 'Ctrl+6', group: 'Scanner' },
    { id: 'new_highs', label: 'SC Nuevos Máximos', description: 'Máximos del día', icon: TrendingUp, group: 'Scanner' },
    { id: 'new_lows', label: 'SC Nuevos Mínimos', description: 'Mínimos del día', icon: TrendingDown, group: 'Scanner' },
    { id: 'anomalies', label: 'SC Anomalías', description: 'RVOL ≥ 3.0', icon: Zap, shortcut: 'Ctrl+7', group: 'Scanner' },
    { id: 'high_volume', label: 'SC Alto Volumen', description: 'RVOL ≥ 2.0', icon: BarChart3, group: 'Scanner' },
    { id: 'reversals', label: 'SC Reversals', description: 'Cambios de dirección', icon: ScanSearch, group: 'Scanner' },
];

export function CommandPalette({ open, onOpenChange, onSelectCategory, activeCategories = [], searchValue = '', onSearchChange }: CommandPaletteProps) {
    const search = searchValue.toLowerCase().trim();
    const setSearch = onSearchChange || (() => { });
    const { executeCommand } = useCommandExecutor();
    const preventCloseRef = useRef(false);

    // Detectar qué comandos mostrar basado en el texto escrito
    const hasScPrefix = search.startsWith('sc');
    const hasDtPrefix = search.startsWith('dt');
    const isEmpty = search === '';

    // Determinar qué comandos mostrar
    const showMainCommands = isEmpty || (!hasScPrefix && !hasDtPrefix);
    const showScannerCommands = hasScPrefix;
    const shouldExecuteDT = hasDtPrefix && search === 'dt';

    // Handler para seleccionar comandos (DEBE estar antes de los useEffect)
    const handleSelect = useCallback((value: string) => {
        const allCommands = [...MAIN_COMMANDS, ...SCANNER_COMMANDS];
        const command = allCommands.find(c => c.id === value);
        if (command?.disabled) return;

        // Comandos principales SC y DT son solo indicadores, no hacen nada
        if (value === 'sc') {
            // Prevenir que handleClickOutside cierre la paleta inmediatamente
            preventCloseRef.current = true;
            // Solo poner "SC " en el input para filtrar
            setSearch('SC ');
            // Resetear el flag después de un momento
            setTimeout(() => {
                preventCloseRef.current = false;
            }, 200);
            // NO cerrar la paleta, mantenerla abierta
            return;
        }

        // Comandos que abren ventanas flotantes (DT, Settings, SEC)
        if (['dt', 'settings', 'sec'].includes(value)) {
            executeCommand(value);
            setSearch('');
            onOpenChange(false);
            return;
        }

        // Todas las tablas del scanner (tienen prefijo SC en el label)
        if (command && command.group === 'Scanner') {
            if (onSelectCategory) {
                onSelectCategory(value);
            }
            setSearch('');
            onOpenChange(false);
        }
    }, [onSelectCategory, onOpenChange, executeCommand, setSearch]);

    // Cerrar al hacer clic fuera
    useEffect(() => {
        if (!open) return;

        const handleClickOutside = (e: MouseEvent) => {
            // Si acabamos de seleccionar SC, no cerrar
            if (preventCloseRef.current) {
                return;
            }

            const target = e.target as HTMLElement;
            // No cerrar si se hace clic en el input del navbar o en el command palette
            if (!target.closest('[cmdk-root]') && !target.closest('input[type="text"]')) {
                setSearch('');
                onOpenChange(false);
            }
        };

        // Pequeño delay para evitar cerrar inmediatamente al abrir
        const timeoutId = setTimeout(() => {
            document.addEventListener('click', handleClickOutside);
        }, 100);

        return () => {
            clearTimeout(timeoutId);
            document.removeEventListener('click', handleClickOutside);
        };
    }, [open, onOpenChange, setSearch]);

    // Cerrar con Escape
    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && open) {
                e.preventDefault();
                setSearch('');
                onOpenChange(false);
            }
        };

        document.addEventListener('keydown', down);
        return () => document.removeEventListener('keydown', down);
    }, [open, onOpenChange, setSearch]);

    // Shortcuts globales
    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (!(e.ctrlKey || e.metaKey)) return;

            const shortcuts: Record<string, string> = {
                '1': 'gappers_up',
                '2': 'gappers_down',
                '3': 'momentum_up',
                '4': 'momentum_down',
                '5': 'winners',
                '6': 'losers',
                '7': 'anomalies',
                'd': 'dilution-tracker',
                'D': 'dilution-tracker',
            };

            const commandId = shortcuts[e.key];
            if (commandId) {
                e.preventDefault();
                handleSelect(commandId);
            }
        };

        document.addEventListener('keydown', down);
        return () => document.removeEventListener('keydown', down);
    }, [handleSelect]);

    if (!open) return null;

    return (
        <>
            {/* Command Palette - Integrado debajo del navbar */}
            <div
                className="fixed left-4 top-16 animate-slideDown"
                style={{
                    zIndex: Z_INDEX.MODAL_BASE + 1,
                    maxHeight: 'calc(100vh - 80px)',
                    width: 'calc(33.333% - 2rem)', // 1/3 del ancho menos padding
                    minWidth: '400px',
                }}
            >
                <Command
                    className="border border-slate-300 bg-white shadow-lg overflow-hidden"
                    shouldFilter={true}
                >
                    {/* Input oculto para el filtrado de cmdk - sincronizado con el navbar */}
                    <Command.Input
                        value={search}
                        onValueChange={setSearch}
                        className="hidden"
                    />

                    {/* Header minimalista */}
                    <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                        <span className="text-xs text-slate-500 uppercase tracking-wide font-mono">
                            {hasScPrefix ? 'Scanner' : hasDtPrefix ? 'Dilution Tracker' : 'Commands'}
                        </span>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                            }}
                            className="text-slate-400 hover:text-slate-600"
                        >
                            <X className="w-3 h-3" />
                        </button>
                    </div>

                    <Command.List className="overflow-y-auto p-1" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                        <Command.Empty className="py-8 text-center text-xs text-slate-400">
                            No se encontraron comandos.
                        </Command.Empty>

                        {/* COMANDOS PRINCIPALES (sin prefijo o prefijo desconocido) */}
                        {showMainCommands && (
                            <Command.Group>
                                {MAIN_COMMANDS.map((cmd) => {
                                    return (
                                        <Command.Item
                                            key={cmd.id}
                                            value={cmd.id}
                                            keywords={[cmd.label, cmd.description, cmd.id]}
                                            onSelect={() => handleSelect(cmd.id)}
                                            className="flex items-center gap-2 px-2 py-1.5 cursor-pointer
                                                       hover:bg-slate-100 data-[selected=true]:bg-slate-100
                                                       transition-colors"
                                        >
                                            <span className="px-1.5 py-0.5 text-xs font-mono font-bold border border-slate-300 text-slate-700">
                                                {cmd.label}
                                            </span>
                                            <span className="text-xs text-slate-600">{cmd.description}</span>
                                        </Command.Item>
                                    );
                                })}
                            </Command.Group>
                        )}

                        {/* COMANDOS DEL SCANNER (prefijo SC) */}
                        {showScannerCommands && (
                            <Command.Group>
                                {SCANNER_COMMANDS.map((cmd) => {
                                    // Extraer solo el nombre sin el prefijo "SC "
                                    const cmdName = cmd.label.replace('SC ', '');

                                    return (
                                        <Command.Item
                                            key={cmd.id}
                                            value={cmd.id}
                                            keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                            onSelect={() => handleSelect(cmd.id)}
                                            className="flex items-center gap-2 px-2 py-1.5 cursor-pointer
                                                       hover:bg-slate-100 data-[selected=true]:bg-slate-100
                                                       transition-colors"
                                        >
                                            <span className="px-1.5 py-0.5 text-xs font-mono font-bold border border-slate-300 text-slate-700">
                                                {cmdName}
                                            </span>
                                            <span className="text-xs text-slate-600">{cmd.description}</span>
                                        </Command.Item>
                                    );
                                })}
                            </Command.Group>
                        )}
                    </Command.List>

                    {/* Footer minimalista */}
                    <div className="flex items-center justify-end px-3 py-1 border-t border-slate-200 bg-slate-50">
                        <span className="text-xs text-slate-400 font-mono">Ent</span>
                    </div>
                </Command>
            </div>
        </>
    );
}

