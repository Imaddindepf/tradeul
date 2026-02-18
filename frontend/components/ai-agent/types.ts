/**
 * Types for AI Agent components
 */

export interface AgentStep {
  id: string;
  type: 'reasoning' | 'tool' | 'code' | 'result';
  title: string;
  description?: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  duration?: number; // seconds
  icon?: string;
  expandable?: boolean;
  expanded?: boolean;
  details?: string;
}

export interface ClarificationOption {
  label: string;
  rewrite: string;
}

export interface ClarificationData {
  message: string;
  options: ClarificationOption[];
  originalQuery: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  status?: 'thinking' | 'executing' | 'complete' | 'error' | 'clarification';
  steps?: AgentStep[];
  thinkingStartTime?: number;
  clarification?: ClarificationData;
}

export interface TableData {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
}

export interface ChartData {
  type: 'bar' | 'scatter' | 'line' | 'heatmap' | 'pie';
  plotly_config: PlotlyConfig;
}

export interface PlotlyConfig {
  data: PlotlyTrace[];
  layout: Record<string, unknown>;
}

export interface PlotlyTrace {
  type: string;
  x?: (string | number)[];
  y?: (string | number)[];
  z?: number[][];
  text?: string[];
  marker?: Record<string, unknown>;
  line?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface StatsData {
  title: string;
  stats: Record<string, {
    min: number;
    max: number;
    mean: number;
    median: number;
    std: number;
    count: number;
  }>;
}

export interface OutputBlock {
  type: 'table' | 'chart' | 'plotly_chart' | 'stats' | 'error' | 'research' | 'news';
  title: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  total?: number;
  chart_type?: string;
  plotly_config?: PlotlyConfig;
  stats?: StatsData['stats'];
  // Research output fields
  content?: string;
  citations?: string[];
  sources_count?: number;
}

export interface ExecutionResult {
  success: boolean;
  code: string;
  outputs: OutputBlock[];
  error?: string;
  execution_time_ms: number;
  timestamp: string;
}

export interface ResultBlockData {
  id: string;
  messageId?: string;
  query?: string;
  title: string;
  status: 'running' | 'fixing' | 'success' | 'error';
  code: string;
  codeVisible: boolean;
  result?: ExecutionResult;
  timestamp: Date;
}

export interface MarketContext {
  session: string;
  time_et: string;
  scanner_count: number;
  category_stats: Record<string, unknown>;
}

// ── Chart Analysis Context ──

export interface ChartSnapshot {
  recentBars: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
  indicators: {
    rsi?: number;
    rsi_trajectory?: number[];
    macd_line?: number;
    macd_signal?: number;
    macd_histogram?: number;
    macd_hist_trajectory?: number[];
    sma20?: number;
    sma50?: number;
    sma200?: number;
    ema12?: number;
    ema26?: number;
    bb_upper?: number;
    bb_mid?: number;
    bb_lower?: number;
    vwap?: number;
    atr?: number;
    stoch_k?: number;
    stoch_d?: number;
    adx?: number;
    adx_pdi?: number;
    adx_mdi?: number;
  };
  levels: { price: number; label?: string }[];
  visibleDateRange: { from: number; to: number };
  isHistorical: boolean;
}

export interface ChartContext {
  ticker: string;
  interval: string;
  range: string;
  activeIndicators: string[];
  currentPrice: number | null;
  snapshot: ChartSnapshot;
  targetCandle: {
    date: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  } | null;
}

// V4 WebSocket protocol types
export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

