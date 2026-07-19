'use client';

/**
 * LiveWorkflowsCanvas — tus workflows activos, como sistema vivo.
 *
 * Izquierda: rail tipo "carpetas" con todos los workflows agrupados por tipo
 * (programados, eventos, secuencias, rankings) y acciones rápidas
 * (activar/pausar). Click en uno → el canvas lo centra.
 *
 * Derecha: el canvas de nodos. Un nodo "Alert Engine" (el runtime de eventos
 * en tiempo real) conectado a una tarjeta por workflow. Los disparos llegan
 * por el WebSocket /ws/alerts (store compartido) y entran en el feed del nodo
 * con animación; el que acaba de disparar se ilumina en ámbar. Los workflows
 * programados (T4) muestran su última captura como tabla en vivo.
 */
import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { Clock3, GitBranch, ListOrdered, Pause, Play, Zap } from 'lucide-react';
import {
  AlertSpec, armAlert, fmtCooldown, formatPriceLevel, formatUniverse, listAlerts, pauseAlert,
} from '@/lib/aiAlerts';
import { useAIAlertFiresStore, type AIAlertFire } from '@/stores/useAIAlertFiresStore';
import { WorkflowCanvas, type FocusRequest } from './workflow/WorkflowCanvas';
import { WorkflowInspector } from './WorkflowInspector';
import type {
  NodeBlock, WorkflowEdgeSpec, WorkflowNodeSpec,
} from './workflow/types';

const POLL_MS = 60_000;
/** Ventana en la que un disparo se considera "recién llegado" (glow + arista). */
const FIRE_GLOW_MS = 10_000;

const TIER_LABELS: Record<string, string> = {
  event_match: 'evento en vivo',
  sequence: 'secuencia',
  membership: 'ranking',
  agentic: 'workflow',
  scheduled: 'programado',
};

function fmtEvery(seconds: number): string {
  if (seconds < 60) return `cada ${seconds}s`;
  if (seconds < 3600) return `cada ${Math.round(seconds / 60)}m`;
  return `cada ${Math.round(seconds / 3600)}h`;
}

function fmtPct(row: Record<string, number | string | undefined>): string {
  for (const k of ['postmarket_change_percent', 'premarket_change_percent', 'change_percent']) {
    const v = row[k];
    if (typeof v === 'number') return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  }
  return '';
}

/** T4 programado: la "foto" periódica como tabla en vivo dentro del nodo. */
function scheduledSpecToNode(
  spec: AlertSpec, fires: AIAlertFire[], justFired: boolean,
  onOpen?: () => void,
): WorkflowNodeSpec {
  const armed = spec.status === 'armed';
  const lastSnap = fires.find(f => f.snapshot && f.snapshot.rows?.length);
  const rows = lastSnap?.snapshot?.rows || [];
  const blocks: NodeBlock[] = [];

  const chips = [spec.schedule?.category || 'snapshot'];
  const universeChips = formatUniverse(spec.universe).slice(0, 3);
  blocks.push({ kind: 'chips', style: 'primary', items: chips });
  if (universeChips.length) blocks.push({ kind: 'chips', style: 'neutral', items: universeChips });

  if (rows.length) {
    blocks.push({
      kind: 'table',
      columns: ['Ticker', 'Precio', 'Cambio'],
      rows: rows.slice(0, 6).map(r => [
        String(r.symbol || ''),
        typeof r.price === 'number' ? `$${r.price.toFixed(2)}` : '',
        fmtPct(r as Record<string, number | string | undefined>),
      ]),
      total: rows.length,
      cascade: true,
    });
    if (lastSnap) {
      blocks.push({
        kind: 'metrics',
        items: [{ label: 'última captura', value: timeAgo(lastSnap.timestamp) }],
      });
    }
  } else {
    blocks.push({
      kind: 'text',
      text: armed
        ? 'Esperando la primera captura del intervalo…'
        : 'Workflow pausado — actívalo para reanudar las capturas.',
    });
  }

  return {
    id: spec.id,
    title: spec.name,
    subtitle: `workflow programado · ${fmtEvery(spec.schedule?.every_seconds || 60)}`,
    status: justFired ? 'fired' : armed ? 'live' : 'paused',
    footerLabel: 'scheduled workflow',
    badge: armed ? 'capturando' : undefined,
    blocks,
    onOpen,
  };
}

