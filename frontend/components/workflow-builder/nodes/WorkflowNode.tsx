'use client'

import React, { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { WorkflowNodeData, CATEGORY_COLORS, NodeExecutionResult } from '../types'
import { cn } from '@/lib/utils'

interface WorkflowNodeProps extends NodeProps<WorkflowNodeData & { executionResult?: NodeExecutionResult }> {}

const WorkflowNode = memo(({ data, selected }: WorkflowNodeProps) => {
  const categoryColor = CATEGORY_COLORS[data.category]
  const result = data.executionResult
  
  const statusColors = {
    pending: 'bg-zinc-600',
    running: 'bg-blue-500 animate-pulse',
    success: 'bg-green-500',
    error: 'bg-red-500'
  }
  
  return (
    <div
      className={cn(
        'relative bg-zinc-900 border rounded-lg shadow-xl min-w-[200px] transition-all',
        selected ? 'border-white ring-2 ring-white/20' : 'border-zinc-700',
        result?.status === 'running' && 'ring-2 ring-blue-500/50'
      )}
      style={{ borderLeftColor: categoryColor, borderLeftWidth: 3 }}
    >
      {/* Input Handles */}
      {data.inputs.map((input, idx) => (
        <Handle
          key={`input-${idx}`}
          type="target"
          position={Position.Left}
          id={input}
          className="!w-3 !h-3 !bg-zinc-400 !border-2 !border-zinc-900"
          style={{ top: `${30 + idx * 20}%` }}
        />
      ))}
      
      {/* Header */}
      <div 
        className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2"
        style={{ backgroundColor: `${categoryColor}15` }}
      >
        <span className="text-lg">{data.icon}</span>
        <span className="font-medium text-white text-sm">{data.label}</span>
        
        {/* Status indicator */}
        {result && (
          <div className={cn(
            'w-2 h-2 rounded-full ml-auto',
            statusColors[result.status]
          )} />
        )}
      </div>
      
      {/* Body */}
      <div className="px-3 py-2">
        <p className="text-xs text-zinc-400">{data.description}</p>
        
        {/* Config preview */}
        {Object.keys(data.config || {}).length > 0 && (
          <div className="mt-2 pt-2 border-t border-zinc-800">
            {Object.entries(data.config).slice(0, 3).map(([key, value]) => (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-zinc-500">{key}:</span>
                <span className="text-zinc-300 font-mono">{String(value).slice(0, 15)}</span>
              </div>
            ))}
          </div>
        )}
        
        {/* Execution result preview */}
        {result?.status === 'success' && result.data && (
          <div className="mt-2 pt-2 border-t border-zinc-800">
            <div className="text-xs text-green-400">
              ✓ {result.executionTime}ms
              {result.data.count && ` • ${result.data.count} items`}
            </div>
          </div>
        )}
        
        {result?.status === 'error' && (
          <div className="mt-2 pt-2 border-t border-zinc-800">
            <div className="text-xs text-red-400 truncate">
              ✗ {result.error?.slice(0, 50)}
            </div>
          </div>
        )}
      </div>
      
      {/* Output Handles */}
      {data.outputs.map((output, idx) => (
        <Handle
          key={`output-${idx}`}
          type="source"
          position={Position.Right}
          id={output}
          className="!w-3 !h-3 !bg-white !border-2 !border-zinc-900"
          style={{ top: `${30 + idx * 20}%` }}
        />
      ))}
    </div>
  )
})

WorkflowNode.displayName = 'WorkflowNode'

export default WorkflowNode
