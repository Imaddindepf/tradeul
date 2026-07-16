'use client';

/**
 * AlertDraftCard — interactive card rendered in the chat when the
 * alert_compiler agent produces a draft. Shows the paraphrase contract,
 * dry-run evidence ("when it would have fired") and a one-click arm button.
 */
import { memo, useMemo, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import {
  BellRing, CheckCircle2, ChevronDown, ChevronRight,
  Clock, Copy, Loader2, ShieldCheck, Zap,
} from 'lucide-react';
import {
  AlertDraftPayload, armAlert, formatPriceLevel, formatUniverse, fmtCooldown, matchSteps,
} from '@/lib/aiAlerts';

const TIER_LABELS: Record<string, string> = {
  event_match: 'Evento en vivo',
  sequence: 'Secuencia',
  membership: 'Ranking',
  agentic: 'Workflow',
};

function pct(v: number | undefined): string {
  if (v == null || isNaN(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

export const AlertDraftCard = memo(function AlertDraftCard({ alert }: { alert: AlertDraftPayload }) {
  const { getToken } = useAuth();
  const [armState, setArmState] = useState<'idle' | 'arming' | 'armed' | 'error'>(
    alert.status === 'armed' ? 'armed' : 'idle',
  );
  const [armNote, setArmNote] = useState('');
  const [expandedDay, setExpandedDay] = useState<string | null>(null);

  const universeChips = useMemo(() => formatUniverse(alert.universe), [alert.universe]);
  const dry = alert.dry_run;
  const daysWithFires = useMemo(
    () => (dry?.per_day || []).filter(d => d.count > 0),
    [dry],
  );
  const avgPerDay = dry && dry.days_scanned.length > 0
    ? Math.round(dry.total_fires / dry.days_scanned.length)
    : 0;
  const noisy = avgPerDay > 100;

  const isDuplicate = Boolean(alert.duplicate);
  const near = alert.similar?.near || [];
  const exact = alert.similar?.exact || [];

  const handleArm = async () => {
    if (armState === 'arming' || armState === 'armed') return;
    setArmState('arming');
    try {
      const res = await armAlert(getToken, alert.spec_id);
      setArmState('armed');
      const kind = (res as { kind?: string }).kind;
      if (res.live) {
        if (kind === 'sequence') setArmNote('Secuencia CEP activa — disparará cuando se complete A→B.');
        else if (kind === 'membership') setArmNote('Watch de ranking activo — disparará al entrar/salir del scanner.');
        else setArmNote('Activa en el motor en tiempo real — los disparos llegarán a tu feed.');
      } else {
        setArmNote(res.note || 'Guardada, pero no evaluable en vivo (contexto de fin de día).');
      }
      window.dispatchEvent(new CustomEvent('tradeul:ai-alerts-changed'));
    } catch (e) {
      setArmState('error');
      setArmNote(e instanceof Error ? e.message : 'No se pudo activar la alerta');
    }
  };

  return (
    <div className={`rounded-xl border bg-surface overflow-hidden ${isDuplicate ? 'border-amber-500/40' : 'border-primary/30'
      }`}>
      {/* Header */}
      <div className={`flex items-center justify-between gap-2 px-3 py-2 border-b border-border ${isDuplicate ? 'bg-amber-500/5' : 'bg-primary/5'
        }`}>
        <div className="flex items-center gap-2 min-w-0">
          {isDuplicate
            ? <Copy className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            : <BellRing className="w-3.5 h-3.5 text-primary flex-shrink-0" />}
          <span className="text-[12px] font-semibold text-foreground truncate">{alert.name}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium bg-primary/10 text-primary">
            {alert.tier === 'event_match' ? <Zap className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
            {TIER_LABELS[alert.tier] || alert.tier}
          </span>
          {isDuplicate && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-amber-500/10 text-amber-500">
              ya existe
            </span>
          )}
          {!isDuplicate && alert.armable_now && armState !== 'armed' && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-emerald-500/10 text-emerald-500">
              lista para activar
            </span>
          )}
        </div>
      </div>

      <div className="p-3 space-y-2.5">
        {isDuplicate && exact[0] && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-[10.5px] text-foreground/80 leading-relaxed">
            Ya tienes una alerta equivalente:{' '}
            <span className="font-semibold">«{exact[0].name}»</span>
            {' '}(estado: <span className="font-mono">{exact[0].status}</span>).
            No he creado un borrador nuevo — puedes reactivarla o gestionarla en el panel.
          </div>
        )}
        {!isDuplicate && near.length > 0 && (
          <div className="rounded-lg border border-border bg-surface-inset/50 px-2.5 py-2 text-[10px] text-muted-fg">
            Parecida(s) que ya tienes:{' '}
            {near.map((n, i) => (
              <span key={n.spec_id}>
                {i > 0 && ', '}
                <span className="text-foreground/80 font-medium">«{n.name}»</span>
                <span className="font-mono"> ({n.status})</span>
              </span>
            ))}
            . Creo esta como borrador nuevo por si quieres ambas.
          </div>
        )}

        {/* Paraphrase = the contract */}
        <p className="text-[11px] text-foreground/90 leading-relaxed">{alert.paraphrase}</p>

        {/* Universe + lifecycle chips */}
        <div className="flex flex-wrap gap-1">
          {universeChips.map((chip, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-surface-hover text-[9px] font-mono text-foreground/70">
              {chip}
            </span>
          ))}
          {alert.steps.map((s, i) => (
            <span key={`s${i}`} className="px-1.5 py-0.5 rounded bg-primary/10 text-[9px] font-mono text-primary">
              {alert.steps.length > 1 ? `${i + 1}. ` : ''}{s.event_types.join(' | ')}
              {s.after === 'opening_low' ? ' (tras mínimo apertura)' : ''}
              {s.within_minutes ? ` ≤${s.within_minutes}m` : ''}
            </span>
          ))}
          {alert.membership && (
            <span className="px-1.5 py-0.5 rounded bg-primary/10 text-[9px] font-mono text-primary">
              {alert.membership.on} {alert.membership.category}
              {alert.membership.rank_lte != null ? ` top${alert.membership.rank_lte}` : ''}
            </span>
          )}
          {(alert.price_levels || []).map((p, i) => (
            <span
              key={`pl${i}`}
              className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${
                p.direction === 'above'
                  ? 'bg-emerald-500/10 text-emerald-500'
                  : 'bg-rose-500/10 text-rose-500'
              }`}
            >
              {formatPriceLevel(p)}
            </span>
          ))}
          {alert.lifecycle?.cooldown_seconds != null && (
            <span className="px-1.5 py-0.5 rounded bg-surface-hover text-[9px] font-mono text-foreground/70">
              cooldown {fmtCooldown(alert.lifecycle.cooldown_seconds)}
            </span>
          )}
        </div>

        {/* Dry-run summary */}
        {dry && (
          <div className="rounded-lg border border-border bg-surface-inset/50 p-2 space-y-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[16px] font-bold tabular-nums text-foreground">{dry.total_fires}</span>
              <span className="text-[10px] text-muted-fg">
                {dry.total_fires === 1 ? 'disparo' : 'disparos'} en los últimos {dry.days_scanned.length} días de mercado
                {dry.unique_symbols.length > 1 &&
                  ` · ${dry.unique_symbols.length}${dry.unique_symbols.length >= 30 ? '+' : ''} símbolos`}
              </span>
            </div>
            {noisy && (
              <div className="text-[9.5px] text-amber-500">
                ~{avgPerDay}/día: puede ser ruidosa. Considera subir RVOL, precio mínimo o el cooldown.
              </div>
            )}
            {dry.total_fires === 0 && (
              <div className="text-[9.5px] text-muted-fg">
                No ocurrió recientemente — la condición es muy restrictiva o poco frecuente.
              </div>
            )}

            {/* Per-day evidence, expandable */}
            {daysWithFires.map(day => (
              <div key={day.date}>
                <button
                  onClick={() => setExpandedDay(expandedDay === day.date ? null : day.date)}
                  className="w-full flex items-center gap-1 text-[10px] text-foreground/70 hover:text-foreground transition-colors"
                >
                  {expandedDay === day.date
                    ? <ChevronDown className="w-3 h-3" />
                    : <ChevronRight className="w-3 h-3" />}
                  <span className="font-mono">{day.date}</span>
                  <span className="text-muted-fg">· {day.count} {day.count === 1 ? 'disparo' : 'disparos'}</span>
                </button>
                {expandedDay === day.date && (
                  <div className="mt-1 ml-4 overflow-x-auto">
                    <table className="w-full text-[9.5px]">
                      <thead>
                        <tr className="text-muted-fg text-left">
                          <th className="pr-2 py-0.5 font-medium">Ticker</th>
                          <th className="pr-2 py-0.5 font-medium">Evento</th>
                          <th className="pr-2 py-0.5 font-medium">Hora</th>
                          <th className="pr-2 py-0.5 font-medium text-right">Precio</th>
                          <th className="pr-2 py-0.5 font-medium text-right">Cierre vs Open</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-subtle">
                        {day.matches.map((m, i) => {
                          const steps = matchSteps(m);
                          const last = steps[steps.length - 1];
                          return (
                            <tr key={i}>
                              <td className="pr-2 py-0.5 font-semibold text-foreground">{m.symbol}</td>
                              <td className="pr-2 py-0.5 font-mono text-foreground/70">{last?.event || '—'}</td>
                              <td className="pr-2 py-0.5 font-mono text-foreground/70">{last?.time || '—'}</td>
                              <td className="pr-2 py-0.5 text-right tabular-nums">
                                {last?.price != null ? `$${last.price.toFixed(2)}` : '—'}
                              </td>
                              <td className={`pr-2 py-0.5 text-right tabular-nums font-medium ${(m.close_vs_open_pct ?? 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'
                                }`}>
                                {pct(m.close_vs_open_pct)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-0.5">
          {armState === 'armed' || (isDuplicate && alert.status === 'armed') ? (
            <span className="inline-flex items-center gap-1.5 text-[10.5px] font-medium text-emerald-500">
              <ShieldCheck className="w-3.5 h-3.5" />
              {isDuplicate ? 'Ya está activa' : 'Alerta activada'}
            </span>
          ) : (
            <button
              onClick={handleArm}
              disabled={armState === 'arming' || (!alert.persisted && !isDuplicate)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10.5px] font-semibold
                         bg-primary text-white hover:bg-primary/90 disabled:opacity-50
                         disabled:cursor-not-allowed transition-colors"
            >
              {armState === 'arming'
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Activando…</>
                : <><CheckCircle2 className="w-3 h-3" />
                  {isDuplicate ? 'Reactivar alerta' : 'Activar alerta'}</>}
            </button>
          )}
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('tradeul:open-ai-alerts'))}
            className="px-2.5 py-1.5 rounded-lg text-[10.5px] font-medium text-foreground/70
                       hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            Ver mis alertas
          </button>
        </div>
        {armNote && (
          <p className={`text-[9.5px] ${armState === 'error' ? 'text-rose-500' : 'text-muted-fg'}`}>
            {armNote}
          </p>
        )}
        {!alert.persisted && !isDuplicate && (
          <p className="text-[9.5px] text-amber-500">
            El borrador no se pudo guardar (persistencia no disponible) — vuelve a pedir la alerta.
          </p>
        )}
      </div>
    </div>
  );
});
