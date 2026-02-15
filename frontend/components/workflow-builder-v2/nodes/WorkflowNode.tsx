"use client"

import React, { memo, useMemo } from "react"
import { Handle, Position, type NodeProps } from "reactflow"
import {
  TrendingUp, Newspaper, FileText, Search, Code, Filter,
  BarChart3, Database, Rss, Zap, Receipt, AlertTriangle,
  SlidersHorizontal, Calendar, GitBranch, GitFork, GitMerge,
  Repeat, Bell, Clock, DollarSign, Table, LineChart, BellRing,
  Download, HelpCircle, Check, X, Loader2,
} from "lucide-react"
import { CATEGORY_COLORS, type WorkflowNodeData } from "../types"
import { useWorkflowStore } from "@/stores/useWorkflowStore"

const ICON_MAP: Record<string, React.ComponentType<{ className?: string; size?: number }>> = {
  TrendingUp, Newspaper, FileText, Search, Code, Filter,
  BarChart3, Database, Rss, Zap, Receipt, AlertTriangle,
  SlidersHorizontal, Calendar, GitBranch, GitFork, GitMerge,
  Repeat, Bell, Clock, DollarSign, Table, LineChart, BellRing,
  Download,
}

function getIcon(name: string) {
  return ICON_MAP[name] || HelpCircle
}

function StatusIndicator({ status }: { status?: "pending" | "running" | "success" | "error" }) {
  if (!status || status === "pending") return null
  if (status === "running") {
    return (
      <div className="absolute -top-1 -right-1">
        <Loader2 size={14} className="text-blue-400 animate-spin" />
      </div>
    )
  }
  if (status === "success") {
    return (
      <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center">
        <Check size={10} className="text-white" />
      </div>
    )
  }
  if (status === "error") {
    return (
      <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 flex items-center justify-center">
        <X size={10} className="text-white" />
      </div>
    )
  }
  return null
}

function WorkflowNodeComponent({ id, data, selected }: NodeProps<WorkflowNodeData>) {
  const nodeResult = useWorkflowStore((s) => s.nodeResults[id])
  const colors = CATEGORY_COLORS[data.category]
  const Icon = getIcon(data.icon)
  const status = nodeResult?.status
  const isRunning = status === "running"
  const isError = status === "error"

  const borderClass = useMemo(() => {
    if (isRunning) return colors.border + " animate-pulse"
    if (selected) return colors.border + " border-opacity-100"
    return colors.border + " border-opacity-50"
  }, [isRunning, selected, colors.border])

  return (
    <div
      className={
        "relative min-w-[180px] rounded-lg border-2 bg-zinc-900/95 backdrop-blur-sm shadow-lg transition-all duration-200 "
        + borderClass
        + (selected ? " shadow-xl ring-1 ring-white/10" : "")
        + (isRunning ? " shadow-blue-500/20 shadow-xl" : "")
      }
    >
      {data.inputs.map((input, i) => (
        <Handle
          key={"input-" + input}
          type="target"
          position={Position.Left}
          id={input}
          className="!w-3 !h-3 !bg-zinc-600 !border-2 !border-zinc-400 hover:!bg-zinc-400 transition-colors"
          style={{ top: ((i + 1) / (data.inputs.length + 1)) * 100 + "%" }}
        />
      ))}

      <div className={"flex items-center gap-2 px-3 py-2 rounded-t-md " + colors.bg}>
        <Icon size={16} className={colors.text} />
        <span className={"text-xs font-semibold uppercase tracking-wide " + colors.text}>
          {data.category}
        </span>
        <StatusIndicator status={status} />
      </div>

      <div className="px-3 py-2">
        <div className="text-sm font-medium text-zinc-100">{data.label}</div>
        <div className="text-xs text-zinc-500 mt-0.5 leading-tight">{data.description}</div>
        {nodeResult?.elapsed_ms !== undefined && (
          <div className="mt-1.5 text-[10px] text-zinc-500 font-mono">
            {nodeResult.elapsed_ms.toFixed(0)}ms
          </div>
        )}
        {isError && nodeResult?.error && (
          <div className="mt-1.5 text-[10px] text-red-400 bg-red-500/10 rounded px-1.5 py-0.5 truncate max-w-[200px]">
            {nodeResult.error}
          </div>
        )}
      </div>

      {data.outputs.map((output, i) => (
        <Handle
          key={"output-" + output}
          type="source"
          position={Position.Right}
          id={output}
          className="!w-3 !h-3 !bg-zinc-600 !border-2 !border-zinc-400 hover:!bg-zinc-400 transition-colors"
          style={{ top: ((i + 1) / (data.outputs.length + 1)) * 100 + "%" }}
        />
      ))}
    </div>
  )
}

export default memo(WorkflowNodeComponent)
