'use client';

import { memo, useState, useCallback, useRef, useEffect } from 'react';
import ReactFlow, {
    Node,
    Edge,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    Position,
    Handle,
    NodeProps,
    BackgroundVariant,
    MiniMap,
    EdgeProps,
    getBezierPath,
    BaseEdge,
    addEdge,
    Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { motion, AnimatePresence } from 'framer-motion';
import {
    X,
    FileText,
    Code2,
    Terminal,
    Table2,
    SlidersHorizontal,
    Maximize2,
} from 'lucide-react';

// =============================================================================
// API CONFIG
// =============================================================================

// Use same URL as useAIAgent for consistency
const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL || 'https://agent.tradeul.com';

// Map frontend node types to backend node types (NEW MODULAR ARCHITECTURE)
const ICON_TO_BACKEND_TYPE: Record<string, string> = {
    // SOURCE nodes
    market_scanner: 'market_scanner',
    anomaly_scanner: 'anomaly_scanner',
    volume_surge: 'volume_surge',
    top_movers: 'top_movers',

    // TRANSFORM nodes
    smart_filter: 'smart_filter',
    sort: 'sort',
    limit: 'limit',
    merge: 'merge',
    ranking: 'ranking',
    sector_classifier: 'sector_classifier',

    // ENRICH nodes
    quick_news: 'quick_news',
    deep_research: 'deep_research',
    news_enricher: 'news_enricher',
    narrative_classifier: 'narrative_classifier',
    risk_scorer: 'risk_scorer',
    sentiment_scorer: 'sentiment_scorer',

    // ACTION nodes
    results: 'results',
    save_signal: 'save_signal',
    export: 'export',
    alert: 'alert',

    // Legacy aliases
    scanner: 'market_scanner',
    sectors: 'sector_classifier',
    market_pulse: 'market_scanner',
    sector_flow: 'sector_classifier',
    display: 'results',
};

// =============================================================================
// TYPES
// =============================================================================

type NodeCategory = 'source' | 'analysis' | 'enrichment' | 'ai' | 'output';
type ContentView = 'code' | 'data' | 'text';
type EditorView = 'builder' | 'report';

interface WorkflowReport {
    executedAt: Date;
    totalTime: number;
    nodeResults: Record<string, {
        nodeId: string;
        status: 'success' | 'error';
        executionTime: number;
        data: unknown;
        title: string;
        icon: string;
    }>;
}

// Node configuration types
interface ScannerConfig {
    limit: number;
    filter_type?: 'all' | 'gainers' | 'losers' | 'volume' | 'premarket' | 'postmarket';
    min_volume?: number;
    min_price?: number;
    include_premarket?: boolean;
}

interface HistoricalConfig {
    date: 'today' | 'yesterday' | string;
    start_hour?: number;
    end_hour?: number;
    symbols?: string[];
}

interface TopMoversConfig {
    date: 'today' | 'yesterday' | string;
    direction: 'up' | 'down';
    limit: number;
    min_volume: number;
}

interface SectorsConfig {
    date: 'today' | 'yesterday';
    max_sectors: number;
}

interface ResearchConfig {
    ticker?: string;
    query?: string;
}

type NodeConfig = ScannerConfig | HistoricalConfig | TopMoversConfig | SectorsConfig | ResearchConfig | Record<string, unknown>;

interface WorkflowNodeData {
    step: number;
    title: string;
    subtitle: string;
    category: NodeCategory;
    icon: string;
    code: string;
    config: NodeConfig;
    data?: { columns: string[]; rows: string[][] };
    description?: string;
    status: 'idle' | 'running' | 'complete' | 'error';
    executionTime?: number;
}

// Default configs for each node type (NEW MODULAR ARCHITECTURE)
const DEFAULT_CONFIGS: Record<string, NodeConfig> = {
    // === SOURCE NODES ===
    market_scanner: {
        limit: 100,
        min_price: 1,
        min_volume: 100000,
    } as ScannerConfig,

    anomaly_scanner: {
        limit: 50,
        min_rvol: 2.0,
        min_change_pct: 5.0,
    },

    volume_surge: {
        limit: 50,
        min_rvol: 3.0,
        min_volume: 500000,
    },

    top_movers: {
        direction: 'up',
        limit: 50,
        min_volume: 100000,
        date: 'today',
    },

    // === TRANSFORM NODES ===
    smart_filter: {
        conditions: [
            { column: 'change_percent', operator: '>=', value: 3 },
        ],
        logic: 'AND',
    },

    sort: {
        columns: ['change_percent'],
        ascending: false,
    },

    limit: {
        limit: 20,
    },

    merge: {
        mode: 'concat',
        dedupe_column: 'symbol',
    },

    ranking: {
        factors: [
            { column: 'change_percent', weight: 0.5 },
            { column: 'rvol', weight: 0.5 },
        ],
        limit: 20,
    },

    sector_classifier: {
        max_sectors: 15,
    },

    // === ENRICH NODES ===
    quick_news: {
        ticker: '',  // From input or specified
        limit: 5,
    },

    deep_research: {
        ticker: '',  // From input or specified
        query: '',
    },

    news_enricher: {
        max_tickers: 20,
        news_limit: 3,
    },

    narrative_classifier: {
        max_tickers: 15,
    },

    risk_scorer: {
        max_tickers: 20,
        risk_window_days: 7,
    },

    sentiment_scorer: {
        max_tickers: 20,
    },

    // === ACTION NODES ===
    results: {
        max_rows: 100,
    },

    save_signal: {
        signal_name: 'Custom Signal',
        ttl_hours: 24,
        max_signals: 20,
    },

    export: {
        format: 'csv',
        filename: 'workflow_export',
    },

    alert: {
        alert_title: 'Workflow Alert',
        min_results: 1,
    },

};

// =============================================================================
// UNIFIED BLUE THEME - Futuristic glow effect
// =============================================================================

const FUTURISTIC_BLUE = {
    primary: '#3b82f6',
    glow: '#60a5fa',
    dark: '#1e40af',
    muted: '#93c5fd',
};

// =============================================================================
// ANIMATED EDGE - Smooth bezier with traveling dot
// =============================================================================

const SmoothEdge = memo(({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style = {},
}: EdgeProps) => {
    const [edgePath] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
    });

    const edgeColor = (style?.stroke as string) || '#3b82f6';

    return (
        <>
            {/* Main line - thin and elegant */}
            <BaseEdge
                id={id}
                path={edgePath}
                style={{
                    stroke: edgeColor,
                    strokeWidth: 1.5,
                    strokeLinecap: 'round',
                    opacity: 0.6,
                }}
            />

            {/* Traveling dot */}
            <circle r="3" fill={edgeColor}>
                <animateMotion dur="2s" repeatCount="indefinite" path={edgePath} />
            </circle>
            <circle r="2" fill={edgeColor} opacity="0.4">
                <animateMotion dur="2s" repeatCount="indefinite" path={edgePath} begin="0.7s" />
            </circle>
        </>
    );
});

SmoothEdge.displayName = 'SmoothEdge';

// =============================================================================
// RICH NODE - 5 Animated Tabs (Info, Code, Terminal, Data, Config)
// =============================================================================

type NodeTab = 'info' | 'code' | 'terminal' | 'data' | 'config';

const formatNum = (n: number | string | undefined): string => {
    if (n === undefined || n === null) return '-';
    const num = typeof n === 'string' ? parseFloat(n) : n;
    if (isNaN(num)) return String(n);
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toFixed(0);
};

