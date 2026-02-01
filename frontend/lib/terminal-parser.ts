/**
 * Terminal Parser
 * ================
 * Parsea comandos tipo terminal: TICKER COMMAND [ARGS]
 * 
 * Ejemplos:
 *   AAPL G     → Gráfico de Apple
 *   TSLA DT    → Dilution Tracker de Tesla
 *   NVDA FA    → Financial Analysis de NVIDIA
 *   AMZN SEC   → SEC Filings de Amazon
 *   MSFT NEWS  → Noticias de Microsoft
 */

// Regex para validar tickers (1-5 letras mayúsculas)
const TICKER_REGEX = /^[A-Z]{1,5}$/;

// Comandos disponibles que pueden aplicarse a un ticker
// Nota: Las descripciones son claves de traducción
export const TICKER_COMMANDS = {
    Q: {
        id: 'quote',
        label: 'Q',
        name: 'Quote',
        descriptionKey: 'terminalCommands.tickerCommands.Q.description',
        shortcut: 'Q'
    },
    G: {
        id: 'graph',
        label: 'G',
        name: 'Graph',
        descriptionKey: 'terminalCommands.tickerCommands.G.description',
        shortcut: 'G'
    },
    DT: {
        id: 'dilution-tracker',
        label: 'DT',
        name: 'Dilution Tracker',
        descriptionKey: 'terminalCommands.tickerCommands.DT.description',
        shortcut: 'Ctrl+D'
    },
    FA: {
        id: 'financials',
        label: 'FA',
        name: 'Financial Analysis',
        descriptionKey: 'terminalCommands.tickerCommands.FA.description',
        shortcut: null
    },
    SEC: {
        id: 'sec-filings',
        label: 'SEC',
        name: 'SEC Filings',
        descriptionKey: 'terminalCommands.tickerCommands.SEC.description',
        shortcut: 'Ctrl+F'
    },
    NEWS: {
        id: 'news',
        label: 'NEWS',
        name: 'News',
        descriptionKey: 'terminalCommands.tickerCommands.NEWS.description',
        shortcut: 'Ctrl+N'
    },
    PM: {
        id: 'patterns',
        label: 'PM',
        name: 'Pattern Matching',
        descriptionKey: 'terminalCommands.tickerCommands.PM.description',
        shortcut: 'Ctrl+P'
    },
    FAN: {
        id: 'fan',
        label: 'FAN',
        name: 'Financial Analyst',
        descriptionKey: 'terminalCommands.tickerCommands.FAN.description',
        shortcut: 'Ctrl+Shift+F'
    },
    HDS: {
        id: 'hds',
        label: 'HDS',
        name: 'Holders',
        descriptionKey: 'terminalCommands.tickerCommands.HDS.description',
        shortcut: null
    },
} as const;

export type TickerCommandKey = keyof typeof TICKER_COMMANDS;

