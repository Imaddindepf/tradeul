/**
 * Workflow Builder v2 Types
 * =========================
 * Type definitions for the visual LangGraph workflow builder.
 */

export type NodeCategory = 'agent' | 'tool' | 'control' | 'trigger' | 'output'

export interface WorkflowNodeData {
  label: string
  description: string
  category: NodeCategory
  icon: string  // lucide icon name
  config: Record<string, any>
  inputs: string[]
  outputs: string[]
}

export interface WorkflowDefinition {
  id: string
  name: string
  description: string
  nodes: any[]  // React Flow nodes
  edges: any[]  // React Flow edges
  createdAt: string
  updatedAt: string
}

export interface CatalogNode {
  type: string
  label: string
  description: string
  icon: string
  inputs: string[]
  outputs: string[]
  category: NodeCategory
  config?: Record<string, any>
}

export interface NodeResult {
  status: 'pending' | 'running' | 'success' | 'error'
  data?: any
  error?: string
  elapsed_ms?: number
}

export const CATEGORY_COLORS: Record<NodeCategory, { border: string; bg: string; text: string; dot: string }> = {
  agent: { border: 'border-blue-500', bg: 'bg-blue-500/10', text: 'text-blue-400', dot: 'bg-blue-500' },
  tool: { border: 'border-purple-500', bg: 'bg-purple-500/10', text: 'text-purple-400', dot: 'bg-purple-500' },
  control: { border: 'border-amber-500', bg: 'bg-amber-500/10', text: 'text-amber-400', dot: 'bg-amber-500' },
  trigger: { border: 'border-emerald-500', bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-500' },
  output: { border: 'border-red-500', bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-500' },
}

export const CATEGORY_HEX: Record<NodeCategory, string> = {
  agent: '#3b82f6',
  tool: '#a855f7',
  control: '#f59e0b',
  trigger: '#10b981',
  output: '#ef4444',
}

export const CATEGORY_LABELS: Record<NodeCategory, string> = {
  agent: 'Agents',
  tool: 'Tools',
  control: 'Control Flow',
  trigger: 'Triggers',
  output: 'Outputs',
}

// Node catalog - all available nodes organized by category
export const NODE_CATALOG: Record<NodeCategory, CatalogNode[]> = {
  agent: [
    { type: 'market_data_agent', label: 'Market Data', description: 'Real-time scanner, enriched snapshots, categories', icon: 'TrendingUp', inputs: [], outputs: ['data'], category: 'agent' },
    { type: 'news_events_agent', label: 'News & Events', description: 'Benzinga news, market events, earnings', icon: 'Newspaper', inputs: [], outputs: ['data'], category: 'agent' },
    { type: 'financial_agent', label: 'Financial Analysis', description: 'Statements, dilution, SEC filings', icon: 'FileText', inputs: ['ticker'], outputs: ['data'], category: 'agent' },
    { type: 'research_agent', label: 'Deep Research', description: 'Grok + web search, sentiment', icon: 'Search', inputs: ['ticker'], outputs: ['data'], category: 'agent' },
    { type: 'code_exec_agent', label: 'Code Analysis', description: 'Python/DuckDB sandbox', icon: 'Code', inputs: ['data'], outputs: ['result'], category: 'agent' },
    { type: 'screener_agent', label: 'Stock Screener', description: 'DuckDB 60+ indicators', icon: 'Filter', inputs: [], outputs: ['data'], category: 'agent' },
  ],
  tool: [
    { type: 'scanner_snapshot', label: 'Scanner Snapshot', description: 'Get scanner category data', icon: 'BarChart3', inputs: [], outputs: ['tickers'], category: 'tool', config: { category: 'gappers_up', limit: 20 } },
    { type: 'enriched_data', label: 'Enriched Data', description: 'Get enriched ticker data', icon: 'Database', inputs: ['symbols'], outputs: ['data'], category: 'tool' },
    { type: 'latest_news', label: 'Latest News', description: 'Benzinga news feed', icon: 'Rss', inputs: [], outputs: ['articles'], category: 'tool' },
    { type: 'recent_events', label: 'Market Events', description: 'Recent market events', icon: 'Zap', inputs: [], outputs: ['events'], category: 'tool' },
    { type: 'financial_statements', label: 'Financials', description: 'Income, balance, cashflow', icon: 'Receipt', inputs: ['symbol'], outputs: ['data'], category: 'tool' },
    { type: 'dilution_profile', label: 'Dilution Profile', description: 'Dilution risk analysis', icon: 'AlertTriangle', inputs: ['symbol'], outputs: ['data'], category: 'tool' },
    { type: 'run_screen', label: 'Run Screen', description: 'DuckDB stock screen', icon: 'SlidersHorizontal', inputs: [], outputs: ['results'], category: 'tool' },
    { type: 'historical_bars', label: 'Historical Bars', description: 'Day/minute OHLCV data', icon: 'Calendar', inputs: [], outputs: ['bars'], category: 'tool' },
  ],
  control: [
    { type: 'conditional', label: 'Condition', description: 'If/else branch', icon: 'GitBranch', inputs: ['data'], outputs: ['true', 'false'], category: 'control' },
    { type: 'parallel', label: 'Parallel', description: 'Execute branches in parallel', icon: 'GitFork', inputs: ['data'], outputs: ['branch_1', 'branch_2'], category: 'control' },
    { type: 'merge', label: 'Merge', description: 'Combine parallel results', icon: 'GitMerge', inputs: ['input_1', 'input_2'], outputs: ['merged'], category: 'control' },
    { type: 'loop', label: 'Loop', description: 'Iterate over items', icon: 'Repeat', inputs: ['items'], outputs: ['item'], category: 'control' },
  ],
  trigger: [
    { type: 'on_event', label: 'On Event', description: 'Trigger on market event', icon: 'Bell', inputs: [], outputs: ['event'], category: 'trigger', config: { event_types: [] } },
    { type: 'on_schedule', label: 'On Schedule', description: 'Cron-based trigger', icon: 'Clock', inputs: [], outputs: ['tick'], category: 'trigger', config: { cron: '30 9 * * 1-5' } },
    { type: 'on_price', label: 'On Price', description: 'Price alert trigger', icon: 'DollarSign', inputs: [], outputs: ['alert'], category: 'trigger', config: { symbol: '', price: 0, direction: 'above' } },
  ],
  output: [
    { type: 'display_table', label: 'Display Table', description: 'Show results as table', icon: 'Table', inputs: ['data'], outputs: [], category: 'output' },
    { type: 'display_chart', label: 'Display Chart', description: 'Visualize as chart', icon: 'LineChart', inputs: ['data'], outputs: [], category: 'output' },
    { type: 'send_alert', label: 'Send Alert', description: 'Push notification', icon: 'BellRing', inputs: ['data'], outputs: [], category: 'output' },
    { type: 'export_data', label: 'Export', description: 'Export to CSV/JSON', icon: 'Download', inputs: ['data'], outputs: [], category: 'output' },
  ],
}
