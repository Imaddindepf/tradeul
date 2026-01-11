'use client'

import React, { useCallback, useRef, useState } from 'react'
import ReactFlow, {
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Connection,
  addEdge,
  useNodesState,
  useEdgesState,
  OnConnect,
  NodeTypes,
  BackgroundVariant
} from 'reactflow'
import 'reactflow/dist/style.css'

import WorkflowNode from './nodes/WorkflowNode'
import NodePalette from './panels/NodePalette'
import NodeConfig from './panels/NodeConfig'
import ExecutionPanel from './panels/ExecutionPanel'
import TemplatesPanel from './panels/TemplatesPanel'
import { 
  WorkflowNodeData, 
  NODE_DEFINITIONS, 
  CATEGORY_COLORS,
  WorkflowExecutionState,
  Workflow
} from './types'
import { Save, FolderOpen, Plus, Trash2, LayoutTemplate } from 'lucide-react'

const nodeTypes: NodeTypes = {
  custom: WorkflowNode
}

// Initial demo workflow
const initialNodes: Node<WorkflowNodeData>[] = [
  {
    id: 'scanner-1',
    type: 'custom',
    position: { x: 50, y: 200 },
    data: { ...NODE_DEFINITIONS.scanner, config: { category: 'winners' } }
  },
  {
    id: 'screener-1',
    type: 'custom',
    position: { x: 320, y: 150 },
    data: { ...NODE_DEFINITIONS.screener, config: { min_volume: 500000, min_change: 5 } }
  },
  {
    id: 'news-1',
    type: 'custom',
    position: { x: 590, y: 100 },
    data: { ...NODE_DEFINITIONS.news, config: { hours_back: 4 } }
  },
  {
    id: 'insiders-1',
    type: 'custom',
    position: { x: 590, y: 280 },
    data: { ...NODE_DEFINITIONS.insiders, config: { transaction_type: 'buy' } }
  },
  {
    id: 'display-1',
    type: 'custom',
    position: { x: 860, y: 200 },
    data: { ...NODE_DEFINITIONS.display, config: { title: 'Hot Stocks with Catalysts', type: 'table' } }
  }
]

const initialEdges: Edge[] = [
  { id: 'e1', source: 'scanner-1', target: 'screener-1', sourceHandle: 'tickers', targetHandle: 'tickers' },
  { id: 'e2', source: 'screener-1', target: 'news-1', sourceHandle: 'filtered', targetHandle: 'tickers' },
  { id: 'e3', source: 'screener-1', target: 'insiders-1', sourceHandle: 'filtered', targetHandle: 'tickers' },
  { id: 'e4', source: 'news-1', target: 'display-1', sourceHandle: 'news', targetHandle: 'data' },
  { id: 'e5', source: 'insiders-1', target: 'display-1', sourceHandle: 'transactions', targetHandle: 'data' }
]

interface WorkflowCanvasProps {
  onExecute?: (workflow: Workflow) => Promise<void>
}

