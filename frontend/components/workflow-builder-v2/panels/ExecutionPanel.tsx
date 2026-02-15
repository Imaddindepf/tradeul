"use client"

import React, { useState, useMemo } from "react"
import { ChevronUp, ChevronDown, Clock, Check, X, Loader2, AlertCircle } from "lucide-react"
import { useWorkflowStore } from "@/stores/useWorkflowStore"
import type { NodeResult } from "../types"

function StatusIcon({ status }: { status: NodeResult["status"] }) {
  switch (status) {
    case "pending":
      return <Clock size={12} className="text-zinc-500" />
    case "running":
      return <Loader2 size={12} className="text-blue-400 animate-spin" />
    case "success":
      return <Check size={12} className="text-emerald-400" />
    case "error":
      return <X size={12} className="text-red-400" />
    default:
      return null
  }
}

function StatusBadge({ status }: { status: NodeResult["status"] }) {
  const styles: Record<string, string> = {
    pending: "bg-zinc-800 text-zinc-500",
    running: "bg-blue-500/10 text-blue-400",
    success: "bg-emerald-500/10 text-emerald-400",
    error: "bg-red-500/10 text-red-400",
  }
  return (
    <span className={"px-1.5 py-0.5 rounded text-[10px] font-medium " + (styles[status] || "")}>
      {status}
    </span>
  )
}

function NodeResultRow({
  nodeId,
  result,
  nodeName,
}: {
  nodeId: string
  result: NodeResult
  nodeName: string
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border border-zinc-800 rounded-md overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-zinc-800/50 transition-colors"
      >
        <StatusIcon status={result.status} />
        <span className="text-xs text-zinc-300 font-medium flex-1 truncate">{nodeName}</span>
        <StatusBadge status={result.status} />
        {result.elapsed_ms !== undefined && (
          <span className="text-[10px] text-zinc-500 font-mono">{result.elapsed_ms.toFixed(0)}ms</span>
        )}
        {(result.data || result.error) && (
          expanded ? <ChevronUp size={12} className="text-zinc-500" /> : <ChevronDown size={12} className="text-zinc-500" />
        )}
      </button>
      {expanded && (result.data || result.error) && (
        <div className="px-3 py-2 border-t border-zinc-800 bg-zinc-900/50">
          {result.error && (
            <div className="flex items-start gap-1.5 mb-2">
              <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
              <span className="text-[11px] text-red-400">{result.error}</span>
            </div>
          )}
          {result.data && (
            <pre className="text-[10px] text-zinc-400 font-mono overflow-x-auto max-h-32 overflow-y-auto">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

export default function ExecutionPanel() {
  const [expanded, setExpanded] = useState(false)
  const executionState = useWorkflowStore((s) => s.executionState)
  const nodeResults = useWorkflowStore((s) => s.nodeResults)
  const workflow = useWorkflowStore((s) => s.getActiveWorkflow())

  const totalElapsed = useMemo(() => {
    return Object.values(nodeResults).reduce((sum, r) => sum + (r.elapsed_ms || 0), 0)
  }, [nodeResults])

  const counts = useMemo(() => {
    const entries = Object.values(nodeResults)
    return {
      total: entries.length,
      pending: entries.filter((r) => r.status === "pending").length,
      running: entries.filter((r) => r.status === "running").length,
      success: entries.filter((r) => r.status === "success").length,
      error: entries.filter((r) => r.status === "error").length,
    }
  }, [nodeResults])

  if (executionState === "idle" && Object.keys(nodeResults).length === 0) return null

  const nodeNameMap: Record<string, string> = {}
  if (workflow) {
    workflow.nodes.forEach((n: any) => {
      nodeNameMap[n.id] = n.data?.label || n.id
    })
  }

  return (
    <div className="bg-zinc-950 border-t border-zinc-800">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-3 w-full px-4 py-2 hover:bg-zinc-900/50 transition-colors"
      >
        {expanded ? <ChevronDown size={14} className="text-zinc-500" /> : <ChevronUp size={14} className="text-zinc-500" />}
        <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          Execution
        </span>

        {executionState === "running" && (
          <Loader2 size={12} className="text-blue-400 animate-spin" />
        )}
        {executionState === "completed" && (
          <Check size={12} className="text-emerald-400" />
        )}
        {executionState === "error" && (
          <AlertCircle size={12} className="text-red-400" />
        )}

        <div className="flex items-center gap-2 ml-auto text-[10px]">
          {counts.success > 0 && (
            <span className="text-emerald-400">{counts.success} passed</span>
          )}
          {counts.error > 0 && (
            <span className="text-red-400">{counts.error} failed</span>
          )}
          {counts.running > 0 && (
            <span className="text-blue-400">{counts.running} running</span>
          )}
          {counts.pending > 0 && (
            <span className="text-zinc-500">{counts.pending} pending</span>
          )}
          {totalElapsed > 0 && (
            <span className="text-zinc-500 font-mono ml-2">
              Total: {totalElapsed.toFixed(0)}ms
            </span>
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 py-3 space-y-2 max-h-64 overflow-y-auto border-t border-zinc-800">
          {Object.entries(nodeResults).map(([nodeId, result]) => (
            <NodeResultRow
              key={nodeId}
              nodeId={nodeId}
              result={result}
              nodeName={nodeNameMap[nodeId] || nodeId}
            />
          ))}
        </div>
      )}
    </div>
  )
}
