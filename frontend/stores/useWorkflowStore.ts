/**
 * Workflow Store - Zustand
 * ========================
 * State management for Workflow Builder v2.
 * Manages workflows, nodes, edges, execution state, and undo/redo history.
 */

import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import type { Node, Edge } from 'reactflow'
import type { NodeResult, WorkflowDefinition, WorkflowNodeData } from '@/components/workflow-builder-v2/types'

// ============================================================================
// TYPES
// ============================================================================

export type ExecutionState = 'idle' | 'running' | 'completed' | 'error'

interface HistoryEntry {
  nodes: Node<WorkflowNodeData>[]
  edges: Edge[]
}

interface WorkflowState {
  // Core state
  workflows: WorkflowDefinition[]
  activeWorkflowId: string | null
  executionState: ExecutionState
  nodeResults: Record<string, NodeResult>

  // Selection
  selectedNodeId: string | null

  // Undo/redo
  past: HistoryEntry[]
  future: HistoryEntry[]

  // Workflow CRUD
  createWorkflow: (name: string, description?: string) => string
  deleteWorkflow: (id: string) => void
  updateWorkflow: (id: string, updates: Partial<Pick<WorkflowDefinition, 'name' | 'description' | 'nodes' | 'edges'>>) => void
  setActiveWorkflow: (id: string | null) => void

  // Node operations
  addNode: (node: Node<WorkflowNodeData>) => void
  removeNode: (nodeId: string) => void
  updateNodeConfig: (nodeId: string, config: Record<string, any>) => void
  setNodes: (nodes: Node<WorkflowNodeData>[]) => void
  setSelectedNode: (nodeId: string | null) => void

  // Edge operations
  addEdge: (edge: Edge) => void
  removeEdge: (edgeId: string) => void
  setEdges: (edges: Edge[]) => void

  // Execution
  startExecution: () => void
  updateNodeStatus: (nodeId: string, result: NodeResult) => void
  completeExecution: (status: 'completed' | 'error') => void
  resetExecution: () => void

  // Undo/Redo
  undo: () => void
  redo: () => void
  pushHistory: () => void

  // Helpers
  getActiveWorkflow: () => WorkflowDefinition | undefined
}

// ============================================================================
// HELPERS
// ============================================================================

const generateId = () => `wf_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`

const MAX_HISTORY = 50

// ============================================================================
// STORE
// ============================================================================

