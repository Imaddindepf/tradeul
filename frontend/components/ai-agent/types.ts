/**
 * AI Agent V4 — Shared types
 */

export interface AgentStep {
  id: string;
  type: 'reasoning' | 'tool';
  title: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  icon?: string;
  description?: string;
  details?: string;
  duration?: number;
}

export interface ClarificationData {
  message: string;
  options: Array<{ label: string; value: string; rewrite: string }>;
  originalQuery: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  status?: 'thinking' | 'complete' | 'error' | 'clarification';
  steps?: AgentStep[];
  thinkingStartTime?: number;
  suggestedQuestions?: string[];
  clarification?: ClarificationData;
}

export interface OutputItem {
  type: string;
  title: string;
  content?: string;
  data?: unknown;
  structured_response?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ResultData {
  success: boolean;
  code: string;
  outputs: OutputItem[];
  execution_time_ms: number;
  timestamp: string;
}

export interface ResultBlockData {
  id: string;
  messageId: string;
  query: string;
  title: string;
  status: 'success' | 'error' | 'running' | 'fixing';
  code: string;
  codeVisible: boolean;
  result: ResultData;
  timestamp: Date;
}

export interface ChartSnapshot {
  recentBars: unknown[];
  indicators: Record<string, number | number[] | undefined>;
  levels: unknown[];
  visibleDateRange: { from: number; to: number };
  isHistorical: boolean;
}

export interface ChartContext {
  ticker: string;
  interval: string;
  range?: string;
  activeIndicators?: string[];
  currentPrice?: number | null;
  snapshot: ChartSnapshot;
  targetCandle?: { date: number; [key: string]: unknown } | null;
}

export interface MarketContext {
  [key: string]: unknown;
}

export interface PlotlyConfig {
  data: Array<Record<string, unknown>>;
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
}

export interface SessionSummary {
  thread_id: string;
  last_query?: string;
  updated_at: number;
  [key: string]: unknown;
}

export interface SessionMessage {
  timestamp: number;
  query: string;
  response: string;
}
