"use client"

/**
 * WorkflowCanvas - Main Workflow Builder v2 Component
 * ====================================================
 * Visual graph editor for LangGraph execution workflows.
 * Uses React Flow for the canvas with drag-and-drop node creation.
 */

import React, { useCallback, useRef, useMemo, useEffect, useState } from "react"
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  BackgroundVariant,
  MarkerType,
} from "reactflow"
import "reactflow/dist/style.css"

import {
  Play, Square, Save, ChevronDown, Plus, Undo2, Redo2,
  Workflow, FileDown, Upload,
} from "lucide-react"

import WorkflowNodeComponent from "./nodes/WorkflowNode"
import NodePalette from "./panels/NodePalette"
import NodeConfigPanel from "./panels/NodeConfigPanel"
import ExecutionPanel from "./panels/ExecutionPanel"
import { useWorkflowStore } from "@/stores/useWorkflowStore"
import { useWorkflowExecution } from "@/hooks/useWorkflowExecution"
import { CATEGORY_HEX, type CatalogNode, type WorkflowNodeData } from "./types"

// ============================================================================
// Constants
// ============================================================================

const NODE_TYPES = {
  workflowNode: WorkflowNodeComponent,
}

const EDGE_DEFAULTS = {
  type: "smoothstep",
  animated: false,
  style: { stroke: "#3f3f46", strokeWidth: 2 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#3f3f46", width: 16, height: 16 },
}

const WORKFLOW_TEMPLATES = [
  { name: "Gap Scanner Pipeline", description: "Scan gappers, enrich, filter, display" },
  { name: "News-Driven Research", description: "News trigger -> research -> alert" },
  { name: "Scheduled Screener", description: "Cron trigger -> screen -> export" },
]

// ============================================================================
// WorkflowCanvas
// ============================================================================

export default function WorkflowCanvas() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const [showTemplates, setShowTemplates] = useState(false)

  // Store
  const workflows = useWorkflowStore((s) => s.workflows)
  const activeWorkflowId = useWorkflowStore((s) => s.activeWorkflowId)
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId)
  const executionState = useWorkflowStore((s) => s.executionState)
  const createWorkflow = useWorkflowStore((s) => s.createWorkflow)
  const updateWorkflow = useWorkflowStore((s) => s.updateWorkflow)
  const setActiveWorkflow = useWorkflowStore((s) => s.setActiveWorkflow)
  const addNodeToStore = useWorkflowStore((s) => s.addNode)
  const addEdgeToStore = useWorkflowStore((s) => s.addEdge)
  const setNodesInStore = useWorkflowStore((s) => s.setNodes)
  const setEdgesInStore = useWorkflowStore((s) => s.setEdges)
  const setSelectedNode = useWorkflowStore((s) => s.setSelectedNode)
  const removeNode = useWorkflowStore((s) => s.removeNode)
  const undo = useWorkflowStore((s) => s.undo)
  const redo = useWorkflowStore((s) => s.redo)
  const pushHistory = useWorkflowStore((s) => s.pushHistory)
  const getActiveWorkflow = useWorkflowStore((s) => s.getActiveWorkflow)

  // Execution hook
  const { execute, stop, isRunning } = useWorkflowExecution()

  // Active workflow
  const activeWorkflow = useMemo(() => {
    return workflows.find((w) => w.id === activeWorkflowId)
  }, [workflows, activeWorkflowId])

  // React Flow state synced from store
  const [nodes, setNodes, onNodesChange] = useNodesState(activeWorkflow?.nodes || [])
  const [edges, setEdges, onEdgesChange] = useEdgesState(activeWorkflow?.edges || [])

  // Sync from store to React Flow
  useEffect(() => {
    if (activeWorkflow) {
      setNodes(activeWorkflow.nodes || [])
      setEdges(activeWorkflow.edges || [])
    } else {
      setNodes([])
      setEdges([])
    }
  }, [activeWorkflow, setNodes, setEdges])

  // Sync React Flow changes back to store
  const handleNodesChange = useCallback(
    (changes: any) => {
      onNodesChange(changes)
      // Debounced sync - only position changes
      const hasPositionChange = changes.some((c: any) => c.type === "position" && c.dragging === false)
      if (hasPositionChange && activeWorkflowId) {
        // Push history before position change
        pushHistory()
        setTimeout(() => {
          const wf = getActiveWorkflow()
          if (!wf) return
          // Get current nodes from rfInstance
          if (rfInstance) {
            const currentNodes = rfInstance.getNodes()
            setNodesInStore(currentNodes)
          }
        }, 0)
      }
    },
    [onNodesChange, activeWorkflowId, pushHistory, getActiveWorkflow, rfInstance, setNodesInStore]
  )

  // Edge connection
  const onConnect = useCallback(
    (connection: Connection) => {
      if (!activeWorkflowId) return
      const newEdge: Edge = {
        ...connection,
        id: `e_${connection.source}_${connection.sourceHandle || "default"}_${connection.target}_${connection.targetHandle || "default"}`,
        ...EDGE_DEFAULTS,
      } as Edge
      setEdges((eds) => addEdge(newEdge, eds))
      addEdgeToStore(newEdge)
    },
    [activeWorkflowId, setEdges, addEdgeToStore]
  )

  // Drag and drop from palette
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      if (!rfInstance || !activeWorkflowId) return

      const rawData = event.dataTransfer.getData("application/workflow-node")
      if (!rawData) return

      const catalogNode: CatalogNode = JSON.parse(rawData)

      const position = rfInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const nodeId = `node_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
      const newNode: Node<WorkflowNodeData> = {
        id: nodeId,
        type: "workflowNode",
        position,
        data: {
          label: catalogNode.label,
          description: catalogNode.description,
          category: catalogNode.category,
          icon: catalogNode.icon,
          config: catalogNode.config || {},
          inputs: catalogNode.inputs,
          outputs: catalogNode.outputs,
        },
      }

      setNodes((nds) => [...nds, newNode])
      addNodeToStore(newNode)
    },
    [rfInstance, activeWorkflowId, setNodes, addNodeToStore]
  )

  // Node selection
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNode(node.id)
    },
    [setSelectedNode]
  )

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
  }, [setSelectedNode])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Delete selected node
      if ((e.key === "Delete" || e.key === "Backspace") && selectedNodeId) {
        const target = e.target as HTMLElement
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return
        e.preventDefault()
        removeNode(selectedNodeId)
      }
      // Undo
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault()
        undo()
      }
      // Redo
      if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault()
        redo()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [selectedNodeId, removeNode, undo, redo])

  // Create new workflow if none
  const handleNewWorkflow = useCallback(() => {
    createWorkflow("Untitled Workflow")
  }, [createWorkflow])

  // Save workflow
  const handleSave = useCallback(() => {
    if (!activeWorkflowId || !rfInstance) return
    const currentNodes = rfInstance.getNodes()
    const currentEdges = rfInstance.getEdges()
    updateWorkflow(activeWorkflowId, { nodes: currentNodes, edges: currentEdges })
  }, [activeWorkflowId, rfInstance, updateWorkflow])

  // Workflow name change
  const handleNameChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!activeWorkflowId) return
      updateWorkflow(activeWorkflowId, { name: e.target.value })
    },
    [activeWorkflowId, updateWorkflow]
  )

  // MiniMap node color
  const minimapNodeColor = useCallback((node: Node) => {
    const data = node.data as WorkflowNodeData
    return CATEGORY_HEX[data?.category] || "#3f3f46"
  }, [])

  // Export workflow as JSON
  const handleExport = useCallback(() => {
    if (!activeWorkflow) return
    const blob = new Blob([JSON.stringify(activeWorkflow, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${activeWorkflow.name.replace(/\s+/g, "_").toLowerCase()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [activeWorkflow])

  // Import workflow from JSON
  const handleImport = useCallback(() => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = ".json"
    input.onchange = (e: any) => {
      const file = e.target.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (re) => {
        try {
          const data = JSON.parse(re.target?.result as string)
          if (data.name && data.nodes && data.edges) {
            const id = createWorkflow(data.name, data.description)
            updateWorkflow(id, { nodes: data.nodes, edges: data.edges })
          }
        } catch {
          // Invalid JSON
        }
      }
      reader.readAsText(file)
    }
    input.click()
  }, [createWorkflow, updateWorkflow])

  return (
    <div className="flex flex-col h-full bg-zinc-950">
      {/* Top Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-950/95 backdrop-blur-sm z-10">
        {/* Workflow icon */}
        <Workflow size={18} className="text-zinc-500" />

        {/* Workflow name */}
        {activeWorkflow ? (
          <input
            type="text"
            value={activeWorkflow.name}
            onChange={handleNameChange}
            className="bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-zinc-500 text-sm font-medium text-zinc-200 px-1 py-0.5 outline-none transition-colors w-48"
          />
        ) : (
          <span className="text-sm text-zinc-500">No workflow selected</span>
        )}

        {/* Separator */}
        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Undo/Redo */}
        <button onClick={undo} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors" title="Undo (Ctrl+Z)">
          <Undo2 size={14} />
        </button>
        <button onClick={redo} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors" title="Redo (Ctrl+Y)">
          <Redo2 size={14} />
        </button>

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        {/* Run / Stop */}
        {isRunning ? (
          <button
            onClick={stop}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-medium transition-colors"
          >
            <Square size={12} />
            Stop
          </button>
        ) : (
          <button
            onClick={execute}
            disabled={!activeWorkflow || executionState === "running"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={12} />
            Run
          </button>
        )}

        {/* Save */}
        <button
          onClick={handleSave}
          disabled={!activeWorkflow}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-colors disabled:opacity-40"
        >
          <Save size={12} />
          Save
        </button>

        {/* Templates dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-colors"
          >
            Templates
            <ChevronDown size={12} />
          </button>
          {showTemplates && (
            <div className="absolute top-full left-0 mt-1 w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl z-50">
              {WORKFLOW_TEMPLATES.map((tpl) => (
                <button
                  key={tpl.name}
                  onClick={() => {
                    createWorkflow(tpl.name, tpl.description)
                    setShowTemplates(false)
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-zinc-800 transition-colors first:rounded-t-lg last:rounded-b-lg"
                >
                  <div className="text-xs font-medium text-zinc-200">{tpl.name}</div>
                  <div className="text-[10px] text-zinc-500">{tpl.description}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Import/Export */}
        <button onClick={handleImport} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors" title="Import workflow">
          <Upload size={14} />
        </button>
        <button onClick={handleExport} disabled={!activeWorkflow} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40" title="Export workflow">
          <FileDown size={14} />
        </button>

        {/* New workflow */}
        <button
          onClick={handleNewWorkflow}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-medium transition-colors"
        >
          <Plus size={12} />
          New
        </button>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar - Node Palette */}
        <NodePalette />

        {/* Canvas */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 relative" ref={reactFlowWrapper}>
            {activeWorkflow ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={handleNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onInit={setRfInstance}
                onDragOver={onDragOver}
                onDrop={onDrop}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                nodeTypes={NODE_TYPES}
                defaultEdgeOptions={EDGE_DEFAULTS}
                fitView
                snapToGrid
                snapGrid={[16, 16]}
                minZoom={0.2}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
                className="bg-zinc-950"
              >
                <Background
                  variant={BackgroundVariant.Dots}
                  gap={20}
                  size={1}
                  color="#27272a"
                />
                <Controls
                  className="!bg-zinc-900 !border-zinc-700 !rounded-lg !shadow-lg [&>button]:!bg-zinc-800 [&>button]:!border-zinc-700 [&>button]:!text-zinc-400 [&>button:hover]:!bg-zinc-700"
                />
                <MiniMap
                  nodeColor={minimapNodeColor}
                  maskColor="rgba(0, 0, 0, 0.7)"
                  className="!bg-zinc-900 !border-zinc-700 !rounded-lg"
                  pannable
                  zoomable
                />
              </ReactFlow>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <Workflow size={48} className="text-zinc-700 mb-4" />
                <h2 className="text-lg font-semibold text-zinc-400 mb-2">No Workflow Selected</h2>
                <p className="text-sm text-zinc-600 mb-4 max-w-sm">
                  Create a new workflow or select an existing one to start building your LangGraph execution pipeline.
                </p>
                <button
                  onClick={handleNewWorkflow}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-sm font-medium transition-colors"
                >
                  <Plus size={16} />
                  Create Workflow
                </button>
              </div>
            )}
          </div>

          {/* Bottom - Execution Panel */}
          <ExecutionPanel />
        </div>

        {/* Right sidebar - Node Config */}
        {selectedNodeId && (
          <NodeConfigPanel onClose={() => setSelectedNode(null)} />
        )}
      </div>
    </div>
  )
}
