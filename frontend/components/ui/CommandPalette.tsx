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
    Activity,
    CircleStop,
    GitBranch,
    Target,
    Layers,
    CheckCircle,
    Clock,
    Square,
    LineChart,
} from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { MAIN_COMMANDS as COMMANDS_BASE, SYSTEM_EVENT_CATEGORIES } from '@/lib/commands';
import { useUserFilters } from '@/hooks/useUserFilters';
import { useAlertStrategies } from '@/hooks/useAlertStrategies';

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

// Iconos para categorías de eventos (estrategias pre-built)
const EVENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    'evt_high_vol_runners': Activity,
    'evt_parabolic_movers': TrendingUp,
    'evt_gap_fade': TrendingDown,
    'evt_gap_recovery': TrendingUp,
    'evt_vwap_reclaim': Zap,
    'evt_ema_trend_break': GitBranch,
    'evt_halt_momentum': CircleStop,
    'evt_dip_buy': Target,
    'evt_confirmed_longs': CheckCircle,
    'evt_confirmed_shorts': TrendingDown,
    'evt_squeeze_play': Activity,
    'evt_institutional_bid': DollarSign,
    'evt_reversal_play': ScanSearch,
    'evt_breakdown_short': TrendingDown,
    'evt_macd_momentum': LineChart,
    'evt_stoch_reversal': ScanSearch,
    'evt_orb_play': Clock,
    'evt_consolidation_break': Square,
    'evt_all': BarChart3,
};

// Comandos de eventos (prefijo EVN)
const EVENT_COMMANDS: CommandItem[] = SYSTEM_EVENT_CATEGORIES.map(cat => ({
    id: cat.id,
    label: `EVN ${cat.label}`,
    description: cat.description,
    icon: EVENT_ICONS[cat.id] || Activity,
    group: 'events',
}));