export const useWorkflowStore = create<WorkflowState>()(
  devtools(
    persist(
      (set, get) => ({
        // ---- Initial State ----
        workflows: [],
        activeWorkflowId: null,
        executionState: 'idle',
        nodeResults: {},
        selectedNodeId: null,
        past: [],
        future: [],

        // ---- Workflow CRUD ----
        createWorkflow: (name, description = '') => {
          const id = generateId()
          const now = new Date().toISOString()
          const workflow: WorkflowDefinition = {
            id,
            name,
            description,
            nodes: [],
            edges: [],
            createdAt: now,
            updatedAt: now,
          }
          set(
            (state) => ({
              workflows: [...state.workflows, workflow],
              activeWorkflowId: id,
              past: [],
              future: [],
            }),
            false,
            'createWorkflow'
          )
          return id
        },

        deleteWorkflow: (id) => {
          set(
            (state) => ({
              workflows: state.workflows.filter((w) => w.id !== id),
              activeWorkflowId: state.activeWorkflowId === id ? null : state.activeWorkflowId,
            }),
            false,
            'deleteWorkflow'
          )
        },

        updateWorkflow: (id, updates) => {
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === id ? { ...w, ...updates, updatedAt: new Date().toISOString() } : w
              ),
            }),
            false,
            'updateWorkflow'
          )
        },

        setActiveWorkflow: (id) => {
          set(
            { activeWorkflowId: id, past: [], future: [], selectedNodeId: null, nodeResults: {}, executionState: 'idle' },
            false,
            'setActiveWorkflow'
          )
        },

        // ---- Node Operations ----
        addNode: (node) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          get().pushHistory()
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? { ...w, nodes: [...w.nodes, node], updatedAt: new Date().toISOString() }
                  : w
              ),
            }),
            false,
            'addNode'
          )
        },

        removeNode: (nodeId) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          get().pushHistory()
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? {
                    ...w,
                    nodes: w.nodes.filter((n: any) => n.id !== nodeId),
                    edges: w.edges.filter((e: any) => e.source !== nodeId && e.target !== nodeId),
                    updatedAt: new Date().toISOString(),
                  }
                  : w
              ),
              selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
            }),
            false,
            'removeNode'
          )
        },

        updateNodeConfig: (nodeId, config) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? {
                    ...w,
                    nodes: w.nodes.map((n: any) =>
                      n.id === nodeId
                        ? { ...n, data: { ...n.data, config: { ...n.data.config, ...config } } }
                        : n
                    ),
                    updatedAt: new Date().toISOString(),
                  }
                  : w
              ),
            }),
            false,
            'updateNodeConfig'
          )
        },

        setNodes: (nodes) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId ? { ...w, nodes, updatedAt: new Date().toISOString() } : w
              ),
            }),
            false,
            'setNodes'
          )
        },

        setSelectedNode: (nodeId) => {
          set({ selectedNodeId: nodeId }, false, 'setSelectedNode')
        },

        // ---- Edge Operations ----
        addEdge: (edge) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          get().pushHistory()
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? { ...w, edges: [...w.edges, edge], updatedAt: new Date().toISOString() }
                  : w
              ),
            }),
            false,
            'addEdge'
          )
        },

        removeEdge: (edgeId) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          get().pushHistory()
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? { ...w, edges: w.edges.filter((e: any) => e.id !== edgeId), updatedAt: new Date().toISOString() }
                  : w
              ),
            }),
            false,
            'removeEdge'
          )
        },

        setEdges: (edges) => {
          const { activeWorkflowId } = get()
          if (!activeWorkflowId) return
          set(
            (state) => ({
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId ? { ...w, edges, updatedAt: new Date().toISOString() } : w
              ),
            }),
            false,
            'setEdges'
          )
        },

        // ---- Execution ----
        startExecution: () => {
          const workflow = get().getActiveWorkflow()
          if (!workflow) return
          const initialResults: Record<string, NodeResult> = {}
          workflow.nodes.forEach((n: any) => {
            initialResults[n.id] = { status: 'pending' }
          })
          set(
            { executionState: 'running', nodeResults: initialResults },
            false,
            'startExecution'
          )
        },

        updateNodeStatus: (nodeId, result) => {
          set(
            (state) => ({
              nodeResults: { ...state.nodeResults, [nodeId]: result },
            }),
            false,
            'updateNodeStatus'
          )
        },

        completeExecution: (status) => {
          set({ executionState: status }, false, 'completeExecution')
        },

        resetExecution: () => {
          set({ executionState: 'idle', nodeResults: {} }, false, 'resetExecution')
        },

        // ---- Undo / Redo ----
        pushHistory: () => {
          const workflow = get().getActiveWorkflow()
          if (!workflow) return
          set(
            (state) => ({
              past: [
                ...state.past.slice(-MAX_HISTORY),
                { nodes: JSON.parse(JSON.stringify(workflow.nodes)), edges: JSON.parse(JSON.stringify(workflow.edges)) },
              ],
              future: [],
            }),
            false,
            'pushHistory'
          )
        },

        undo: () => {
          const { past, activeWorkflowId } = get()
          if (past.length === 0 || !activeWorkflowId) return
          const workflow = get().getActiveWorkflow()
          if (!workflow) return
          const previous = past[past.length - 1]
          set(
            (state) => ({
              past: state.past.slice(0, -1),
              future: [
                { nodes: JSON.parse(JSON.stringify(workflow.nodes)), edges: JSON.parse(JSON.stringify(workflow.edges)) },
                ...state.future,
              ],
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? { ...w, nodes: previous.nodes, edges: previous.edges, updatedAt: new Date().toISOString() }
                  : w
              ),
            }),
            false,
            'undo'
          )
        },

        redo: () => {
          const { future, activeWorkflowId } = get()
          if (future.length === 0 || !activeWorkflowId) return
          const workflow = get().getActiveWorkflow()
          if (!workflow) return
          const next = future[0]
          set(
            (state) => ({
              future: state.future.slice(1),
              past: [
                ...state.past,
                { nodes: JSON.parse(JSON.stringify(workflow.nodes)), edges: JSON.parse(JSON.stringify(workflow.edges)) },
              ],
              workflows: state.workflows.map((w) =>
                w.id === activeWorkflowId
                  ? { ...w, nodes: next.nodes, edges: next.edges, updatedAt: new Date().toISOString() }
                  : w
              ),
            }),
            false,
            'redo'
          )
        },

        // ---- Helpers ----
        getActiveWorkflow: () => {
          const { workflows, activeWorkflowId } = get()
          return workflows.find((w) => w.id === activeWorkflowId)
        },
      }),
      {
        name: 'tradeul-workflow-v2',
        partialize: (state) => ({
          workflows: state.workflows,
          activeWorkflowId: state.activeWorkflowId,
        }),
      }
    ),
    { name: 'WorkflowStore' }
  )
)