function timeAgo(epoch: number): string {
  const s = Math.max(0, Date.now() / 1000 - epoch);
  if (s < 60) return 'ahora';
  if (s < 3600) return `hace ${Math.floor(s / 60)}m`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
}

function isToday(epoch: number): boolean {
  const d = new Date(epoch * 1000);
  const n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
}

function engineSpec(connected: boolean, armedCount: number, firesToday: number): WorkflowNodeSpec {
  return {
    id: '__engine__',
    title: 'Alert Engine',
    subtitle: '240+ tipos de evento · todo el universo · tiempo real',
    status: connected ? 'live' : 'error',
    badge: connected ? 'emitiendo' : 'offline',
    footerLabel: 'event stream',
    blocks: [{
      kind: 'metrics',
      items: [
        { label: 'alertas activas', value: armedCount },
        { label: 'disparos hoy', value: firesToday },
      ],
    }],
  };
}

function alertSpecToNode(
  spec: AlertSpec, fires: AIAlertFire[], justFired: boolean,
  onOpen?: () => void,
): WorkflowNodeSpec {
  const armed = spec.status === 'armed';
  const firesToday = fires.filter(f => isToday(f.timestamp)).length;
  const lastFire = fires[0];

  const blocks: NodeBlock[] = [];

  const eventChips = [
    ...spec.steps.flatMap(s => s.event_types).slice(0, 3),
    ...(spec.price_levels || []).map(formatPriceLevel).slice(0, 3),
  ];
  if (eventChips.length) blocks.push({ kind: 'chips', style: 'primary', items: eventChips });

  const universeChips = formatUniverse(spec.universe).slice(0, 4);
  if (universeChips.length) blocks.push({ kind: 'chips', style: 'neutral', items: universeChips });

  const metrics: Array<{ label: string; value: string | number }> = [
    { label: 'hoy', value: firesToday },
  ];
  if (lastFire) metrics.push({ label: 'último', value: timeAgo(lastFire.timestamp) });
  blocks.push({ kind: 'metrics', items: metrics });

  if (fires.length) {
    blocks.push({
      kind: 'feed',
      rows: fires.slice(0, 3).map((f, i) => ({
        id: f.id,
        cells: [
          f.symbol,
          f.event_type,
          ...(f.price != null ? [`$${f.price.toFixed(2)}`] : []),
          timeAgo(f.timestamp),
        ],
        highlight: justFired && i === 0,
      })),
    });
  }

  return {
    id: spec.id,
    title: spec.name,
    subtitle: `${TIER_LABELS[spec.tier] || spec.tier} · cooldown ${fmtCooldown(spec.lifecycle.cooldown_seconds)}`,
    status: justFired ? 'fired' : armed ? 'live' : 'paused',
    footerLabel: 'live workflow',
    blocks,
    onOpen,
  };
}

/* ── Rail lateral: "carpetas" de workflows ─────────────────────── */

const GROUPS: Array<{ id: string; label: string; tiers: string[]; icon: typeof Zap }> = [
  { id: 'scheduled', label: 'Programados', tiers: ['scheduled'], icon: Clock3 },
  { id: 'events', label: 'Eventos en vivo', tiers: ['event_match'], icon: Zap },
  { id: 'sequences', label: 'Secuencias', tiers: ['sequence', 'agentic'], icon: GitBranch },
  { id: 'rankings', label: 'Rankings', tiers: ['membership'], icon: ListOrdered },
];

