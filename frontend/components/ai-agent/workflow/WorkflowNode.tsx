'use client';

/**
 * WorkflowNode — LA tarjeta de nodo de todos los canvases de Tradeul.
 *
 * Renderiza un WorkflowNodeSpec: header con estado, bloques tipados
 * (progreso, métricas, chips, tabla en cascada, código typewriter, feed en
 * vivo) y footer. Los nodos "running"/"live" llevan una scanline interna de
 * procesamiento — el efecto de "se ve trabajar al sistema por dentro".
 */
import { memo, useState } from 'react';
import { motion } from 'framer-motion';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { NodeBlock, WorkflowNodeSpec, WorkflowNodeStatus } from './types';
import {
  CascadeTable, Chips, LiveFeed, MetricChips, ProgressLine, TypewriterCode,
} from './blocks';

export const CARD_W = 236;

const STATUS_LABEL: Record<WorkflowNodeStatus, string> = {
  pending: 'en cola',
  running: 'ejecutando',
  complete: 'listo',
  error: 'error',
  live: 'vigilando',
  paused: 'en pausa',
  fired: '¡disparó!',
};

const STATUS_TEXT: Record<WorkflowNodeStatus, string> = {
  pending: 'text-muted-fg/50',
  running: 'text-primary',
  complete: 'text-emerald-400',
  error: 'text-red-400',
  live: 'text-emerald-400',
  paused: 'text-muted-fg/60',
  fired: 'text-amber-400',
};

const CARD_STYLE: Record<WorkflowNodeStatus, string> = {
  pending: 'border-border-subtle bg-surface/60 opacity-55',
  running: 'border-primary/70 bg-surface shadow-[0_0_24px_-6px_rgba(99,102,241,0.55)]',
  complete: 'border-emerald-500/30 bg-surface shadow-[0_0_16px_-10px_rgba(16,185,129,0.4)]',
  error: 'border-red-500/50 bg-surface',
  live: 'border-emerald-500/40 bg-surface shadow-[0_0_16px_-10px_rgba(16,185,129,0.45)]',
  paused: 'border-border-subtle bg-surface/60 opacity-60',
  fired: 'border-amber-400/80 bg-surface shadow-[0_0_28px_-4px_rgba(251,191,36,0.65)]',
};

const FOOTER_STYLE: Record<WorkflowNodeStatus, string> = {
  pending: 'border-border-subtle bg-transparent',
  running: 'border-primary/15 bg-primary/[0.04]',
  complete: 'border-emerald-500/10 bg-emerald-500/[0.03]',
  error: 'border-red-500/15 bg-red-500/[0.04]',
  live: 'border-emerald-500/10 bg-emerald-500/[0.03]',
  paused: 'border-border-subtle bg-transparent',
  fired: 'border-amber-400/20 bg-amber-400/[0.05]',
};

const DOT_COLOR: Record<WorkflowNodeStatus, string> = {
  pending: 'bg-muted-fg/40',
  running: 'bg-primary',
  complete: 'bg-emerald-400',
  error: 'bg-red-400',
  live: 'bg-emerald-400',
  paused: 'bg-muted-fg/40',
  fired: 'bg-amber-400',
};

const PULSING: Set<WorkflowNodeStatus> = new Set(['running', 'live', 'fired']);

function fmtDuration(s: number): string {
  return s < 1 ? `${Math.round(s * 1000)}ms` : `${s.toFixed(1)}s`;
}

const StatusDot = ({ status }: { status: WorkflowNodeStatus }) => (
  <span className="relative flex h-1.5 w-1.5 shrink-0">
    {PULSING.has(status) && (
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOT_COLOR[status]}`} />
    )}
    <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${DOT_COLOR[status]}`} />
  </span>
);

/** Scanline de procesamiento que recorre el nodo mientras trabaja. */
const Scanline = ({ slow }: { slow?: boolean }) => (
  <motion.div
    className="pointer-events-none absolute left-0 right-0 h-10 bg-gradient-to-b from-transparent via-primary/[0.07] to-transparent"
    initial={{ top: '-15%' }}
    animate={{ top: '115%' }}
    transition={{ duration: slow ? 3.6 : 1.9, repeat: Infinity, ease: 'linear' }}
  />
);

