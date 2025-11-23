'use client';

import { useEffect, useState, useCallback } from 'react';
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
    ChevronLeft,
    LayoutGrid,
} from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';

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

const SCANNER_COMMANDS: CommandItem[] = [
    { id: 'gappers_up', label: 'Gap Up', description: 'Gap up ≥ 2%', icon: TrendingUp, shortcut: 'Ctrl+1', group: 'Scanner' },
    { id: 'gappers_down', label: 'Gap Down', description: 'Gap down ≤ -2%', icon: TrendingDown, shortcut: 'Ctrl+2', group: 'Scanner' },
    { id: 'momentum_up', label: 'Momentum Alcista', description: 'Cambio ≥ 3%', icon: ArrowUp, shortcut: 'Ctrl+3', group: 'Scanner' },
    { id: 'momentum_down', label: 'Momentum Bajista', description: 'Cambio ≤ -3%', icon: ArrowDown, shortcut: 'Ctrl+4', group: 'Scanner' },
    { id: 'winners', label: 'Mayores Ganadores', description: 'Cambio ≥ 5%', icon: Trophy, shortcut: 'Ctrl+5', group: 'Scanner' },
    { id: 'losers', label: 'Mayores Perdedores', description: 'Cambio ≤ -5%', icon: AlertTriangle, shortcut: 'Ctrl+6', group: 'Scanner' },
    { id: 'new_highs', label: 'Nuevos Máximos', description: 'Máximos del día', icon: TrendingUp, group: 'Scanner' },
    { id: 'new_lows', label: 'Nuevos Mínimos', description: 'Mínimos del día', icon: TrendingDown, group: 'Scanner' },
    { id: 'anomalies', label: 'Anomalías', description: 'RVOL ≥ 3.0', icon: Zap, shortcut: 'Ctrl+7', group: 'Scanner' },
    { id: 'high_volume', label: 'Alto Volumen', description: 'RVOL ≥ 2.0', icon: BarChart3, group: 'Scanner' },
    { id: 'reversals', label: 'Reversals', description: 'Cambios de dirección', icon: ScanSearch, group: 'Scanner' },
];

// Comandos principales (Nivel 1)
const MAIN_COMMANDS: CommandItem[] = [
    { id: 'scanner', label: 'SC - Scanner', description: 'Abrir tablas del scanner', icon: LayoutGrid, group: 'Principal' },
    { id: 'dilution-tracker', label: 'DT - Dilution Tracker', description: 'Análisis de dilución', icon: BarChart3, shortcut: 'Ctrl+D', group: 'Principal' },
];

const OTHER_COMMANDS: CommandItem[] = [
    { id: 'analytics', label: 'Analytics', description: 'Próximamente', icon: TrendingUp, group: 'Herramientas', disabled: true },
    { id: 'alerts', label: 'Alertas', description: 'Próximamente', icon: Bell, group: 'Herramientas', disabled: true },
    { id: 'settings', label: 'Configuración', description: 'Próximamente', icon: Settings, group: 'Sistema', disabled: true },
];

