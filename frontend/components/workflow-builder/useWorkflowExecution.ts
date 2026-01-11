'use client'

import { useState, useCallback, useRef } from 'react'
import { Workflow, WorkflowExecutionState, NodeExecutionResult } from './types'

interface UseWorkflowExecutionOptions {
    wsUrl?: string
    apiUrl?: string
}

export function useWorkflowExecution(options: UseWorkflowExecutionOptions = {}) {
    const {
        wsUrl = process.env.NEXT_PUBLIC_AI_AGENT_WS_URL || 'ws://localhost:8030/ws/chat/workflow',
        apiUrl = process.env.NEXT_PUBLIC_AI_AGENT_API_URL || 'http://localhost:8030'
    } = options

    const [state, setState] = useState<WorkflowExecutionState | null>(null)
    const wsRef = useRef<WebSocket | null>(null)
    const abortRef = useRef<AbortController | null>(null)

    const execute = useCallback(async (workflow: Workflow) => {
        // Initialize state
        setState({
            workflowId: workflow.id,
            status: 'running',
            results: {}
        })

        // Create abort controller
        abortRef.current = new AbortController()

        try {
            // Connect via WebSocket for real-time updates
            const ws = new WebSocket(wsUrl)
            wsRef.current = ws

            ws.onopen = () => {
                // Send workflow execution request
                ws.send(JSON.stringify({
                    type: 'execute_workflow',
                    workflow
                }))
            }

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data)

                switch (data.type) {
                    case 'node_started':
                        setState(prev => prev ? {
                            ...prev,
                            currentNodeId: data.nodeId,
                            results: {
                                ...prev.results,
                                [data.nodeId]: {
                                    nodeId: data.nodeId,
                                    status: 'running'
                                }
                            }
                        } : null)
                        break

                    case 'node_completed':
                        setState(prev => prev ? {
                            ...prev,
                            results: {
                                ...prev.results,
                                [data.nodeId]: {
                                    nodeId: data.nodeId,
                                    status: 'success',
                                    data: data.result,
                                    executionTime: data.executionTime
                                }
                            }
                        } : null)
                        break

                    case 'node_error':
                        setState(prev => prev ? {
                            ...prev,
                            results: {
                                ...prev.results,
                                [data.nodeId]: {
                                    nodeId: data.nodeId,
                                    status: 'error',
                                    error: data.error
                                }
                            }
                        } : null)
                        break

                    case 'workflow_completed':
                        setState(prev => prev ? {
                            ...prev,
                            status: 'completed'
                        } : null)
                        ws.close()
                        break

                    case 'workflow_error':
                        setState(prev => prev ? {
                            ...prev,
                            status: 'error'
                        } : null)
                        ws.close()
                        break
                }
            }

            ws.onerror = () => {
                // Fallback to HTTP API if WebSocket fails
                executeViaHttp(workflow)
            }

        } catch (error) {
            console.error('Workflow execution error:', error)
            setState(prev => prev ? { ...prev, status: 'error' } : null)
        }
    }, [wsUrl])

    const executeViaHttp = async (workflow: Workflow) => {
        try {
            const response = await fetch(`${apiUrl}/api/workflow-execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: workflow.name || 'Workflow',
                    nodes: workflow.nodes,
                    edges: workflow.edges
                }),
                signal: abortRef.current?.signal
            })

            if (!response.ok) throw new Error('Execution failed')

            const result = await response.json()

            // Update state with all results
            setState(prev => prev ? {
                ...prev,
                status: 'completed',
                results: result.nodeResults
            } : null)

        } catch (error) {
            if (error instanceof Error && error.name === 'AbortError') return
            setState(prev => prev ? { ...prev, status: 'error' } : null)
        }
    }

    const stop = useCallback(() => {
        // Close WebSocket
        if (wsRef.current) {
            wsRef.current.close()
            wsRef.current = null
        }

        // Abort HTTP request
        if (abortRef.current) {
            abortRef.current.abort()
            abortRef.current = null
        }

        setState(prev => prev ? { ...prev, status: 'idle' } : null)
    }, [])

    const reset = useCallback(() => {
        stop()
        setState(null)
    }, [stop])

    return {
        state,
        execute,
        stop,
        reset
    }
}

/**
 * Topologically sort workflow nodes for execution order
 */
export function getExecutionOrder(workflow: Workflow): string[] {
    const { nodes, edges } = workflow

    // Build adjacency list
    const adj: Record<string, string[]> = {}
    const inDegree: Record<string, number> = {}

    nodes.forEach(n => {
        adj[n.id] = []
        inDegree[n.id] = 0
    })

    edges.forEach(e => {
        adj[e.source].push(e.target)
        inDegree[e.target]++
    })

    // Kahn's algorithm
    const queue = nodes.filter(n => inDegree[n.id] === 0).map(n => n.id)
    const order: string[] = []

    while (queue.length > 0) {
        const nodeId = queue.shift()!
        order.push(nodeId)

        for (const neighbor of adj[nodeId]) {
            inDegree[neighbor]--
            if (inDegree[neighbor] === 0) {
                queue.push(neighbor)
            }
        }
    }

    return order
}
