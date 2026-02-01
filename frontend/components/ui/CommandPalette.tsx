'use client';

import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
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
    DollarSign,
    Newspaper,
    Moon,
    Star,
} from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { MAIN_COMMANDS as COMMANDS_BASE } from '@/lib/commands';
import { useUserFilters } from '@/hooks/useUserFilters';

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
    isNew?: boolean;
};

// Comandos principales - extendidos desde la fuente centralizada
const MAIN_COMMANDS: CommandItem[] = COMMANDS_BASE.map(cmd => ({
    ...cmd,
    group: 'mainCommands',
}));

// Comandos del scanner (prefijo SC)
const SCANNER_COMMANDS: CommandItem[] = [
    { id: 'gappers_up', label: 'SC Gap Up', description: 'scanner.gapUpDescription', icon: TrendingUp, shortcut: 'Ctrl+1', group: 'scanner' },
    { id: 'gappers_down', label: 'SC Gap Down', description: 'scanner.gapDownDescription', icon: TrendingDown, shortcut: 'Ctrl+2', group: 'scanner' },
    { id: 'momentum_up', label: 'SC Momentum Up', description: 'scanner.momentumUpDescription', icon: ArrowUp, shortcut: 'Ctrl+3', group: 'scanner' },
    { id: 'momentum_down', label: 'SC Momentum Down', description: 'scanner.momentumDownDescription', icon: ArrowDown, shortcut: 'Ctrl+4', group: 'scanner' },
    { id: 'winners', label: 'SC Top Gainers', description: 'scanner.topGainersDescription', icon: Trophy, shortcut: 'Ctrl+5', group: 'scanner' },
    { id: 'losers', label: 'SC Top Losers', description: 'scanner.topLosersDescription', icon: AlertTriangle, shortcut: 'Ctrl+6', group: 'scanner' },
    { id: 'new_highs', label: 'SC New Highs', description: 'scanner.newHighsDescription', icon: TrendingUp, group: 'scanner' },
    { id: 'new_lows', label: 'SC New Lows', description: 'scanner.newLowsDescription', icon: TrendingDown, group: 'scanner' },
    { id: 'anomalies', label: 'SC Anomalies', description: 'scanner.anomaliesDescription', icon: Zap, shortcut: 'Ctrl+7', group: 'scanner' },
    { id: 'high_volume', label: 'SC High Volume', description: 'scanner.highVolumeDescription', icon: BarChart3, group: 'scanner' },
    { id: 'reversals', label: 'SC Reversals', description: 'scanner.reversalsDescription', icon: ScanSearch, group: 'scanner' },
    { id: 'post_market', label: 'SC Post-Market', description: 'scanner.postMarketDescription', icon: Moon, shortcut: 'Ctrl+9', group: 'scanner' },
    { id: 'with_news', label: 'SC With News', description: 'scanner.withNewsDescription', icon: Newspaper, shortcut: 'Ctrl+0', group: 'scanner' },
];

