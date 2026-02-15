"use client"

import React, { useState, useMemo } from "react"
import {
  TrendingUp, Newspaper, FileText, Search, Code, Filter,
  BarChart3, Database, Rss, Zap, Receipt, AlertTriangle,
  SlidersHorizontal, Calendar, GitBranch, GitFork, GitMerge,
  Repeat, Bell, Clock, DollarSign, Table, LineChart, BellRing,
  Download, HelpCircle, ChevronDown, ChevronRight,
  Search as SearchIcon, GripVertical,
} from "lucide-react"
import {
  NODE_CATALOG,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  type NodeCategory,
  type CatalogNode,
} from "../types"
import type { LucideIcon } from "lucide-react"

const ICON_MAP: Record<string, LucideIcon> = {
  TrendingUp, Newspaper, FileText, Search, Code, Filter,
  BarChart3, Database, Rss, Zap, Receipt, AlertTriangle,
  SlidersHorizontal, Calendar, GitBranch, GitFork, GitMerge,
  Repeat, Bell, Clock, DollarSign, Table, LineChart, BellRing,
  Download,
}

function getIcon(name: string): LucideIcon {
  return ICON_MAP[name] || HelpCircle
}

function DraggableNode({ node }: { node: CatalogNode }) {
  const Icon = getIcon(node.icon)
  const colors = CATEGORY_COLORS[node.category]

  const onDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("application/workflow-node", JSON.stringify(node))
    e.dataTransfer.effectAllowed = "move"
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="flex items-center gap-2 px-2 py-2 rounded-md cursor-grab active:cursor-grabbing bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700 transition-all duration-150 group h-12"
    >
      <GripVertical size={12} className="text-zinc-600 group-hover:text-zinc-400 flex-shrink-0" />
      <div className={"w-7 h-7 rounded flex items-center justify-center flex-shrink-0 " + colors.bg}>
        <Icon size={14} className={colors.text} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-zinc-200 truncate">{node.label}</div>
        <div className="text-[10px] text-zinc-500 truncate">{node.description}</div>
      </div>
    </div>
  )
}

function CategorySection({
  category,
  nodes,
  defaultExpanded = false,
}: {
  category: NodeCategory
  nodes: CatalogNode[]
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const colors = CATEGORY_COLORS[category]

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-2 py-1.5 text-left hover:bg-zinc-800/50 rounded-md transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-zinc-500" />
        ) : (
          <ChevronRight size={14} className="text-zinc-500" />
        )}
        <div className={"w-2 h-2 rounded-full " + colors.dot} />
        <span className={"text-xs font-semibold uppercase tracking-wider " + colors.text}>
          {CATEGORY_LABELS[category]}
        </span>
        <span className="text-[10px] text-zinc-600 ml-auto">{nodes.length}</span>
      </button>
      {expanded && (
        <div className="mt-1 ml-2 space-y-1">
          {nodes.map((node) => (
            <DraggableNode key={node.type} node={node} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function NodePalette() {
  const [search, setSearch] = useState("")

  const categories = useMemo(() => {
    const order: NodeCategory[] = ["trigger", "agent", "tool", "control", "output"]
    return order.map((cat) => {
      const nodes = NODE_CATALOG[cat].filter(
        (n) =>
          !search ||
          n.label.toLowerCase().includes(search.toLowerCase()) ||
          n.description.toLowerCase().includes(search.toLowerCase()) ||
          n.type.toLowerCase().includes(search.toLowerCase())
      )
      return { category: cat, nodes }
    })
  }, [search])

  const hasResults = categories.some((c) => c.nodes.length > 0)

  return (
    <div className="w-60 bg-zinc-950 border-r border-zinc-800 flex flex-col h-full">
      <div className="px-3 py-3 border-b border-zinc-800">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
          Node Palette
        </h3>
        <div className="relative">
          <SearchIcon size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search nodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-md pl-7 pr-2 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {hasResults ? (
          categories
            .filter((c) => c.nodes.length > 0)
            .map((c) => (
              <CategorySection
                key={c.category}
                category={c.category}
                nodes={c.nodes}
                defaultExpanded={!!search}
              />
            ))
        ) : (
          <div className="text-center text-xs text-zinc-600 py-8">No nodes match your search</div>
        )}
      </div>
    </div>
  )
}
