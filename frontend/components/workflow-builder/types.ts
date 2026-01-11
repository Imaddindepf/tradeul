/**
 * Workflow Builder Types
 * ======================
 * Type definitions for the visual workflow builder.
 */

export type NodeCategory = 
  | 'data_source'      // Scanner, Historical, SEC Filings
  | 'filter'           // Screener, Pattern Match
  | 'enrichment'       // News, Insiders, Financials
  | 'ai'               // AI Agent, Research
  | 'output'           // Display, Alert, Export

export interface WorkflowNodeData {
  label: string
  description: string
  category: NodeCategory
  icon: string
  config: Record<string, any>
  inputs: string[]
  outputs: string[]
}

export interface WorkflowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: WorkflowNodeData
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export interface Workflow {
  id: string
  name: string
  description: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  createdAt: string
  updatedAt: string
}

export interface NodeExecutionResult {
  nodeId: string
  status: 'pending' | 'running' | 'success' | 'error'
  data?: any
  error?: string
  executionTime?: number
}

export interface WorkflowExecutionState {
  workflowId: string
  status: 'idle' | 'running' | 'completed' | 'error'
  results: Record<string, NodeExecutionResult>
  currentNodeId?: string
}

// Available node definitions
export const NODE_DEFINITIONS: Record<string, Omit<WorkflowNodeData, 'config'>> = {
  // Data Sources
  scanner: {
    label: 'Scanner',
    description: 'Real-time market data (~1000 active tickers)',
    category: 'data_source',
    icon: '📡',
    inputs: [],
    outputs: ['tickers']
  },
  historical: {
    label: 'Historical Data',
    description: 'Minute-level OHLCV (1760+ days)',
    category: 'data_source',
    icon: '📊',
    inputs: [],
    outputs: ['bars']
  },
  sec_filings: {
    label: 'SEC Filings',
    description: 'Latest SEC filings (10-K, 10-Q, 8-K, etc.)',
    category: 'data_source',
    icon: '📄',
    inputs: ['tickers'],
    outputs: ['filings']
  },
  
  // Filters
  screener: {
    label: 'Screener',
    description: 'Filter stocks by criteria',
    category: 'filter',
    icon: '🔍',
    inputs: ['tickers'],
    outputs: ['filtered']
  },
  pattern_match: {
    label: 'Pattern Matcher',
    description: 'Find technical patterns',
    category: 'filter',
    icon: '📈',
    inputs: ['bars'],
    outputs: ['patterns']
  },
  top_movers: {
    label: 'Top Movers',
    description: 'Top gainers/losers',
    category: 'filter',
    icon: '🚀',
    inputs: ['tickers'],
    outputs: ['movers']
  },
  
  // Enrichment
  news: {
    label: 'News Feed',
    description: 'Benzinga news for tickers',
    category: 'enrichment',
    icon: '📰',
    inputs: ['tickers'],
    outputs: ['news']
  },
  insiders: {
    label: 'Insider Trading',
    description: 'Insider transactions',
    category: 'enrichment',
    icon: '👔',
    inputs: ['tickers'],
    outputs: ['transactions']
  },
  financials: {
    label: 'Financials',
    description: 'Financial statements & ratios',
    category: 'enrichment',
    icon: '💰',
    inputs: ['tickers'],
    outputs: ['financials']
  },
  
  // AI
  ai_research: {
    label: 'AI Research',
    description: 'Deep research with Grok',
    category: 'ai',
    icon: '🤖',
    inputs: ['tickers'],
    outputs: ['research']
  },
  synthetic_sectors: {
    label: 'Synthetic ETFs',
    description: 'AI-generated thematic sectors',
    category: 'ai',
    icon: '🧬',
    inputs: ['tickers'],
    outputs: ['sectors']
  },
  ai_analysis: {
    label: 'AI Analysis',
    description: 'Custom analysis with code',
    category: 'ai',
    icon: '🧠',
    inputs: ['data'],
    outputs: ['analysis']
  },
  
  // Output
  display: {
    label: 'Display',
    description: 'Show results in table/chart',
    category: 'output',
    icon: '📋',
    inputs: ['data'],
    outputs: []
  },
  alert: {
    label: 'Alert',
    description: 'Send notification',
    category: 'output',
    icon: '🔔',
    inputs: ['data'],
    outputs: []
  },
  export: {
    label: 'Export',
    description: 'Export to CSV/JSON',
    category: 'output',
    icon: '💾',
    inputs: ['data'],
    outputs: []
  }
}

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  data_source: '#3b82f6',  // Blue
  filter: '#8b5cf6',       // Purple
  enrichment: '#10b981',   // Green
  ai: '#f59e0b',           // Orange
  output: '#ef4444'        // Red
}
