'use client'

import React from 'react'
import { NODE_DEFINITIONS, NodeCategory, CATEGORY_COLORS } from '../types'

interface NodePaletteProps {
    onDragStart: (event: React.DragEvent, nodeType: string) => void
}

const categoryLabels: Record<NodeCategory, string> = {
    data_source: '📡 Data Sources',
    filter: '🔍 Filters',
    enrichment: '✨ Enrichment',
    ai: '🤖 AI',
    output: '📋 Output'
}

const NodePalette: React.FC<NodePaletteProps> = ({ onDragStart }) => {
    // Group nodes by category
    const nodesByCategory = Object.entries(NODE_DEFINITIONS).reduce((acc, [key, node]) => {
        if (!acc[node.category]) acc[node.category] = []
        acc[node.category].push({ key, ...node })
        return acc
    }, {} as Record<NodeCategory, Array<typeof NODE_DEFINITIONS[string] & { key: string }>>)

    return (
        <div className="w-64 bg-zinc-950 border-r border-zinc-800 overflow-y-auto">
            <div className="p-4 border-b border-zinc-800">
                <h2 className="text-lg font-bold text-white">Nodes</h2>
                <p className="text-xs text-zinc-500 mt-1">Drag to canvas to add</p>
            </div>

            {Object.entries(categoryLabels).map(([category, label]) => (
                <div key={category} className="border-b border-zinc-800">
                    <div
                        className="px-4 py-2 text-sm font-medium"
                        style={{ color: CATEGORY_COLORS[category as NodeCategory] }}
                    >
                        {label}
                    </div>

                    <div className="px-2 pb-2 space-y-1">
                        {nodesByCategory[category as NodeCategory]?.map((node) => (
                            <div
                                key={node.key}
                                draggable
                                onDragStart={(e) => onDragStart(e, node.key)}
                                className="flex items-center gap-2 px-3 py-2 bg-zinc-900 rounded-lg 
                           cursor-grab hover:bg-zinc-800 transition-colors
                           border border-zinc-800 hover:border-zinc-700"
                            >
                                <span className="text-lg">{node.icon}</span>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium text-white">{node.label}</div>
                                    <div className="text-xs text-zinc-500 truncate">{node.description}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    )
}

export default NodePalette
