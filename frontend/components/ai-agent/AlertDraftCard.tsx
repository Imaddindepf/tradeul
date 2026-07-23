'use client';

/**
 * AlertDraftCard — interactive card rendered in the chat when the
 * alert_compiler agent produces a draft. Shows the paraphrase contract,
 * dry-run evidence ("when it would have fired") and a one-click arm button.
 */
import { memo, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@clerk/nextjs';
import dynamic from 'next/dynamic';
import {
  ArrowRight, BellRing, CheckCircle2, ChevronDown, ChevronRight,
  Clock, Copy, Globe, Loader2, ShieldCheck, SlidersHorizontal, Timer, Zap,
} from 'lucide-react';
import i18n from '@/lib/i18n';
import {
  AlertDraftPayload, armAlert, formatPriceLevel, formatUniverse, fmtCooldown, matchSteps,
} from '@/lib/aiAlerts';

const LazyEvidenceChart = dynamic(
  () => import('./EvidenceChart').then(m => m.EvidenceChart),
  {
    ssr: false,
    loading: () => <div className="h-[180px] bg-surface-hover rounded-lg animate-pulse" />,
  },
);

function tierLabel(tier: string): string {
  return i18n.t(`aiAlerts.tier.${tier}`, { defaultValue: tier });
}

function pct(v: number | undefined): string {
  if (v == null || isNaN(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
}

/* ── SpecPipeline — the compiled rule as a visual dataflow ─────────
   Universo → Condición → Cooldown → Feed. The user sees the machine
   they just built with words. */

function PipelineNode({
  icon,
  label,
  children,
  accent = false,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`flex-1 min-w-[90px] rounded-lg border px-2 py-1.5 ${
      accent ? 'border-primary/30 bg-primary/5' : 'border-border bg-surface-inset/40'
    }`}>
      <div className="flex items-center gap-1 mb-1">
        <span className={accent ? 'text-primary' : 'text-muted-fg'}>{icon}</span>
        <span className="text-[8px] font-semibold uppercase tracking-wider text-muted-fg">{label}</span>
      </div>
      <div className="flex flex-wrap gap-0.5">{children}</div>
    </div>
  );
}

function SpecPipeline({ alert }: { alert: AlertDraftPayload }) {
  const { t } = useTranslation();
  const universeChips = formatUniverse(alert.universe);
  const symbols = alert.universe?.symbols_include || [];
  const filterChips = symbols.length
    ? universeChips.filter(c => c !== symbols.join(', '))
    : universeChips;

  const chip = (text: string, cls = 'bg-surface-hover text-foreground/70') => (
    <span key={text} className={`px-1 py-px rounded text-[8.5px] font-mono leading-tight ${cls}`}>
      {text}
    </span>
  );

  return (
    <div className="flex items-stretch gap-1">
      <PipelineNode icon={<Globe className="w-2.5 h-2.5" />} label={t('aiAgent.draft.universe')}>
        {symbols.length
          ? chip(symbols.join(' '), 'bg-surface-hover text-foreground font-semibold')
          : chip(t('aiAgent.draft.entireMarket'))}
        {filterChips.map(c => chip(c))}
      </PipelineNode>

      <span className="self-center flex-shrink-0 text-muted-fg/50">
        <ArrowRight className="w-3 h-3" />
      </span>

      <PipelineNode icon={<Zap className="w-2.5 h-2.5" />} label={t('aiAgent.draft.condition')} accent>
        {alert.steps.map((s, i) =>
          chip(
            `${alert.steps.length > 1 ? `${i + 1}· ` : ''}${s.event_types.join('|')}` +
            (s.after === 'opening_low' ? t('aiAgent.draft.afterOpeningLow') : '') +
            (s.within_minutes ? ` ≤${s.within_minutes}m` : ''),
            'bg-primary/10 text-primary',
          ),
        )}
        {(alert.price_levels || []).map(p =>
          chip(
            formatPriceLevel(p),
            p.direction === 'above'
              ? 'bg-emerald-500/10 text-emerald-500'
              : 'bg-rose-500/10 text-rose-500',
          ),
        )}
        {alert.membership &&
          chip(
            (alert.membership.on === 'enter'
              ? t('aiAgent.draft.enterCategory', { category: alert.membership.category })
              : t('aiAgent.draft.exitCategory', { category: alert.membership.category })) +
            (alert.membership.rank_lte != null ? ` top${alert.membership.rank_lte}` : ''),
            'bg-primary/10 text-primary',
          )}
        {(alert.day_conditions || []).map(dc =>
          chip(`${dc.metric} ${dc.op} ${dc.value}`, 'bg-amber-500/10 text-amber-500'),
        )}
      </PipelineNode>

      <span className="self-center flex-shrink-0 text-muted-fg/50">
        <ArrowRight className="w-3 h-3" />
      </span>

      <PipelineNode icon={<Timer className="w-2.5 h-2.5" />} label={t('aiAgent.draft.cooldown')}>
        {alert.lifecycle?.cooldown_seconds != null &&
          chip(`cooldown ${fmtCooldown(alert.lifecycle.cooldown_seconds)}`)}
        {alert.lifecycle?.max_fires_per_day != null &&
          chip(t('aiAgent.draft.maxPerDay', { count: alert.lifecycle.max_fires_per_day }))}
      </PipelineNode>

      <span className="self-center flex-shrink-0 text-muted-fg/50">
        <ArrowRight className="w-3 h-3" />
      </span>

      <PipelineNode icon={<BellRing className="w-2.5 h-2.5" />} label={t('aiAgent.draft.feed')}>
        {chip(t('aiAgent.draft.liveFeedChip'))}
        {chip(t('aiAgent.draft.popupSound'))}
      </PipelineNode>
    </div>
  );
}

/* ── AdjustPanel — tweak the compiled spec and recompile via chat ──
   The card is the contract; this lets the user renegotiate it without
   retyping the whole request. Changes go through the same
   compile → validate → dry-run loop, so evidence stays honest. */

const COOLDOWN_PRESETS = [60, 300, 900, 1800, 3600];

function AdjustPanel({ alert, onSent }: { alert: AlertDraftPayload; onSent: () => void }) {
  const { t } = useTranslation();
  const [cooldown, setCooldown] = useState<number>(alert.lifecycle?.cooldown_seconds ?? 900);
  const [minRvol, setMinRvol] = useState(
    alert.universe?.min_rvol != null ? String(alert.universe.min_rvol) : '',
  );
  const [minPrice, setMinPrice] = useState(
    alert.universe?.min_price != null ? String(alert.universe.min_price) : '',
  );
  const [levels, setLevels] = useState(
    (alert.price_levels || []).map(p => ({ direction: p.direction, value: String(p.value) })),
  );
  const [extra, setExtra] = useState('');

  const buildChanges = (): string[] => {
    const changes: string[] = [];
    if (cooldown !== (alert.lifecycle?.cooldown_seconds ?? 900)) {
      changes.push(t('aiAgent.draft.cooldownOf', { value: fmtCooldown(cooldown) }));
    }
    const origRvol = alert.universe?.min_rvol != null ? String(alert.universe.min_rvol) : '';
    if (minRvol !== origRvol && minRvol.trim()) {
      changes.push(t('aiAgent.draft.minRvol', { value: minRvol.trim() }));
    }
    const origPrice = alert.universe?.min_price != null ? String(alert.universe.min_price) : '';
    if (minPrice !== origPrice && minPrice.trim()) {
      changes.push(t('aiAgent.draft.minPrice', { value: minPrice.trim() }));
    }
    levels.forEach((l, i) => {
      const orig = alert.price_levels?.[i];
      if (orig && String(orig.value) !== l.value && l.value.trim()) {
        changes.push(
          l.direction === 'above'
            ? t('aiAgent.draft.levelAbove', { value: l.value.trim() })
            : t('aiAgent.draft.levelBelow', { value: l.value.trim() }),
        );
      }
    });
    if (extra.trim()) changes.push(extra.trim());
    return changes;
  };

  const changes = buildChanges();

  const handleApply = () => {
    if (!changes.length) return;
    const message =
      t('aiAgent.draft.recompilePrefix', { paraphrase: alert.paraphrase }) +
      changes.join('; ') + '.';    window.dispatchEvent(new CustomEvent('agent:send', { detail: { message } }));
    onSent();
  };

  const inputCls =
    'w-full px-1.5 py-1 rounded border border-border bg-surface text-[10px] text-foreground ' +
    'placeholder-muted-fg focus:outline-none focus:border-primary';

  return (
    <div className="rounded-lg border border-border bg-surface-inset/40 p-2 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-[8.5px] font-semibold uppercase tracking-wider text-muted-fg mb-1">
            Cooldown
          </div>
          <div className="flex flex-wrap gap-0.5">
            {COOLDOWN_PRESETS.map(s => (
              <button
                key={s}
                onClick={() => setCooldown(s)}
                className={`px-1.5 py-0.5 rounded text-[9px] font-mono transition-colors ${
                  cooldown === s
                    ? 'bg-primary/15 text-primary font-semibold'
                    : 'bg-surface-hover text-muted-fg hover:text-foreground'
                }`}
              >
                {fmtCooldown(s)}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <div>
            <div className="text-[8.5px] font-semibold uppercase tracking-wider text-muted-fg mb-1">
              {t('aiAgent.draft.minRvolLabel')}
            </div>
            <input value={minRvol} onChange={e => setMinRvol(e.target.value)}
              placeholder="—" inputMode="decimal" className={inputCls} />
          </div>
          <div>
            <div className="text-[8.5px] font-semibold uppercase tracking-wider text-muted-fg mb-1">
              {t('aiAgent.draft.minPriceLabel')}
            </div>
            <input value={minPrice} onChange={e => setMinPrice(e.target.value)}
              placeholder="—" inputMode="decimal" className={inputCls} />
          </div>
        </div>
      </div>

      {levels.length > 0 && (
        <div>
          <div className="text-[8.5px] font-semibold uppercase tracking-wider text-muted-fg mb-1">
            {t('aiAgent.draft.priceLevelsLabel')}
          </div>
          <div className="flex gap-1.5">
            {levels.map((l, i) => (
              <div key={i} className="flex items-center gap-1 flex-1">
                <span className={`text-[10px] font-mono ${
                  l.direction === 'above' ? 'text-emerald-500' : 'text-rose-500'
                }`}>
                  {l.direction === 'above' ? '↑' : '↓'}
                </span>
                <input
                  value={l.value}
                  onChange={e =>
                    setLevels(prev => prev.map((p, j) => (j === i ? { ...p, value: e.target.value } : p)))
                  }
                  inputMode="decimal"
                  className={inputCls}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-[8.5px] font-semibold uppercase tracking-wider text-muted-fg mb-1">
          {t('aiAgent.draft.otherChanges')}
        </div>
        <input
          value={extra}
          onChange={e => setExtra(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleApply()}
          placeholder={t('aiAgent.draft.adjustPlaceholder')}
          className={inputCls}
        />
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[9px] text-muted-fg">
          {changes.length
            ? t('aiAgent.draft.changesCount', { count: changes.length, list: changes.join(' · ') })
            : t('aiAgent.draft.modifyToRecompile')}
        </span>
        <button
          onClick={handleApply}
          disabled={!changes.length}
          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-primary text-white
                     hover:bg-primary/90 disabled:opacity-40 transition-colors flex-shrink-0"
        >
          {t('aiAgent.draft.recompile')}
        </button>
      </div>
    </div>
  );
}

export const AlertDraftCard = memo(function AlertDraftCard({ alert }: { alert: AlertDraftPayload }) {
  const { t } = useTranslation();
  const { getToken } = useAuth();
  const [armState, setArmState] = useState<'idle' | 'arming' | 'armed' | 'error'>(
    alert.status === 'armed' ? 'armed' : 'idle',
  );
  const [armNote, setArmNote] = useState('');
  const [expandedDay, setExpandedDay] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState(false);

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
        if (kind === 'sequence') setArmNote(t('aiAgent.draft.noteSequence'));
        else if (kind === 'membership') setArmNote(t('aiAgent.draft.noteMembership'));
        else setArmNote(t('aiAgent.draft.noteLive'));
      } else {
        setArmNote(res.note || t('aiAgent.draft.noteSavedOffline'));
      }
      window.dispatchEvent(new CustomEvent('tradeul:ai-alerts-changed'));
    } catch (e) {
      setArmState('error');
      setArmNote(e instanceof Error ? e.message : t('aiAgent.draft.armFailed'));
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
            {tierLabel(alert.tier)}
          </span>
          {isDuplicate && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-amber-500/10 text-amber-500">
              {t('aiAgent.draft.alreadyExists')}
            </span>
          )}
          {!isDuplicate && alert.armable_now && armState !== 'armed' && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-emerald-500/10 text-emerald-500">
              {t('aiAgent.draft.readyToArm')}
            </span>
          )}
        </div>
      </div>

      <div className="p-3 space-y-2.5">
        {isDuplicate && exact[0] && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-[10.5px] text-foreground/80 leading-relaxed">
            {t('aiAgent.draft.duplicateBody', { name: exact[0].name, status: exact[0].status })}
          </div>
        )}
        {!isDuplicate && near.length > 0 && (
          <div className="rounded-lg border border-border bg-surface-inset/50 px-2.5 py-2 text-[10px] text-muted-fg">
            {t('aiAgent.draft.similarExisting')}{' '}
            {near.map((n, i) => (
              <span key={n.spec_id}>
                {i > 0 && ', '}
                <span className="text-foreground/80 font-medium">«{n.name}»</span>
                <span className="font-mono"> ({n.status})</span>
              </span>
            ))}
            {t('aiAgent.draft.createAsNewDraft')}
          </div>
        )}

        {/* Paraphrase = the contract */}
        <p className="text-[11px] text-foreground/90 leading-relaxed">{alert.paraphrase}</p>

        {/* Compiled rule as a visual pipeline */}
        <SpecPipeline alert={alert} />

        {/* Dry-run summary */}
        {dry && (
          <div className="rounded-lg border border-border bg-surface-inset/50 p-2 space-y-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[16px] font-bold tabular-nums text-foreground">{dry.total_fires}</span>
              <span className="text-[10px] text-muted-fg">
                {t('aiAgent.draft.fire', { count: dry.total_fires })}{' '}
                {t('aiAgent.draft.inLastMarketDays', { days: dry.days_scanned.length })}
                {dry.unique_symbols.length > 1 &&
                  ` · ${dry.unique_symbols.length}${dry.unique_symbols.length >= 30 ? '+' : ''} ${t('aiAgent.draft.symbols')}`}
              </span>
            </div>
            {noisy && (
              <div className="text-[9.5px] text-amber-500">
                {t('aiAgent.draft.noisyHint', { avg: avgPerDay })}
              </div>
            )}
            {dry.total_fires === 0 && (
              <div className="text-[9.5px] text-muted-fg">
                {t('aiAgent.draft.noRecentFires')}
              </div>
            )}

            {/* Evidence on real candles — each fire marked on the tape */}
            {(dry.chart_evidence || []).map(ev => (
              <LazyEvidenceChart key={`${ev.symbol}-${ev.date}`} evidence={ev} />
            ))}

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
                  <span className="text-muted-fg">· {day.count} {t('aiAgent.draft.fire', { count: day.count })}</span>
                </button>
                {expandedDay === day.date && (
                  <div className="mt-1 ml-4 overflow-x-auto">
                    <table className="w-full text-[9.5px]">
                      <thead>
                        <tr className="text-muted-fg text-left">
                          <th className="pr-2 py-0.5 font-medium">Ticker</th>
                          <th className="pr-2 py-0.5 font-medium">{t('aiAlerts.event')}</th>
                          <th className="pr-2 py-0.5 font-medium">{t('aiAgent.draft.time')}</th>
                          <th className="pr-2 py-0.5 font-medium text-right">{t('aiAlerts.price')}</th>
                          <th className="pr-2 py-0.5 font-medium text-right">{t('aiAgent.draft.closeVsOpen')}</th>
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
              {isDuplicate ? t('aiAlerts.alertAlreadyActive') : t('aiAlerts.alertArmed')}
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
                ? <><Loader2 className="w-3 h-3 animate-spin" /> {t('aiAlerts.arming')}</>
                : <><CheckCircle2 className="w-3 h-3" />
                  {isDuplicate ? t('aiAlerts.rearmAlert') : t('aiAlerts.armAlert')}</>}
            </button>
          )}
          {!isDuplicate && (
            <button
              onClick={() => setAdjusting(a => !a)}
              className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10.5px] font-medium
                         transition-colors ${adjusting
                  ? 'text-primary bg-primary/10'
                  : 'text-foreground/70 hover:text-foreground hover:bg-surface-hover'}`}
            >
              <SlidersHorizontal className="w-3 h-3" />
              {t('aiAgent.draft.adjust')}
            </button>
          )}
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('tradeul:open-ai-alerts'))}
            className="px-2.5 py-1.5 rounded-lg text-[10.5px] font-medium text-foreground/70
                       hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            {t('aiAgent.draft.myWorkflows')}
          </button>
        </div>

        {adjusting && <AdjustPanel alert={alert} onSent={() => setAdjusting(false)} />}
        {armNote && (
          <p className={`text-[9.5px] ${armState === 'error' ? 'text-rose-500' : 'text-muted-fg'}`}>
            {armNote}
          </p>
        )}
        {!alert.persisted && !isDuplicate && (
          <p className="text-[9.5px] text-amber-500">
            {t('aiAgent.draft.persistFailed')}
          </p>
        )}
      </div>
    </div>
  );
});
