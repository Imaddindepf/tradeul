"use client"

import React from "react"
import { X, Trash2, Settings2 } from "lucide-react"
import { useWorkflowStore } from "@/stores/useWorkflowStore"
import type { WorkflowNodeData } from "../types"
import { CATEGORY_COLORS } from "../types"

interface ConfigField {
  key: string
  label: string
  type: "text" | "number" | "select" | "multiselect" | "textarea"
  options?: { value: string; label: string }[]
  placeholder?: string
}

const NODE_CONFIG_FIELDS: Record<string, ConfigField[]> = {
  scanner_snapshot: [
    {
      key: "category",
      label: "Scanner Category",
      type: "select",
      options: [
        { value: "gappers_up", label: "Gappers Up" },
        { value: "gappers_down", label: "Gappers Down" },
        { value: "most_active", label: "Most Active" },
        { value: "high_short_interest", label: "High Short Interest" },
        { value: "unusual_volume", label: "Unusual Volume" },
        { value: "new_highs", label: "New Highs" },
        { value: "new_lows", label: "New Lows" },
      ],
    },
    { key: "limit", label: "Limit", type: "number", placeholder: "20" },
  ],
  on_event: [
    {
      key: "event_types",
      label: "Event Types",
      type: "multiselect",
      options: [
        { value: "earnings", label: "Earnings" },
        { value: "fda", label: "FDA Approval" },
        { value: "merger", label: "Merger/Acquisition" },
        { value: "offering", label: "Offering" },
        { value: "split", label: "Stock Split" },
        { value: "dividend", label: "Dividend" },
      ],
    },
  ],
  on_schedule: [
    { key: "cron", label: "Cron Expression", type: "text", placeholder: "30 9 * * 1-5" },
  ],
  on_price: [
    { key: "symbol", label: "Symbol", type: "text", placeholder: "AAPL" },
    { key: "price", label: "Price", type: "number", placeholder: "150.00" },
    {
      key: "direction",
      label: "Direction",
      type: "select",
      options: [
        { value: "above", label: "Above" },
        { value: "below", label: "Below" },
      ],
    },
  ],
  conditional: [
    { key: "condition", label: "Condition Expression", type: "textarea", placeholder: "data.price > 10 && data.volume > 1000000" },
  ],
  parallel: [
    { key: "branch_count", label: "Number of Branches", type: "number", placeholder: "2" },
  ],
  loop: [
    { key: "max_iterations", label: "Max Iterations", type: "number", placeholder: "100" },
  ],
  enriched_data: [
    { key: "fields", label: "Fields to Enrich", type: "text", placeholder: "price,volume,market_cap" },
  ],
  run_screen: [
    { key: "screen_query", label: "Screen Query (SQL)", type: "textarea", placeholder: "SELECT * FROM stocks WHERE market_cap > 1000000" },
  ],
  historical_bars: [
    {
      key: "timeframe",
      label: "Timeframe",
      type: "select",
      options: [
        { value: "1Min", label: "1 Minute" },
        { value: "5Min", label: "5 Minutes" },
        { value: "15Min", label: "15 Minutes" },
        { value: "1Hour", label: "1 Hour" },
        { value: "1Day", label: "1 Day" },
      ],
    },
    { key: "days", label: "Days Back", type: "number", placeholder: "30" },
  ],
  display_table: [
    { key: "title", label: "Table Title", type: "text", placeholder: "Results" },
    { key: "columns", label: "Columns (comma-sep)", type: "text", placeholder: "symbol,price,change" },
  ],
  display_chart: [
    {
      key: "chart_type",
      label: "Chart Type",
      type: "select",
      options: [
        { value: "line", label: "Line" },
        { value: "bar", label: "Bar" },
        { value: "candlestick", label: "Candlestick" },
        { value: "scatter", label: "Scatter" },
      ],
    },
  ],
  send_alert: [
    {
      key: "channel",
      label: "Alert Channel",
      type: "select",
      options: [
        { value: "push", label: "Push Notification" },
        { value: "email", label: "Email" },
        { value: "webhook", label: "Webhook" },
      ],
    },
    { key: "message_template", label: "Message Template", type: "textarea", placeholder: "Alert: {{symbol}} reached {{price}}" },
  ],
  export_data: [
    {
      key: "format",
      label: "Export Format",
      type: "select",
      options: [
        { value: "csv", label: "CSV" },
        { value: "json", label: "JSON" },
      ],
    },
    { key: "filename", label: "Filename", type: "text", placeholder: "export" },
  ],
}

