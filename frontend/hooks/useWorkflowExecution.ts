"use client"

/**
 * useWorkflowExecution Hook
 * ==========================
 * Connects to ai-agent-v4 WebSocket for workflow execution.
 * Sends workflow definition and processes streaming events.
 */

import { useCallback, useRef, useState } from "react"
import { useWorkflowStore } from "@/stores/useWorkflowStore"
import type { NodeResult } from "@/components/workflow-builder-v2/types"

const WS_URL = process.env.NEXT_PUBLIC_AI_AGENT_V4_WS_URL || "wss://agent.tradeul.com/v4/ws/chat/workflow"

interface WorkflowEvent {
  type: "node_started" | "node_completed" | "node_error" | "workflow_completed" | "workflow_error"
  node_id?: string
  data?: any
  error?: string
  elapsed_ms?: number
  status?: string
}

export function useWorkflowExecution() {
  const wsRef = useRef<WebSocket | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const startExecution = useWorkflowStore((s) => s.startExecution)
  const updateNodeStatus = useWorkflowStore((s) => s.updateNodeStatus)
  const completeExecution = useWorkflowStore((s) => s.completeExecution)
  const getActiveWorkflow = useWorkflowStore((s) => s.getActiveWorkflow)

  const execute = useCallback(() => {
    const workflow = getActiveWorkflow()
    if (!workflow) return

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close()
    }

    setIsRunning(true)
    startExecution()

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      const payload = {
        type: "execute_workflow",
        workflow: {
          id: workflow.id,
          name: workflow.name,
          nodes: workflow.nodes.map((n: any) => ({
            id: n.id,
            type: n.type,
            data: n.data,
          })),
          edges: workflow.edges.map((e: any) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle,
            targetHandle: e.targetHandle,
          })),
        },
      }
      ws.send(JSON.stringify(payload))
    }

    ws.onmessage = (event) => {
      try {
        const msg: WorkflowEvent = JSON.parse(event.data)

        switch (msg.type) {
          case "node_started": {
            if (msg.node_id) {
              const result: NodeResult = { status: "running" }
              updateNodeStatus(msg.node_id, result)
            }
            break
          }
          case "node_completed": {
            if (msg.node_id) {
              const result: NodeResult = {
                status: "success",
                data: msg.data,
                elapsed_ms: msg.elapsed_ms,
              }
              updateNodeStatus(msg.node_id, result)
            }
            break
          }
          case "node_error": {
            if (msg.node_id) {
              const result: NodeResult = {
                status: "error",
                error: msg.error,
                elapsed_ms: msg.elapsed_ms,
              }
              updateNodeStatus(msg.node_id, result)
            }
            break
          }
          case "workflow_completed": {
            completeExecution("completed")
            setIsRunning(false)
            ws.close()
            break
          }
          case "workflow_error": {
            completeExecution("error")
            setIsRunning(false)
            ws.close()
            break
          }
        }
      } catch {
        // Ignore non-JSON messages
      }
    }

    ws.onerror = () => {
      completeExecution("error")
      setIsRunning(false)
    }

    ws.onclose = () => {
      setIsRunning(false)
      wsRef.current = null
    }
  }, [getActiveWorkflow, startExecution, updateNodeStatus, completeExecution])

  const stop = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    completeExecution("error")
    setIsRunning(false)
  }, [completeExecution])

  const results = useWorkflowStore((s) => s.nodeResults)

  return { execute, stop, isRunning, results }
}