export function CommandPalette({ open, onOpenChange, onSelectCategory, activeCategories = [], searchValue = '', onSearchChange }: CommandPaletteProps) {
    const search = searchValue;
    const setSearch = onSearchChange || (() => { });
    const { openWindow } = useFloatingWindow();
    
    // Estado para navegación jerárquica
    const [mode, setMode] = useState<'main' | 'scanner'>('main');

    // Handler para seleccionar comandos (DEBE estar antes de los useEffect)
    const handleSelect = useCallback((value: string) => {
        const allCommands = [...MAIN_COMMANDS, ...SCANNER_COMMANDS, ...OTHER_COMMANDS];
        const command = allCommands.find(c => c.id === value);
        if (command?.disabled) return;

        // Manejar comando scanner (cambiar a submenu)
        if (value === 'scanner') {
            setMode('scanner');
            setSearch('');
            return;
        }

        // Manejar dilution tracker
        if (value === 'dilution-tracker') {
            const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
            const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
            openWindow({
                title: 'Dilution Tracker',
                content: <DilutionTrackerContent />,
                width: 700,
                height: 600,
                x: screenWidth / 2 - 350,
                y: screenHeight / 2 - 300,
                minWidth: 500,
                minHeight: 400,
            });
            setSearch('');
            onOpenChange(false);
            setMode('main');
            return;
        }

        // Comandos sin implementar
        if (value === 'settings' || value === 'analytics' || value === 'alerts') {
            console.log('Comando:', value, '- Próximamente');
            setSearch('');
            onOpenChange(false);
            setMode('main');
            return;
        }

        // Categorías del scanner (solo en modo scanner)
        if (mode === 'scanner' && onSelectCategory) {
            onSelectCategory(value);
            setSearch('');
            onOpenChange(false);
            setMode('main');
        }
    }, [mode, onSelectCategory, onOpenChange, openWindow, setSearch]);

    // Resetear modo al cerrar
    useEffect(() => {
        if (!open) {
            setMode('main');
        }
    }, [open]);

    // Cerrar al hacer clic fuera
    useEffect(() => {
        if (!open) return;

        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            // No cerrar si se hace clic en el input del navbar o en el command palette
            if (!target.closest('[cmdk-root]') && !target.closest('input[type="text"]')) {
                setSearch('');
                onOpenChange(false);
                setMode('main');
            }
        };

        // Pequeño delay para evitar cerrar inmediatamente al abrir
        setTimeout(() => {
            document.addEventListener('click', handleClickOutside);
        }, 100);

        return () => {
            document.removeEventListener('click', handleClickOutside);
        };
    }, [open, onOpenChange, setSearch]);

    // Cerrar con Escape o volver atrás
    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && open) {
                e.preventDefault();
                if (mode === 'scanner') {
                    // Si estás en submenu, volver al principal
                    setMode('main');
                    setSearch('');
                } else {
                    // Si estás en principal, cerrar
                    setSearch('');
                    onOpenChange(false);
                    setMode('main');
                }
            }
        };

        document.addEventListener('keydown', down);
        return () => document.removeEventListener('keydown', down);
    }, [open, mode, onOpenChange, setSearch]);

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
                    className="border-2 border-blue-500 bg-white shadow-2xl overflow-hidden rounded-lg"
                    shouldFilter={true}
                >
                    {/* Input oculto para el filtrado de cmdk - sincronizado con el navbar */}
                    <Command.Input
                        value={search}
                        onValueChange={setSearch}
                        className="hidden"
                    />

                    {/* Header con breadcrumb */}
                    <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200 bg-gradient-to-r from-blue-50 to-white">
                        <div className="flex items-center gap-2">
                            {mode === 'scanner' && (
                                <button
                                    onClick={() => {
                                        setMode('main');
                                        setSearch('');
                                    }}
                                    className="p-1 hover:bg-slate-200 rounded transition-colors mr-1"
                                    title="Volver"
                                >
                                    <ChevronLeft className="w-4 h-4 text-slate-600" />
                                </button>
                            )}
                            <span className="text-slate-400 font-mono text-xs">$</span>
                            <h3 className="text-xs font-bold text-slate-700">
                                {mode === 'main' ? 'Comandos disponibles' : 'Scanner - Tablas'}
                            </h3>
                        </div>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                                setMode('main');
                            }}
                            className="p-1 hover:bg-slate-200 rounded transition-colors"
                        >
                            <X className="w-3.5 h-3.5 text-slate-600" />
                        </button>
                    </div>

                    <Command.List className="flex-1 overflow-y-auto p-2" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                        <Command.Empty className="py-12 text-center text-sm text-slate-500">
                            No se encontraron comandos.
                        </Command.Empty>

                        {/* MODO PRINCIPAL */}
                        {mode === 'main' && (
                            <Command.Group heading="COMANDOS PRINCIPALES">
                                {MAIN_COMMANDS.map((cmd) => {
                                    const Icon = cmd.icon;
                                    return (
                                        <Command.Item
                                            key={cmd.id}
                                            value={`${cmd.label} ${cmd.description} ${cmd.id}`}
                                            onSelect={() => handleSelect(cmd.id)}
                                            className="flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer
                                                       hover:bg-blue-50 data-[selected=true]:bg-blue-50
                                                       transition-colors group"
                                        >
                                            <Icon className="w-6 h-6 text-slate-600 group-hover:text-blue-600" />
                                            <div className="flex-1 min-w-0">
                                                <span className="text-base font-semibold text-slate-900">
                                                    {cmd.label}
                                                </span>
                                                <p className="text-sm text-slate-500 mt-0.5">{cmd.description}</p>
                                            </div>
                                            {cmd.shortcut && (
                                                <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-slate-500 bg-slate-100 rounded">
                                                    {cmd.shortcut}
                                                </kbd>
                                            )}
                                        </Command.Item>
                                    );
                                })}
                            </Command.Group>
                        )}

                        {/* MODO SCANNER */}
                        {mode === 'scanner' && (
                            <Command.Group heading="TABLAS DEL SCANNER">
                                {SCANNER_COMMANDS.map((cmd) => {
                                    const Icon = cmd.icon;
                                    const isActive = activeCategories.includes(cmd.id);

                                    return (
                                        <Command.Item
                                            key={cmd.id}
                                            value={`${cmd.label} ${cmd.description} ${cmd.id}`}
                                            onSelect={() => handleSelect(cmd.id)}
                                            className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer
                                                       hover:bg-blue-50 data-[selected=true]:bg-blue-50
                                                       transition-colors group"
                                        >
                                            <Icon className="w-5 h-5 text-slate-600 group-hover:text-blue-600" />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-medium text-slate-900">
                                                        {cmd.label}
                                                    </span>
                                                    {isActive && (
                                                        <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded font-semibold">
                                                            Activa
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-slate-500">{cmd.description}</p>
                                            </div>
                                            {cmd.shortcut && (
                                                <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-slate-500 bg-slate-100 rounded">
                                                    {cmd.shortcut}
                                                </kbd>
                                            )}
                                        </Command.Item>
                                    );
                                })}
                            </Command.Group>
                        )}
                    </Command.List>

                    {/* Footer con hints */}
                    <div className="flex items-center justify-between px-4 py-2 border-t border-slate-200 bg-gradient-to-r from-slate-50 to-white text-xs text-slate-500">
                        <span className="font-mono">↑↓ navegar • Enter seleccionar</span>
                        <span className="font-mono">
                            {mode === 'scanner' ? 'Esc volver' : 'Esc cerrar'}
                        </span>
                    </div>
                </Command>
            </div>
        </>
    );
}