export function CommandPalette({ open, onOpenChange, onSelectCategory, activeCategories = [], searchValue = '', onSearchChange }: CommandPaletteProps) {
    const { t } = useTranslation();
    const search = searchValue.toLowerCase().trim();
    const setSearch = onSearchChange || (() => { });
    const { executeCommand, openUserScanTable, openUserStrategyTable } = useCommandExecutor();
    const preventCloseRef = useRef(false);

    // Cargar user scans
    const { filters: userScans, loading: userScansLoading, error: userScansError } = useUserFilters();

    // Cargar user alert strategies
    const { strategies: userStrategies, loading: userStrategiesLoading } = useAlertStrategies();

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

    // Crear comandos dinámicos para user strategies
    const userStrategyCommands: CommandItem[] = useMemo(() => {
        return userStrategies.map(s => ({
            id: `user_strategy_${s.id}`,
            label: `EVN ${s.name}`,
            description: `${s.eventTypes.length} alerts · ${s.category || 'custom'}`,
            icon: Star,
            group: 'user_strategy',
        }));
    }, [userStrategies]);

    // Detectar qué comandos mostrar basado en el texto escrito
    const hasScPrefix = search.startsWith('sc');
    const hasDtPrefix = search.startsWith('dt');
    const hasEvnPrefix = search.startsWith('evn');
    const isEmpty = search === '';

    // Determinar qué comandos mostrar
    const showMainCommands = isEmpty || (!hasScPrefix && !hasDtPrefix && !hasEvnPrefix);
    const showScannerCommands = hasScPrefix;
    const showEventCommands = hasEvnPrefix;
    const shouldExecuteDT = hasDtPrefix && search === 'dt';

    // Handler para seleccionar comandos
    const handleSelect = useCallback((value: string) => {
        const allCommands = [...MAIN_COMMANDS, ...SCANNER_COMMANDS, ...EVENT_COMMANDS, ...userScanCommands, ...userStrategyCommands];
        const command = allCommands.find(c => c.id === value);
        if (command?.disabled) return;

        // SC expande el menú del scanner
        if (value === 'sc') {
            preventCloseRef.current = true;
            setSearch('SC ');
            setTimeout(() => {
                preventCloseRef.current = false;
            }, 200);
            return;
        }

        // Comando EVN expande el menú de eventos
        if (value === 'evn') {
            preventCloseRef.current = true;
            setSearch('EVN ');
            setTimeout(() => {
                preventCloseRef.current = false;
            }, 200);
            return;
        }

        // Comandos que abren ventanas flotantes (principales)
        if (['dt', 'settings', 'sec', 'news', 'alerts', 'fa', 'ipo', 'profile', 'watchlist', 'chat', 'notes', 'patterns', 'ratio', 'screener', 'mp', 'insider', 'earnings', 'heatmap', 'predict', 'ai', 'ins', 'fan', 'hds', 'pulse', 'rtn', 'backtest', 'bt', 'opn'].includes(value)) {
            executeCommand(value);
            setSearch('');
            onOpenChange(false);
            return;
        }

        // User alert strategies
        if (value.startsWith('user_strategy_')) {
            const strategyId = parseInt(value.replace('user_strategy_', ''));
            const strategy = userStrategies.find(s => s.id === strategyId);
            if (strategy) {
                openUserStrategyTable({
                    id: strategy.id,
                    name: strategy.name,
                    eventTypes: strategy.eventTypes,
                    filters: strategy.filters as Record<string, any>,
                });
                setSearch('');
                onOpenChange(false);
            }
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
            return;
        }

        // Todas las tablas de eventos (group === 'events')
        if (command && command.group === 'events') {
            executeCommand(value);
            setSearch('');
            onOpenChange(false);
            return;
        }
    }, [onSelectCategory, onOpenChange, executeCommand, setSearch, userScanCommands, userScans, openUserScanTable, userStrategyCommands, userStrategies, openUserStrategyTable]);

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
                    className="border border-border bg-surface shadow-lg overflow-hidden"
                    shouldFilter={!hasEvnPrefix && !hasScPrefix}
                >
                    <Command.Input
                        value={search}
                        onValueChange={setSearch}
                        className="hidden"
                    />

                    <div className="flex items-center justify-between px-2 py-1 border-b border-border bg-surface-hover">
                        <span className="text-[10px] text-muted-fg uppercase tracking-wide font-mono">
                            {hasScPrefix ? t('commandPalette.scanner') : hasEvnPrefix ? t('commandPalette.events') : hasDtPrefix ? t('commandPalette.dilutionTracker') : t('commandPalette.commands')}
                        </span>
                        <button
                            onClick={() => {
                                onOpenChange(false);
                                setSearch('');
                            }}
                            className="text-muted-fg hover:text-foreground"
                        >
                            <X className="w-2.5 h-2.5" />
                        </button>
                    </div>

                    <Command.List className="overflow-y-auto p-0.5" style={{ maxHeight: 'calc(100vh - 200px)' }}>
                        <Command.Empty className="py-4 text-center text-[10px] text-muted-fg">
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
                                        className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-surface-hover data-[selected=true]:bg-surface-hover transition-colors"
                                    >
                                        <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-border text-foreground">
                                            {cmd.label}
                                        </span>
                                        {cmd.isNew && (
                                            <span className="px-1 py-0.5 text-[8px] font-bold bg-primary text-white rounded">
                                                NEW
                                            </span>
                                        )}
                                        <span className="text-[10px] text-muted-fg">{t(cmd.description)}</span>
                                    </Command.Item>
                                ))}
                            </Command.Group>
                        )}

                        {/* COMANDOS DEL SCANNER */}
                        {showScannerCommands && (
                            <>
                                {/* System Scans */}
                                <Command.Group heading={<span className="text-[9px] text-muted-fg uppercase px-1">System</span>}>
                                    {SCANNER_COMMANDS.map((cmd) => {
                                        const cmdName = cmd.label.replace('SC ', '');
                                        return (
                                            <Command.Item
                                                key={cmd.id}
                                                value={cmd.id}
                                                keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                                onSelect={() => handleSelect(cmd.id)}
                                                className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-surface-hover data-[selected=true]:bg-surface-hover transition-colors"
                                            >
                                                <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-border text-foreground">
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-muted-fg">{t(cmd.description)}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>

                                {/* User Scans */}
                                <Command.Group heading={<span className="text-[9px] text-muted-fg uppercase px-1">My Scans {userScansLoading && '(loading...)'} {userScansError && `(error: ${userScansError})`}</span>}>
                                    {userScanCommands.length === 0 && !userScansLoading && (
                                        <div className="px-2 py-1 text-[10px] text-muted-fg">No custom scans yet. Create one with SB command.</div>
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
                                                className={`flex items-center gap-1.5 px-1.5 py-1 cursor-pointer transition-colors ${isDisabled ? 'opacity-50' : 'hover:bg-surface-hover data-[selected=true]:bg-surface-hover'}`}
                                            >
                                                <Star className={`w-3 h-3 ${isDisabled ? 'text-muted-fg' : 'text-amber-500'}`} />
                                                <span className={`px-1 py-0.5 text-[10px] font-mono font-bold border ${isDisabled ? 'border-border text-muted-fg bg-surface-hover' : 'border-amber-500/40 text-amber-700 dark:text-amber-400 bg-amber-500/10'}`}>
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-muted-fg">{cmd.description}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>
                            </>
                        )}

                        {/* COMANDOS DE EVENTOS */}
                        {showEventCommands && (
                            <>
                                {/* Pre-built Strategies */}
                                <Command.Group heading={<span className="text-[9px] text-muted-fg uppercase px-1">Strategies</span>}>
                                    {EVENT_COMMANDS.map((cmd) => {
                                        const cmdName = cmd.label.replace('EVN ', '');
                                        const IconComponent = cmd.icon;
                                        return (
                                            <Command.Item
                                                key={cmd.id}
                                                value={cmd.id}
                                                keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                                onSelect={() => handleSelect(cmd.id)}
                                                className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-surface-hover data-[selected=true]:bg-surface-hover transition-colors"
                                            >
                                                <IconComponent className="w-3 h-3 text-primary" />
                                                <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-primary text-primary bg-primary/10">
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-muted-fg">{cmd.description}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>

                                {/* User Strategies */}
                                <Command.Group heading={<span className="text-[9px] text-muted-fg uppercase px-1">My Strategies {userStrategiesLoading && '(loading...)'}</span>}>
                                    {userStrategyCommands.length === 0 && !userStrategiesLoading && (
                                        <div className="px-2 py-1 text-[10px] text-muted-fg">No strategies yet. Create one with BUILD command.</div>
                                    )}
                                    {userStrategyCommands.map((cmd) => {
                                        const cmdName = cmd.label.replace('EVN ', '');
                                        return (
                                            <Command.Item
                                                key={cmd.id}
                                                value={cmd.id}
                                                keywords={[cmd.label, cmdName, cmd.description, cmd.id]}
                                                onSelect={() => handleSelect(cmd.id)}
                                                className="flex items-center gap-1.5 px-1.5 py-1 cursor-pointer hover:bg-surface-hover data-[selected=true]:bg-surface-hover transition-colors"
                                            >
                                                <Star className="w-3 h-3 text-emerald-500" />
                                                <span className="px-1 py-0.5 text-[10px] font-mono font-bold border border-emerald-500/40 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10">
                                                    {cmdName}
                                                </span>
                                                <span className="text-[10px] text-muted-fg">{cmd.description}</span>
                                            </Command.Item>
                                        );
                                    })}
                                </Command.Group>
                            </>
                        )}
                    </Command.List>

                    <div className="flex items-center justify-end px-2 py-0.5 border-t border-border bg-surface-hover">
                        <span className="text-[9px] text-muted-fg font-mono">↵</span>
                    </div>
                </Command>
            </div>
        </>
    );
}
