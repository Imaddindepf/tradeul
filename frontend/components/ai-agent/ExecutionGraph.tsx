'use client';

/**
 * ExecutionGraph — live dataflow view of the multi-agent run.
 *
 * Renders the LangGraph execution as a real graph: planner on top, the
 * agents it activated fan out in parallel, and everything converges on
 * the synthesizer. Node state (pending/running/complete/error) updates
 * live from the same steps the StepCards use.
 */
import { memo, useMemo } from 'react';
import ReactFlow, {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  Compass, Activity, Radio, Landmark, Search, Code2,
  SlidersHorizontal, FlaskConical, Layers, Circle, BellRing, ListChecks,
} from 'lucide-react';
import type { AgentStep } from './types';

const NODE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  query_planner: Compass,
  supervisor: Compass,
  market_data: Activity,
  news_events: Radio,
  financial: Landmark,
  research: Search,
  code_exec: Code2,
  screener: SlidersHorizontal,
  backtest: FlaskConical,
  synthesizer: Layers,
  dilution: Activity,
  strategy_scanner: SlidersHorizontal,
  alert_compiler: BellRing,
  alert_manager: ListChecks,
  context_enricher: Search,
  context_brief: Radio,
};

type NodeStatus = 'pending' | 'running' | 'complete' | 'error';

interface AgentNodeData {
  label: string;
  nodeName: string;
  status: NodeStatus;
  duration?: number;
}

function fmtDuration(s: number): string {
  return s < 1 ? `${Math.round(s * 1000)}ms` : `${s.toFixed(1)}s`;
}

const STATUS_STYLE: Record<NodeStatus, string> = {
  pending: 'border-border-subtle bg-surface opacity-50',
  running: 'border-primary/60 bg-primary/5 shadow-sm',
  complete: 'border-emerald-500/40 bg-surface',
  error: 'border-red-400/60 bg-red-500/5',
};

const AgentNode = memo(function AgentNode({ data }: NodeProps<AgentNodeData>) {
  const Icon = NODE_ICONS[data.nodeName] || Circle;
  return (
    <div className={`rounded-lg border px-2 py-1.5 w-[132px] transition-colors ${STATUS_STYLE[data.status]}`}>
      <Handle type="target" position={Position.Top} className="!w-1.5 !h-1.5 !bg-border !border-0" />
      <div className="flex items-center gap-1.5">
        <span className={
          data.status === 'running' ? 'text-primary' :
          data.status === 'error' ? 'text-red-400' :
          data.status === 'complete' ? 'text-emerald-500' : 'text-muted-fg/60'
        }>
          <Icon className={`w-3 h-3 ${data.status === 'running' ? 'animate-pulse' : ''}`} />
        </span>
        <span className="text-[9px] font-medium text-foreground leading-tight flex-1 truncate">
          {data.label}
        </span>
      </div>
      <div className="flex items-center justify-between mt-0.5 pl-[18px]">
        <span className={`text-[7.5px] uppercase tracking-wider font-semibold ${
          data.status === 'running' ? 'text-primary' :
          data.status === 'error' ? 'text-red-400' :
          data.status === 'complete' ? 'text-emerald-500' : 'text-muted-fg/50'
        }`}>
          {data.status === 'running' ? 'en curso' :
           data.status === 'complete' ? 'listo' :
           data.status === 'error' ? 'error' : 'pendiente'}
        </span>
        {data.duration != null && data.duration > 0 && (
          <span className="text-[7.5px] font-mono text-muted-fg tabular-nums">
            {fmtDuration(data.duration)}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!w-1.5 !h-1.5 !bg-border !border-0" />
    </div>
  );
});

const nodeTypes = { agent: AgentNode };

const PLANNERS = new Set(['query_planner', 'supervisor']);
const FINALS = new Set(['synthesizer']);

interface ExecutionGraphProps {
  steps: AgentStep[];
  height?: number;
}

export const ExecutionGraph = memo(function ExecutionGraph({
  steps,
  height = 260,
}: ExecutionGraphProps) {
  const { nodes, edges } = useMemo(() => {
    const toStatus = (s: AgentStep): NodeStatus =>
      s.status === 'running' ? 'running'
        : s.status === 'complete' ? 'complete'
          : s.status === 'error' ? 'error' : 'pending';

    const byName = new Map<string, AgentStep>();
    for (const s of steps) byName.set(s.id.replace(/^step-/, ''), s);

    const planner = [...byName.keys()].find(n => PLANNERS.has(n));
    const synth = [...byName.keys()].find(n => FINALS.has(n));
    const agents = [...byName.keys()].filter(n => !PLANNERS.has(n) && !FINALS.has(n));

    const NODE_W = 132;
    const GAP_X = 14;
    const rowWidth = (n: number) => n * NODE_W + (n - 1) * GAP_X;
    const totalWidth = Math.max(rowWidth(Math.max(agents.length, 1)), NODE_W);

    const nodes: Node<AgentNodeData>[] = [];
    const edges: Edge[] = [];

    const mkNode = (name: string, x: number, y: number, status: NodeStatus, step?: AgentStep) => {
      nodes.push({
        id: name,
        type: 'agent',
        position: { x, y },
        draggable: false,
        selectable: false,
        data: {
          nodeName: name,
          label: step?.title || name,
          status,
          duration: step?.duration,
        },
      });
    };

    const cx = totalWidth / 2 - NODE_W / 2;

    // Planner (always first — show it even before its event arrives)
    const plannerName = planner || 'query_planner';
    mkNode(plannerName, cx, 0,
      planner ? toStatus(byName.get(planner)!) : 'pending',
      planner ? byName.get(planner) : undefined);

    // Agents fan out in a row
    agents.forEach((name, i) => {
      const x = i * (NODE_W + GAP_X);
      mkNode(name, x, 86, toStatus(byName.get(name)!), byName.get(name));
      edges.push({
        id: `${plannerName}-${name}`,
        source: plannerName,
        target: name,
        animated: byName.get(name)!.status === 'running',
        style: { strokeWidth: 1.2 },
      });
    });

    // Synthesizer converges (placeholder while agents run — it always closes the graph)
    if (agents.length > 0 || synth) {
      const synthName = synth || 'synthesizer';
      mkNode(synthName, cx, agents.length > 0 ? 172 : 86,
        synth ? toStatus(byName.get(synth)!) : 'pending',
        synth ? byName.get(synth) : undefined);
      const sources = agents.length > 0 ? agents : [plannerName];
      for (const src of sources) {
        edges.push({
          id: `${src}-${synthName}`,
          source: src,
          target: synthName,
          animated: synth ? byName.get(synth)!.status === 'running' : false,
          style: { strokeWidth: 1.2 },
        });
      }
    }

    return { nodes, edges };
  }, [steps]);

  if (!steps.length) return null;

  return (
    <div style={{ height }} className="rounded-lg border border-border-subtle overflow-hidden bg-surface-inset/30">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        minZoom={0.4}
        maxZoom={1.4}
      >
        <Background variant={BackgroundVariant.Dots} gap={14} size={0.6} />
      </ReactFlow>
    </div>
  );
});
