'use client';

/**
 * Bloques internos de un WorkflowNode, con las animaciones de procesamiento:
 *  - TypewriterCode: el código/spec se escribe en vivo con cursor.
 *  - CascadeTable: las filas de datos reales entran una a una en cascada.
 *  - LiveFeed: filas en vivo (disparos/ticks) que se deslizan al llegar.
 *  - Progress: línea de estado con cursor parpadeante.
 *
 * Cada animación corre UNA vez por contenido (refs de "ya animado") para que
 * los re-renders del canvas no la reinicien.
 */
import { memo, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { NodeBlock } from './types';

/* ── Typewriter ──────────────────────────────────────────────────── */

const CHARS_PER_TICK = 4;
const TICK_MS = 14;

function useTypewriter(content: string, enabled: boolean): { text: string; typing: boolean } {
  // Clave por contenido: si el contenido cambia, vuelve a escribirse.
  const animatedRef = useRef<string | null>(null);
  const [visible, setVisible] = useState(() => (enabled ? 0 : content.length));

  useEffect(() => {
    if (!enabled || animatedRef.current === content) {
      setVisible(content.length);
      return;
    }
    animatedRef.current = content;
    setVisible(0);
    let i = 0;
    const t = setInterval(() => {
      i += CHARS_PER_TICK;
      if (i >= content.length) {
        clearInterval(t);
        setVisible(content.length);
      } else {
        setVisible(i);
      }
    }, TICK_MS);
    return () => clearInterval(t);
  }, [content, enabled]);

  return { text: content.slice(0, visible), typing: visible < content.length };
}

export const TypewriterCode = memo(function TypewriterCode({
  content,
  typewriter,
}: {
  content: string;
  typewriter?: boolean;
}) {
  const { text, typing } = useTypewriter(content, !!typewriter);
  return (
    <pre className="rounded-md border border-border-subtle bg-slate-100 dark:bg-[#0a0e16] px-2 py-1.5 text-[8px] leading-[1.5] font-mono text-sky-800 dark:text-sky-300/90 overflow-hidden max-h-[104px] whitespace-pre-wrap break-all">
      {text}
      {typing && <span className="inline-block w-[5px] h-[9px] bg-sky-300/90 align-middle animate-pulse ml-px" />}
    </pre>
  );
});

/* ── Tabla con cascada ───────────────────────────────────────────── */

export const CascadeTable = memo(function CascadeTable({
  block,
}: {
  block: Extract<NodeBlock, { kind: 'table' }>;
}) {
  // Cascada solo la primera vez que este contenido se pinta.
  const key = block.rows.map(r => r[0]).join('|');
  const animatedRef = useRef<string | null>(null);
  const shouldCascade = !!block.cascade && animatedRef.current !== key;
  useEffect(() => {
    animatedRef.current = key;
  }, [key]);

  return (
    <div className="rounded-md border border-border-subtle overflow-hidden bg-surface-inset/60">
      {block.title && (
        <div className="px-2 py-1 text-[8px] font-semibold text-muted-fg uppercase tracking-wider border-b border-border-subtle bg-surface-inset">
          {block.title}
          {block.total != null && <span className="normal-case font-normal"> · {block.total}</span>}
        </div>
      )}
      <table className="w-full border-collapse table-fixed">
        <thead>
          <tr>
            {block.columns.map((c, i) => (
              <th key={i} className="px-1 py-0.5 text-left text-[7.5px] font-semibold text-muted-fg/80 uppercase tracking-wide border-b border-border-subtle truncate overflow-hidden">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, ri) => (
            <motion.tr
              key={ri}
              initial={shouldCascade ? { opacity: 0, x: -10 } : false}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: shouldCascade ? ri * 0.09 : 0 }}
              className={ri % 2 === 1 ? 'bg-surface-hover/30' : ''}
            >
              {row.map((cell, ci) => (
                <td key={ci} className={`px-1 py-0.5 text-[8px] truncate overflow-hidden whitespace-nowrap ${
                  ci === 0 ? 'font-semibold text-foreground font-mono' : 'text-foreground/70 tabular-nums'
                }`}>
                  {cell}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

/* ── Feed en vivo (disparos / ticks) ─────────────────────────────── */

export const LiveFeed = memo(function LiveFeed({
  rows,
}: {
  rows: Array<{ id: string; cells: string[]; highlight?: boolean }>;
}) {
  return (
    <div className="rounded-md border border-border-subtle overflow-hidden bg-surface-inset/60">
      <AnimatePresence initial={false}>
        {rows.map((r, i) => (
          <motion.div
            key={r.id}
            layout
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className={`flex items-center gap-1.5 px-1.5 py-0.5 ${i > 0 ? 'border-t border-border-subtle/60' : ''} ${
              r.highlight ? 'bg-amber-400/10' : ''
            }`}
          >
            <span className="text-[8px] font-mono font-bold text-foreground w-[42px] truncate shrink-0">
              {r.cells[0]}
            </span>
            {r.cells.slice(1, -1).map((c, ci) => (
              <span key={ci} className="text-[7.5px] font-mono text-muted-fg flex-1 truncate">{c}</span>
            ))}
            {r.cells.length > 1 && (
              <span className="text-[7.5px] text-muted-fg/70 tabular-nums shrink-0">
                {r.cells[r.cells.length - 1]}
              </span>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
});

/* ── Bloques simples ─────────────────────────────────────────────── */

export const ProgressLine = memo(function ProgressLine({ text }: { text: string }) {
  return (
    <div className="rounded-md bg-primary/5 border border-primary/15 px-2 py-1 text-[8px] leading-snug text-primary/90">
      {text}
      <span className="inline-block w-[4px] h-[8px] bg-primary/70 align-middle animate-pulse ml-0.5" />
    </div>
  );
});

export const MetricChips = memo(function MetricChips({
  items,
}: {
  items: Array<{ label: string; value: string | number }>;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.slice(0, 6).map(({ label, value }) => (
        <span key={label} className="inline-flex items-baseline gap-1 rounded bg-surface-inset px-1.5 py-0.5">
          <span className="text-[7px] uppercase tracking-wide text-muted-fg/70">{label}</span>
          <span className="text-[8.5px] font-semibold text-foreground tabular-nums">{String(value)}</span>
        </span>
      ))}
    </div>
  );
});

const CHIP_STYLES: Record<'primary' | 'neutral' | 'mono', string> = {
  primary: 'rounded bg-primary/10 border border-primary/20 px-1.5 py-0.5 text-[7.5px] font-medium text-primary',
  neutral: 'rounded bg-surface-inset px-1.5 py-0.5 text-[7.5px] text-foreground/70',
  mono: 'rounded bg-surface-inset px-1.5 py-0.5 text-[8px] font-mono font-semibold text-foreground/80',
};

export const Chips = memo(function Chips({
  items,
  style,
}: {
  items: string[];
  style: 'primary' | 'neutral' | 'mono';
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map(c => (
        <span key={c} className={CHIP_STYLES[style]}>{c}</span>
      ))}
    </div>
  );
});
