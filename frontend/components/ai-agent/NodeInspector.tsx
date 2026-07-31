'use client';

/**
 * NodeInspector — el "mini-notebook" de un nodo del workflow.
 *
 * Al hacer clic en un nodo del canvas se abre este modal con TODO lo que el
 * nodo produjo, sin truncar: resumen, código/spec completo, tablas enteras,
 * charts de evidencia y el JSON raw. Los tabs son dinámicos: solo aparecen
 * los tipos de artifact que el nodo generó.
 *
 * Los artifacts viven en el backend (runs/artifacts.py → Postgres); aquí se
 * piden por REST con la referencia {runId, node} que llegó por WebSocket.
 *
 * `InspectorModal` es el shell genérico: también lo usa WorkflowInspector
 * (detalles de un workflow armado) con artifacts construidos en el cliente.
 */
import { memo, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '@clerk/nextjs';
import i18n from '@/lib/i18n';
import { getNodeArtifacts } from '@/lib/agentRuns';
import { getOverlayRoot } from '@/lib/overlayRoot';
import type { Artifact } from './types';
import { EvidenceChart } from './EvidenceChart';
import type { ChartEvidence } from '@/lib/aiAlerts';

export interface InspectTarget {
  runId: string;
  node: string;
  title: string;
  subtitle?: string;
}

/* ── Formato de celdas (los artifacts llevan valores crudos) ── */
function fmtCell(v: string | number | boolean | null): string {
  if (v == null) return '—';
  if (typeof v === 'boolean') return v ? i18n.t('aiAgent.node.yes') : i18n.t('aiAgent.node.no');
  if (typeof v === 'number') {
    if (Number.isInteger(v) && Math.abs(v) < 10_000) return String(v);
    if (Math.abs(v) >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
    if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (Math.abs(v) >= 10_000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }
  return String(v);
}

/* ── Agrupación de artifacts en tabs ── */
type TabId = 'resumen' | 'codigo' | 'datos' | 'charts' | 'raw';

function tabLabel(id: TabId): string {
  switch (id) {
    case 'codigo': return i18n.t('aiAgent.node.code');
    case 'resumen': return 'Resumen';
    case 'datos': return 'Output';
    case 'charts': return 'Charts';
    case 'raw': return 'Raw';
  }
}

const TAB_OF_KIND: Record<Artifact['kind'], TabId> = {
  summary: 'resumen',
  metrics: 'resumen',
  chips: 'resumen',
  code: 'codigo',
  table: 'datos',
  chart: 'charts',
  image: 'charts',
  json: 'raw',
};

const TAB_ORDER: TabId[] = ['resumen', 'datos', 'codigo', 'charts', 'raw'];

/* ── Renderers por tipo de artifact ── */

const SummaryArt = ({ art }: { art: Extract<Artifact, { kind: 'summary' }> }) => (
  <section>
    {art.title && <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title}</h4>}
    <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-foreground">{art.text}</p>
  </section>
);

const MetricsArt = ({ art }: { art: Extract<Artifact, { kind: 'metrics' }> }) => (
  <section>
    {art.title && <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title}</h4>}
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
      {art.items.map((it, i) => (
        <div key={i} className="rounded-lg border border-border-subtle bg-surface-inset/60 px-2.5 py-1.5">
          <div className="text-[9px] uppercase tracking-wider text-muted-fg/70 truncate" title={it.label}>
            {it.label.replace(/_/g, ' ')}
          </div>
          <div className="text-[12px] font-semibold tabular-nums text-foreground truncate">
            {typeof it.value === 'number' ? fmtCell(it.value) : it.value}
          </div>
        </div>
      ))}
    </div>
  </section>
);

const ChipsArt = ({ art }: { art: Extract<Artifact, { kind: 'chips' }> }) => (
  <section>
    {art.title && <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title}</h4>}
    <div className="flex flex-wrap gap-1">
      {art.items.map((c, i) => (
        <span key={i} className="rounded-md border border-primary/25 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary">
          {c}
        </span>
      ))}
    </div>
  </section>
);

const CodeArt = ({ art }: { art: Extract<Artifact, { kind: 'code' }> }) => (
  <section>
    <div className="mb-1 flex items-center justify-between">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title || i18n.t('aiAgent.node.code')}</h4>
      {art.language && <span className="font-mono text-[9px] text-muted-fg/60">{art.language}</span>}
    </div>
    <pre className="max-h-[420px] overflow-auto rounded-lg border border-border-subtle bg-surface-inset p-3 font-mono text-[10.5px] leading-relaxed text-foreground/90">
      {art.content}
    </pre>
  </section>
);