const DashboardNode = memo(({ data, selected }: NodeProps<WorkflowNodeData>) => {
    const [activeTab, setActiveTab] = useState<NodeTab>('info');
    const config = data.config || {};
    const hasData = data.data && data.data.rows && data.data.rows.length > 0;

    // Debug: log when data changes
    useEffect(() => {
        if (data.icon === 'display') {
        }
    }, [data.data, hasData, data.icon]);

    // Tab definitions with minimalist icons (no color)
    const tabs: { id: NodeTab; icon: React.ReactNode; tip: string }[] = [
        { id: 'info', icon: <FileText className="w-3 h-3" />, tip: 'Description' },
        { id: 'code', icon: <Code2 className="w-3 h-3" />, tip: 'Code' },
        { id: 'terminal', icon: <Terminal className="w-3 h-3" />, tip: 'Terminal' },
        { id: 'data', icon: <Table2 className="w-3 h-3" />, tip: 'Output' },
        { id: 'config', icon: <SlidersHorizontal className="w-3 h-3" />, tip: 'Config' },
    ];

    // Rich descriptions for each node type
    const getDescription = () => {
        const c = config;
        switch (data.icon) {
            // NEW CONCEPTUAL NODES (v2)
            case 'market_pulse':
                return `Step ${data.step}: Market Pulse

Real-time snapshot of market activity.

Scans ${formatNum((c as ScannerConfig).limit || 200)}+ active tickers with current prices, volume, and bid/ask data.

Filters applied:
• Min price: $${(c as ScannerConfig).min_price || 1}
• Min volume: ${formatNum((c as ScannerConfig).min_volume || 50000)}
• Includes premarket: ${(c as ScannerConfig).include_premarket ? 'Yes' : 'No'}

Output: Universe of active tickers with real-time metrics.`;

            case 'volume_surge':
                return `Step ${data.step}: Volume Surge Detector

Identifies stocks with unusual volume activity.

Compares current volume to ${(c as Record<string, number>).lookback_days || 20}-day average. Stocks with RVOL (Relative Volume) above ${(c as Record<string, number>).min_rvol || 2.0}x are flagged.

Why this matters:
• Unusual volume often precedes price moves
• Institutional activity leaves volume footprints
• Early signal before news breaks

Output: Tickers with abnormal volume + RVOL score.`;

            case 'momentum_wave':
                return `Step ${data.step}: Momentum Wave

Detects sustained directional price movement.

Finds ${(c as Record<string, string>).direction === 'down' ? 'declining' : 'advancing'} stocks with >${(c as Record<string, number>).min_change || 5}% change and volume confirmation.

Criteria:
• Direction: ${(c as Record<string, string>).direction || 'up'}
• Min change: ${(c as Record<string, number>).min_change || 5}%
• Min volume: ${formatNum((c as Record<string, number>).min_volume || 100000)}

Output: Top movers with momentum score.`;

            case 'sector_flow':
                return `Step ${data.step}: Sector Flow Analysis

AI-powered thematic sector classification.

Groups tickers into dynamic sectors based on current market narratives. Unlike static classifications, we detect:

• Nuclear / Uranium plays
• AI Infrastructure
• Solar / Clean Energy
• Biotech themes
• Emerging narratives

Max sectors: ${(c as Record<string, number>).max_sectors || 15}

Output: Sector performance with rotation signals.`;

            case 'news_validator':
                return `Step ${data.step}: News Validator

Validates signals against news and events.

Cross-references tickers with recent news to understand the "why" behind movements.

Checks:
• Breaking news (last ${(c as Record<string, number>).max_news_age_hours || 24}h)
• Earnings dates / FDA decisions
• Analyst ratings changes
• Social sentiment

Output: Narrative type + sentiment score + risk flags.`;

            case 'results':
                return `Step ${data.step}: Results

Displays the final output from the pipeline.

Shows data from the previous node in a clean table format. This is where you review the signals before taking action.`;

            // LEGACY NODES (backward compatibility)
            case 'scanner':
                return `Step ${data.step}: ${data.title}

Legacy scanner node. Use Market Pulse instead.

Scans ${formatNum((c as ScannerConfig).limit || 200)}+ active tickers from the market.

Output: A ranked list of active tickers with price, volume, and change data.`;

            case 'top_movers':
                return `Step ${data.step}: ${data.title}

Legacy top movers. Use Momentum Wave instead.

Top ${(c as TopMoversConfig).direction === 'down' ? 'losers' : 'gainers'} from ${(c as TopMoversConfig).date || 'yesterday'}.

Output: Top ${formatNum((c as TopMoversConfig).limit || 50)} stocks ranked by % change.`;

            case 'sectors':
                return `Step ${data.step}: ${data.title}

Legacy sectors. Use Sector Flow instead.

Output: Up to ${(c as SectorsConfig).max_sectors || 20} synthetic sectors.`;

            case 'news_validator':
            case 'research':
                return `Step ${data.step}: ${data.title}

Validates signals with news and events using AI research.

For ${(c as ResearchConfig).ticker || 'each ticker from input'}, we analyze:
• Breaking news and catalysts
• Social sentiment signals
• Upcoming binary events (earnings, FDA)
• Analyst rating changes

Risk flags:
• Earnings within 7 days
• Pending FDA decisions
• Lockup expirations
• Macro sensitivity

Output: Validation score + narrative type + risk flags.`;

            case 'results':
            case 'display':
                return `Step ${data.step}: ${data.title}

Displays the final output from connected nodes.

This is a pass-through visualization node that renders the data from the previous step in a clean table format.`;

            default:
                return `Step ${data.step}: ${data.title}\n\nConfigure this node to define its behavior.`;
        }
    };

    // More complete code examples
    const getCode = () => {
        const c = config;
        switch (data.icon) {
            case 'scanner':
                return `def fetch_scanner_data(config):
    """Fetch real-time scanner data."""
    scanner = get_market_snapshot(
        filter_type="${(c as ScannerConfig).filter_type || 'all'}",
        limit=${(c as ScannerConfig).limit || 200}${(c as ScannerConfig).min_volume ? `,\n        min_volume=${(c as ScannerConfig).min_volume}` : ''}
    )
    return scanner.sort_by("change_pct")`;

            case 'top_movers':
                return `def get_top_movers_data(config):
    """Get top movers from historical."""
    movers = get_top_movers(
        date="${(c as TopMoversConfig).date || 'yesterday'}",
        direction="${(c as TopMoversConfig).direction || 'up'}",
        limit=${(c as TopMoversConfig).limit || 50},
        min_volume=${(c as TopMoversConfig).min_volume || 100000}
    )
    return movers`;

            case 'sectors':
                return `def classify_sectors(tickers):
    """Classify into synthetic sectors."""
    sectors = classify_synthetic_sectors(
        tickers=tickers,
        date="${(c as SectorsConfig).date || 'today'}",
        max_sectors=${(c as SectorsConfig).max_sectors || 20}
    )
    # Calculate avg performance
    for s in sectors:
        s.avg_change = mean(s.tickers)
    return sectors.sort_by("avg_change")`;

            case 'news_validator':
            case 'research':
                return `async def news_validator(tickers):
    """Validate signals with news & events."""
    results = []
    for ticker in tickers[:10]:
        research = await research_ticker(
            symbol=ticker,
            query="why is it moving? any upcoming events?"
        )
        results.append({
            "ticker": ticker,
            "narrative": classify_narrative(research),
            "risk_flags": detect_binary_events(ticker),
            "sentiment": research.sentiment_score
        })
    return sort_by_conviction(results)`;

            case 'results':
            case 'display':
                return `def display_results(data):
    """Render final output."""
    if data.type == "dataframe":
        return render_table(data)
    return render_json(data)`;

            default:
                return `# ${data.title}\n# Configure this node`;
        }
    };

    // Terminal output (theme claro)
    const getTerminal = () => {
        if (data.status === 'complete') {
            return `[${new Date().toLocaleTimeString()}] Execution completed
✓ Finished in ${((data.executionTime || 0) / 1000).toFixed(2)}s
${hasData ? `✓ Returned ${data.data?.rows.length || 0} rows` : '✓ Success'}
○ Ready for next step`;
        }
        if (data.status === 'running') {
            return `[${new Date().toLocaleTimeString()}] Executing...
⏳ Processing ${data.title}
   Fetching data...`;
        }
        if (data.status === 'error') {
            return `[${new Date().toLocaleTimeString()}] Error
✗ Execution failed
   Check configuration`;
        }
        return `○ Waiting to execute
   Connect inputs and run workflow`;
    };

    // Example data for each node type (shown when no real data)
    const getExampleData = (): { columns: string[]; rows: string[][] } => {
        switch (data.icon) {
            case 'scanner':
                return {
                    columns: ['Symbol', 'Price', 'Change', 'Volume'],
                    rows: [
                        ['NVDA', '$142.50', '+8.3%', '45M'],
                        ['SMCI', '$89.20', '+12.4%', '28M'],
                        ['AMD', '$156.80', '+5.6%', '32M'],
                        ['TSLA', '$248.50', '+3.2%', '18M'],
                        ['AAPL', '$185.20', '+1.8%', '42M'],
                    ]
                };
            case 'top_movers':
                return {
                    columns: ['Symbol', 'Change', 'Volume', 'High'],
                    rows: [
                        ['GP', '+49.8%', '76.8M', '$1.45'],
                        ['LRHC', '+18.3%', '80.3M', '$1.02'],
                        ['BLZR', '+12.1%', '5.2M', '$11.20'],
                        ['FEED', '+8.7%', '3.1M', '$2.50'],
                        ['ANPA', '+6.4%', '1.8M', '$83.00'],
                    ]
                };
            case 'sectors':
                return {
                    columns: ['Sector', 'Tickers', 'Avg %', 'Top'],
                    rows: [
                        ['Nuclear', '8', '+7.8%', 'CEG, VST'],
                        ['AI Infra', '12', '+5.4%', 'NVDA, SMCI'],
                        ['Solar', '6', '+4.2%', 'ENPH, FSLR'],
                        ['Biotech', '15', '+3.1%', 'MRNA, REGN'],
                        ['EV', '9', '+2.8%', 'TSLA, RIVN'],
                    ]
                };
            case 'historical':
                return {
                    columns: ['Time', 'Open', 'High', 'Low', 'Close'],
                    rows: [
                        ['09:30', '$142.00', '$142.50', '$141.80', '$142.30'],
                        ['09:31', '$142.30', '$142.80', '$142.20', '$142.60'],
                        ['09:32', '$142.60', '$143.00', '$142.50', '$142.90'],
                    ]
                };
            case 'news_validator':
            case 'research':
                return {
                    columns: ['Ticker', 'Narrative', 'Risk', 'Score'],
                    rows: [
                        ['NVDA', 'CATALYST_DRIVEN', 'None', '+0.92'],
                        ['AMD', 'EARNINGS_PLAY', 'ER 7d', '+0.65'],
                        ['SMCI', 'SILENT_ACCUMULATION', 'None', '+0.78'],
                    ]
                };
            case 'results':
            case 'display':
                return {
                    columns: ['Output', 'Value', 'Type'],
                    rows: [
                        ['Data', 'From input', 'Table'],
                        ['Rows', '50', 'Count'],
                        ['Status', 'Ready', 'Info'],
                    ]
                };
            default:
                return { columns: ['Data'], rows: [['No preview']] };
        }
    };

    // Config fields
    const renderConfig = () => {
        switch (data.icon) {
            case 'scanner': {
                const c = config as ScannerConfig;
                return (<>
                    <div className="flex justify-between"><span className="text-slate-400">Limit</span><span>{formatNum(c.limit || 200)}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Filter</span><span>{c.filter_type || 'all'}</span></div>
                    {c.min_volume && <div className="flex justify-between"><span className="text-slate-400">Min Vol</span><span>{formatNum(c.min_volume)}</span></div>}
                </>);
            }
            case 'top_movers': {
                const c = config as TopMoversConfig;
                return (<>
                    <div className="flex justify-between"><span className="text-slate-400">Date</span><span>{c.date || 'yesterday'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Dir</span><span className={c.direction === 'down' ? 'text-red-500' : 'text-emerald-600'}>{c.direction || 'up'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Limit</span><span>{formatNum(c.limit || 50)}</span></div>
                </>);
            }
            case 'sectors': {
                const c = config as SectorsConfig;
                return (<>
                    <div className="flex justify-between"><span className="text-slate-400">Date</span><span>{c.date || 'today'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Max</span><span>{c.max_sectors || 20}</span></div>
                </>);
            }
            case 'historical': {
                const c = config as HistoricalConfig;
                return (<>
                    <div className="flex justify-between"><span className="text-slate-400">Date</span><span>{c.date || 'yesterday'}</span></div>
                    {c.start_hour && <div className="flex justify-between"><span className="text-slate-400">Hours</span><span>{c.start_hour}-{c.end_hour || 20}</span></div>}
                </>);
            }
            case 'news_validator':
            case 'research': {
                const c = config as ResearchConfig;
                return (<>
                    <div className="flex justify-between"><span className="text-slate-400">Ticker</span><span>{c.ticker || 'from input'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Risk check</span><span>Yes</span></div>
                </>);
            }
            case 'results':
            case 'display':
                return <span className="text-slate-400">Shows output from previous node</span>;
            default:
                return <span className="text-slate-400">No config</span>;
        }
    };

    return (
        <>
            <Handle type="target" position={Position.Left} className="!w-2.5 !h-2.5 !bg-blue-500 !border-2 !border-white" />

            {/* Node - Animated neon border */}
            <motion.div
                className="w-[220px] rounded-lg overflow-hidden bg-white border-2"
                animate={{
                    borderColor: selected
                        ? ['#3b82f6', '#60a5fa', '#93c5fd', '#60a5fa', '#3b82f6']
                        : data.status === 'running'
                            ? ['#93c5fd', '#3b82f6', '#60a5fa', '#3b82f6', '#93c5fd']
                            : '#e2e8f0',
                    boxShadow: selected
                        ? ['0 0 10px #3b82f650', '0 0 18px #60a5fa60', '0 0 10px #3b82f650']
                        : data.status === 'running'
                            ? ['0 0 6px #3b82f640', '0 0 14px #60a5fa50', '0 0 6px #3b82f640']
                            : '0 1px 2px rgba(0,0,0,0.05)'
                }}
                transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
            >
                {/* Header */}
                <div className="px-2 py-1.5 border-b border-slate-100 flex items-center gap-1.5">
                    <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1 py-0.5 rounded">{data.step}</span>
                    <h3 className="flex-1 text-[11px] font-medium text-slate-700 truncate">{data.title}</h3>
                    <div className={`w-2 h-2 rounded-full ${data.status === 'complete' ? 'bg-emerald-500' :
                        data.status === 'running' ? 'bg-blue-500 animate-pulse' :
                            data.status === 'error' ? 'bg-red-500' : 'bg-slate-300'
                        }`} />
                </div>

                {/* Tabs - Minimalist icons, no color */}
                <div className="flex items-center px-1.5 py-0.5 border-b border-slate-100 bg-slate-50/50">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            title={tab.tip}
                            className={`p-1 rounded transition-all ${activeTab === tab.id
                                ? 'bg-slate-200 text-slate-700'
                                : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                                }`}
                        >
                            {tab.icon}
                        </button>
                    ))}
                    <div className="flex-1" />
                    {data.status === 'complete' && (
                        <span className="text-[9px] font-mono text-slate-400">{((data.executionTime || 0) / 1000).toFixed(1)}s</span>
                    )}
                </div>

                {/* Animated Content */}
                <div className="min-h-[50px] max-h-[80px] overflow-y-auto">
                    <AnimatePresence mode="wait">
                        {activeTab === 'info' && (
                            <motion.div
                                key="info"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 8 }}
                                transition={{ duration: 0.12 }}
                                className="p-2 text-[9px] text-slate-600 leading-relaxed whitespace-pre-line"
                            >
                                {getDescription()}
                            </motion.div>
                        )}

                        {activeTab === 'code' && (
                            <motion.div
                                key="code"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 8 }}
                                transition={{ duration: 0.12 }}
                                className="p-1.5 font-mono text-[8px] leading-relaxed bg-slate-50"
                            >
                                {getCode().split('\n').map((line, i) => (
                                    <div key={i} className="flex">
                                        <span className="w-3 text-slate-300 select-none text-right mr-2">{i + 1}</span>
                                        <span className={
                                            line.includes('#') ? 'text-slate-400' :
                                                line.includes('=') ? 'text-blue-600' :
                                                    line.includes('"') ? 'text-emerald-600' :
                                                        'text-slate-600'
                                        }>{line || ' '}</span>
                                    </div>
                                ))}
                            </motion.div>
                        )}

                        {activeTab === 'terminal' && (
                            <motion.div
                                key="terminal"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 8 }}
                                transition={{ duration: 0.12 }}
                                className="p-2 font-mono text-[8px] leading-relaxed bg-slate-50 text-slate-600 whitespace-pre-line"
                            >
                                {getTerminal()}
                            </motion.div>
                        )}

                        {activeTab === 'data' && (
                            <motion.div
                                key="data"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 8 }}
                                transition={{ duration: 0.12 }}
                                className="p-1.5"
                            >
                                {(() => {
                                    const displayData = hasData && data.data ? data.data : getExampleData();
                                    const isExample = !hasData;
                                    return (
                                        <>
                                            {isExample && <p className="text-[7px] text-slate-400 mb-0.5 italic">Example:</p>}
                                            <table className="w-full text-[7px]">
                                                <thead>
                                                    <tr className="border-b border-slate-200">
                                                        {displayData.columns.slice(0, 5).map((col, i) => (
                                                            <th key={i} className="px-1 py-1 text-left text-slate-500 font-medium uppercase">{col}</th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {displayData.rows.slice(0, 5).map((row, i) => (
                                                        <tr key={i} className={`border-b border-slate-50 ${isExample ? 'opacity-60' : ''}`}>
                                                            {row.slice(0, 5).map((cell, j) => (
                                                                <td key={j} className={`px-1 py-0.5 ${cell.includes('+') ? 'text-emerald-600' :
                                                                    cell.includes('-') && !cell.includes('$') ? 'text-red-500' :
                                                                        j === 0 ? 'text-slate-700 font-medium' : 'text-slate-500'
                                                                    }`}>{cell}</td>
                                                            ))}
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </>
                                    );
                                })()}
                            </motion.div>
                        )}

                        {activeTab === 'config' && (
                            <motion.div
                                key="config"
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 8 }}
                                transition={{ duration: 0.12 }}
                                className="p-2 text-[9px] space-y-0.5"
                            >
                                {renderConfig()}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </motion.div>

            <Handle type="source" position={Position.Right} className="!w-2.5 !h-2.5 !bg-blue-500 !border-2 !border-white" />
        </>
    );
});

DashboardNode.displayName = 'DashboardNode';

// =============================================================================
// INITIAL DATA - Empty canvas, user builds from scratch
// =============================================================================

const initialNodes: Node<WorkflowNodeData>[] = [];
const initialEdges: Edge[] = [];

// =============================================================================
// NODE PALETTE - Dark theme
// =============================================================================

// Only include nodes that have backend tools implemented
const NODE_TEMPLATES = [
    // === SOURCE NODES ===
    { type: 'market_scanner', label: 'Market Scanner', category: 'source' as NodeCategory },
    { type: 'anomaly_scanner', label: 'Anomaly Scanner', category: 'source' as NodeCategory },
    { type: 'volume_surge', label: 'Volume Surge', category: 'source' as NodeCategory },
    { type: 'top_movers', label: 'Top Movers', category: 'source' as NodeCategory },

    // === TRANSFORM NODES ===
    { type: 'smart_filter', label: 'Smart Filter', category: 'analysis' as NodeCategory },
    { type: 'sort', label: 'Sort', category: 'analysis' as NodeCategory },
    { type: 'limit', label: 'Limit', category: 'analysis' as NodeCategory },
    { type: 'ranking', label: 'Ranking', category: 'analysis' as NodeCategory },
    { type: 'sector_classifier', label: 'Sector Classifier', category: 'ai' as NodeCategory },

    // === ENRICH NODES ===
    { type: 'quick_news', label: 'Quick News', category: 'enrichment' as NodeCategory },
    { type: 'deep_research', label: 'Deep Research', category: 'ai' as NodeCategory },
    { type: 'news_enricher', label: 'News Enricher', category: 'enrichment' as NodeCategory },
    { type: 'narrative_classifier', label: 'Narrative Classifier', category: 'ai' as NodeCategory },
    { type: 'risk_scorer', label: 'Risk Scorer', category: 'enrichment' as NodeCategory },
    { type: 'sentiment_scorer', label: 'Sentiment Scorer', category: 'enrichment' as NodeCategory },

    // === ACTION NODES ===
    { type: 'results', label: 'Results', category: 'output' as NodeCategory },
    { type: 'save_signal', label: 'Save Signal', category: 'output' as NodeCategory },
    { type: 'export', label: 'Export', category: 'output' as NodeCategory },
    { type: 'alert', label: 'Alert', category: 'output' as NodeCategory },
];

interface NodePaletteProps {
    isOpen: boolean;
    onClose: () => void;
    onAddNode: (type: string) => void;
}

const NodePalette = memo(({ isOpen, onClose, onAddNode }: NodePaletteProps) => {
    if (!isOpen) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute left-3 top-14 w-44 bg-white rounded-lg border border-slate-200 shadow-lg z-50 overflow-hidden"
        >
            <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-slate-100">
                <span className="text-[10px] font-medium text-slate-600">Add Node</span>
                <button onClick={onClose} className="p-0.5 hover:bg-slate-100 rounded transition-colors">
                    <X className="w-3 h-3 text-slate-400" />
                </button>
            </div>

            <div className="p-1 max-h-80 overflow-y-auto">
                {NODE_TEMPLATES.map((template) => (
                    <button
                        key={template.type}
                        onClick={() => { onAddNode(template.type); onClose(); }}
                        className="w-full flex items-center px-2 py-1 rounded hover:bg-blue-50 border border-transparent hover:border-blue-200 transition-all text-left group"
                    >
                        <span className="text-[10px] text-slate-500 group-hover:text-blue-600 transition-colors">{template.label}</span>
                    </button>
                ))}
            </div>
        </motion.div>
    );
});

