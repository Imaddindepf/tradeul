'use client'

import React, { useState, useEffect } from 'react'
import { Workflow, CATEGORY_COLORS, NodeCategory } from '../types'
import { Download, Play, ChevronRight } from 'lucide-react'

interface TemplatesPanelProps {
  onLoadTemplate: (workflow: Workflow) => void
  isOpen: boolean
  onClose: () => void
}

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  nodes: any[]
  edges: any[]
}

const TemplatesPanel: React.FC<TemplatesPanelProps> = ({ onLoadTemplate, isOpen, onClose }) => {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    if (isOpen) {
      fetchTemplates()
    }
  }, [isOpen])
  
  const fetchTemplates = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_AI_AGENT_API_URL || 'http://localhost:8085'
      const response = await fetch(`${apiUrl}/api/workflow-templates`)
      if (response.ok) {
        const data = await response.json()
        setTemplates(data)
      }
    } catch (error) {
      console.error('Failed to fetch templates:', error)
      // Use fallback templates
      setTemplates(FALLBACK_TEMPLATES)
    } finally {
      setLoading(false)
    }
  }
  
  const handleLoad = (template: WorkflowTemplate) => {
    const workflow: Workflow = {
      id: `${template.id}-${Date.now()}`,
      name: template.name.replace(/^[\u{1F300}-\u{1F9FF}]/u, '').trim(),
      description: template.description,
      nodes: template.nodes,
      edges: template.edges,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    }
    onLoadTemplate(workflow)
    onClose()
  }
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-zinc-900 rounded-xl w-[800px] max-h-[80vh] overflow-hidden border border-zinc-700">
        {/* Header */}
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Workflow Templates</h2>
            <p className="text-sm text-zinc-400 mt-1">
              Start with a pre-built workflow or create your own
            </p>
          </div>
          <button 
            onClick={onClose}
            className="text-zinc-400 hover:text-white"
          >
            ✕
          </button>
        </div>
        
        {/* Templates Grid */}
        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin w-6 h-6 border-2 border-white border-t-transparent rounded-full" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {templates.map((template) => (
                <div 
                  key={template.id}
                  className="bg-zinc-800 rounded-lg p-4 border border-zinc-700 hover:border-zinc-600 
                             transition-colors group cursor-pointer"
                  onClick={() => handleLoad(template)}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-3xl">{template.name.match(/^[\u{1F300}-\u{1F9FF}]/u)?.[0] || '📊'}</span>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-white group-hover:text-blue-400 transition-colors">
                        {template.name.replace(/^[\u{1F300}-\u{1F9FF}]\s*/u, '')}
                      </h3>
                      <p className="text-sm text-zinc-400 mt-1">{template.description}</p>
                      
                      {/* Node preview */}
                      <div className="flex flex-wrap gap-1 mt-3">
                        {template.nodes.slice(0, 4).map((node, idx) => {
                          const category = (node.data?.category as NodeCategory) || 'output';
                          return (
                            <span 
                              key={idx}
                              className="text-xs px-2 py-0.5 rounded-full"
                              style={{ 
                                backgroundColor: `${CATEGORY_COLORS[category]}20`,
                                color: CATEGORY_COLORS[category]
                              }}
                            >
                              {node.data?.icon} {node.data?.label}
                            </span>
                          );
                        })}
                        {template.nodes.length > 4 && (
                          <span className="text-xs px-2 py-0.5 text-zinc-500">
                            +{template.nodes.length - 4} more
                          </span>
                        )}
                      </div>
                    </div>
                    
                    <ChevronRight className="w-5 h-5 text-zinc-500 group-hover:text-white transition-colors" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Footer */}
        <div className="p-4 border-t border-zinc-800 bg-zinc-950">
          <p className="text-xs text-zinc-500 text-center">
            💡 Tip: Drag nodes from the left palette to customize your workflow
          </p>
        </div>
      </div>
    </div>
  )
}

// Fallback templates in case API fails
const FALLBACK_TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'whale-tracker',
    name: '🐋 Whale Activity Tracker',
    description: 'Track large unusual activity and insider transactions',
    nodes: [
      { id: 'scanner-1', type: 'custom', position: { x: 50, y: 200 },
        data: { label: 'Scanner', category: 'data_source', icon: '📡', config: {}, inputs: [], outputs: ['tickers'] }},
      { id: 'screener-1', type: 'custom', position: { x: 300, y: 200 },
        data: { label: 'Screener', category: 'filter', icon: '🔍', config: {}, inputs: ['tickers'], outputs: ['filtered'] }},
      { id: 'insiders-1', type: 'custom', position: { x: 550, y: 200 },
        data: { label: 'Insiders', category: 'enrichment', icon: '👔', config: {}, inputs: ['tickers'], outputs: ['transactions'] }},
      { id: 'display-1', type: 'custom', position: { x: 800, y: 200 },
        data: { label: 'Display', category: 'output', icon: '📋', config: {}, inputs: ['data'], outputs: [] }}
    ],
    edges: [
      { id: 'e1', source: 'scanner-1', target: 'screener-1' },
      { id: 'e2', source: 'screener-1', target: 'insiders-1' },
      { id: 'e3', source: 'insiders-1', target: 'display-1' }
    ]
  },
  {
    id: 'ai-sectors',
    name: '🧬 AI Sector Analysis',
    description: 'Analyze synthetic sectors with AI research',
    nodes: [
      { id: 'scanner-1', type: 'custom', position: { x: 50, y: 200 },
        data: { label: 'Scanner', category: 'data_source', icon: '📡', config: {}, inputs: [], outputs: ['tickers'] }},
      { id: 'synthetic-1', type: 'custom', position: { x: 300, y: 200 },
        data: { label: 'Synthetic ETFs', category: 'ai', icon: '🧬', config: {}, inputs: ['tickers'], outputs: ['sectors'] }},
      { id: 'display-1', type: 'custom', position: { x: 550, y: 200 },
        data: { label: 'Display', category: 'output', icon: '📋', config: {}, inputs: ['data'], outputs: [] }}
    ],
    edges: [
      { id: 'e1', source: 'scanner-1', target: 'synthetic-1' },
      { id: 'e2', source: 'synthetic-1', target: 'display-1' }
    ]
  }
]

export default TemplatesPanel
