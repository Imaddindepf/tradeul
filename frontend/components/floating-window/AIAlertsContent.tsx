'use client';

/**
 * AIAlertsContent — floating window for LLM-compiled alerts.
 *
 * Lists every alert spec the user created from the chat (drafts, armed,
 * paused), with the paraphrase contract, universe chips, dry-run stats,
 * per-alert fire history with evidence, and lifecycle actions
 * (arm / pause / re-check / archive). Refreshes when the chat creates or
 * arms a draft (tradeul:ai-alerts-changed) and polls while open.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import dynamic from 'next/dynamic';
import {
  Archive, BellRing, CheckCircle2, ChevronDown, ChevronRight, Clock,
  FlaskConical, Loader2, MessageSquarePlus, Pause, Radio, RefreshCw,
  ShieldCheck, Volume2, VolumeX, Zap,
} from 'lucide-react';

const LazyEvidenceChart = dynamic(
  () => import('@/components/ai-agent/EvidenceChart').then(m => m.EvidenceChart),
  { ssr: false, loading: () => <div className="h-[150px] bg-surface-hover rounded-lg animate-pulse" /> },
);
import {
  AlertFire, AlertSpec, DryRunResult,
  archiveAlert, armAlert, fmtCooldown, formatPriceLevel, formatUniverse,
  listAlerts, listFires, matchSteps, pauseAlert, rerunDryRun,
} from '@/lib/aiAlerts';
import { useAIAlertFiresStore } from '@/stores/useAIAlertFiresStore';

const POLL_MS = 45_000;

const STATUS_META: Record<string, { label: string; cls: string; dot: string }> = {
  armed: { label: 'ACTIVA', cls: 'bg-emerald-500/10 text-emerald-500', dot: 'bg-emerald-500 animate-pulse' },
  draft: { label: 'BORRADOR', cls: 'bg-amber-500/10 text-amber-500', dot: 'bg-amber-500' },
  paused: { label: 'PAUSADA', cls: 'bg-slate-500/10 text-slate-400', dot: 'bg-slate-400' },
  archived: { label: 'ARCHIVADA', cls: 'bg-slate-500/10 text-slate-500', dot: 'bg-slate-500' },
};

const TIER_LABELS: Record<string, string> = {
  event_match: 'Evento en vivo',
  sequence: 'Secuencia',
  membership: 'Ranking',
  agentic: 'Workflow',
};

function timeAgo(epoch: number): string {
  const s = Math.max(0, Date.now() / 1000 - epoch);
  if (s < 60) return 'ahora';
  if (s < 3600) return `hace ${Math.floor(s / 60)}m`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
}

function pct(v: number | undefined | null): string {
  if (v == null || isNaN(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

// ── Fire performance mini-dashboard ───────────────────────────────
// Answers "¿esta alerta me sirve?" at a glance: cadence over the last
// 7 days, which tickers dominate, and how fresh the last fire is.

function FireDashboard({ fires }: { fires: AlertFire[] }) {
  const stats = useMemo(() => {
    const now = Date.now() / 1000;
    const dayKey = (epoch: number) => {
      const d = new Date(epoch * 1000);
      return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    };
    const days: Array<{ key: string; label: string; count: number }> = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400_000);
      days.push({
        key: `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`,
        label: d.toLocaleDateString('es-ES', { weekday: 'short' }).slice(0, 2),
        count: 0,
      });
    }
    const byDay = new Map(days.map(d => [d.key, d]));
    const bySymbol = new Map<string, number>();
    let today = 0;
    let last7 = 0;
    for (const f of fires) {
      const slot = byDay.get(dayKey(f.fired_at));
      if (slot) slot.count++;
      if (now - f.fired_at < 7 * 86400) {
        last7++;
        bySymbol.set(f.symbol, (bySymbol.get(f.symbol) || 0) + 1);
      }
      if (dayKey(f.fired_at) === dayKey(now)) today++;
    }
    const topSymbols = [...bySymbol.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
    const lastFire = fires.length ? Math.max(...fires.map(f => f.fired_at)) : null;
    return { days, today, last7, topSymbols, lastFire };
  }, [fires]);

  if (!fires.length) return null;
  const maxCount = Math.max(1, ...stats.days.map(d => d.count));

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-inset/40 p-2">
      <div className="flex items-center gap-3">
        {/* Stat row */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div>
            <div className="text-[13px] font-bold tabular-nums text-foreground leading-none">{stats.today}</div>
            <div className="text-[7.5px] uppercase tracking-wider text-muted-fg mt-0.5">hoy</div>
          </div>
          <div>
            <div className="text-[13px] font-bold tabular-nums text-foreground leading-none">{stats.last7}</div>
            <div className="text-[7.5px] uppercase tracking-wider text-muted-fg mt-0.5">7 días</div>
          </div>
          <div>
            <div className="text-[13px] font-bold tabular-nums text-foreground leading-none">
              {(stats.last7 / 7).toFixed(1)}
            </div>
            <div className="text-[7.5px] uppercase tracking-wider text-muted-fg mt-0.5">media/día</div>
          </div>
        </div>

        {/* 7-day histogram */}
        <div className="flex-1 flex items-end gap-[3px] h-8 min-w-0">
          {stats.days.map((d, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-0.5 min-w-0">
              <div
                className={`w-full rounded-sm ${d.count > 0 ? 'bg-primary/70' : 'bg-surface-hover'}`}
                style={{ height: `${Math.max(8, (d.count / maxCount) * 100)}%` }}
                title={`${d.count} disparos`}
              />
              <span className="text-[6.5px] text-muted-fg leading-none">{d.label}</span>
            </div>
          ))}
        </div>
      </div>

      {(stats.topSymbols.length > 0 || stats.lastFire) && (
        <div className="flex items-center justify-between mt-1.5 pt-1.5 border-t border-border-subtle">
          <div className="flex items-center gap-1">
            {stats.topSymbols.map(([sym, n]) => (
              <span key={sym} className="px-1 py-px rounded bg-surface-hover text-[8px] font-mono text-foreground/70">
                {sym}·{n}
              </span>
            ))}
          </div>
          {stats.lastFire && (
            <span className="text-[8px] text-muted-fg">último {timeAgo(stats.lastFire)}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Per-alert expanded detail ─────────────────────────────────────

function AlertDetail({ spec, onChanged }: { spec: AlertSpec; onChanged: () => void }) {
  const { getToken } = useAuth();
  const [fires, setFires] = useState<AlertFire[] | null>(null);
  const [dryResult, setDryResult] = useState<DryRunResult | null>(null);
  const [dryRunning, setDryRunning] = useState(false);
  const [error, setError] = useState('');

  // Nº de disparos en vivo de esta spec: al crecer, refresca el historial REST
  const liveFireCount = useAIAlertFiresStore(
    (s) => s.fires.filter((f) => f.spec_id === spec.id && !f.backlog).length,
  );

  useEffect(() => {
    let cancelled = false;
    listFires(getToken, spec.id, 200)
      .then(r => { if (!cancelled) setFires(r.fires); })
      .catch(() => { if (!cancelled) setFires([]); });
    return () => { cancelled = true; };
  }, [getToken, spec.id, liveFireCount]);

  const handleDryRun = async () => {
    setDryRunning(true);
    setError('');
    try {
      const res = await rerunDryRun(getToken, spec.id, 5);
      setDryResult(res);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Dry-run falló');
    } finally {
      setDryRunning(false);
    }
  };

  const evidenceDays = (dryResult?.per_day || []).filter(d => d.count > 0);

  return (
    <div className="space-y-2 pt-2 border-t border-border-subtle mt-2">
      {spec.source_query && (
        <div className="flex items-start gap-1.5 text-[9.5px] text-muted-fg italic">
          <MessageSquarePlus className="w-3 h-3 mt-px flex-shrink-0" />
          <span>&ldquo;{spec.source_query}&rdquo;</span>
        </div>
      )}

      {/* Fire performance at a glance */}
      {fires && fires.length > 0 && <FireDashboard fires={fires} />}

      {/* Fire history */}
      <div>
        <div className="text-[9px] font-semibold text-muted-fg uppercase tracking-wide mb-1">
          Disparos reales
        </div>
        {fires === null ? (
          <div className="text-[9.5px] text-muted-fg flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Cargando…
          </div>
        ) : fires.length === 0 ? (
          <div className="text-[9.5px] text-muted-fg">
            Sin disparos todavía{spec.status !== 'armed' ? ' — la alerta no está activa' : ''}.
          </div>
        ) : (
          <div className="overflow-x-auto rounded border border-border-subtle">
            <table className="w-full text-[9.5px]">
              <thead>
                <tr className="bg-surface-hover/60 text-muted-fg text-left">
                  <th className="px-1.5 py-1 font-medium">Ticker</th>
                  <th className="px-1.5 py-1 font-medium">Evento</th>
                  <th className="px-1.5 py-1 font-medium text-right">Precio</th>
                  <th className="px-1.5 py-1 font-medium text-right">RVOL</th>
                  <th className="px-1.5 py-1 font-medium text-right">Cuándo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {fires.slice(0, 25).map((f, i) => (
                  <tr key={i} className="hover:bg-surface-hover/50">
                    <td className="px-1.5 py-1 font-semibold text-foreground">{f.symbol}</td>
                    <td className="px-1.5 py-1 font-mono text-foreground/70">{f.event_type || '—'}</td>
                    <td className="px-1.5 py-1 text-right tabular-nums">
                      {f.price != null ? `$${f.price.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-1.5 py-1 text-right tabular-nums text-foreground/70">
                      {typeof f.evidence?.rvol === 'number' ? (f.evidence.rvol as number).toFixed(1) : '—'}
                    </td>
                    <td className="px-1.5 py-1 text-right text-muted-fg">{timeAgo(f.fired_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {fires.length > 25 && (
              <div className="px-1.5 py-1 text-[8.5px] text-muted-fg border-t border-border-subtle">
                Mostrando los 25 más recientes de {fires.length}.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Dry-run re-check */}
      <div>
        <button
          onClick={handleDryRun}
          disabled={dryRunning}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[9.5px] font-medium
                     text-primary bg-primary/10 hover:bg-primary/15 disabled:opacity-50 transition-colors"
        >
          {dryRunning
            ? <><Loader2 className="w-3 h-3 animate-spin" /> Comprobando últimos 5 días…</>
            : <><FlaskConical className="w-3 h-3" /> ¿Cuándo habría disparado? (5 días)</>}
        </button>
        {error && <div className="text-[9.5px] text-rose-500 mt-1">{error}</div>}

        {dryResult && (
          <div className="mt-1.5 rounded border border-border-subtle bg-surface-inset/40 p-1.5 space-y-1">
            <div className="text-[10px] text-foreground/80">
              <span className="font-bold tabular-nums">{dryResult.total_fires}</span> disparos
              en {dryResult.days_scanned.length} días · {dryResult.unique_symbols.length} símbolos
            </div>
            {evidenceDays.slice(0, 3).map(day => (
              <div key={day.date} className="text-[9.5px]">
                <span className="font-mono text-muted-fg">{day.date}</span>{' '}
                {day.matches.slice(0, 5).map((m, i) => {
                  const last = matchSteps(m).pop();
                  return (
                    <span key={i} className="inline-flex items-center gap-0.5 mr-1.5">
                      <span className="font-semibold text-foreground">{m.symbol}</span>
                      {last && <span className="text-muted-fg">{last.time?.replace(' ET', '')}</span>}
                      <span className={(m.close_vs_open_pct ?? 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                        {pct(m.close_vs_open_pct)}
                      </span>
                    </span>
                  );
                })}
                {day.count > 5 && <span className="text-muted-fg">+{day.count - 5} más</span>}
              </div>
            ))}
            {(dryResult.chart_evidence || []).map(ev => (
              <LazyEvidenceChart key={`${ev.symbol}-${ev.date}`} evidence={ev} height={150} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Alert row ─────────────────────────────────────────────────────

function AlertRow({ spec, onChanged }: { spec: AlertSpec; onChanged: () => void }) {
  const { getToken } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState<'arm' | 'pause' | 'archive' | null>(null);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [actionError, setActionError] = useState('');

  const meta = STATUS_META[spec.status] || STATUS_META.draft;
  const chips = useMemo(() => formatUniverse(spec.universe), [spec.universe]);

  const run = async (kind: 'arm' | 'pause' | 'archive', fn: () => Promise<unknown>) => {
    setBusy(kind);
    setActionError('');
    try {
      await fn();
      onChanged();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'La acción falló');
    } finally {
      setBusy(null);
      setConfirmArchive(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-2.5 hover:border-border/80 transition-colors">
      {/* Title row */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 min-w-0 flex-1 text-left group"
        >
          {expanded
            ? <ChevronDown className="w-3 h-3 text-muted-fg flex-shrink-0" />
            : <ChevronRight className="w-3 h-3 text-muted-fg flex-shrink-0" />}
          <span className="text-[11.5px] font-semibold text-foreground truncate group-hover:text-primary transition-colors">
            {spec.name}
          </span>
        </button>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8.5px] font-bold ${meta.cls}`}>
          <span className={`w-1 h-1 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
      </div>

      {/* Paraphrase */}
      <p className="text-[10px] text-foreground/70 leading-snug mt-1 ml-[18px]">{spec.paraphrase}</p>

      {/* Chips */}
      <div className="flex flex-wrap items-center gap-1 mt-1.5 ml-[18px]">
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-primary/10 text-[8.5px] font-medium text-primary">
          {spec.tier === 'event_match' ? <Zap className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
          {TIER_LABELS[spec.tier] || spec.tier}
        </span>
        {(spec.steps || []).map((s, i) => (
          <span key={i} className="px-1.5 py-0.5 rounded bg-surface-hover text-[8.5px] font-mono text-foreground/60">
            {s.event_types.join('|')}
          </span>
        ))}
        {(spec.price_levels || []).map((p, i) => (
          <span
            key={`pl${i}`}
            className={`px-1.5 py-0.5 rounded text-[8.5px] font-mono ${
              p.direction === 'above' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'
            }`}
          >
            {formatPriceLevel(p)}
          </span>
        ))}
        {chips.map((c, i) => (
          <span key={`u${i}`} className="px-1.5 py-0.5 rounded bg-surface-hover text-[8.5px] font-mono text-foreground/60">
            {c}
          </span>
        ))}
        <span className="px-1.5 py-0.5 rounded bg-surface-hover text-[8.5px] font-mono text-foreground/60">
          cd {fmtCooldown(spec.lifecycle?.cooldown_seconds ?? 0)}
        </span>
        {spec.dry_run && (
          <span className="text-[8.5px] text-muted-fg">
            · dry-run: {spec.dry_run.total_fires} en {spec.dry_run.days_scanned?.length ?? 0}d
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 mt-2 ml-[18px]">
        {spec.status !== 'armed' && (
          <button
            onClick={() => run('arm', () => armAlert(getToken, spec.id))}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-[9px] font-semibold
                       bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
          >
            {busy === 'arm' ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <CheckCircle2 className="w-2.5 h-2.5" />}
            Activar
          </button>
        )}
        {spec.status === 'armed' && (
          <button
            onClick={() => run('pause', () => pauseAlert(getToken, spec.id))}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-[9px] font-semibold
                       bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
          >
            {busy === 'pause' ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Pause className="w-2.5 h-2.5" />}
            Pausar
          </button>
        )}
        {confirmArchive ? (
          <span className="inline-flex items-center gap-1 text-[9px]">
            <span className="text-muted-fg">¿Archivar?</span>
            <button
              onClick={() => run('archive', () => archiveAlert(getToken, spec.id))}
              disabled={busy !== null}
              className="px-1.5 py-1 rounded font-semibold bg-rose-500/10 text-rose-500 hover:bg-rose-500/20 transition-colors"
            >
              {busy === 'archive' ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : 'Sí'}
            </button>
            <button
              onClick={() => setConfirmArchive(false)}
              className="px-1.5 py-1 rounded text-muted-fg hover:text-foreground transition-colors"
            >
              No
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmArchive(true)}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-[9px] font-medium
                       text-muted-fg hover:text-rose-500 hover:bg-rose-500/10 disabled:opacity-50 transition-colors"
          >
            <Archive className="w-2.5 h-2.5" /> Archivar
          </button>
        )}
        <span className="ml-auto text-[8.5px] text-muted-fg">{timeAgo(spec.updated_at)}</span>
      </div>
      {actionError && <div className="text-[9px] text-rose-500 mt-1 ml-[18px]">{actionError}</div>}

      {expanded && <AlertDetail spec={spec} onChanged={onChanged} />}
    </div>
  );
}

// ── Live feed ─────────────────────────────────────────────────────

const FEED_PREVIEW = 6;

function LiveFeed() {
  const fires = useAIAlertFiresStore((s) => s.fires);
  const connected = useAIAlertFiresStore((s) => s.connected);
  const [expanded, setExpanded] = useState(false);

  const rows = expanded ? fires.slice(0, 40) : fires.slice(0, FEED_PREVIEW);
  if (fires.length === 0) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[9.5px] text-muted-fg border-b border-border">
        <Radio className={`w-3 h-3 ${connected ? 'text-emerald-500' : 'text-muted-fg'}`} />
        {connected
          ? 'En vivo — los disparos de tus alertas activas aparecerán aquí.'
          : 'Conectando al feed de disparos…'}
      </div>
    );
  }

  return (
    <div className="border-b border-border">
      <div className="flex items-center gap-1.5 px-2.5 pt-1.5 text-[9px] font-semibold text-muted-fg uppercase tracking-wide">
        <Radio className={`w-3 h-3 ${connected ? 'text-emerald-500 animate-pulse' : 'text-muted-fg'}`} />
        Disparos en vivo
      </div>
      <div className="px-2.5 py-1.5 space-y-0.5">
        {rows.map((f) => (
          <div key={f.id} className="flex items-center gap-1.5 text-[9.5px]">
            <span className="text-muted-fg tabular-nums flex-shrink-0 w-14">
              {new Date(f.timestamp * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            <span className="font-semibold text-foreground w-12 flex-shrink-0">{f.symbol}</span>
            <span className="font-mono text-foreground/60 truncate">{f.event_type}</span>
            {f.price != null && (
              <span className="ml-auto font-mono tabular-nums text-foreground/80 flex-shrink-0">
                ${f.price.toFixed(2)}
              </span>
            )}
            {f.rvol != null && (
              <span className="text-muted-fg tabular-nums flex-shrink-0">{f.rvol.toFixed(1)}x</span>
            )}
          </div>
        ))}
      </div>
      {fires.length > FEED_PREVIEW && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full pb-1.5 text-[9px] text-muted-fg hover:text-foreground transition-colors"
        >
          {expanded ? 'Ver menos' : `Ver ${Math.min(fires.length, 40) - FEED_PREVIEW} más`}
        </button>
      )}
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────

export function AIAlertsContent() {
  const { getToken } = useAuth();
  const [alerts, setAlerts] = useState<AlertSpec[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const mountedRef = useRef(true);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await listAlerts(getToken);
      if (mountedRef.current) {
        setAlerts(res.alerts);
        setLoadError('');
      }
    } catch (e) {
      if (mountedRef.current && !silent) {
        setLoadError(e instanceof Error ? e.message : 'No se pudieron cargar las alertas');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    useAIAlertFiresStore.getState().markAllSeen();
    const onChanged = () => refresh(true);
    window.addEventListener('tradeul:ai-alerts-changed', onChanged);
    const poll = setInterval(() => refresh(true), POLL_MS);
    return () => {
      mountedRef.current = false;
      window.removeEventListener('tradeul:ai-alerts-changed', onChanged);
      clearInterval(poll);
    };
  }, [refresh]);

  const soundEnabled = useAIAlertFiresStore((s) => s.soundEnabled);
  const setSoundEnabled = useAIAlertFiresStore((s) => s.setSoundEnabled);

  const counts = useMemo(() => {
    const c = { armed: 0, draft: 0, paused: 0 };
    for (const a of alerts || []) {
      if (a.status in c) c[a.status as keyof typeof c] += 1;
    }
    return c;
  }, [alerts]);

  const sorted = useMemo(() => {
    const order: Record<string, number> = { armed: 0, draft: 1, paused: 2, archived: 3 };
    return [...(alerts || [])].sort(
      (a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || b.updated_at - a.updated_at,
    );
  }, [alerts]);

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <BellRing className="w-3.5 h-3.5 text-primary" />
          <span className="text-[11px] font-semibold text-foreground">Alertas IA</span>
          <span className="flex items-center gap-1.5 text-[9px] text-muted-fg">
            <span className="inline-flex items-center gap-0.5">
              <ShieldCheck className="w-2.5 h-2.5 text-emerald-500" /> {counts.armed}
            </span>
            <span>· {counts.draft} borrador{counts.draft === 1 ? '' : 'es'}</span>
            {counts.paused > 0 && <span>· {counts.paused} pausadas</span>}
          </span>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className="p-1 rounded text-muted-fg hover:text-foreground hover:bg-surface-hover transition-colors"
            title={soundEnabled ? 'Silenciar disparos' : 'Activar sonido'}
          >
            {soundEnabled ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
          </button>
          <button
            onClick={() => refresh()}
            disabled={loading}
            className="p-1 rounded text-muted-fg hover:text-foreground hover:bg-surface-hover transition-colors"
            title="Refrescar"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Live fires feed */}
      <LiveFeed />

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {alerts === null && (
          <div className="flex items-center justify-center h-32 text-[10px] text-muted-fg gap-1.5">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Cargando alertas…
          </div>
        )}
        {loadError && (
          <div className="text-[10px] text-rose-500 rounded border border-rose-500/20 bg-rose-500/5 px-2.5 py-2">
            {loadError}
          </div>
        )}
        {alerts !== null && alerts.length === 0 && !loadError && (
          <div className="flex flex-col items-center justify-center h-48 text-center px-6 gap-2">
            <BellRing className="w-6 h-6 text-muted-fg/50" />
            <p className="text-[11px] text-foreground/70 font-medium">Todavía no tienes alertas IA</p>
            <p className="text-[10px] text-muted-fg leading-relaxed">
              Pídesela al agente en lenguaje natural, por ejemplo:{' '}
              <span className="text-primary">
                &ldquo;avísame cuando cualquier acción con RVOL sobre 1.5 cruce el VWAP al alza&rdquo;
              </span>
            </p>
          </div>
        )}
        {sorted.map(spec => (
          <AlertRow key={spec.id} spec={spec} onChanged={() => refresh(true)} />
        ))}
      </div>
    </div>
  );
}
