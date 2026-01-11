'use client'

import React from 'react'
import { Node } from 'reactflow'
import { WorkflowNodeData, NODE_DEFINITIONS, CATEGORY_COLORS } from '../types'
import { X } from 'lucide-react'

interface NodeConfigProps {
  node: Node<WorkflowNodeData> | null
  onUpdate: (nodeId: string, config: Record<string, any>) => void
  onClose: () => void
  onDelete: (nodeId: string) => void
}

// Config schemas for each node type
const NODE_CONFIG_SCHEMAS: Record<string, Array<{
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'multiselect' | 'boolean'
  options?: { value: string; label: string }[]
  placeholder?: string
  default?: any
}>> = {
  scanner: [
    { key: 'category', label: 'Category', type: 'select', options: [
      { value: 'all', label: 'All Tickers' },
      { value: 'winners', label: 'Winners' },
      { value: 'losers', label: 'Losers' },
      { value: 'gappers', label: 'Gappers' }
    ], default: 'all' }
  ],
  historical: [
    { key: 'symbol', label: 'Symbol', type: 'text', placeholder: 'AAPL, NVDA...' },
    { key: 'date', label: 'Date', type: 'text', placeholder: 'today, yesterday, 2026-01-09' },
    { key: 'interval', label: 'Interval', type: 'select', options: [
      { value: '1min', label: '1 Minute' },
      { value: '5min', label: '5 Minutes' },
      { value: '15min', label: '15 Minutes' }
    ], default: '1min' }
  ],
  sec_filings: [
    { key: 'form_type', label: 'Form Type', type: 'multiselect', options: [
      { value: '10-K', label: '10-K (Annual)' },
      { value: '10-Q', label: '10-Q (Quarterly)' },
      { value: '8-K', label: '8-K (Current)' },
      { value: '4', label: 'Form 4 (Insider)' },
      { value: 'S-1', label: 'S-1 (IPO)' }
    ] },
    { key: 'days_back', label: 'Days Back', type: 'number', default: 7 }
  ],
  screener: [
    { key: 'min_price', label: 'Min Price ($)', type: 'number', default: 0 },
    { key: 'max_price', label: 'Max Price ($)', type: 'number', default: 1000 },
    { key: 'min_volume', label: 'Min Volume', type: 'number', default: 100000 },
    { key: 'min_change', label: 'Min Change (%)', type: 'number', default: -100 },
    { key: 'max_change', label: 'Max Change (%)', type: 'number', default: 100 }
  ],
  pattern_match: [
    { key: 'patterns', label: 'Patterns', type: 'multiselect', options: [
      { value: 'double_bottom', label: 'Double Bottom' },
      { value: 'double_top', label: 'Double Top' },
      { value: 'head_shoulders', label: 'Head & Shoulders' },
      { value: 'triangle', label: 'Triangle' },
      { value: 'flag', label: 'Flag' },
      { value: 'wedge', label: 'Wedge' }
    ] },
    { key: 'timeframe', label: 'Timeframe', type: 'select', options: [
      { value: 'intraday', label: 'Intraday' },
      { value: 'daily', label: 'Daily' },
      { value: 'weekly', label: 'Weekly' }
    ], default: 'daily' }
  ],
  top_movers: [
    { key: 'direction', label: 'Direction', type: 'select', options: [
      { value: 'gainers', label: 'Top Gainers' },
      { value: 'losers', label: 'Top Losers' },
      { value: 'both', label: 'Both' }
    ], default: 'gainers' },
    { key: 'limit', label: 'Limit', type: 'number', default: 20 }
  ],
  news: [
    { key: 'sentiment', label: 'Sentiment', type: 'select', options: [
      { value: 'all', label: 'All' },
      { value: 'positive', label: 'Positive' },
      { value: 'negative', label: 'Negative' }
    ], default: 'all' },
    { key: 'hours_back', label: 'Hours Back', type: 'number', default: 24 }
  ],
  insiders: [
    { key: 'transaction_type', label: 'Transaction', type: 'select', options: [
      { value: 'all', label: 'All' },
      { value: 'buy', label: 'Buys Only' },
      { value: 'sell', label: 'Sells Only' }
    ], default: 'all' },
    { key: 'min_value', label: 'Min Value ($)', type: 'number', default: 10000 }
  ],
  financials: [
    { key: 'metrics', label: 'Metrics', type: 'multiselect', options: [
      { value: 'revenue', label: 'Revenue' },
      { value: 'earnings', label: 'Earnings' },
      { value: 'pe_ratio', label: 'P/E Ratio' },
      { value: 'market_cap', label: 'Market Cap' },
      { value: 'debt_equity', label: 'Debt/Equity' }
    ] }
  ],
  ai_research: [
    { key: 'query', label: 'Research Query', type: 'text', placeholder: 'Why is this stock moving?' },
    { key: 'include_news', label: 'Include News', type: 'boolean', default: true },
    { key: 'include_social', label: 'Include X.com', type: 'boolean', default: true }
  ],
  synthetic_sectors: [
    { key: 'date', label: 'Date', type: 'text', placeholder: 'today, yesterday', default: 'today' },
    { key: 'min_tickers', label: 'Min Tickers/Sector', type: 'number', default: 3 }
  ],
  ai_analysis: [
    { key: 'prompt', label: 'Analysis Prompt', type: 'text', placeholder: 'Calculate RSI and find oversold stocks...' },
    { key: 'output_type', label: 'Output', type: 'select', options: [
      { value: 'table', label: 'Table' },
      { value: 'chart', label: 'Chart' },
      { value: 'both', label: 'Both' }
    ], default: 'table' }
  ],
  display: [
    { key: 'title', label: 'Title', type: 'text', placeholder: 'Results' },
    { key: 'type', label: 'Display Type', type: 'select', options: [
      { value: 'table', label: 'Table' },
      { value: 'chart', label: 'Chart' },
      { value: 'card', label: 'Cards' }
    ], default: 'table' }
  ],
  alert: [
    { key: 'channel', label: 'Channel', type: 'select', options: [
      { value: 'notification', label: 'Browser Notification' },
      { value: 'email', label: 'Email' },
      { value: 'discord', label: 'Discord' }
    ], default: 'notification' },
    { key: 'condition', label: 'Condition', type: 'text', placeholder: 'When count > 0' }
  ],
  export: [
    { key: 'format', label: 'Format', type: 'select', options: [
      { value: 'csv', label: 'CSV' },
      { value: 'json', label: 'JSON' },
      { value: 'xlsx', label: 'Excel' }
    ], default: 'csv' },
    { key: 'filename', label: 'Filename', type: 'text', placeholder: 'export' }
  ]
}