const TableArt = ({ art }: { art: Extract<Artifact, { kind: 'table' }> }) => (
  <section>
    <div className="mb-1 flex items-center justify-between">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title || 'Tabla'}</h4>
      {art.total != null && (
        <span className="text-[9px] tabular-nums text-muted-fg/70">
          {art.rows.length < art.total ? `${art.rows.length} de ${art.total} filas` : `${art.total} filas`}
        </span>
      )}
    </div>
    <div className="max-h-[420px] overflow-auto rounded-lg border border-border-subtle">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 z-10 bg-surface-inset">
          <tr>
            {art.columns.map((c, i) => (
              <th key={i} className="whitespace-nowrap px-2 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-fg">
                {c.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {art.rows.map((row, ri) => (
            <tr key={ri} className="border-t border-border-subtle/60 hover:bg-surface-inset/50">
              {row.map((cell, ci) => (
                <td key={ci} className={`whitespace-nowrap px-2 py-1 text-[10.5px] tabular-nums ${ci === 0 ? 'font-semibold text-foreground' : 'text-foreground/80'}`}>
                  {fmtCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </section>
);

const ChartArt = ({ art }: { art: Extract<Artifact, { kind: 'chart' }> }) => {
  const c = art.chart;
  const hasBars = Array.isArray((c as { bars?: unknown[] }).bars) && ((c as { bars?: unknown[] }).bars?.length || 0) > 0;
  return (
    <section>
      <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title || 'Chart'}</h4>
      {hasBars ? (
        <div className="rounded-lg border border-border-subtle bg-surface-inset/40 p-1">
          <EvidenceChart evidence={c as unknown as ChartEvidence} height={220} />
        </div>
      ) : (
        <pre className="max-h-[280px] overflow-auto rounded-lg border border-border-subtle bg-surface-inset p-3 font-mono text-[10px] text-foreground/80">
          {JSON.stringify(c, null, 2)}
        </pre>
      )}
    </section>
  );
};

const JsonArt = ({ art }: { art: Extract<Artifact, { kind: 'json' }> }) => (
  <section>
    <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title || 'JSON'}</h4>
    <pre className="max-h-[460px] overflow-auto rounded-lg border border-border-subtle bg-surface-inset p-3 font-mono text-[10px] leading-relaxed text-foreground/85">
      {JSON.stringify(art.data, null, 2)}
    </pre>
  </section>
);

const ImageArt = ({ art }: { art: Extract<Artifact, { kind: 'image' }> }) => (
  <section>
    <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-fg">{art.title || 'Chart'}</h4>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img
      src={`data:${art.mime || 'image/png'};base64,${art.data_base64}`}
      alt={art.title || 'chart'}
      className="max-h-[420px] w-full rounded-lg border border-border-subtle bg-white object-contain"
    />
  </section>
);

function renderArtifact(art: Artifact, i: number) {
  switch (art.kind) {
    case 'summary': return <SummaryArt key={i} art={art} />;
    case 'metrics': return <MetricsArt key={i} art={art} />;
    case 'chips': return <ChipsArt key={i} art={art} />;
    case 'code': return <CodeArt key={i} art={art} />;
    case 'table': return <TableArt key={i} art={art} />;
    case 'chart': return <ChartArt key={i} art={art} />;
    case 'json': return <JsonArt key={i} art={art} />;
    case 'image': return <ImageArt key={i} art={art} />;
    default: return null;
  }
}

/* ── Shell genérico del inspector (modal + tabs dinámicos) ── */

export interface InspectorModalProps {
  open: boolean;
  title: string;
  subtitle?: string;
  /** Etiqueta mono a la derecha del header (nombre técnico del nodo). */
  tag?: string;
  /** null = cargando. */
  artifacts: Artifact[] | null;
  error?: string | null;
  onClose: () => void;
  /** Acciones del header (activar/pausar/archivar en workflows). */
  actions?: ReactNode;
  footerLeft?: string;
}

export const InspectorModal = memo(function InspectorModal({
  open, title, subtitle, tag, artifacts, error, onClose, actions, footerLeft,
}: InspectorModalProps) {
  const [tab, setTab] = useState<TabId>('resumen');

  const tabs = useMemo(() => {
    if (!artifacts) return [] as TabId[];
    const present = new Set(artifacts.map(a => TAB_OF_KIND[a.kind]));
    return TAB_ORDER.filter(t => present.has(t));
  }, [artifacts]);

  useEffect(() => {
    if (tabs.length && !tabs.includes(tab)) setTab(tabs[0]);
  }, [tabs, tab]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[1300] flex items-center justify-center bg-black/50 backdrop-blur-[2px] p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            className="flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
            style={{ maxHeight: '84vh' }}
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 6 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            {/* Header */}
            <div className="flex items-start gap-2 border-b border-border-subtle px-4 py-3">
              <div className="min-w-0 flex-1">
                <h3 className="text-[13px] font-semibold text-foreground truncate">{title}</h3>
                {subtitle && (
                  <p className="text-[10px] text-muted-fg truncate">{subtitle}</p>
                )}
              </div>
              {actions}
              {tag && (
                <span className="rounded-md bg-surface-inset px-1.5 py-0.5 font-mono text-[9px] text-muted-fg/70">
                  {tag}
                </span>
              )}
              <button
                onClick={onClose}
                className="rounded-md p-1 text-muted-fg transition-colors hover:bg-surface-inset hover:text-foreground"
                aria-label="Cerrar inspector"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tabs dinámicos */}
            {tabs.length > 1 && (
              <div className="flex gap-1 border-b border-border-subtle px-4 pt-2">
                {tabs.map(t => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`rounded-t-md px-2.5 py-1.5 text-[10.5px] font-semibold transition-colors ${
                      tab === t
                        ? 'border-b-2 border-primary text-foreground'
                        : 'text-muted-fg hover:text-foreground'
                    }`}
                  >
                    {tabLabel(t)}
                  </button>
                ))}
              </div>
            )}

            {/* Contenido */}
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
              {artifacts === null && !error && (
                <div className="flex items-center gap-2 py-8 text-[11px] text-muted-fg justify-center">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  Cargando detalles…
                </div>
              )}
              {error && (
                <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[11px] text-red-400">
                  {error}
                </div>
              )}
              {artifacts !== null && !error && artifacts.length === 0 && (
                <p className="py-8 text-center text-[11px] text-muted-fg">
                  Sin datos persistidos para mostrar.
                </p>
              )}
              {artifacts
                ?.filter(a => TAB_OF_KIND[a.kind] === tab)
                .map((a, i) => renderArtifact(a, i))}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-border-subtle px-4 py-2">
              <span className="text-[8.5px] uppercase tracking-[0.14em] text-muted-fg/60">
                {footerLeft || 'node inspector · artifacts completos'}
              </span>
              {artifacts && (
                <span className="text-[9px] tabular-nums text-muted-fg/70">
                  {artifacts.length} artifact{artifacts.length === 1 ? '' : 's'}
                </span>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    getOverlayRoot(),
  );
});

/* ── Inspector de nodo de ejecución: pide los artifacts por REST ── */

interface NodeInspectorProps {
  target: InspectTarget | null;
  onClose: () => void;
}

export const NodeInspector = memo(function NodeInspector({ target, onClose }: NodeInspectorProps) {
  const { getToken } = useAuth();
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setArtifacts(null);
    setError(null);
    let cancelled = false;
    // Reintentos: el WS llega antes de que Postgres termine el save (fire-and-forget).
    const load = async () => {
      let lastErr: unknown = null;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (cancelled) return;
        try {
          const res = await getNodeArtifacts(getToken, target.runId, target.node);
          if (cancelled) return;
          if ((res.artifacts || []).length > 0 || attempt === 3) {
            setArtifacts(res.artifacts || []);
            return;
          }
        } catch (err) {
          lastErr = err;
        }
        await new Promise(r => setTimeout(r, 350 * (attempt + 1)));
      }
      if (!cancelled && lastErr) {
        setError(lastErr instanceof Error ? lastErr.message : i18n.t('aiAgent.errors.loadArtifacts'));
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [target, getToken]);

  return (
    <InspectorModal
      open={target !== null}
      title={target?.title || ''}
      subtitle={target?.subtitle}
      tag={target?.node}
      artifacts={artifacts}
      error={error}
      onClose={onClose}
    />
  );
});