// Global commands (no ticker)
// Nota: Las descripciones son claves de traducción
export const GLOBAL_COMMANDS = {
    SC: {
        id: 'sc',
        label: 'SC',
        name: 'Scanner',
        descriptionKey: 'terminalCommands.globalCommands.SC.description'
    },
    DT: {
        id: 'dt',
        label: 'DT',
        name: 'Dilution Tracker',
        descriptionKey: 'terminalCommands.globalCommands.DT.description',
        shortcut: 'Ctrl+D'
    },
    FA: {
        id: 'fa',
        label: 'FA',
        name: 'Financial Analysis',
        descriptionKey: 'terminalCommands.globalCommands.FA.description'
    },
    SEC: {
        id: 'sec',
        label: 'SEC',
        name: 'SEC Filings',
        descriptionKey: 'terminalCommands.globalCommands.SEC.description',
        shortcut: 'Ctrl+F'
    },
    NEWS: {
        id: 'news',
        label: 'NEWS',
        name: 'News',
        descriptionKey: 'terminalCommands.globalCommands.NEWS.description',
        shortcut: 'Ctrl+N'
    },
    INS: {
        id: 'ins',
        label: 'INS',
        name: 'Insights',
        descriptionKey: 'terminalCommands.globalCommands.INS.description'
    },
    ALERTS: {
        id: 'alerts',
        label: 'ALERTS',
        name: 'Catalyst Alerts',
        descriptionKey: 'terminalCommands.globalCommands.ALERTS.description'
    },
    IPO: {
        id: 'ipo',
        label: 'IPO',
        name: 'IPOs',
        descriptionKey: 'terminalCommands.globalCommands.IPO.description'
    },
    WL: {
        id: 'watchlist',
        label: 'WL',
        name: 'Quote Monitor',
        descriptionKey: 'terminalCommands.globalCommands.WL.description',
        shortcut: 'Ctrl+W'
    },
    PROFILE: {
        id: 'profile',
        label: 'PROFILE',
        name: 'Profile',
        descriptionKey: 'terminalCommands.globalCommands.PROFILE.description'
    },
    SET: {
        id: 'settings',
        label: 'SET',
        name: 'Settings',
        descriptionKey: 'terminalCommands.globalCommands.SET.description',
        shortcut: 'Ctrl+,'
    },
    FILTERS: {
        id: 'filters',
        label: 'FILTERS',
        name: 'Scanner Filters',
        descriptionKey: 'terminalCommands.globalCommands.FILTERS.description',
        shortcut: 'Ctrl+Shift+F'
    },
    HELP: {
        id: 'help',
        label: 'HELP',
        name: 'Help',
        descriptionKey: 'terminalCommands.globalCommands.HELP.description',
        shortcut: '?'
    },
    CHAT: {
        id: 'chat',
        label: 'CHAT',
        name: 'Community Chat',
        descriptionKey: 'terminalCommands.globalCommands.CHAT.description',
        shortcut: 'Ctrl+Shift+C'
    },
    NOTE: {
        id: 'notes',
        label: 'NOTE',
        name: 'Notes',
        descriptionKey: 'terminalCommands.globalCommands.NOTE.description',
        shortcut: 'Ctrl+Shift+N'
    },
    PM: {
        id: 'patterns',
        label: 'PM',
        name: 'Pattern Matching',
        descriptionKey: 'terminalCommands.globalCommands.PM.description',
        shortcut: 'Ctrl+P'
    },
    PRT: {
        id: 'prt',
        label: 'PRT',
        name: 'Pattern Real-Time',
        descriptionKey: 'terminalCommands.globalCommands.PRT.description',
        shortcut: 'Ctrl+Shift+P'
    },
    GR: {
        id: 'ratio',
        label: 'GR',
        name: 'Ratio Analysis',
        descriptionKey: 'terminalCommands.globalCommands.GR.description',
        shortcut: 'Ctrl+G'
    },
    SCREEN: {
        id: 'screener',
        label: 'SCREEN',
        name: 'Stock Screener',
        descriptionKey: 'terminalCommands.globalCommands.SCREEN.description',
        shortcut: 'Ctrl+Shift+S'
    },
    MP: {
        id: 'mp',
        label: 'MP',
        name: 'Historical Multiple Security',
        descriptionKey: 'terminalCommands.globalCommands.MP.description',
        shortcut: 'Ctrl+M'
    },
    INSIDER: {
        id: 'insider',
        label: 'INSIDER',
        name: 'Insider Trading',
        descriptionKey: 'terminalCommands.globalCommands.INSIDER.description',
        shortcut: 'Ctrl+I'
    },
    FAN: {
        id: 'fan',
        label: 'FAN',
        name: 'Financial Analyst',
        descriptionKey: 'terminalCommands.globalCommands.FAN.description',
        shortcut: 'Ctrl+Shift+F'
    },
    AI: {
        id: 'ai',
        label: 'AI',
        name: 'AI Agent',
        descriptionKey: 'terminalCommands.globalCommands.AI.description',
        shortcut: 'Ctrl+Shift+A'
    },
    ERN: {
        id: 'earnings',
        label: 'ERN',
        name: 'Earnings Calendar',
        descriptionKey: 'terminalCommands.globalCommands.ERN.description',
        shortcut: 'Ctrl+E'
    },
    PREDICT: {
        id: 'predict',
        label: 'PREDICT',
        name: 'Prediction Markets',
        descriptionKey: 'terminalCommands.globalCommands.PREDICT.description',
        shortcut: null
    },
    HM: {
        id: 'heatmap',
        label: 'HM',
        name: 'Market Heatmap',
        descriptionKey: 'terminalCommands.globalCommands.HM.description',
        shortcut: 'Ctrl+H'
    },
    SB: {
        id: 'sb',
        label: 'SB',
        name: 'Scan Builder',
        descriptionKey: 'terminalCommands.globalCommands.SB.description',
        shortcut: null
    },
    HDS: {
        id: 'hds',
        label: 'HDS',
        name: 'Holders',
        descriptionKey: 'terminalCommands.globalCommands.HDS.description',
        shortcut: null
    },
} as const;

export type GlobalCommandKey = keyof typeof GLOBAL_COMMANDS;

// Resultado del parser
export interface ParsedCommand {
    type: 'ticker-command' | 'global-command' | 'partial' | 'unknown';
    ticker?: string;
    command?: TickerCommandKey | GlobalCommandKey;
    raw: string;
    suggestions: CommandSuggestion[];
}

export interface CommandSuggestion {
    type: 'ticker-command' | 'global-command';
    label: string;
    description: string;
    descriptionKey?: string; // Clave de traducción
    fullCommand: string;
    shortcut?: string | null;
}

