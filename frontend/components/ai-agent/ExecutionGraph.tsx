'use client';

/**
 * ExecutionGraph — adaptador del grafo LangGraph al WorkflowCanvas genérico.
 *
 * Convierte los AgentStep del run en curso (con sus NodeCardData de
 * node_summary.py) en capas de WorkflowNodeSpec: planner arriba, agentes en
 * el medio, synthesizer abajo. El renderizado y las animaciones internas
 * (typewriter de specs, cascada de filas, scanline) viven en workflow/.
 */
import { memo, useMemo } from 'react';
import i18n from '@/lib/i18n';
import type { AgentStep, CanvasSubstep, NodeCardData } from './types';
import { WorkflowCanvas } from './workflow/WorkflowCanvas';
import type {
  NodeBlock, WorkflowEdgeSpec, WorkflowNodeSpec, WorkflowNodeStatus,
} from './workflow/types';

/* ── Etiquetas legibles por nodo ── */
export const NODE_TITLES: Record<string, string> = {
  query_planner: 'Query Planner',
  supervisor: 'Query Planner',
  market_data: 'Market Data',
  news_events: 'News & Events',
  financial: 'Financials',
  research: 'Deep Research',
  code_exec: 'Code Engine',
  screener: 'Screener',
  backtest: 'Backtester',
  synthesizer: 'Synthesizer',
  dilution: 'Dilution Tracker',
  strategy_scanner: 'Strategy Scanner',
  alert_compiler: 'Alert Compiler',
  alert_manager: 'Alert Manager',
  context_enricher: 'Context',
  context_brief: 'Contexto Fundamental',
};

function nodeSubtitle(name: string): string | undefined {
  const hints: Record<string, string> = {
    query_planner: 'routing + intent',
    supervisor: 'routing + intent',
    market_data: i18n.t('aiAgent.execHints.market_data'),
    news_events: 'noticias · earnings · eventos',
    financial: 'fundamentales',
    research: i18n.t('aiAgent.execHints.research'),
    code_exec: 'python sandbox',
    screener: 'filtros duckdb',
    backtest: i18n.t('aiAgent.execHints.backtest'),
    synthesizer: 'respuesta final',
    dilution: 'SEC · ATM · S-3',
    strategy_scanner: 'secuencias de eventos',
    alert_compiler: 'NL → spec ejecutable',
    alert_manager: 'alertas guardadas',
    context_enricher: i18n.t('aiAgent.execHints.context_enricher'),
  };
  return hints[name];
}

const PLANNERS = new Set(['query_planner', 'supervisor']);
const FINALS = new Set(['synthesizer']);

function toStatus(s?: AgentStep): WorkflowNodeStatus {
  if (!s) return 'pending';
  return s.status === 'running' ? 'running'
    : s.status === 'complete' ? 'complete'
      : s.status === 'error' ? 'error' : 'pending';
}

/** NodeCardData (backend node_summary) → bloques tipados del canvas. */
function cardToBlocks(name: string, step: AgentStep | undefined, status: WorkflowNodeStatus): NodeBlock[] {
  const blocks: NodeBlock[] = [];
  const card: NodeCardData | undefined = step?.data;

  if (status === 'running' && step?.description) {
    blocks.push({ kind: 'progress', text: step.description });
  }
  if (card?.metrics && Object.keys(card.metrics).length > 0) {
    blocks.push({
      kind: 'metrics',
      items: Object.entries(card.metrics).slice(0, 5).map(([k, v]) => ({
        label: k.replace(/_/g, ' '),
        value: v,
      })),
    });
  }
  if (card?.routing?.length) {
    blocks.push({
      kind: 'chips',
      style: 'primary',
      items: card.routing.map(a => NODE_TITLES[a] || a),
    });
  }
  if (card?.tickers?.length) {
    blocks.push({ kind: 'chips', style: 'mono', items: card.tickers });
  }
  if (card?.text) {
    blocks.push({ kind: 'text', text: card.text });
  }
  if (card?.error) {
    blocks.push({ kind: 'error', text: card.error });
  }
  if (card?.table) {
    blocks.push({
      kind: 'table',
      title: card.table.title,
      columns: card.table.columns,
      rows: card.table.rows,
      total: card.table.total,
      cascade: true,
    });
  }
  if (card?.code) {
    blocks.push({
      kind: 'code',
      language: card.code.language,
      content: card.code.content,
      typewriter: true,
    });
  }
  return blocks;
}

interface ExecutionGraphProps {
  steps: AgentStep[];
  height?: number | string;
  /** Abre el inspector con los artifacts completos de un nodo. */
  onInspect?: (target: { runId: string; node: string; title: string; subtitle?: string }) => void;
}

