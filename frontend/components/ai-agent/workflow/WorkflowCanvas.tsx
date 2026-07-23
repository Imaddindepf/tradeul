'use client';

/**
 * WorkflowCanvas — el lienzo de nodos compartido.
 *
 * Recibe capas de WorkflowNodeSpec (cada capa se centra y se envuelve en
 * filas de `perRow`) y aristas con estado. Con esto, cualquier sistema
 * (ejecución del agente, alertas armadas, pipelines futuros) se dibuja igual:
 * dot-grid, tarjetas ricas animadas, aristas que "fluyen" según el estado.
 */
import { memo, useEffect, useMemo, useRef } from 'react';
import ReactFlow, {
  Background,
  BackgroundVariant,
  useReactFlow,
  type Edge,
  type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import i18n from '@/lib/i18n';
import type { NodeBlock, WorkflowEdgeSpec, WorkflowNodeSpec } from './types';
import { CARD_W, WorkflowNode } from './WorkflowNode';

const nodeTypes = { workflow: WorkflowNode };

/** Re-encuadra el viewport cuando el agente monta nodos nuevos en vivo. */
function AutoFit({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();
  const prev = useRef(nodeCount);
  useEffect(() => {
    if (nodeCount !== prev.current) {
      prev.current = nodeCount;
      // Pequeño delay para que el nodo nuevo ya esté medido.
      const t = setTimeout(() => fitView({ padding: 0.1, maxZoom: 1, duration: 350 }), 60);
      return () => clearTimeout(t);
    }
  }, [nodeCount, fitView]);
  return null;
}

/** Petición de foco: centra el viewport sobre un nodo concreto. */
export interface FocusRequest {
  nodeId: string;
  /** Cambia en cada petición para poder re-enfocar el mismo nodo. */
  token: number;
}

function FocusNode({ request }: { request: FocusRequest | null }) {
  const { fitView } = useReactFlow();
  const prevToken = useRef<number | null>(null);
  useEffect(() => {
    if (!request || request.token === prevToken.current) return;
    prevToken.current = request.token;
    const t = setTimeout(() => {
      fitView({ nodes: [{ id: request.nodeId }], padding: 0.25, maxZoom: 1.1, duration: 400 });
    }, 40);
    return () => clearTimeout(t);
  }, [request, fitView]);
  return null;
}

const GAP_X = 26;
const GAP_Y = 40;

/* ── Estimación de altura por bloque (para el layout) ── */

function blockHeight(b: NodeBlock): number {
  switch (b.kind) {
    case 'progress': return 30;
    case 'metrics': return 26 * Math.ceil(Math.min(b.items.length, 6) / 3);
    case 'chips': return 24 * Math.ceil(b.items.length / 4);
    case 'text': return 34;
    case 'error': return 30;
    case 'table':
      return (b.title ? 18 : 0) + 14 + Math.min(b.rows.length, 6) * 15 + 10;
    case 'code':
      return Math.min(110, 20 + b.content.split('\n').length * 12) + 6;
    case 'feed':
      return Math.min(b.rows.length, 4) * 16 + 8;
  }
}

function estimateHeight(spec: WorkflowNodeSpec): number {
  let h = 62; // header + subtítulo + footer
  const hasTable = spec.blocks.some(b => b.kind === 'table');
  const hasCode = spec.blocks.some(b => b.kind === 'code');
  for (const b of spec.blocks) {
    // Con pestañas solo se ve uno de los dos a la vez: cuenta el mayor.
    if (hasTable && hasCode && b.kind === 'code') continue;
    h += blockHeight(b) + 6;
  }
  if (hasTable && hasCode) h += 18; // barra de pestañas
  return h;
}

/* ── Estilo de aristas por estado ── */

const EDGE_STYLE: Record<WorkflowEdgeSpec['state'], { stroke: string; strokeWidth: number; animated: boolean }> = {
  idle: { stroke: 'rgba(120,130,150,0.3)', strokeWidth: 1.2, animated: false },
  active: { stroke: 'rgb(99,102,241)', strokeWidth: 1.8, animated: true },
  live: { stroke: 'rgba(16,185,129,0.55)', strokeWidth: 1.6, animated: true },
  done: { stroke: 'rgba(16,185,129,0.45)', strokeWidth: 1.2, animated: false },
  fired: { stroke: 'rgb(251,191,36)', strokeWidth: 2.2, animated: true },
};

export interface WorkflowCanvasProps {
  /** Capas de arriba a abajo; cada capa se envuelve en filas de perRow. */
  layers: WorkflowNodeSpec[][];
  edges: WorkflowEdgeSpec[];
  height?: number | string;
  perRow?: number;
  /** Marca de agua inferior derecha. */
  watermark?: string;
  emptyMessage?: string;
  /** Centra el viewport sobre un nodo (cambia token para repetir). */
  focusRequest?: FocusRequest | null;
}

export const WorkflowCanvas = memo(function WorkflowCanvas({
  layers,
  edges: edgeSpecs,
  height = '100%',
  perRow = 2,
  watermark = 'live canvas',
  emptyMessage,
  focusRequest = null,
}: WorkflowCanvasProps) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node<WorkflowNodeSpec>[] = [];

    const rowWidth = (n: number) => n * CARD_W + (n - 1) * GAP_X;
    const maxPerLayer = Math.max(1, ...layers.map(l => Math.min(l.length, perRow)));
    const totalWidth = rowWidth(maxPerLayer);

    let y = 0;
    for (const layer of layers) {
      if (!layer.length) continue;
      let rowY = y;
      let rowBottom = rowY;
      layer.forEach((spec, i) => {
        const col = i % perRow;
        const inRow = Math.min(perRow, layer.length - Math.floor(i / perRow) * perRow);
        const rowW = rowWidth(inRow);
        const x = (totalWidth - rowW) / 2 + col * (CARD_W + GAP_X);
        if (col === 0 && i > 0) {
          rowY = rowBottom + GAP_Y - 6;
        }
        nodes.push({
          id: spec.id,
          type: 'workflow',
          position: { x, y: rowY },
          draggable: true,
          selectable: false,
          data: spec,
        });
        const h = estimateHeight(spec);
        rowBottom = Math.max(col === 0 ? 0 : rowBottom, rowY + h);
      });
      y = rowBottom + GAP_Y;
    }

    const edges: Edge[] = edgeSpecs.map(e => {
      const s = EDGE_STYLE[e.state];
      return {
        id: `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: s.animated,
        style: { stroke: s.stroke, strokeWidth: s.strokeWidth },
      };
    });

    return { nodes, edges };
  }, [layers, edgeSpecs, perRow]);

  if (!nodes.length) {
    return (
      <div style={{ height }} className="rounded-lg border border-border-subtle bg-surface-inset flex items-center justify-center">
        <p className="text-[10px] text-muted-fg text-center px-6 leading-relaxed whitespace-pre-line">
          {emptyMessage || i18n.t('aiAgent.workflow.noNodes')}
        </p>
      </div>
    );
  }

  return (
    <div style={{ height }} className="rounded-lg border border-border-subtle overflow-hidden bg-surface-inset relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.1, maxZoom: 1 }}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        minZoom={0.3}
        maxZoom={1.6}
      >
        <AutoFit nodeCount={nodes.length} />
        <FocusNode request={focusRequest} />
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="rgba(120,130,155,0.18)" />
      </ReactFlow>
      <div className="pointer-events-none absolute bottom-1.5 right-2 text-[7.5px] uppercase tracking-[0.16em] text-muted-fg/40">
        {watermark}
      </div>
    </div>
  );
});
