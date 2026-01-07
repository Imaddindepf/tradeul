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

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  status?: 'thinking' | 'executing' | 'complete' | 'error';
  steps?: AgentStep[];
  thinkingStartTime?: number;
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
  type: 'table' | 'chart' | 'stats' | 'error';
  title: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  total?: number;
  chart_type?: string;
  plotly_config?: PlotlyConfig;
  stats?: StatsData['stats'];
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
  id: string;  // ID unico: message_id-block_id
  messageId?: string;  // ID del mensaje al que pertenece
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

// WebSocket message types
export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

export interface WSConnectedMessage extends WSMessage {
  type: 'connected';
  client_id: string;
  market_context: MarketContext;
}

export interface WSResponseStartMessage extends WSMessage {
  type: 'response_start';
  message_id: string;
}

export interface WSAssistantTextMessage extends WSMessage {
  type: 'assistant_text';
  message_id: string;
  delta: string;
}

export interface WSCodeExecutionMessage extends WSMessage {
  type: 'code_execution';
  message_id: string;
  block_id: number;
  status: 'running' | 'fixing';
  code: string;
}

export interface WSResultMessage extends WSMessage {
  type: 'result';
  message_id: string;
  block_id: number;
  status: 'success' | 'error';
  success: boolean;
  code: string;
  outputs: OutputBlock[];
  error?: string;
  execution_time_ms: number;
  timestamp: string;
}

export interface WSResponseEndMessage extends WSMessage {
  type: 'response_end';
  message_id: string;
}

export interface WSErrorMessage extends WSMessage {
  type: 'error';
  message_id?: string;
  error: string;
}

export interface WSMarketUpdateMessage extends WSMessage {
  type: 'market_update';
  session: string;
  timestamp: string;
}

export interface WSAgentStepMessage extends WSMessage {
  type: 'agent_step';
  message_id: string;
  step: AgentStep;
}

export interface WSAgentStepUpdateMessage extends WSMessage {
  type: 'agent_step_update';
  message_id: string;
  step_id: string;
  status: AgentStep['status'];
  description?: string;
}