function renderBlock(block: NodeBlock, i: number) {
  switch (block.kind) {
    case 'progress':
      return <ProgressLine key={i} text={block.text} />;
    case 'metrics':
      return <MetricChips key={i} items={block.items} />;
    case 'chips':
      return <Chips key={i} items={block.items} style={block.style} />;
    case 'text':
      return <p key={i} className="text-[8px] leading-snug text-muted-fg line-clamp-3">{block.text}</p>;
    case 'error':
      return (
        <div key={i} className="rounded-md bg-red-500/10 border border-red-500/20 px-2 py-1 text-[8px] leading-snug text-red-400">
          {block.text}
        </div>
      );
    case 'table':
      return <CascadeTable key={i} block={block} />;
    case 'code':
      return <TypewriterCode key={i} content={block.content} typewriter={block.typewriter} />;
    case 'feed':
      return <LiveFeed key={i} rows={block.rows} />;
  }
}

export const WorkflowNode = memo(function WorkflowNode({ data }: NodeProps<WorkflowNodeSpec>) {
  const { status } = data;

  // Tabla + código conviven en pestañas para contener la altura.
  const tableIdx = data.blocks.findIndex(b => b.kind === 'table');
  const codeIdx = data.blocks.findIndex(b => b.kind === 'code');
  const tabbed = tableIdx !== -1 && codeIdx !== -1;
  const [tab, setTab] = useState<'data' | 'code'>('data');
  const inlineBlocks = tabbed
    ? data.blocks.filter((_, i) => i !== tableIdx && i !== codeIdx)
    : data.blocks;

  return (
    <div
      style={{ width: CARD_W }}
      className={`relative overflow-hidden rounded-xl border backdrop-blur-sm transition-all duration-500 ${CARD_STYLE[status]}`}
    >
      {status === 'running' && <Scanline />}
      {status === 'live' && <Scanline slow />}

      <Handle type="target" position={Position.Top} className="!w-1.5 !h-1.5 !bg-border !border-0 !-top-[3px]" />

      {/* Header */}
      <div className="flex items-center gap-1.5 px-2.5 pt-2">
        {data.stepNumber != null && (
          <span className={`flex h-4 w-4 items-center justify-center rounded text-[8px] font-bold tabular-nums shrink-0 ${
            status === 'running' ? 'bg-primary text-white' :
            status === 'complete' || status === 'live' ? 'bg-emerald-500/15 text-emerald-400' :
            status === 'error' ? 'bg-red-500/15 text-red-400' :
            status === 'fired' ? 'bg-amber-400/15 text-amber-400' : 'bg-surface-inset text-muted-fg'
          }`}>
            {data.stepNumber}
          </span>
        )}
        <span className="text-[10px] font-semibold text-foreground leading-tight flex-1 truncate" title={data.title}>
          {data.title}
        </span>
        <StatusDot status={status} />
      </div>

      {/* Subtítulo + duración */}
      {(data.subtitle || (data.duration != null && data.duration > 0)) && (
        <div className="flex items-center justify-between px-2.5 pt-0.5 pb-1.5">
          <span className="text-[8px] text-muted-fg/70 truncate">{data.subtitle || ''}</span>
          {data.duration != null && data.duration > 0 && (
            <span className="text-[8px] font-mono text-muted-fg tabular-nums shrink-0 ml-1">
              {fmtDuration(data.duration)}
            </span>
          )}
        </div>
      )}

      {/* Bloques */}
      <div className="flex flex-col gap-1.5 px-2.5 pb-2 empty:pb-1 nowheel nodrag">
        {inlineBlocks.map((b, i) => renderBlock(b, i))}

        {tabbed && (
          <div>
            <div className="flex gap-0.5 mb-1">
              {(['data', 'code'] as const).map(t => (
                <button
                  key={t}
                  onClick={(e) => { e.stopPropagation(); setTab(t); }}
                  className={`rounded px-1.5 py-0.5 text-[7.5px] font-semibold uppercase tracking-wider transition-colors ${
                    tab === t ? 'bg-surface-inset text-foreground' : 'text-muted-fg/60 hover:text-muted-fg'
                  }`}
                >
                  {t === 'data' ? 'Datos' : 'Spec'}
                </button>
              ))}
            </div>
            {renderBlock(data.blocks[tab === 'data' ? tableIdx : codeIdx], tab === 'data' ? tableIdx : codeIdx)}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className={`flex items-center justify-between rounded-b-xl border-t px-2.5 py-1 ${FOOTER_STYLE[status]}`}>
        <span className="text-[7px] uppercase tracking-[0.14em] text-muted-fg/60">
          {data.footerLabel || 'computation step'}
        </span>
        <span className={`text-[7.5px] font-semibold uppercase tracking-wider ${STATUS_TEXT[status]}`}>
          {data.badge || STATUS_LABEL[status]}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!w-1.5 !h-1.5 !bg-border !border-0 !-bottom-[3px]" />
    </div>
  );
});