/**
 * Valida si un string parece un ticker válido
 */
export function isValidTicker(str: string): boolean {
    return TICKER_REGEX.test(str.toUpperCase());
}

/**
 * Parsea el input del terminal
 * @param input - El texto del comando a parsear
 * @param t - Función opcional de traducción (i18n)
 */
export function parseTerminalCommand(input: string, t?: (key: string) => string): ParsedCommand {
    const trimmed = input.trim().toUpperCase();
    const parts = trimmed.split(/\s+/);

    const result: ParsedCommand = {
        type: 'unknown',
        raw: input,
        suggestions: [],
    };

    // Helper para obtener descripción traducida
    const getDescription = (cmd: typeof TICKER_COMMANDS[keyof typeof TICKER_COMMANDS] | typeof GLOBAL_COMMANDS[keyof typeof GLOBAL_COMMANDS]): string => {
        if (t && 'descriptionKey' in cmd) {
            const translated = t(cmd.descriptionKey as string);
            return typeof translated === 'string' ? translated : (cmd.descriptionKey as string);
        }
        return '';
    };

    // Input vacío
    if (!trimmed) {
        result.type = 'partial';
        result.suggestions = [
            ...Object.values(TICKER_COMMANDS).map(cmd => ({
                type: 'ticker-command' as const,
                label: `TICKER ${cmd.label}`,
                description: getDescription(cmd),
                descriptionKey: cmd.descriptionKey,
                fullCommand: `TICKER ${cmd.label}`,
                shortcut: cmd.shortcut,
            })),
            ...Object.values(GLOBAL_COMMANDS).map(cmd => ({
                type: 'global-command' as const,
                label: cmd.label,
                description: getDescription(cmd),
                descriptionKey: cmd.descriptionKey,
                fullCommand: cmd.label,
                shortcut: 'shortcut' in cmd ? cmd.shortcut : undefined,
            })),
        ];
        return result;
    }

    const firstPart = parts[0];
    const secondPart = parts[1];

    // Verificar si es un comando global (SC, IPO, SET, HELP)
    if (firstPart in GLOBAL_COMMANDS) {
        result.type = 'global-command';
        result.command = firstPart as GlobalCommandKey;
        return result;
    }

    // Verificar si parece un ticker
    if (isValidTicker(firstPart)) {
        result.ticker = firstPart;

        // Si hay segundo argumento, verificar si es un comando válido
        if (secondPart) {
            if (secondPart in TICKER_COMMANDS) {
                result.type = 'ticker-command';
                result.command = secondPart as TickerCommandKey;
                return result;
            } else {
                // Comando no reconocido, sugerir comandos válidos
                result.type = 'partial';
                result.suggestions = Object.values(TICKER_COMMANDS)
                    .filter(cmd => cmd.label.startsWith(secondPart))
                    .map(cmd => ({
                        type: 'ticker-command' as const,
                        label: `${firstPart} ${cmd.label}`,
                        description: getDescription(cmd),
                        descriptionKey: cmd.descriptionKey,
                        fullCommand: `${firstPart} ${cmd.label}`,
                        shortcut: cmd.shortcut,
                    }));
                return result;
            }
        }

        // Solo ticker, sin comando - mostrar sugerencias de comandos
        result.type = 'partial';
        result.suggestions = Object.values(TICKER_COMMANDS).map(cmd => ({
            type: 'ticker-command' as const,
            label: `${firstPart} ${cmd.label}`,
            description: getDescription(cmd),
            descriptionKey: cmd.descriptionKey,
            fullCommand: `${firstPart} ${cmd.label}`,
            shortcut: cmd.shortcut,
        }));
        return result;
    }

    // No es ni comando global ni ticker válido - buscar en comandos
    result.type = 'partial';

    // Sugerir comandos globales que empiecen con lo escrito
    const matchingGlobal = Object.values(GLOBAL_COMMANDS)
        .filter(cmd => cmd.label.startsWith(firstPart) || cmd.name.toUpperCase().startsWith(firstPart));

    result.suggestions = matchingGlobal.map(cmd => ({
        type: 'global-command' as const,
        label: cmd.label,
        description: getDescription(cmd),
        descriptionKey: cmd.descriptionKey,
        fullCommand: cmd.label,
        shortcut: 'shortcut' in cmd ? cmd.shortcut : undefined,
    }));

    return result;
}

/**
 * Obtiene el comando completo dado el resultado parseado
 */
export function getTickerCommand(key: TickerCommandKey) {
    return TICKER_COMMANDS[key];
}

export function getGlobalCommand(key: GlobalCommandKey) {
    return GLOBAL_COMMANDS[key];
}