const NodeConfig: React.FC<NodeConfigProps> = ({ node, onUpdate, onClose, onDelete }) => {
  if (!node) return null
  
  const definition = NODE_DEFINITIONS[node.type || '']
  const schema = NODE_CONFIG_SCHEMAS[node.type || ''] || []
  const categoryColor = CATEGORY_COLORS[definition?.category || 'output']
  
  const handleChange = (key: string, value: any) => {
    onUpdate(node.id, { ...node.data.config, [key]: value })
  }
  
  return (
    <div className="w-80 bg-zinc-950 border-l border-zinc-800 flex flex-col">
      {/* Header */}
      <div 
        className="p-4 border-b border-zinc-800 flex items-center gap-3"
        style={{ backgroundColor: `${categoryColor}15` }}
      >
        <span className="text-2xl">{definition?.icon}</span>
        <div className="flex-1">
          <h3 className="font-bold text-white">{definition?.label}</h3>
          <p className="text-xs text-zinc-400">{definition?.description}</p>
        </div>
        <button 
          onClick={onClose}
          className="p-1 hover:bg-zinc-800 rounded"
        >
          <X className="w-4 h-4 text-zinc-400" />
        </button>
      </div>
      
      {/* Config Form */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {schema.map((field) => (
          <div key={field.key} className="space-y-1">
            <label className="text-sm font-medium text-zinc-300">
              {field.label}
            </label>
            
            {field.type === 'text' && (
              <input
                type="text"
                value={node.data.config[field.key] || ''}
                onChange={(e) => handleChange(field.key, e.target.value)}
                placeholder={field.placeholder}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg
                           text-white text-sm placeholder:text-zinc-500
                           focus:outline-none focus:border-blue-500"
              />
            )}
            
            {field.type === 'number' && (
              <input
                type="number"
                value={node.data.config[field.key] ?? field.default ?? ''}
                onChange={(e) => handleChange(field.key, Number(e.target.value))}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg
                           text-white text-sm
                           focus:outline-none focus:border-blue-500"
              />
            )}
            
            {field.type === 'select' && (
              <select
                value={node.data.config[field.key] ?? field.default ?? ''}
                onChange={(e) => handleChange(field.key, e.target.value)}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg
                           text-white text-sm
                           focus:outline-none focus:border-blue-500"
              >
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            )}
            
            {field.type === 'multiselect' && (
              <div className="space-y-1">
                {field.options?.map((opt) => (
                  <label 
                    key={opt.value} 
                    className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={(node.data.config[field.key] || []).includes(opt.value)}
                      onChange={(e) => {
                        const current = node.data.config[field.key] || []
                        const updated = e.target.checked
                          ? [...current, opt.value]
                          : current.filter((v: string) => v !== opt.value)
                        handleChange(field.key, updated)
                      }}
                      className="rounded bg-zinc-800 border-zinc-600"
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            )}
            
            {field.type === 'boolean' && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={node.data.config[field.key] ?? field.default ?? false}
                  onChange={(e) => handleChange(field.key, e.target.checked)}
                  className="rounded bg-zinc-800 border-zinc-600"
                />
                <span className="text-sm text-zinc-300">Enabled</span>
              </label>
            )}
          </div>
        ))}
        
        {schema.length === 0 && (
          <p className="text-sm text-zinc-500 text-center py-4">
            No configuration options for this node
          </p>
        )}
      </div>
      
      {/* Actions */}
      <div className="p-4 border-t border-zinc-800 space-y-2">
        <button
          onClick={() => onDelete(node.id)}
          className="w-full px-4 py-2 bg-red-900/30 hover:bg-red-900/50 
                     text-red-400 rounded-lg text-sm font-medium transition-colors"
        >
          Delete Node
        </button>
      </div>
    </div>
  )
}

export default NodeConfig