function ConfigFieldRenderer({
  field,
  value,
  onChange,
}: {
  field: ConfigField
  value: any
  onChange: (val: any) => void
}) {
  const baseInputClass =
    "w-full bg-zinc-900 border border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors"

  switch (field.type) {
    case "text":
      return (
        <input
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          className={baseInputClass}
        />
      )
    case "number":
      return (
        <input
          type="number"
          value={value ?? ""}
          onChange={(e) => onChange(Number(e.target.value))}
          placeholder={field.placeholder}
          className={baseInputClass}
        />
      )
    case "select":
      return (
        <select
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          className={baseInputClass}
        >
          <option value="">Select...</option>
          {field.options?.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )
    case "multiselect":
      return (
        <div className="space-y-1">
          {field.options?.map((opt) => {
            const checked = Array.isArray(value) && value.includes(opt.value)
            return (
              <label
                key={opt.value}
                className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer hover:text-zinc-100"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => {
                    const arr = Array.isArray(value) ? [...value] : []
                    if (checked) {
                      onChange(arr.filter((v: string) => v !== opt.value))
                    } else {
                      onChange([...arr, opt.value])
                    }
                  }}
                  className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
                />
                {opt.label}
              </label>
            )
          })}
        </div>
      )
    case "textarea":
      return (
        <textarea
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          className={baseInputClass + " resize-none font-mono"}
        />
      )
    default:
      return null
  }
}

interface NodeConfigPanelProps {
  onClose: () => void
}

export default function NodeConfigPanel({ onClose }: NodeConfigPanelProps) {
  const selectedNodeId = useWorkflowStore((s) => s.selectedNodeId)
  const workflow = useWorkflowStore((s) => s.getActiveWorkflow())
  const updateNodeConfig = useWorkflowStore((s) => s.updateNodeConfig)
  const removeNode = useWorkflowStore((s) => s.removeNode)

  if (!selectedNodeId || !workflow) return null

  const node = workflow.nodes.find((n: any) => n.id === selectedNodeId)
  if (!node) return null

  const nodeData = node.data as WorkflowNodeData
  const colors = CATEGORY_COLORS[nodeData.category]
  const fields = NODE_CONFIG_FIELDS[node.type || ""] || []

  const handleConfigChange = (key: string, value: any) => {
    updateNodeConfig(selectedNodeId, { [key]: value })
  }

  const handleDelete = () => {
    removeNode(selectedNodeId)
    onClose()
  }

  return (
    <div className="w-72 bg-zinc-950 border-l border-zinc-800 flex flex-col h-full animate-in slide-in-from-right duration-200">
      <div className="flex items-center justify-between px-3 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Settings2 size={14} className="text-zinc-400" />
          <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            Configure
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      <div className={"px-3 py-3 border-b border-zinc-800 " + colors.bg}>
        <div className={"text-xs font-semibold uppercase tracking-wide " + colors.text}>
          {nodeData.category}
        </div>
        <div className="text-sm font-medium text-zinc-100 mt-0.5">{nodeData.label}</div>
        <div className="text-xs text-zinc-400 mt-0.5">{nodeData.description}</div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {fields.length > 0 ? (
          fields.map((field) => (
            <div key={field.key}>
              <label className="block text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">
                {field.label}
              </label>
              <ConfigFieldRenderer
                field={field}
                value={nodeData.config?.[field.key]}
                onChange={(val) => handleConfigChange(field.key, val)}
              />
            </div>
          ))
        ) : (
          <div className="text-xs text-zinc-600 text-center py-4">
            No configurable options for this node.
          </div>
        )}

        <div className="pt-3 border-t border-zinc-800">
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">
            Inputs
          </div>
          <div className="flex flex-wrap gap-1">
            {nodeData.inputs.length > 0 ? (
              nodeData.inputs.map((inp) => (
                <span key={inp} className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400 font-mono">
                  {inp}
                </span>
              ))
            ) : (
              <span className="text-[10px] text-zinc-600">None (trigger node)</span>
            )}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1">
            Outputs
          </div>
          <div className="flex flex-wrap gap-1">
            {nodeData.outputs.length > 0 ? (
              nodeData.outputs.map((out) => (
                <span key={out} className="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400 font-mono">
                  {out}
                </span>
              ))
            ) : (
              <span className="text-[10px] text-zinc-600">None (output node)</span>
            )}
          </div>
        </div>
      </div>

      <div className="px-3 py-3 border-t border-zinc-800">
        <button
          onClick={handleDelete}
          className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-medium transition-colors"
        >
          <Trash2 size={12} />
          Delete Node
        </button>
      </div>
    </div>
  )
}