NodePalette.displayName = 'NodePalette';

// =============================================================================
// NODE CONFIGURATION PANEL
// =============================================================================

interface NodeConfigPanelProps {
    node: Node<WorkflowNodeData> | null;
    onClose: () => void;
    onUpdate: (nodeId: string, config: NodeConfig) => void;
}

const NodeConfigPanel = memo(({ node, onClose, onUpdate }: NodeConfigPanelProps) => {
    if (!node) return null;

    const nodeType = node.data.icon;
    const config = node.data.config || DEFAULT_CONFIGS[nodeType] || {};

    const handleChange = (key: string, value: unknown) => {
        onUpdate(node.id, { ...config, [key]: value });
    };

    const renderFields = () => {
        const inputClass = "w-full px-2 py-1 text-[10px] border border-slate-200 rounded focus:border-blue-400 focus:outline-none";
        const labelClass = "text-[9px] text-slate-500 uppercase";
        const hintClass = "text-[8px] text-slate-400";

        switch (nodeType) {
            // === SOURCE NODES ===
            case 'market_scanner':
            case 'market_pulse':
            case 'scanner':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Limit</label>
                            <input type="number" min={1} max={1000} value={(config as any).limit || 100}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 100)}
                                className={inputClass} />
                            <p className={hintClass}>1-1000 tickers</p>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Volume</label>
                            <input type="number" min={0} value={(config as any).min_volume || ''}
                                placeholder="Any" onChange={(e) => handleChange('min_volume', e.target.value ? parseInt(e.target.value) : undefined)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Price ($)</label>
                            <input type="number" min={0} step={0.5} value={(config as any).min_price || ''}
                                placeholder="Any" onChange={(e) => handleChange('min_price', e.target.value ? parseFloat(e.target.value) : undefined)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'anomaly_scanner':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Limit</label>
                            <input type="number" min={1} max={500} value={(config as any).limit || 50}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 50)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Relative Volume</label>
                            <input type="number" min={1} step={0.5} value={(config as any).min_rvol || 2.0}
                                onChange={(e) => handleChange('min_rvol', parseFloat(e.target.value) || 2.0)}
                                className={inputClass} />
                            <p className={hintClass}>e.g., 2.0 = 2x average volume</p>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Change %</label>
                            <input type="number" min={0} step={1} value={(config as any).min_change_pct || 5}
                                onChange={(e) => handleChange('min_change_pct', parseFloat(e.target.value) || 5)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'volume_surge':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Limit</label>
                            <input type="number" min={1} max={500} value={(config as any).limit || 50}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 50)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Relative Volume</label>
                            <input type="number" min={1} step={0.5} value={(config as any).min_rvol || 3.0}
                                onChange={(e) => handleChange('min_rvol', parseFloat(e.target.value) || 3.0)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Volume</label>
                            <input type="number" min={0} value={(config as any).min_volume || 500000}
                                onChange={(e) => handleChange('min_volume', parseInt(e.target.value) || 500000)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'top_movers':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Direction</label>
                            <select value={(config as any).direction || 'up'}
                                onChange={(e) => handleChange('direction', e.target.value)}
                                className={inputClass}>
                                <option value="up">Gainers</option>
                                <option value="down">Losers</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Limit</label>
                            <input type="number" min={1} max={500} value={(config as any).limit || 50}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 50)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Volume</label>
                            <input type="number" min={0} value={(config as any).min_volume || 100000}
                                onChange={(e) => handleChange('min_volume', parseInt(e.target.value) || 100000)}
                                className={inputClass} />
                        </div>
                    </>
                );

            // === TRANSFORM NODES ===
            case 'smart_filter':
                return (
                    <>
                        <p className={hintClass + " mb-2"}>Filter conditions (JSON format)</p>
                        <div className="space-y-1">
                            <label className={labelClass}>Column</label>
                            <select value={(config as any).conditions?.[0]?.column || 'change_percent'}
                                onChange={(e) => handleChange('conditions', [{ ...(config as any).conditions?.[0], column: e.target.value }])}
                                className={inputClass}>
                                <option value="change_percent">Change %</option>
                                <option value="rvol">Relative Volume</option>
                                <option value="volume_today">Volume</option>
                                <option value="price">Price</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Operator</label>
                            <select value={(config as any).conditions?.[0]?.operator || '>='}
                                onChange={(e) => handleChange('conditions', [{ ...(config as any).conditions?.[0], operator: e.target.value }])}
                                className={inputClass}>
                                <option value=">=">≥ (greater or equal)</option>
                                <option value=">">{">"} (greater)</option>
                                <option value="<=">≤ (less or equal)</option>
                                <option value="<">{"<"} (less)</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Value</label>
                            <input type="number" step="any" value={(config as any).conditions?.[0]?.value || 3}
                                onChange={(e) => handleChange('conditions', [{ ...(config as any).conditions?.[0], value: parseFloat(e.target.value) }])}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'sort':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Sort By</label>
                            <select value={(config as any).columns?.[0] || 'change_percent'}
                                onChange={(e) => handleChange('columns', [e.target.value])}
                                className={inputClass}>
                                <option value="change_percent">Change %</option>
                                <option value="rvol">Relative Volume</option>
                                <option value="volume_today">Volume</option>
                                <option value="price">Price</option>
                                <option value="rank_score">Rank Score</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Order</label>
                            <select value={(config as any).ascending ? 'asc' : 'desc'}
                                onChange={(e) => handleChange('ascending', e.target.value === 'asc')}
                                className={inputClass}>
                                <option value="desc">Descending (highest first)</option>
                                <option value="asc">Ascending (lowest first)</option>
                            </select>
                        </div>
                    </>
                );

            case 'limit':
                return (
                    <div className="space-y-1">
                        <label className={labelClass}>Max Results</label>
                        <input type="number" min={1} max={500} value={(config as any).limit || 20}
                            onChange={(e) => handleChange('limit', parseInt(e.target.value) || 20)}
                            className={inputClass} />
                        <p className={hintClass}>Take top N results</p>
                    </div>
                );

            case 'ranking':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Rank By</label>
                            <select value={(config as any).factors?.[0]?.column || 'change_percent'}
                                onChange={(e) => handleChange('factors', [{ column: e.target.value, weight: 1.0 }])}
                                className={inputClass}>
                                <option value="change_percent">Change %</option>
                                <option value="rvol">Relative Volume</option>
                                <option value="volume_today">Volume</option>
                                <option value="anomaly_score">Anomaly Score</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Top N</label>
                            <input type="number" min={1} max={100} value={(config as any).limit || 20}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 20)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'sector_classifier':
            case 'sector_flow':
            case 'sectors':
                return (
                    <div className="space-y-1">
                        <label className={labelClass}>Max Sectors</label>
                        <input type="number" min={5} max={30} value={(config as any).max_sectors || 15}
                            onChange={(e) => handleChange('max_sectors', parseInt(e.target.value) || 15)}
                            className={inputClass} />
                        <p className={hintClass}>AI classifies into thematic sectors</p>
                    </div>
                );

            // === ENRICH NODES ===
            case 'quick_news':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Ticker</label>
                            <input type="text" value={(config as any).ticker || ''}
                                placeholder="From input"
                                onChange={(e) => handleChange('ticker', e.target.value.toUpperCase())}
                                className={inputClass} />
                            <p className={hintClass}>Leave empty to use input ticker</p>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Max Articles</label>
                            <input type="number" min={1} max={10} value={(config as any).limit || 5}
                                onChange={(e) => handleChange('limit', parseInt(e.target.value) || 5)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'deep_research':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Ticker</label>
                            <input type="text" value={(config as any).ticker || ''}
                                placeholder="From input"
                                onChange={(e) => handleChange('ticker', e.target.value.toUpperCase())}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Query</label>
                            <input type="text" value={(config as any).query || ''}
                                placeholder="Why is it moving?"
                                onChange={(e) => handleChange('query', e.target.value)}
                                className={inputClass} />
                            <p className={hintClass}>Grok AI deep analysis (60-90s)</p>
                        </div>
                    </>
                );

            case 'news_enricher':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Max Tickers</label>
                            <input type="number" min={1} max={50} value={(config as any).max_tickers || 20}
                                onChange={(e) => handleChange('max_tickers', parseInt(e.target.value) || 20)}
                                className={inputClass} />
                            <p className={hintClass}>News lookup per ticker (slow)</p>
                        </div>
                    </>
                );

            case 'narrative_classifier':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Max Tickers</label>
                            <input type="number" min={1} max={30} value={(config as any).max_tickers || 15}
                                onChange={(e) => handleChange('max_tickers', parseInt(e.target.value) || 15)}
                                className={inputClass} />
                            <p className={hintClass}>AI classifies: CATALYST, MACRO, SILENT, EARNINGS</p>
                        </div>
                    </>
                );

            case 'risk_scorer':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Max Tickers</label>
                            <input type="number" min={1} max={30} value={(config as any).max_tickers || 20}
                                onChange={(e) => handleChange('max_tickers', parseInt(e.target.value) || 20)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Risk Window (days)</label>
                            <input type="number" min={1} max={30} value={(config as any).risk_window_days || 7}
                                onChange={(e) => handleChange('risk_window_days', parseInt(e.target.value) || 7)}
                                className={inputClass} />
                            <p className={hintClass}>Look for events in next N days</p>
                        </div>
                    </>
                );

            case 'sentiment_scorer':
                return (
                    <div className="space-y-1">
                        <label className={labelClass}>Max Tickers</label>
                        <input type="number" min={1} max={30} value={(config as any).max_tickers || 20}
                            onChange={(e) => handleChange('max_tickers', parseInt(e.target.value) || 20)}
                            className={inputClass} />
                        <p className={hintClass}>Scores: BULLISH, BEARISH, NEUTRAL</p>
                    </div>
                );

            // === ACTION NODES ===
            case 'results':
            case 'display':
                return (
                    <div className="space-y-1">
                        <label className={labelClass}>Max Rows</label>
                        <input type="number" min={10} max={500} value={(config as any).max_rows || 100}
                            onChange={(e) => handleChange('max_rows', parseInt(e.target.value) || 100)}
                            className={inputClass} />
                    </div>
                );

            case 'save_signal':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Signal Name</label>
                            <input type="text" value={(config as any).signal_name || 'Custom Signal'}
                                onChange={(e) => handleChange('signal_name', e.target.value)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>TTL (hours)</label>
                            <input type="number" min={1} max={168} value={(config as any).ttl_hours || 24}
                                onChange={(e) => handleChange('ttl_hours', parseInt(e.target.value) || 24)}
                                className={inputClass} />
                            <p className={hintClass}>Signal expires after N hours</p>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Max Signals</label>
                            <input type="number" min={1} max={100} value={(config as any).max_signals || 20}
                                onChange={(e) => handleChange('max_signals', parseInt(e.target.value) || 20)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'export':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Format</label>
                            <select value={(config as any).format || 'csv'}
                                onChange={(e) => handleChange('format', e.target.value)}
                                className={inputClass}>
                                <option value="csv">CSV</option>
                                <option value="json">JSON</option>
                            </select>
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Filename</label>
                            <input type="text" value={(config as any).filename || 'workflow_export'}
                                onChange={(e) => handleChange('filename', e.target.value)}
                                className={inputClass} />
                        </div>
                    </>
                );

            case 'alert':
                return (
                    <>
                        <div className="space-y-1">
                            <label className={labelClass}>Alert Title</label>
                            <input type="text" value={(config as any).alert_title || 'Workflow Alert'}
                                onChange={(e) => handleChange('alert_title', e.target.value)}
                                className={inputClass} />
                        </div>
                        <div className="space-y-1">
                            <label className={labelClass}>Min Results to Trigger</label>
                            <input type="number" min={1} max={100} value={(config as any).min_results || 1}
                                onChange={(e) => handleChange('min_results', parseInt(e.target.value) || 1)}
                                className={inputClass} />
                        </div>
                    </>
                );

            default:
                return <p className="text-[10px] text-slate-400">Select a node to configure</p>;
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="absolute right-3 top-14 w-52 bg-white rounded-lg border border-slate-200 shadow-lg z-50 overflow-hidden"
        >
            <div className="flex items-center justify-between px-2.5 py-2 border-b border-slate-100 bg-gradient-to-r from-blue-50 to-transparent">
                <span className="text-[10px] font-medium text-slate-700">{node.data.title}</span>
                <button onClick={onClose} className="p-0.5 hover:bg-slate-100 rounded transition-colors">
                    <X className="w-3 h-3 text-slate-400" />
                </button>
            </div>

            <div className="p-2.5 space-y-2.5">
                {renderFields()}
            </div>
        </motion.div>
    );
});