/** Substep dinámico (canvas_step del backend) → nodo del workflow. */
function substepToSpec(
  agentName: string,
  sub: CanvasSubstep,
  stepNumber: number,
  onInspect?: ExecutionGraphProps['onInspect'],
): WorkflowNodeSpec {
  const nodeKey = `${agentName}::${sub.id}`;
  const art = sub.artifacts;
  return {
    id: nodeKey,
    title: sub.title,
    subtitle: sub.subtitle,
    status: sub.status === 'running' ? 'running' : sub.status === 'error' ? 'error' : 'complete',
    stepNumber,
    duration: sub.durationMs ? sub.durationMs / 1000 : undefined,
    // Los bloques ya llegan con el shape NodeBlock desde agents/_canvas.py
    blocks: (sub.blocks as NodeBlock[]) || [],
    onOpen: (art && onInspect)
      ? () => onInspect({
          runId: art.runId,
          node: nodeKey,
          title: sub.title,
          subtitle: sub.subtitle,
        })
      : undefined,
  };
}

export const ExecutionGraph = memo(function ExecutionGraph({
  steps,
  height = 300,
  onInspect,
}: ExecutionGraphProps) {
  const { layers, edges } = useMemo(() => {
    const byName = new Map<string, AgentStep>();
    for (const s of steps) byName.set(s.id.replace(/^step-/, ''), s);

    const planner = [...byName.keys()].find(n => PLANNERS.has(n));
    const synth = [...byName.keys()].find(n => FINALS.has(n));
    const started = [...byName.keys()].filter(n => !PLANNERS.has(n) && !FINALS.has(n));

    // Plan visible desde el segundo 1: los agentes que el planner enrutó
    // (card routing del supervisor) se pre-renderizan como nodos "pending"
    // aunque su node_started aún no haya llegado — el grafo completo aparece
    // al instante y los nodos se van encendiendo según ejecutan. El orden del
    // plan manda; los que arrancan sin estar en el plan se añaden detrás.
    const routed = (planner ? byName.get(planner)?.data?.routing ?? [] : [])
      .filter(n => !PLANNERS.has(n) && !FINALS.has(n));
    const agents = [...new Set([...routed, ...started])];

    let stepCounter = 0;
    const mkSpec = (name: string, step?: AgentStep): WorkflowNodeSpec => {
      stepCounter += 1;
      const status = toStatus(step);
      const title = NODE_TITLES[name] || step?.title || name;
      const art = step?.artifacts;
      return {
        id: name,
        title,
        subtitle: nodeSubtitle(name),
        status,
        stepNumber: stepCounter,
        duration: step?.duration,
        blocks: cardToBlocks(name, step, status),
        // Nodo inspeccionable: sus outputs completos están persistidos
        onOpen: (art && onInspect)
          ? () => onInspect({ runId: art.runId, node: name, title, subtitle: nodeSubtitle(name) })
          : undefined,
      };
    };

    // Planner (paso 1 — visible aunque su evento aún no llegó)
    const plannerName = planner || 'query_planner';
    const plannerSpec = mkSpec(plannerName, planner ? byName.get(planner) : undefined);

    const agentSpecs = agents.map(n => mkSpec(n, byName.get(n)));

    const layers: WorkflowNodeSpec[][] = [[plannerSpec]];
    if (agentSpecs.length) layers.push(agentSpecs);

    const edges: WorkflowEdgeSpec[] = [];
    const edgeState = (targetStatus: WorkflowNodeStatus, sourceStatus: WorkflowNodeStatus): WorkflowEdgeSpec['state'] =>
      targetStatus === 'running' ? 'active'
        : targetStatus === 'complete' && sourceStatus === 'complete' ? 'done' : 'idle';

    for (const a of agentSpecs) {
      edges.push({ source: plannerSpec.id, target: a.id, state: edgeState(a.status, plannerSpec.status) });
    }

    // ── Substeps dinámicos: los nodos que el agente MONTA mientras trabaja ──
    // Se encadenan agente → sub1 → sub2 → … y el último conecta al synth,
    // así el canvas crece en vivo como un pipeline (estilo "Added step N").
    const lastOf = new Map<string, WorkflowNodeSpec>(); // agente → último nodo de su cadena
    for (const a of agentSpecs) lastOf.set(a.id, a);

    for (const name of agents) {
      const step = byName.get(name);
      const subs = step?.substeps || [];
      if (!subs.length) continue;
      const agentSpec = agentSpecs.find(s => s.id === name)!;
      const subSpecs = subs.map((sub, i) => substepToSpec(name, sub, i + 1, onInspect));
      layers.push(subSpecs);
      let prev: WorkflowNodeSpec = agentSpec;
      for (const ss of subSpecs) {
        edges.push({ source: prev.id, target: ss.id, state: edgeState(ss.status, prev.status) });
        prev = ss;
      }
      lastOf.set(agentSpec.id, prev);
    }

    // Synthesizer cierra el grafo siempre que hay agentes
    if (agentSpecs.length > 0 || synth) {
      const synthSpec = mkSpec(synth || 'synthesizer', synth ? byName.get(synth) : undefined);
      layers.push([synthSpec]);
      const sources = agentSpecs.length
        ? agentSpecs.map(a => lastOf.get(a.id)!)
        : [plannerSpec];
      for (const s of sources) {
        edges.push({ source: s.id, target: synthSpec.id, state: edgeState(synthSpec.status, s.status) });
      }
    }

    return { layers, edges };
  }, [steps, onInspect]);

  if (!steps.length) return null;

  return (
    <WorkflowCanvas
      layers={layers}
      edges={edges}
      height={height}
      watermark="live execution canvas"
    />
  );
});