function WorkflowRailItem({
  spec, firesToday, justFired, busy, onFocus, onToggle,
}: {
  spec: AlertSpec;
  firesToday: number;
  justFired: boolean;
  busy: boolean;
  onFocus: () => void;
  onToggle: () => void;
}) {
  const armed = spec.status === 'armed';
  return (
    <div
      onClick={onFocus}
      className={`group flex items-center gap-1.5 rounded px-1.5 py-1 cursor-pointer transition-colors ${
        justFired ? 'bg-amber-500/10' : 'hover:bg-surface-hover'
      }`}
      title={spec.paraphrase || spec.name}
    >
      <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
        {armed && (
          <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${
            justFired ? 'bg-amber-400' : 'bg-emerald-400'
          }`} />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${
          justFired ? 'bg-amber-400' : armed ? 'bg-emerald-400' : 'bg-zinc-600'
        }`} />
      </span>
      <div className="min-w-0 flex-1">
        <p className={`truncate text-[9.5px] leading-tight ${armed ? 'text-foreground/90' : 'text-muted-fg'}`}>
          {spec.name}
        </p>
        <p className="truncate text-[8px] text-muted-fg/70 leading-tight">
          {spec.tier === 'scheduled'
            ? fmtEvery(spec.schedule?.every_seconds || 60)
            : `${firesToday} hoy`}
        </p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        disabled={busy}
        className="flex-shrink-0 rounded p-0.5 text-muted-fg opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 disabled:opacity-40"
        title={armed ? 'Pausar workflow' : 'Activar workflow'}
      >
        {armed ? <Pause size={10} /> : <Play size={10} />}
      </button>
    </div>
  );
}

interface LiveWorkflowsCanvasProps {
  height?: number | string;
}

export const LiveWorkflowsCanvas = memo(function LiveWorkflowsCanvas({
  height = '100%',
}: LiveWorkflowsCanvasProps) {
  const { getToken } = useAuth();
  const [specs, setSpecs] = useState<AlertSpec[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [focusReq, setFocusReq] = useState<FocusRequest | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Inspector de workflow (la antigua ventana AI Alerts, fusionada al canvas)
  const [inspectingId, setInspectingId] = useState<string | null>(null);
  const fires = useAIAlertFiresStore(s => s.fires);
  const connected = useAIAlertFiresStore(s => s.connected);

  // Tick para expirar el glow de "recién disparó" sin nuevos eventos.
  const [, setTick] = useState(0);
  useEffect(() => {
    const hasRecent = fires.some(f => !f.backlog && Date.now() - f.receivedAt < FIRE_GLOW_MS);
    if (!hasRecent) return;
    const t = setInterval(() => setTick(x => x + 1), 2_000);
    return () => clearInterval(t);
  }, [fires]);

  // Cargar alertas: al montar, al cambiar desde el chat, y polling suave.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await listAlerts(getToken, false);
        if (!cancelled) {
          setSpecs(res.alerts.filter(a => a.status === 'armed' || a.status === 'paused'));
          setLoaded(true);
        }
      } catch {
        if (!cancelled) setLoaded(true);
      }
    };
    void load();
    const poll = setInterval(load, POLL_MS);
    const onChanged = () => { void load(); };
    window.addEventListener('tradeul:ai-alerts-changed', onChanged);
    return () => {
      cancelled = true;
      clearInterval(poll);
      window.removeEventListener('tradeul:ai-alerts-changed', onChanged);
    };
  }, [getToken]);

  const { layers, edges } = useMemo(() => {
    const now = Date.now();
    const firesBySpec = new Map<string, AIAlertFire[]>();
    for (const f of fires) {
      if (!f.spec_id) continue;
      const list = firesBySpec.get(f.spec_id) || [];
      list.push(f);
      firesBySpec.set(f.spec_id, list);
    }
    for (const list of firesBySpec.values()) {
      list.sort((a, b) => b.timestamp - a.timestamp);
    }

    const armed = specs.filter(s => s.status === 'armed');
    const paused = specs.filter(s => s.status === 'paused');
    const ordered = [...armed, ...paused];
    const firesToday = fires.filter(f => isToday(f.timestamp)).length;

    const engine = engineSpec(connected, armed.length, firesToday);
    const alertNodes = ordered.map(spec => {
      const specFires = firesBySpec.get(spec.id) || [];
      const justFired = specFires.some(f => !f.backlog && now - f.receivedAt < FIRE_GLOW_MS);
      const onOpen = () => setInspectingId(spec.id);
      return spec.tier === 'scheduled'
        ? scheduledSpecToNode(spec, specFires, justFired, onOpen)
        : alertSpecToNode(spec, specFires, justFired, onOpen);
    });

    const layers: WorkflowNodeSpec[][] = alertNodes.length
      ? [[engine], alertNodes]
      : [[engine]];

    const edges: WorkflowEdgeSpec[] = alertNodes.map(n => ({
      source: engine.id,
      target: n.id,
      state: n.status === 'fired' ? 'fired' : n.status === 'live' ? 'live' : 'idle',
    }));

    return { layers, edges };
  }, [specs, fires, connected]);

  // Disparos de hoy por spec y glow para el rail.
  const railMeta = useMemo(() => {
    const now = Date.now();
    const meta = new Map<string, { today: number; justFired: boolean }>();
    for (const spec of specs) {
      const specFires = fires.filter(f => f.spec_id === spec.id);
      meta.set(spec.id, {
        today: specFires.filter(f => isToday(f.timestamp) && f.event_type !== 'scheduled_snapshot').length,
        justFired: specFires.some(f => !f.backlog && now - f.receivedAt < FIRE_GLOW_MS),
      });
    }
    return meta;
  }, [specs, fires]);

  const focusNode = useCallback((id: string) => {
    setFocusReq(prev => ({ nodeId: id, token: (prev?.token || 0) + 1 }));
  }, []);

  const toggleSpec = useCallback(async (spec: AlertSpec) => {
    setBusyId(spec.id);
    try {
      if (spec.status === 'armed') await pauseAlert(getToken, spec.id);
      else await armAlert(getToken, spec.id);
      window.dispatchEvent(new CustomEvent('tradeul:ai-alerts-changed'));
    } catch {
      // el polling lo reconciliará
    } finally {
      setBusyId(null);
    }
  }, [getToken]);

  if (loaded && specs.length === 0) {
    return (
      <WorkflowCanvas
        layers={[]}
        edges={[]}
        height={height}
        emptyMessage={
          'No tienes workflows activos todavía.\n\n' +
          'Pídele uno al agente y actívalo — p. ej.:\n' +
          '«Avísame cuando cualquier acción con RVOL > 2 cruce el VWAP al alza»\n' +
          '«Cada minuto, una foto del top after-hours con market cap > 1B»\n\n' +
          'Aparecerán aquí como nodos vivos con sus disparos y capturas en tiempo real.'
        }
      />
    );
  }

  return (
    <div style={{ height }} className="flex gap-1.5">
      {/* Rail: mis workflows, agrupados por tipo */}
      <div className="w-[168px] flex-shrink-0 overflow-y-auto rounded-lg border border-border-subtle bg-[#080b12] py-1.5 px-1">
        <p className="px-1.5 pb-1 text-[8px] font-semibold uppercase tracking-[0.14em] text-muted-fg/70">
          Mis workflows
        </p>
        {GROUPS.map(group => {
          const items = specs.filter(s => group.tiers.includes(s.tier));
          if (!items.length) return null;
          const Icon = group.icon;
          return (
            <div key={group.id} className="mb-1.5">
              <div className="flex items-center gap-1 px-1.5 py-0.5 text-muted-fg/80">
                <Icon size={9} />
                <span className="text-[8px] font-semibold uppercase tracking-wider">{group.label}</span>
                <span className="ml-auto text-[8px] tabular-nums">{items.length}</span>
              </div>
              {items.map(spec => {
                const m = railMeta.get(spec.id);
                return (
                  <WorkflowRailItem
                    key={spec.id}
                    spec={spec}
                    firesToday={m?.today || 0}
                    justFired={m?.justFired || false}
                    busy={busyId === spec.id}
                    onFocus={() => focusNode(spec.id)}
                    onToggle={() => void toggleSpec(spec)}
                  />
                );
              })}
            </div>
          );
        })}
        <button
          onClick={() => focusNode('__engine__')}
          className="mt-1 w-full rounded px-1.5 py-1 text-left text-[8.5px] text-muted-fg hover:bg-surface-hover hover:text-foreground/80 transition-colors"
        >
          ⌂ Ver todo el sistema
        </button>
      </div>

      {/* Canvas de nodos */}
      <div className="min-w-0 flex-1">
        <WorkflowCanvas
          layers={layers}
          edges={edges}
          height="100%"
          watermark="live workflows"
          focusRequest={focusReq}
        />
      </div>

      {/* Inspector: detalle completo del workflow (spec + historial de disparos) */}
      <WorkflowInspector
        spec={specs.find(s => s.id === inspectingId) || null}
        onClose={() => setInspectingId(null)}
      />
    </div>
  );
});