NodeConfigPanel.displayName = 'NodeConfigPanel';

// =============================================================================
// MAIN EDITOR
// =============================================================================

const nodeTypes = { dashboardNode: DashboardNode };
const edgeTypes = { smoothEdge: SmoothEdge };

// =============================================================================
// REPORT VIEW COMPONENT
// =============================================================================

interface ReportViewProps {
    report: WorkflowReport | null;
    onBackToBuilder: () => void;
    onRerun: () => void;
    isExecuting: boolean;
}

// =============================================================================
// CELL DETAIL MODAL - View full content of truncated cells
// =============================================================================

interface CellModalProps {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    content: string;
    rowData?: Record<string, unknown>;
}

const CellModal = memo(({ isOpen, onClose, title, content, rowData }: CellModalProps) => {
    if (!isOpen) return null;

    // Parse content for better formatting (handle citations like [[1]](url))
    const formatContent = (text: string) => {
        // Replace citation patterns [[n]](url) with cleaner format
        const withCitations = text.replace(/\[\[(\d+)\]\]\((https?:\/\/[^\s)]+)\)/g, ' [$1]');
        // Split into paragraphs
        return withCitations.split(/\n\n+/).filter(p => p.trim());
    };

    const paragraphs = formatContent(content);

    // Extract key fields from rowData for quick view
    const keyFields = rowData ? ['symbol', 'price', 'change_percent', 'volume_today', 'sector'] : [];
    const quickData = keyFields
        .filter(k => rowData && k in rowData)
        .map(k => ({ key: k, val: rowData![k] }));

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
            onClick={onClose}
        >
            <motion.div
                initial={{ scale: 0.95, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.95, opacity: 0, y: 20 }}
                transition={{ type: "spring", damping: 25, stiffness: 300 }}
                className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header with symbol badge */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-gradient-to-r from-blue-600 to-indigo-600">
                    <div className="flex items-center gap-3">
                        {(() => {
                            const symbol = rowData?.symbol;
                            if (symbol) {
                                return (
                                    <span className="px-3 py-1 bg-white/20 rounded-lg text-white font-bold text-sm">
                                        ${String(symbol)}
                                    </span>
                                );
                            }
                            return null;
                        })()}
                        <h3 className="font-semibold text-white capitalize">{title.replace(/_/g, ' ')}</h3>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5 text-white" />
                    </button>
                </div>

                {/* Quick stats bar */}
                {quickData.length > 0 && (
                    <div className="px-5 py-3 bg-slate-50 border-b border-slate-200 flex items-center gap-4 flex-wrap">
                        {quickData.map(({ key, val }) => (
                            <div key={key} className="flex items-center gap-1.5">
                                <span className="text-xs text-slate-500 uppercase">{key.replace(/_/g, ' ')}:</span>
                                <span className={`text-sm font-semibold ${key.includes('change') && typeof val === 'number'
                                    ? val > 0 ? 'text-emerald-600' : 'text-red-500'
                                    : 'text-slate-700'
                                    }`}>
                                    {key === 'price' && typeof val === 'number' ? `$${val.toFixed(2)}` :
                                        key.includes('change') && typeof val === 'number' ? `${val > 0 ? '+' : ''}${val.toFixed(2)}%` :
                                            key.includes('volume') && typeof val === 'number' ? (val >= 1e6 ? `${(val / 1e6).toFixed(1)}M` : val >= 1e3 ? `${(val / 1e3).toFixed(0)}K` : val) :
                                                String(val ?? '-')}
                                </span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Main Content */}
                <div className="p-5 overflow-y-auto max-h-[50vh]">
                    <div className="space-y-3">
                        {paragraphs.map((p, i) => (
                            <p key={i} className={`text-slate-700 leading-relaxed ${i === 0 ? 'text-base font-medium' : 'text-sm'}`}>
                                {p}
                            </p>
                        ))}
                    </div>
                </div>

                {/* Expandable full row data */}
                {rowData && (
                    <details className="border-t border-slate-200">
                        <summary className="px-5 py-3 bg-slate-50 cursor-pointer hover:bg-slate-100 text-sm font-medium text-slate-600 flex items-center gap-2">
                            <span>View All Data Fields ({Object.keys(rowData).length} fields)</span>
                        </summary>
                        <div className="px-5 py-4 max-h-[200px] overflow-y-auto bg-slate-50">
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-2">
                                {Object.entries(rowData)
                                    .filter(([k]) => !['news_summary', 'latest_headline'].includes(k))
                                    .map(([key, val]) => (
                                        <div key={key} className="text-xs truncate">
                                            <span className="font-medium text-slate-500">{key.replace(/_/g, ' ')}: </span>
                                            <span className="text-slate-700">{
                                                typeof val === 'number' ? val.toFixed(2) :
                                                    typeof val === 'boolean' ? (val ? '✓' : '✗') :
                                                        String(val ?? '-').slice(0, 50)
                                            }</span>
                                        </div>
                                    ))}
                            </div>
                        </div>
                    </details>
                )}

                {/* Footer */}
                <div className="px-5 py-4 border-t border-slate-200 bg-white flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/20"
                    >
                        Close
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
});

CellModal.displayName = 'CellModal';

const ReportView = memo(({ report, onBackToBuilder, onRerun, isExecuting }: ReportViewProps) => {
    // State for cell modal
    const [cellModal, setCellModal] = useState<{ isOpen: boolean; title: string; content: string; rowData?: Record<string, unknown> }>({
        isOpen: false,
        title: '',
        content: '',
        rowData: undefined
    });

    // State for showing all rows per node
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

    const toggleNodeExpansion = (nodeId: string) => {
        setExpandedNodes(prev => {
            const next = new Set(prev);
            if (next.has(nodeId)) {
                next.delete(nodeId);
            } else {
                next.add(nodeId);
            }
            return next;
        });
    };

    const openCellModal = (title: string, content: string, rowData?: Record<string, unknown>) => {
        setCellModal({ isOpen: true, title, content, rowData });
    };

    const closeCellModal = () => {
        setCellModal({ isOpen: false, title: '', content: '', rowData: undefined });
    };

    if (!report) return null;

    const nodeEntries = Object.entries(report.nodeResults);
    const successCount = nodeEntries.filter(([, r]) => r.status === 'success').length;
    const errorCount = nodeEntries.filter(([, r]) => r.status === 'error').length;

    const formatValue = (val: unknown, col?: string): string => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'number') {
            if (col?.includes('change') || col?.includes('percent')) {
                return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
            }
            if (col?.includes('volume') || col?.includes('market_cap')) {
                if (val >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
                if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
                if (val >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
                return val.toFixed(2);
            }
            if (col === 'price') return `$${val.toFixed(2)}`;
            return val.toFixed(2);
        }
        return String(val);
    };

    // Check if a value should be truncated (long text)
    const shouldTruncate = (val: unknown, col: string): boolean => {
        if (typeof val !== 'string') return false;
        const longTextCols = ['headline', 'summary', 'reason', 'content', 'description', 'news'];
        return val.length > 50 || longTextCols.some(c => col.toLowerCase().includes(c));
    };

    // Get truncated display value
    const getTruncatedValue = (val: unknown, col: string): string => {
        const str = formatValue(val, col);
        if (shouldTruncate(val, col) && str.length > 50) {
            return str.slice(0, 47) + '...';
        }
        return str;
    };

    // Helper to find a DataFrame in nested data
    const findDataFrame = (obj: unknown, maxDepth = 3): { columns: string[]; data: Record<string, unknown>[] } | null => {
        if (maxDepth <= 0 || !obj || typeof obj !== 'object') return null;

        const o = obj as Record<string, unknown>;

        // Direct DataFrame
        if (o.type === 'dataframe' && Array.isArray(o.columns) && Array.isArray(o.data)) {
            return { columns: o.columns as string[], data: o.data as Record<string, unknown>[] };
        }

        // Check known keys that contain DataFrames
        for (const key of ['sectors', 'tickers', 'data', 'results']) {
            if (o[key] && typeof o[key] === 'object') {
                const found = findDataFrame(o[key], maxDepth - 1);
                if (found) return found;
            }
        }

        return null;
    };

    const renderDataTable = (data: unknown, title: string, nodeId: string = 'default'): React.ReactNode => {
        // Try to find a DataFrame anywhere in the data
        const df = findDataFrame(data);

        if (df && df.columns.length > 0 && df.data.length > 0) {
            // Smart column selection - prioritize enrichment columns
            const priorityCols = [
                'symbol', 'price', 'change_percent', 'volume_today', 'rvol',
                // News Enricher columns
                'has_news', 'news_count', 'latest_headline', 'news_summary',
                // Narrative Classifier columns
                'narrative', 'narrative_confidence', 'narrative_reason',
                // Sentiment Scorer columns
                'sentiment_score', 'sentiment_label',
                // Risk Scorer columns
                'risk_score', 'has_binary_event', 'risk_factors', 'event_date',
                // Sector columns
                'synthetic_sector', 'sector',
                // Ranking columns
                'rank', 'rank_score', 'anomaly_score',
                // Signal columns
                'signal_id', 'signal_name'
            ];

            // Get available priority columns that exist in data
            const availablePriority = priorityCols.filter(c => df.columns.includes(c));
            // Add any other columns up to 15 total for better visibility
            const otherCols = df.columns.filter(c => !availablePriority.includes(c));
            const cols = [...availablePriority, ...otherCols].slice(0, 15);

            // Show all rows if expanded, otherwise limit to 15
            const isExpanded = expandedNodes.has(nodeId);
            const displayRows = isExpanded ? df.data : df.data.slice(0, 15);
            const totalRows = df.data.length;

            return (
                <div className="overflow-x-auto">
                    <div className="max-h-[400px] overflow-y-auto">
                        <table className="w-full text-[10px]">
                            <thead className="sticky top-0 bg-white z-10">
                                <tr className="border-b border-slate-200">
                                    {cols.map((col, i) => (
                                        <th key={i} className="px-2 py-1.5 text-left font-medium text-blue-600 uppercase tracking-wider whitespace-nowrap">
                                            {col.replace(/_/g, ' ')}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {displayRows.map((row, i) => (
                                    <tr key={i} className="border-b border-slate-100 hover:bg-blue-50/50 transition-colors">
                                        {cols.map((col, j) => {
                                            const val = row[col];
                                            const fullValue = formatValue(val, col);
                                            const displayValue = getTruncatedValue(val, col);
                                            const isTruncated = shouldTruncate(val, col) && fullValue.length > 50;
                                            const isPositive = typeof val === 'number' && val > 0 && (col.includes('change') || col.includes('percent'));
                                            const isNegative = typeof val === 'number' && val < 0 && (col.includes('change') || col.includes('percent'));

                                            return (
                                                <td
                                                    key={j}
                                                    className={`px-2 py-1.5 ${isPositive ? 'text-emerald-600' : isNegative ? 'text-red-500' : j === 0 ? 'text-slate-700 font-medium' : 'text-slate-500'} ${isTruncated ? 'cursor-pointer hover:bg-blue-100 rounded' : ''}`}
                                                    onClick={isTruncated ? () => openCellModal(col.replace(/_/g, ' '), fullValue, row) : undefined}
                                                    title={isTruncated ? 'Click to view full content' : undefined}
                                                >
                                                    <span className="flex items-center gap-1">
                                                        {displayValue}
                                                        {isTruncated && (
                                                            <Maximize2 className="w-3 h-3 text-blue-400 flex-shrink-0" />
                                                        )}
                                                    </span>
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {totalRows > 15 && (
                        <div className="flex items-center justify-center gap-2 mt-2 pt-2 border-t border-slate-100">
                            <span className="text-[9px] text-slate-400">
                                {isExpanded ? `Showing all ${totalRows} rows` : `${Math.min(15, totalRows)} of ${totalRows} rows`}
                            </span>
                            <button
                                onClick={() => toggleNodeExpansion(nodeId)}
                                className="text-[9px] text-blue-600 hover:text-blue-800 font-medium"
                            >
                                {isExpanded ? 'Show Less' : 'Show All'}
                            </button>
                        </div>
                    )}
                </div>
            );
        }

        // Handle array of objects directly
        if (Array.isArray(data) && data.length > 0 && typeof data[0] === 'object') {
            const allCols = Object.keys(data[0] as Record<string, unknown>);
            const priorityCols = ['symbol', 'price', 'change_percent', 'narrative', 'sentiment_score', 'risk_score', 'rank'];
            const availablePriority = priorityCols.filter(c => allCols.includes(c));
            const cols = [...availablePriority, ...allCols.filter(c => !availablePriority.includes(c))].slice(0, 8);
            return (
                <div className="overflow-x-auto">
                    <table className="w-full text-[10px]">
                        <thead>
                            <tr className="border-b border-slate-200">
                                {cols.map((col, i) => (
                                    <th key={i} className="px-2 py-1.5 text-left font-medium text-blue-600 uppercase tracking-wider">
                                        {col.replace(/_/g, ' ')}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {data.slice(0, 10).map((row, i) => (
                                <tr key={i} className="border-b border-slate-100 hover:bg-blue-50/50 transition-colors">
                                    {cols.map((col, j) => (
                                        <td key={j} className={`px-2 py-1.5 ${j === 0 ? 'text-slate-700' : 'text-slate-500'}`}>
                                            {formatValue((row as Record<string, unknown>)[col], col)}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            );
        }

        // For Display/Results node - try to extract useful data from nested structure
        if (data && typeof data === 'object') {
            const o = data as Record<string, unknown>;

            // If it's a display wrapper, try to find DataFrame inside
            if (o.type === 'display' && o.data) {
                const innerData = o.data as Record<string, unknown>;
                // Try recursively finding DataFrame
                const nestedDf = findDataFrame(innerData);
                if (nestedDf && nestedDf.columns.length > 0 && nestedDf.data.length > 0) {
                    return renderDataTable(nestedDf, title, nodeId);
                }
                // Check if innerData itself has data key
                if (innerData.data && typeof innerData.data === 'object') {
                    const deeperDf = findDataFrame(innerData.data);
                    if (deeperDf && deeperDf.columns.length > 0 && deeperDf.data.length > 0) {
                        return renderDataTable(deeperDf, title, nodeId);
                    }
                }
            }

            // Show summary of what we received (fallback)
            const keys = Object.keys(o).filter(k => !['type', 'success', 'displayType'].includes(k));
            if (keys.length === 0) {
                return <p className="text-slate-400 text-[10px]">No renderable data</p>;
            }

            // Show key-value summary with better formatting
            return (
                <div className="space-y-1">
                    {keys.slice(0, 4).map(key => {
                        const val = o[key];
                        let display = '';
                        if (typeof val === 'object' && val !== null) {
                            if ('type' in val && (val as { type: string }).type === 'dataframe') {
                                const dfData = val as { data?: unknown[] };
                                display = `DataFrame (${dfData.data?.length || 0} rows)`;
                            } else if (Array.isArray(val)) {
                                display = `Array (${val.length} items)`;
                            } else {
                                // Try to show count or meaningful summary
                                const vObj = val as Record<string, unknown>;
                                if ('count' in vObj) {
                                    display = `${vObj.count} items`;
                                } else if ('data' in vObj && Array.isArray(vObj.data)) {
                                    display = `${(vObj.data as unknown[]).length} items`;
                                } else {
                                    display = JSON.stringify(val).slice(0, 50) + '...';
                                }
                            }
                        } else {
                            display = String(val);
                        }
                        return (
                            <div key={key} className="flex items-center gap-2 text-[10px]">
                                <span className="text-slate-400">{key}:</span>
                                <span className="text-slate-600">{display}</span>
                            </div>
                        );
                    })}
                </div>
            );
        }

        // Primitive value
        if (data !== null && data !== undefined) {
            return <p className="text-slate-600 text-[10px]">{String(data)}</p>;
        }

        return <p className="text-slate-400 text-[10px]">No data</p>;
    };

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col h-full bg-slate-100 overflow-hidden"
        >
            {/* Header - Light */}
            <div className="flex-shrink-0 px-5 py-3 border-b border-slate-200 bg-white">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={onBackToBuilder}
                            className="text-[11px] text-slate-500 hover:text-blue-600 transition-colors"
                        >
                            Back to Builder
                        </button>
                        <div className="w-px h-4 bg-slate-200" />
                        <div>
                            <h2 className="text-[13px] font-medium text-slate-700">Workflow Report</h2>
                            <p className="text-[10px] text-slate-400">
                                {report.executedAt.toLocaleTimeString()} | {(report.totalTime / 1000).toFixed(1)}s total
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-[10px] text-emerald-600">{successCount} ok</span>
                        {errorCount > 0 && <span className="text-[10px] text-red-500">{errorCount} fail</span>}
                        <button
                            onClick={onRerun}
                            disabled={isExecuting}
                            className="px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-[10px] font-medium transition-colors disabled:opacity-50"
                        >
                            {isExecuting ? 'Running...' : 'Rerun'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Results Grid */}
            <div className="flex-1 overflow-y-auto p-4">
                <div className="max-w-5xl mx-auto space-y-3">
                    {/* Pipeline Flow */}
                    <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-2">
                        {nodeEntries.map(([id, result], i) => (
                            <div key={id} className="flex items-center">
                                <div className={`px-2 py-1 rounded border ${result.status === 'success' ? 'border-blue-200 bg-blue-50' : 'border-red-200 bg-red-50'}`}>
                                    <span className={`text-[10px] ${result.status === 'success' ? 'text-blue-600' : 'text-red-600'}`}>
                                        {result.title}
                                    </span>
                                    <span className="text-[9px] text-slate-400 ml-1.5">
                                        {(result.executionTime / 1000).toFixed(1)}s
                                    </span>
                                </div>
                                {i < nodeEntries.length - 1 && (
                                    <span className="text-slate-300 mx-1">→</span>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Node Result Cards */}
                    {nodeEntries.map(([id, result], i) => {
                        const isSuccess = result.status === 'success';

                        return (
                            <motion.div
                                key={id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.05 }}
                                className="bg-white rounded-lg border-2 border-blue-100 overflow-hidden shadow-sm"
                                style={isSuccess ? { boxShadow: `0 0 15px ${FUTURISTIC_BLUE.glow}15` } : {}}
                            >
                                {/* Card Header */}
                                <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-blue-50 to-transparent">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[9px] font-mono text-blue-500">{String(i + 1).padStart(2, '0')}</span>
                                        <h3 className="text-[11px] font-medium text-slate-700">{result.title}</h3>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-[9px] font-mono text-slate-400">{(result.executionTime / 1000).toFixed(2)}s</span>
                                        <div className={`w-1.5 h-1.5 rounded-full ${isSuccess ? 'bg-emerald-500' : 'bg-red-500'}`} />
                                    </div>
                                </div>

                                {/* Card Content */}
                                <div className="p-3">
                                    {result.data ? (
                                        renderDataTable(result.data, result.title, id)
                                    ) : (
                                        <p className="text-slate-400 text-[10px] text-center py-2">No output</p>
                                    )}
                                </div>
                            </motion.div>
                        );
                    })}
                </div>
            </div>

            {/* Cell Detail Modal */}
            <AnimatePresence>
                <CellModal
                    isOpen={cellModal.isOpen}
                    onClose={closeCellModal}
                    title={cellModal.title}
                    content={cellModal.content}
                    rowData={cellModal.rowData}
                />
            </AnimatePresence>
        </motion.div>
    );
});

ReportView.displayName = 'ReportView';

// =============================================================================
// MAIN WORKFLOW EDITOR
// =============================================================================

interface WorkflowEditorProps {
    onClose?: () => void;
    onExecute?: () => Promise<void>;
}

export const WorkflowEditor = memo(({ onClose, onExecute }: WorkflowEditorProps) => {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [showPalette, setShowPalette] = useState(false);
    const [isExecuting, setIsExecuting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [currentView, setCurrentView] = useState<EditorView>('builder');
    const [workflowReport, setWorkflowReport] = useState<WorkflowReport | null>(null);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);

    // Get currently selected node
    const selectedNode = nodes.find(n => n.id === selectedNodeId) || null;

    // Handle node selection
    const handleNodeClick = useCallback((_: React.MouseEvent, node: Node<WorkflowNodeData>) => {
        setSelectedNodeId(node.id);
    }, []);

    // Close config panel when clicking on canvas
    const handlePaneClick = useCallback(() => {
        setSelectedNodeId(null);
    }, []);

    // Update node configuration
    const handleUpdateNodeConfig = useCallback((nodeId: string, config: NodeConfig) => {
        setNodes(prev => prev.map(n =>
            n.id === nodeId
                ? { ...n, data: { ...n.data, config } }
                : n
        ));
    }, [setNodes]);

    const handleAddNode = useCallback((type: string) => {
        const template = NODE_TEMPLATES.find(t => t.type === type);
        if (!template) return;

        const defaultConfig = DEFAULT_CONFIGS[type] || {};

        const newNode: Node<WorkflowNodeData> = {
            id: `node-${Date.now()}`,
            type: 'dashboardNode',
            position: { x: 200 + Math.random() * 150, y: 150 + Math.random() * 150 },
            data: {
                step: nodes.length + 1,
                title: template.label,
                subtitle: 'Click to configure',
                category: template.category,
                icon: type,
                status: 'idle',
                config: defaultConfig,
                code: `# ${template.label}\n# Configure logic here`,
            },
        };

        setNodes(prev => [...prev, newNode]);
    }, [nodes.length, setNodes]);

    // Handle new connections between nodes
    const onConnect = useCallback((connection: Connection) => {
        setEdges((eds) => addEdge({
            ...connection,
            type: 'smoothEdge',
            style: { stroke: '#3b82f6' }
        }, eds));
    }, [setEdges]);

    // Convert frontend nodes to backend format - use actual node config!
    const convertToBackendFormat = useCallback(() => {
        const backendNodes = nodes.map((node) => ({
            id: node.id,
            type: ICON_TO_BACKEND_TYPE[node.data.icon] || node.data.icon,
            position: node.position,
            data: {
                label: node.data.title,
                config: node.data.config || DEFAULT_CONFIGS[node.data.icon] || {}
            }
        }));

        const backendEdges = edges.map(edge => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
        }));

        return {
            name: 'Workflow Execution',
            nodes: backendNodes,
            edges: backendEdges
        };
    }, [nodes, edges]);

    // Execute workflow via backend API
    const handleExecute = useCallback(async () => {
        setIsExecuting(true);
        setError(null);
        abortRef.current = new AbortController();

        // Reset all nodes to idle
        setNodes(prev => prev.map(n => ({
            ...n,
            data: { ...n.data, status: 'idle', executionTime: undefined }
        })));

        try {
            const workflow = convertToBackendFormat();

            // Mark first node as running
            setNodes(prev => prev.map((n, idx) => ({
                ...n,
                data: { ...n.data, status: idx === 0 ? 'running' : 'idle' }
            })));

            const response = await fetch(`${AGENT_URL}/api/workflow-execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(workflow),
                signal: abortRef.current.signal,
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const result = await response.json();

            // Update nodes with real results
            if (result.nodeResults) {

                setNodes(prev => prev.map(node => {
                    const nodeResult = result.nodeResults[node.id];
                    if (nodeResult) {

                        // Parse result data into table format
                        let tableData = node.data.data;

                        try {
                            // Navigate through nested structure: nodeResult.data.data for tools
                            let toolResult = nodeResult.data;
                            let innerData = toolResult?.data;

                            // Special handling for Display/Results node
                            if (toolResult?.type === 'display') {
                                // Handle combined sources (multiple inputs)
                                if (toolResult?.displayType === 'combined' && Array.isArray(toolResult?.sources)) {
                                    const sources = toolResult.sources as Array<{ source: string; data: unknown }>;
                                    // Use first source's data
                                    if (sources.length > 0 && sources[0].data) {
                                        const firstData = sources[0].data as Record<string, unknown>;
                                        if (firstData?.type === 'dataframe') {
                                            innerData = firstData;
                                        }
                                    }
                                }
                                // Single source
                                else if (toolResult?.data) {
                                    let unwrapped = toolResult.data;
                                    if (unwrapped?.type === 'dataframe') {
                                        innerData = unwrapped;
                                    } else if (unwrapped?.data && typeof unwrapped.data === 'object') {
                                        unwrapped = unwrapped.data;
                                        if (unwrapped?.type === 'dataframe') {
                                            innerData = unwrapped;
                                        }
                                    }
                                    toolResult = unwrapped;
                                }
                            }



                            // Handle DataFrame format: { type: 'dataframe', columns: [...], data: [...] }
                            if (innerData?.type === 'dataframe' && Array.isArray(innerData.data)) {
                                const allCols = innerData.columns || [];
                                // Prefer useful columns for display (including enrichment columns)
                                const preferredCols = [
                                    'symbol', 'price', 'change_percent', 'volume_today', 'rvol', 'sector',
                                    // News Enricher
                                    'has_news', 'news_count', 'latest_headline',
                                    // Narrative Classifier
                                    'narrative', 'narrative_reason',
                                    // Sentiment & Risk
                                    'sentiment_label', 'risk_score', 'has_binary_event'
                                ];
                                const displayCols = preferredCols.filter(c => allCols.includes(c));
                                // Fallback to first 6 if none found (increased from 4)
                                const finalCols = displayCols.length > 0 ? displayCols.slice(0, 8) : allCols.slice(0, 6);

                                tableData = {
                                    columns: finalCols.map((c: string) =>
                                        c === 'change_percent' ? 'Change %' :
                                            c === 'volume_today' ? 'Volume' :
                                                c === 'has_news' ? 'News?' :
                                                    c === 'news_count' ? '#News' :
                                                        c === 'latest_headline' ? 'Headline' :
                                                            c === 'has_binary_event' ? 'Event?' :
                                                                c === 'sentiment_label' ? 'Sentiment' :
                                                                    c === 'risk_score' ? 'Risk' :
                                                                        c.charAt(0).toUpperCase() + c.slice(1).replace(/_/g, ' ')
                                    ),
                                    rows: innerData.data.slice(0, 5).map((row: Record<string, unknown>) =>
                                        finalCols.map((col: string) => {
                                            const val = row[col];
                                            if (val === null || val === undefined) return '-';
                                            // Boolean columns
                                            if (typeof val === 'boolean') {
                                                return val ? '✓' : '✗';
                                            }
                                            if (typeof val === 'number') {
                                                if (col.includes('percent') || col.includes('change')) {
                                                    return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
                                                }
                                                if (col.includes('volume')) {
                                                    return val >= 1000000 ? `${(val / 1000000).toFixed(1)}M` :
                                                        val >= 1000 ? `${(val / 1000).toFixed(0)}K` : String(val);
                                                }
                                                if (col === 'price') return `$${val.toFixed(2)}`;
                                                if (col === 'risk_score') return val.toFixed(2);
                                                return val.toFixed(2);
                                            }
                                            // Truncate long strings (headlines, summaries)
                                            const strVal = String(val);
                                            if (col.includes('headline') || col.includes('summary') || col.includes('reason')) {
                                                return strVal.length > 40 ? strVal.slice(0, 40) + '...' : strVal;
                                            }
                                            return strVal;
                                        })
                                    )
                                };
                            }
                            // Handle sectors format: { sectors: { type: 'dataframe', data: [...] } }
                            else if (toolResult?.sectors?.type === 'dataframe' && Array.isArray(toolResult.sectors.data)) {
                                const sectorsData = toolResult.sectors.data;
                                // Find columns for sector display
                                const sectorCols = ['sector', 'ticker_count', 'avg_change'];
                                tableData = {
                                    columns: ['Sector', 'Tickers', 'Avg %'],
                                    rows: sectorsData.slice(0, 5).map((s: Record<string, unknown>) => [
                                        String(s.sector || s.synthetic_sector || '-'),
                                        String(s.ticker_count || s.count || '-'),
                                        typeof s.avg_change === 'number'
                                            ? `${s.avg_change > 0 ? '+' : ''}${s.avg_change.toFixed(2)}%`
                                            : String(s.avg_change || '-')
                                    ])
                                };
                            }
                            // Handle sectors as array (fallback)
                            else if (toolResult?.sectors && Array.isArray(toolResult.sectors)) {
                                tableData = {
                                    columns: ['Sector', 'Tickers', 'Avg %'],
                                    rows: toolResult.sectors.slice(0, 5).map((s: { sector: string; ticker_count: number; avg_change: number }) => [
                                        s.sector,
                                        String(s.ticker_count),
                                        `${s.avg_change > 0 ? '+' : ''}${s.avg_change.toFixed(2)}%`
                                    ])
                                };
                            }
                            // Handle direct array
                            else if (Array.isArray(innerData)) {
                                const firstItem = innerData[0];
                                if (firstItem && typeof firstItem === 'object') {
                                    const cols = Object.keys(firstItem).slice(0, 4);
                                    tableData = {
                                        columns: cols,
                                        rows: innerData.slice(0, 5).map((row: Record<string, unknown>) =>
                                            cols.map(col => String(row[col] ?? ''))
                                        )
                                    };
                                }
                            }
                        } catch (e) {
                            console.warn('Error parsing node result:', e);
                        }


                        return {
                            ...node,
                            data: {
                                ...node.data,
                                status: nodeResult.status === 'success' ? 'complete' : 'error',
                                executionTime: nodeResult.executionTime,
                                data: tableData,
                            }
                        };
                    }
                    return { ...node, data: { ...node.data, status: 'complete' } };
                }));
            }

            // Build workflow report - use PARSED data, not raw backend data
            const reportResults: WorkflowReport['nodeResults'] = {};
            let totalTime = 0;

            // Helper to parse node result into table format (same logic as above)
            const parseNodeData = (nodeResult: { data: unknown }) => {
                let toolResult = nodeResult.data as Record<string, unknown>;
                let innerData = toolResult?.data as Record<string, unknown>;

                // Special handling for Display node with combined sources
                if (toolResult?.type === 'display') {
                    // Handle combined sources (multiple inputs)
                    if (toolResult?.displayType === 'combined' && Array.isArray(toolResult?.sources)) {
                        const sources = toolResult.sources as Array<{ source: string; data: unknown }>;
                        // Return first source's data as primary
                        if (sources.length > 0 && sources[0].data) {
                            const firstData = sources[0].data as Record<string, unknown>;
                            if (firstData?.type === 'dataframe') return firstData;
                        }
                    }
                    // Single source
                    if (toolResult?.data) {
                        let unwrapped = toolResult.data as Record<string, unknown>;
                        if (unwrapped?.type === 'dataframe') return unwrapped;
                        if (unwrapped?.data && typeof unwrapped.data === 'object') {
                            unwrapped = unwrapped.data as Record<string, unknown>;
                            if (unwrapped?.type === 'dataframe') return unwrapped;
                        }
                        toolResult = unwrapped;
                        innerData = toolResult?.data as Record<string, unknown>;
                    }
                }

                // DataFrame format
                if (innerData?.type === 'dataframe' && Array.isArray(innerData.data)) {
                    return innerData; // Already in correct format for renderDataTable
                }
                // Sectors format
                if (toolResult?.sectors && typeof toolResult.sectors === 'object') {
                    return toolResult.sectors; // Return sectors DataFrame
                }
                return nodeResult.data; // Fallback to raw
            };

            nodes.forEach(node => {
                const nodeResult = result.nodeResults[node.id];
                if (nodeResult) {
                    totalTime += nodeResult.executionTime || 0;
                    reportResults[node.id] = {
                        nodeId: node.id,
                        status: nodeResult.status === 'success' ? 'success' : 'error',
                        executionTime: nodeResult.executionTime || 0,
                        data: parseNodeData(nodeResult), // Use PARSED data
                        title: node.data.title,
                        icon: node.data.icon,
                    };
                }
            });

            const newReport: WorkflowReport = {
                executedAt: new Date(),
                totalTime,
                nodeResults: reportResults,
            };

            setWorkflowReport(newReport);

            // Transition to report view with delay for smooth animation
            setTimeout(() => {
                setCurrentView('report');
            }, 300);

            if (onExecute) await onExecute();

        } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') return;

            const errorMessage = err instanceof Error ? err.message : 'Execution failed';
            setError(errorMessage);

            // Mark all nodes as error
            setNodes(prev => prev.map(n => ({
                ...n,
                data: { ...n.data, status: 'error' }
            })));
        } finally {
            setIsExecuting(false);
        }
    }, [convertToBackendFormat, setNodes, nodes, onExecute]);

    const handleReset = useCallback(() => {
        setError(null);
        if (abortRef.current) {
            abortRef.current.abort();
        }
        setNodes(prev => prev.map(n => ({
            ...n,
            data: { ...n.data, status: 'idle', executionTime: undefined }
        })));
    }, [setNodes]);

    const handleClearAll = useCallback(() => {
        setError(null);
        if (abortRef.current) {
            abortRef.current.abort();
        }
        setNodes([]);
        setEdges([]);
    }, [setNodes, setEdges]);

    const nodeColor = useCallback(() => {
        return FUTURISTIC_BLUE.primary;
    }, []);

    // Callback for going back to builder from report
    const handleBackToBuilder = useCallback(() => {
        setCurrentView('builder');
    }, []);

    // Callback for rerunning workflow from report
    const handleRerun = useCallback(() => {
        setCurrentView('builder');
        // Small delay to ensure view change happens first
        setTimeout(() => {
            handleExecute();
        }, 100);
    }, [handleExecute]);

    // Show Report view
    if (currentView === 'report' && workflowReport) {
        return (
            <AnimatePresence mode="wait">
                <ReportView
                    report={workflowReport}
                    onBackToBuilder={handleBackToBuilder}
                    onRerun={handleRerun}
                    isExecuting={isExecuting}
                />
            </AnimatePresence>
        );
    }

    // Builder view (default)
    return (
        <div className="flex flex-col h-full bg-slate-100 overflow-hidden">
            {/* Toolbar - Light with blue accents */}
            <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-200 bg-white">
                <div className="flex items-center gap-3">
                    <h2 className="text-[12px] font-medium text-slate-700">Workflow Builder</h2>
                    <span className="text-[10px] text-slate-400">{nodes.length} nodes</span>
                    {workflowReport && (
                        <button
                            onClick={() => setCurrentView('report')}
                            className="px-2 py-0.5 text-[10px] text-blue-600 hover:text-blue-700 transition-colors"
                        >
                            View Report
                        </button>
                    )}
                </div>

                <div className="flex items-center gap-1.5">
                    <button
                        onClick={() => setShowPalette(!showPalette)}
                        className={`px-2.5 py-1 rounded text-[10px] font-medium transition-all ${showPalette
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-500 hover:text-blue-600 border border-slate-200 hover:border-blue-300'
                            }`}
                    >
                        Add Node
                    </button>

                    <div className="w-px h-3 bg-slate-200" />

                    <button
                        onClick={handleClearAll}
                        disabled={isExecuting}
                        className="px-2 py-1 text-[10px] text-slate-400 hover:text-red-500 transition-colors disabled:opacity-50"
                    >
                        Clear
                    </button>
                    <button
                        onClick={handleReset}
                        disabled={isExecuting}
                        className="px-2 py-1 text-[10px] text-slate-400 hover:text-slate-600 transition-colors disabled:opacity-50"
                    >
                        Reset
                    </button>
                    <button
                        onClick={handleExecute}
                        disabled={isExecuting}
                        className={`px-3 py-1 rounded text-[10px] font-medium transition-all ${isExecuting
                            ? 'bg-blue-400 text-white'
                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                            }`}
                    >
                        {isExecuting ? 'Running...' : 'Run'}
                    </button>
                </div>
            </div>

            {/* Error Banner */}
            <AnimatePresence>
                {error && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="flex-shrink-0 px-4 py-1.5 bg-red-50 border-b border-red-200"
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-red-600">{error}</span>
                            <button
                                onClick={() => setError(null)}
                                className="ml-auto text-red-400 hover:text-red-600"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* React Flow Canvas - Light with blue accents */}
            <div className="flex-1 relative">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onNodeClick={handleNodeClick}
                    onPaneClick={handlePaneClick}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    fitView={nodes.length > 0}
                    fitViewOptions={{ padding: 0.5, maxZoom: 0.8 }}
                    minZoom={0.2}
                    maxZoom={1.2}
                    defaultViewport={{ x: 100, y: 100, zoom: 0.6 }}
                    proOptions={{ hideAttribution: true }}
                    className="bg-slate-50"
                >
                    <Background
                        variant={BackgroundVariant.Dots}
                        gap={20}
                        size={1}
                        color="#cbd5e1"
                    />
                    <Controls
                        showInteractive={false}
                        className="!bg-white !border-slate-200 !rounded-lg [&>button]:!bg-white [&>button]:!border-slate-200 [&>button]:!text-slate-400 [&>button:hover]:!bg-slate-50 [&>button:hover]:!text-blue-600"
                    />
                    <MiniMap
                        nodeColor={nodeColor}
                        maskColor="rgba(248, 250, 252, 0.9)"
                        className="!bg-white !border-slate-200 !rounded-lg"
                        style={{ width: 100, height: 70 }}
                    />
                </ReactFlow>

                {/* Node Palette */}
                <AnimatePresence>
                    {showPalette && (
                        <NodePalette
                            isOpen={showPalette}
                            onClose={() => setShowPalette(false)}
                            onAddNode={handleAddNode}
                        />
                    )}
                </AnimatePresence>

                {/* Node Configuration Panel */}
                <AnimatePresence>
                    {selectedNode && (
                        <NodeConfigPanel
                            node={selectedNode}
                            onClose={() => setSelectedNodeId(null)}
                            onUpdate={handleUpdateNodeConfig}
                        />
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
});

WorkflowEditor.displayName = 'WorkflowEditor';
