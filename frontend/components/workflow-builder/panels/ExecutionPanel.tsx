'use client'

import React from 'react'
import { WorkflowExecutionState, NodeExecutionResult } from '../types'
import { Play, Square, RotateCcw, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ExecutionPanelProps {
  state: WorkflowExecutionState | null
  onRun: () => void
  onStop: () => void
  onReset: () => void
}

const ExecutionPanel: React.FC<ExecutionPanelProps> = ({ state, onRun, onStop, onReset }) => {
  const [expandedNodes, setExpandedNodes] = React.useState<Set<string>>(new Set())
  
  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }
  
  const statusLabels = {
    idle: { label: 'Ready', color: 'text-zinc-400' },
    running: { label: 'Running...', color: 'text-blue-400' },
    completed: { label: 'Completed', color: 'text-green-400' },
    error: { label: 'Error', color: 'text-red-400' }
  }
  
  const nodeResults = state ? Object.values(state.results) : []
  const totalTime = nodeResults.reduce((sum, r) => sum + (r.executionTime || 0), 0)
  
  return (
    <div className="h-64 bg-zinc-950 border-t border-zinc-800 flex flex-col">
      {/* Header */}
      <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-4">
        <h3 className="font-bold text-white">Execution</h3>
        
        {state && (
          <span className={cn('text-sm', statusLabels[state.status].color)}>
            {statusLabels[state.status].label}
          </span>
        )}
        
        {totalTime > 0 && (
          <span className="text-xs text-zinc-500">
            {(totalTime / 1000).toFixed(2)}s total
          </span>
        )}
        
        <div className="flex-1" />
        
        <div className="flex items-center gap-2">
          {state?.status === 'running' ? (
            <button
              onClick={onStop}
              className="flex items-center gap-1 px-3 py-1 bg-red-600 hover:bg-red-700 
                         text-white rounded text-sm font-medium transition-colors"
            >
              <Square className="w-3 h-3" />
              Stop
            </button>
          ) : (
            <button
              onClick={onRun}
              className="flex items-center gap-1 px-3 py-1 bg-green-600 hover:bg-green-700 
                         text-white rounded text-sm font-medium transition-colors"
            >
              <Play className="w-3 h-3" />
              Run
            </button>
          )}
          
          <button
            onClick={onReset}
            className="flex items-center gap-1 px-3 py-1 bg-zinc-700 hover:bg-zinc-600 
                       text-white rounded text-sm font-medium transition-colors"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>
      
      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {nodeResults.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
            Click "Run" to execute the workflow
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {nodeResults.map((result) => (
              <div key={result.nodeId} className="hover:bg-zinc-900/50">
                <button
                  onClick={() => toggleNode(result.nodeId)}
                  className="w-full px-4 py-2 flex items-center gap-2 text-left"
                >
                  {expandedNodes.has(result.nodeId) ? (
                    <ChevronDown className="w-4 h-4 text-zinc-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-zinc-500" />
                  )}
                  
                  <span className={cn(
                    'w-2 h-2 rounded-full',
                    result.status === 'pending' && 'bg-zinc-600',
                    result.status === 'running' && 'bg-blue-500 animate-pulse',
                    result.status === 'success' && 'bg-green-500',
                    result.status === 'error' && 'bg-red-500'
                  )} />
                  
                  <span className="text-sm text-white font-mono">{result.nodeId}</span>
                  
                  {result.executionTime && (
                    <span className="text-xs text-zinc-500">
                      {result.executionTime}ms
                    </span>
                  )}
                  
                  {result.data?.count && (
                    <span className="text-xs text-zinc-400">
                      {result.data.count} items
                    </span>
                  )}
                </button>
                
                {expandedNodes.has(result.nodeId) && (
                  <div className="px-10 pb-3">
                    {result.error && (
                      <pre className="text-xs text-red-400 bg-red-900/20 p-2 rounded overflow-x-auto">
                        {result.error}
                      </pre>
                    )}
                    
                    {result.data && (
                      <pre className="text-xs text-zinc-300 bg-zinc-900 p-2 rounded overflow-x-auto max-h-32">
                        {JSON.stringify(result.data, null, 2).slice(0, 1000)}
                        {JSON.stringify(result.data).length > 1000 && '...'}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default ExecutionPanel