const WorkflowCanvasInner: React.FC<WorkflowCanvasProps> = ({ onExecute }) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNode, setSelectedNode] = useState<Node<WorkflowNodeData> | null>(null)
  const [executionState, setExecutionState] = useState<WorkflowExecutionState | null>(null)
  const [workflowName, setWorkflowName] = useState('My Workflow')
  const [showTemplates, setShowTemplates] = useState(false)
  
  const handleLoadTemplate = useCallback((workflow: Workflow) => {
    setNodes(workflow.nodes.map(n => ({ ...n, data: n.data as WorkflowNodeData })))
    setEdges(workflow.edges)
    setWorkflowName(workflow.name)
    setExecutionState(null)
  }, [setNodes, setEdges])
  
  const onConnect: OnConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({
      ...params,
      style: { stroke: '#52525b', strokeWidth: 2 },
      animated: false
    }, eds)),
    [setEdges]
  )
  
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])
  
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      
      const nodeType = event.dataTransfer.getData('application/reactflow')
      if (!nodeType || !NODE_DEFINITIONS[nodeType]) return
      
      const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect()
      if (!reactFlowBounds) return
      
      const position = {
        x: event.clientX - reactFlowBounds.left - 100,
        y: event.clientY - reactFlowBounds.top - 40
      }
      
      const newNode: Node<WorkflowNodeData> = {
        id: `${nodeType}-${Date.now()}`,
        type: 'custom',
        position,
        data: { ...NODE_DEFINITIONS[nodeType], config: {} }
      }
      
      setNodes((nds) => [...nds, newNode])
    },
    [setNodes]
  )
  
  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }
  
  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node as Node<WorkflowNodeData>)
  }, [])
  
  const handlePaneClick = useCallback(() => {
    setSelectedNode(null)
  }, [])
  
  const handleNodeUpdate = useCallback((nodeId: string, config: Record<string, any>) => {
    setNodes((nds) =>
      nds.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, config } }
          : node
      )
    )
    if (selectedNode?.id === nodeId) {
      setSelectedNode((prev) => prev ? { ...prev, data: { ...prev.data, config } } : null)
    }
  }, [setNodes, selectedNode])
  
  const handleNodeDelete = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId))
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId))
    setSelectedNode(null)
  }, [setNodes, setEdges])
  
  const handleRun = useCallback(async () => {
    const workflow: Workflow = {
      id: `workflow-${Date.now()}`,
      name: workflowName,
      description: '',
      nodes: nodes.map(n => ({
        id: n.id,
        type: n.type || 'custom',
        position: n.position,
        data: n.data
      })),
      edges: edges.map(e => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || undefined,
        targetHandle: e.targetHandle || undefined
      })),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
    
    setExecutionState({
      workflowId: workflow.id,
      status: 'running',
      results: {}
    })
    
    // Simulate execution - in real implementation, call backend
    if (onExecute) {
      try {
        await onExecute(workflow)
        setExecutionState(prev => prev ? { ...prev, status: 'completed' } : null)
      } catch (error) {
        setExecutionState(prev => prev ? { ...prev, status: 'error' } : null)
      }
    } else {
      // Demo simulation
      for (const node of nodes) {
        setExecutionState(prev => prev ? {
          ...prev,
          currentNodeId: node.id,
          results: {
            ...prev.results,
            [node.id]: { nodeId: node.id, status: 'running' }
          }
        } : null)
        
        await new Promise(r => setTimeout(r, 500 + Math.random() * 500))
        
        setExecutionState(prev => prev ? {
          ...prev,
          results: {
            ...prev.results,
            [node.id]: { 
              nodeId: node.id, 
              status: 'success',
              executionTime: Math.floor(100 + Math.random() * 500),
              data: { count: Math.floor(Math.random() * 100) }
            }
          }
        } : null)
      }
      
      setExecutionState(prev => prev ? { ...prev, status: 'completed' } : null)
    }
  }, [nodes, edges, workflowName, onExecute])
  
  const handleStop = useCallback(() => {
    setExecutionState(prev => prev ? { ...prev, status: 'idle' } : null)
  }, [])
  
  const handleReset = useCallback(() => {
    setExecutionState(null)
  }, [])
  
  const handleClear = useCallback(() => {
    setNodes([])
    setEdges([])
    setSelectedNode(null)
    setExecutionState(null)
  }, [setNodes, setEdges])
  
  return (
    <div className="flex h-screen bg-zinc-950">
      {/* Left Panel - Node Palette */}
      <NodePalette onDragStart={onDragStart} />
      
      {/* Main Canvas */}
      <div className="flex-1 flex flex-col">
        {/* Toolbar */}
        <div className="h-12 bg-zinc-900 border-b border-zinc-800 flex items-center gap-4 px-4">
          <input
            type="text"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            className="bg-transparent text-white font-bold text-lg focus:outline-none 
                       border-b border-transparent focus:border-blue-500"
          />
          
          <div className="flex-1" />
          
          <button 
            onClick={() => setShowTemplates(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-zinc-400 hover:text-white 
                             hover:bg-zinc-800 rounded text-sm transition-colors">
            <LayoutTemplate className="w-4 h-4" />
            Templates
          </button>
          <button className="flex items-center gap-1 px-3 py-1.5 text-zinc-400 hover:text-white 
                             hover:bg-zinc-800 rounded text-sm transition-colors">
            <Plus className="w-4 h-4" />
            New
          </button>
          <button className="flex items-center gap-1 px-3 py-1.5 text-zinc-400 hover:text-white 
                             hover:bg-zinc-800 rounded text-sm transition-colors">
            <FolderOpen className="w-4 h-4" />
            Load
          </button>
          <button className="flex items-center gap-1 px-3 py-1.5 text-zinc-400 hover:text-white 
                             hover:bg-zinc-800 rounded text-sm transition-colors">
            <Save className="w-4 h-4" />
            Save
          </button>
          <button 
            onClick={handleClear}
            className="flex items-center gap-1 px-3 py-1.5 text-red-400 hover:text-red-300 
                             hover:bg-red-900/30 rounded text-sm transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Clear
          </button>
        </div>
        
        {/* Canvas */}
        <div className="flex-1" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            nodeTypes={nodeTypes}
            fitView
            snapToGrid
            snapGrid={[20, 20]}
            defaultEdgeOptions={{
              style: { stroke: '#52525b', strokeWidth: 2 },
              type: 'smoothstep'
            }}
          >
            <Background 
              variant={BackgroundVariant.Dots} 
              gap={20} 
              size={1} 
              color="#27272a" 
            />
            <Controls className="!bg-zinc-900 !border-zinc-700" />
            <MiniMap 
              nodeColor={(node) => {
                const data = node.data as WorkflowNodeData
                return CATEGORY_COLORS[data?.category || 'output'] || '#6b7280'
              }}
              className="!bg-zinc-900 !border-zinc-700"
            />
          </ReactFlow>
        </div>
        
        {/* Execution Panel */}
        <ExecutionPanel 
          state={executionState}
          onRun={handleRun}
          onStop={handleStop}
          onReset={handleReset}
        />
      </div>
      
      {/* Right Panel - Node Config */}
      {selectedNode && (
        <NodeConfig 
          node={selectedNode}
          onUpdate={handleNodeUpdate}
          onClose={() => setSelectedNode(null)}
          onDelete={handleNodeDelete}
        />
      )}
      
      {/* Templates Modal */}
      <TemplatesPanel
        isOpen={showTemplates}
        onClose={() => setShowTemplates(false)}
        onLoadTemplate={handleLoadTemplate}
      />
    </div>
  )
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = (props) => (
  <ReactFlowProvider>
    <WorkflowCanvasInner {...props} />
  </ReactFlowProvider>
)

export default WorkflowCanvas