export function CommandPalette({ open, onOpenChange, onSelectCategory, activeCategories = [], searchValue = '', onSearchChange }: CommandPaletteProps) {
    const { t } = useTranslation();
    const search = searchValue.toLowerCase().trim();
    const setSearch = onSearchChange || (() => { });
    const { executeCommand, openUserScanTable } = useCommandExecutor();
    const preventCloseRef = useRef(false);

    // Cargar user scans
    const { filters: userScans, loading: userScansLoading, error: userScansError } = useUserFilters();

    // DEBUG - Log cada vez que cambia
    useEffect(() => {
        console.log('=== [CommandPalette] USER SCANS DEBUG ===');
        console.log('Loading:', userScansLoading);
        console.log('Error:', userScansError);
        console.log('Filters count:', userScans.length);
        console.log('Filters:', userScans);
    }, [userScans, userScansLoading, userScansError]);

    // Crear comandos dinámicos para TODOS los user scans
    const userScanCommands: CommandItem[] = useMemo(() => {
        return userScans.map(scan => ({
            id: `user_scan_${scan.id}`,
            label: `SC ${scan.name}`,
            description: scan.enabled ? `${Object.keys(scan.parameters || {}).length} filters` : '(disabled)',
            icon: Star,
            group: 'user_scanner',
            disabled: !scan.enabled,
        }));
    }, [userScans]);

    // Detectar qué comandos mostrar basado en el texto escrito
    const hasScPrefix = search.startsWith('sc');
    const hasDtPrefix = search.startsWith('dt');
    const isEmpty = search === '';

    // Determinar qué comandos mostrar
    const showMainCommands = isEmpty || (!hasScPrefix && !hasDtPrefix);
    const showScannerCommands = hasScPrefix;
    const shouldExecuteDT = hasDtPrefix && search === 'dt';

    // Handler para seleccionar comandos
    const handleSelect = useCallback((value: string) => {
        const allCommands = [...MAIN_COMMANDS, ...SCANNER_COMMANDS, ...userScanCommands];
        const command = allCommands.find(c => c.id === value);
        if (command?.disabled) return;

        // Comandos principales SC son solo indicadores - expande el menú
        if (value === 'sc') {
            preventCloseRef.current = true;
            setSearch('SC ');
            setTimeout(() => {
                preventCloseRef.current = false;
            }, 200);
            return;
        }

        // Comandos que abren ventanas flotantes (principales)
        if (['dt', 'settings', 'sec', 'news', 'alerts', 'fa', 'ipo', 'profile', 'filters', 'sb', 'watchlist', 'chat', 'notes', 'patterns', 'ratio', 'screener', 'mp', 'insider', 'earnings', 'heatmap', 'predict', 'ai', 'ins', 'fan', 'hds'].includes(value)) {
            executeCommand(value);
            setSearch('');
            onOpenChange(false);
            return;
        }

        // User scans personalizados
        if (value.startsWith('user_scan_')) {
            const scanId = parseInt(value.replace('user_scan_', ''));
            const scan = userScans.find(s => s.id === scanId);
            if (scan) {
                openUserScanTable(scan);
                setSearch('');
                onOpenChange(false);
            }
            return;
        }

        // Todas las tablas del scanner (group === 'scanner')
        if (command && command.group === 'scanner') {
            executeCommand(value);
            if (onSelectCategory) {
                onSelectCategory(value);
            }
            setSearch('');
            onOpenChange(false);
        }
    }, [onSelectCategory, onOpenChange, executeCommand, setSearch, userScanCommands, userScans, openUserScanTable]);

    // Cerrar al hacer clic fuera
    useEffect(() => {
        if (!open) return;

        const handleClickOutside = (e: MouseEvent) => {
            if (preventCloseRef.current) return;

            const target = e.target as HTMLElement;
            if (!target.closest('[cmdk-root]') && !target.closest('input[type="text"]')) {
                setSearch('');
                onOpenChange(false);
            }
        };

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
                '9': 'post_market',
                '0': 'with_news',
                'd': 'dilution-tracker',
                'D': 'dilution-tracker',
                'h': 'heatmap',
                'H': 'heatmap',
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
            <div
                className="fixed left-4 top-12 animate-slideDown"
                style={{
                    zIndex: Z_INDEX.MODAL_BASE + 1,
                    maxHeight: 'calc(100vh - 80px)',
                    width: 'calc(33.333% - 2rem)',
                    minWidth: '400px',
                }}
            >
                <Command
                    className="border border-slate-300 bg-white shadow-lg overflow-hidden"
                    shouldFilter={true}
                >
                    <Command.Input
                        value={search}
                        onValueChange={setSearch}
                        className="hidden"
                    />

                    <div className="flex items-center justify-between px-2 py-1 border-b border-slate-200 bg-slate-50">
                        <span className="text-[10px] text-slate-500 uppercase tracking-wide font-mono">
                            {hasScPrefix ? t('commandPalette.scanner') : hasDtPrefix ? t('commandPalette.dilutionTracker') : t('commandPalette.commands')}
                        </span>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                            }}
                            className="text-slate-400 hover:text-slate-600"
                        >
                            <X className="w-2.5 h-2.5" />
                        </button>
                    </div>

                    <Command.List className="overflow-y-auto p-0.5" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                        <Command.Empty className="py-4 text-center text-[10px] text-slate-400">
                            {t('commands.noCommandsFound')}
                        </Command.Empty>

                        {/* COMANDOS PRINCIPALES */}
                        {showMainCommands && (
                            <Command.Group>
                                {MAIN_COMMANDS.map((cmd) => (
                                    <Command.Item
                                        key={cmd.id}
                                        value={cmd.id}
                                        keywords={[cmd.label, cmd.description, cmd.id]}
                                        onSelect={() => handleSelect(cmd.id)}
                                        className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-slate-100 data-[selected=true]:bg-slate-100 transition-colors"
                                    >
                                        <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-slate-300 text-slate-700">
                                            {cmd.label}
                                        </span>
                                        {cmd.isNew && (
                                            <span className="px-1 py-0.5 text-[8px] font-bold bg-blue-600 text-white rounded">
                                                NEW
                                            </span>
                                        )}
                                        <span className="text-[10px] text-slate-500">{t(cmd.description)}</span>
                                    </Command.Item>
                                ))}
                            </Command.Group>
                        )}

                        {/* COMANDOS DEL SCANNER */}
                        {showScannerCommands && (
                            <>
                                {/* System Scans */}
                                <Command.Group heading={<span className="text-[9px] text-slate-400 uppercase px-1">System</span>}>
                                    {SCANNER_COMMANDS.map((cmd) => {
                                        const cmdName = cmd.label.replace('SC ', '');
                                        return (
                                            <Command.Item
                                                key={cmd.id}
                                                value={cmd.id}
                                                keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                                onSelect={() => handleSelect(cmd.id)}
                                                className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-slate-100 data-[selected=true]:bg-slate-100 transition-colors"
                                            >
                                                <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-slate-300 text-slate-700">
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-slate-500">{t(cmd.description)}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>

                                {/* User Scans */}
                                <Command.Group heading={<span className="text-[9px] text-slate-400 uppercase px-1">My Scans {userScansLoading && '(loading...)'} {userScansError && `(error: ${userScansError})`}</span>}>
                                    {userScanCommands.length === 0 && !userScansLoading && (
                                        <div className="px-2 py-1 text-[10px] text-slate-400">No custom scans yet. Create one with SB command.</div>
                                    )}
                                    {userScanCommands.map((cmd) => {
                                        const cmdName = cmd.label.replace('SC ', '');
                                        const isDisabled = cmd.disabled;
                                        return (
                                            <Command.Item
                                                key={cmd.id}
                                                value={cmd.id}
                                                keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                                onSelect={() => !isDisabled && handleSelect(cmd.id)}
                                                disabled={isDisabled}
                                                className={`flex items-center gap-1.5 px-1.5 py-1 cursor-pointer transition-colors ${isDisabled ? 'opacity-50' : 'hover:bg-slate-100 data-[selected=true]:bg-slate-100'}`}
                                            >
                                                <Star className={`w-3 h-3 ${isDisabled ? 'text-slate-400' : 'text-amber-500'}`} />
                                                <span className={`px-1 py-0.5 text-[10px] font-mono font-bold border ${isDisabled ? 'border-slate-300 text-slate-500 bg-slate-50' : 'border-amber-300 text-amber-700 bg-amber-50'}`}>
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-slate-500">{cmd.description}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>
                            </>
                        )}
                    </Command.List>

                    <div className="flex items-center justify-end px-2 py-0.5 border-t border-slate-200 bg-slate-50">
                        <span className="text-[9px] text-slate-400 font-mono">↵</span>
                    </div>
                </Command>
            </div>
        </>
    );
}
