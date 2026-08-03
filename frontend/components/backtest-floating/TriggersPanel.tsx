'use client';

/**
 * Análisis de disparos (L0) — el producto (a) de la Fase 1 del diseño.
 *
 * «¿Mi estrategia es señal o es ruido?»: cuántas veces disparó de VERDAD la
 * estrategia BUILD (eventos reales del lake filtrados con el matcher portado,
 * paridad 1.113/1.113 con producción), dónde, a qué hora, y qué hizo el
 * precio 5/15/60 min después y al cierre.
 *
 * La honestidad se pinta, no se esconde (§7.3): warnings del motor SIEMPRE
 * visibles, estado por día (snapshot, agujeros de datos, rechazos por índice)
 * y semántica de cada filtro (exacto / degradado, con su porqué).
 */

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { cn } from '@/lib/utils';
import {
  ActionButton, Badge, CenterMessage, Field, RULE, SectionHead, TextButton,
} from './ui';
import { useCatalog, eventLabel, type CatalogEntry, type EntryKind } from './catalog';
import { CatalogPicker } from './CatalogPicker';
import { NumericField, specFromFilterDef } from '@/components/ui/FilterNumInput';

/* ── Contrato de /api/backtest/triggers ─────────────────────────────────── */

interface FwdStat {
  n: number;
  mean_pct?: number;
  median_pct?: number;
  win_rate?: number;
  p10_pct?: number;
  p90_pct?: number;
}

interface DayStatus {
  events_scanned: number;
  triggers: number;
  snapshot: boolean;
  quality?: boolean;
  types_present: number;
  index_rejected?: number;
  data_holes?: Record<string, number>;
}

interface TriggersResult {
  triggers_total: number;
  range: { from: string; to: string; days_analyzed: string[] };
  per_day: Record<string, DayStatus>;
  by_type: Record<string, number>;
  by_hour_et: Record<string, number>;
  top_symbols: Record<string, number>;
  forward_returns: Record<string, FwdStat | number | boolean> & {
    population_n?: number;
    sampled?: boolean;
  };
  warnings: { code: string; detail: string; filters?: string[]; days?: string[] }[];
  provenance?: { source: string };
}

const HORIZONS = ['5min', '15min', '60min', 'close'] as const;
const HORIZON_LABEL: Record<string, string> = {
  '5min': '5 min', '15min': '15 min', '60min': '60 min', close: 'Cierre',
};

const pct = (v: number | undefined) =>
  v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const pctColor = (v: number | undefined) =>
  v === undefined ? '' : v > 0 ? 'text-emerald-600' : v < 0 ? 'text-rose-500 dark:text-rose-400' : '';

/* ══════════════════════════════════════════════════════════════════════ */

export function TriggersPanel({
  events, setEvents, filters, setFilters,
}: {
  /* La estrategia BUILD vive en el padre y es LA MISMA que edita el modo
     cartera: una definición, dos análisis (§5.1 del diseño). Cambiar de modo
     no la pierde. */
  events: string[];
  setEvents: Dispatch<SetStateAction<string[]>>;
  filters: Record<string, number | null>;
  setFilters: Dispatch<SetStateAction<Record<string, number | null>>>;
}) {
  const { triggerEntries, dataAxis, loading } = useCatalog();

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [picker, setPicker] = useState<null | { kinds: readonly EntryKind[]; target: 'events' | 'filters' }>(null);

  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<TriggersResult | null>(null);
  const [error, setError] = useState<string>('');

  /* Rango por defecto = lo que el lake tiene de verdad. */
  const lake = dataAxis?.events_lake?.range ?? null;
  useEffect(() => {
    if (lake && !dateFrom && !dateTo) {
      setDateFrom(lake.from);
      setDateTo(lake.to);
    }
  }, [lake, dateFrom, dateTo]);

  const selectedUids = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(`event:${e}`);
    for (const k of Object.keys(filters)) {
      if (k.startsWith('aq:')) continue;
      s.add(`filter:${k.replace(/^(min|max)_/, '')}`);
    }
    return s;
  }, [events, filters]);

  const filterKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const k of Object.keys(filters)) {
      // aq: viaja en la estrategia pero no es una fila min/max editable
      if (k.startsWith('aq:')) continue;
      keys.add(k.replace(/^(min|max)_/, ''));
    }
    return [...keys];
  }, [filters]);

  const degradedActive = useMemo(
    () => filterKeys
      .map(k => triggerEntries.find(c => c.uid === `filter:${k}`))
      .filter((c): c is CatalogEntry => !!c && c.capability === 'degraded'),
    [filterKeys, triggerEntries],
  );

  const problem = !events.length
    ? 'Añade al menos un evento de BUILD'
    : (!dateFrom || !dateTo || dateFrom > dateTo)
      ? 'Revisa el rango de fechas'
      : null;

  const run = useCallback(async () => {
    if (problem) return;
    setStatus('running');
    setError('');
    try {
      const clean = Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v !== null && v !== undefined),
      );
      const res = await fetch('/api/backtest/triggers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: { event_types: events, ...clean },
          date_from: dateFrom,
          date_to: dateTo,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const d = data?.detail ?? data;
        setError(typeof d === 'string' ? d : JSON.stringify(d));
        setStatus('error');
        return;
      }
      setResult(data as TriggersResult);
      setStatus('done');
    } catch (e: any) {
      setError(e?.message || 'Fallo de red');
      setStatus('error');
    }
  }, [problem, filters, events, dateFrom, dateTo]);

  const onPick = useCallback((entry: CatalogEntry) => {
    if (picker?.target === 'events' && entry.kind === 'event') {
      setEvents(prev => (prev.includes(entry.id) ? prev : [...prev, entry.id]));
    } else if (picker?.target === 'filters' && entry.kind === 'filter') {
      setFilters(prev => ({ ...prev, [`min_${entry.id}`]: prev[`min_${entry.id}`] ?? null }));
    }
    setPicker(null);
  }, [picker]);

  return (
    <div className="flex-1 min-h-0 flex flex-col relative">
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 flex flex-col gap-5">

        {/* ── Estrategia ────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2">
          <SectionHead
            title="Eventos (OR)"
            action={<TextButton onClick={() => setPicker({ kinds: ['event'], target: 'events' })}>Añadir</TextButton>}
          />
          {events.length === 0
            ? <p className="m-0 text-[11px] text-foreground/45">Los mismos de BUILD — los 279 tipos valen: aquí son alertas reales grabadas.</p>
            : (
              <div className="flex flex-wrap gap-1.5">
                {events.map(e => (
                  <span
                    key={e}
                    className="inline-flex items-center gap-1.5 h-6 px-2 rounded text-[11px] bg-foreground/[0.06] border"
                    style={{ borderColor: RULE }}
                  >
                    {eventLabel(e)}
                    <button
                      type="button"
                      aria-label={`Quitar ${eventLabel(e)}`}
                      onClick={() => setEvents(prev => prev.filter(x => x !== e))}
                      className="text-foreground/30 hover:text-foreground leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
        </section>

        <section className="flex flex-col gap-2">
          <SectionHead
            title="Filtros (AND)"
            action={<TextButton onClick={() => setPicker({ kinds: ['filter'], target: 'filters' })}>Añadir</TextButton>}
          />
          <TriggerFilterRows
            filters={filters}
            keys={filterKeys}
            catalog={triggerEntries}
            onChange={setFilters}
          />
          {degradedActive.length > 0 && (
            <p className="m-0 text-[11px] text-foreground/55 leading-snug">
              {degradedActive.map(c => c.label).join(', ')}: {degradedActive[0].reason}
            </p>
          )}
        </section>

        {/* ── Rango ─────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2">
          <SectionHead title="Rango" />
          <div className="flex items-end gap-3">
            <Field label="Desde" className="w-[132px]">
              {(p) => (
                <input
                  id={p.id} type="date" value={dateFrom}
                  min={lake?.from} max={lake?.to}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="h-7 px-1.5 rounded bg-transparent text-[12px] font-mono border border-transparent focus:border-foreground/25 outline-none"
                />
              )}
            </Field>
            <Field label="Hasta" className="w-[132px]">
              {(p) => (
                <input
                  id={p.id} type="date" value={dateTo}
                  min={lake?.from} max={lake?.to}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="h-7 px-1.5 rounded bg-transparent text-[12px] font-mono border border-transparent focus:border-foreground/25 outline-none"
                />
              )}
            </Field>
            <span className="text-[11px] text-foreground/45 pb-1.5">
              {lake
                ? `El lake de eventos cubre ${lake.from} → ${lake.to} (${lake.days} días) y crece a diario.`
                : loading ? 'Consultando cobertura…' : 'Cobertura del lake desconocida.'}
            </span>
          </div>
        </section>

        {/* ── Resultados ────────────────────────────────────────────── */}
        {status === 'error' && (
          <CenterMessage tone="error">
            <span className="block text-[12px] font-medium mb-1">El motor rechazó la petición</span>
            <span className="font-mono text-[11px] break-all">{error}</span>
          </CenterMessage>
        )}
        {status === 'done' && result && <TriggersResults r={result} />}
      </div>

      {/* ── Pie ───────────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-3 px-4 h-11 border-t" style={{ borderColor: RULE }}>
        <span className="text-[11px] text-foreground/45">
          Disparos reales del motor vivo · matcher con paridad verificada
        </span>
        <span className="flex-1" />
        {problem && <span className="text-[11px] text-foreground/55">{problem}</span>}
        <ActionButton onClick={run} disabled={status === 'running'}>
          {status === 'running' ? 'Analizando…' : 'Analizar disparos'}
        </ActionButton>
      </div>

      {picker && (
        <CatalogPicker
          entries={triggerEntries}
          kinds={picker.kinds}
          selected={selectedUids}
          onPick={onPick}
          onClose={() => setPicker(null)}
          title={picker.target === 'events' ? 'Eventos de BUILD' : 'Filtros de BUILD'}
        />
      )}
    </div>
  );
}

/* ── Filtros min/max (mismo lenguaje que el modo cartera) ───────────────── */

export function TriggerFilterRows({
  filters, keys, catalog, onChange,
}: {
  filters: Record<string, number | null>;
  keys: string[];
  catalog: CatalogEntry[];
  onChange: (f: Record<string, number | null>) => void;
}) {
  if (!keys.length) {
    return <p className="m-0 text-[11px] text-foreground/45">Ninguno.</p>;
  }
  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-[1fr_92px_92px] gap-1.5 pb-1 border-b" style={{ borderColor: RULE }}>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55">Filtro</span>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55 text-right pr-1">Mín</span>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55 text-right pr-1">Máx</span>
      </div>
      {keys.map(k => {
        const meta = catalog.find(c => c.uid === `filter:${k}`);
        return (
          <div key={k} className="grid grid-cols-[1fr_92px_92px] gap-1.5 items-center py-1 border-b" style={{ borderColor: RULE }}>
            <span className="text-[12px] truncate flex items-center gap-1.5" title={meta?.reason}>
              {meta?.label ?? k}
              {meta?.suffix && <span className="text-[10px] text-foreground/45">{meta.suffix}</span>}
              {meta?.capability === 'degraded' && (
                <span className="text-[9px] uppercase tracking-wider text-foreground/40">aprox</span>
              )}
              <button
                type="button"
                aria-label={`Quitar ${meta?.label ?? k}`}
                onClick={() => {
                  const n = { ...filters };
                  delete n[`min_${k}`]; delete n[`max_${k}`];
                  onChange(n);
                }}
                className="text-foreground/25 hover:text-foreground text-[12px] leading-none"
              >
                ×
              </button>
            </span>
            <NumericField
              value={filters[`min_${k}`] ?? null}
              onChange={(v) => onChange({ ...filters, [`min_${k}`]: v })}
              spec={specFromFilterDef({ suf: meta?.suffix, units: meta?.units, defU: meta?.defU })}
              ariaLabel={`${meta?.label ?? k} min`}
            />
            <NumericField
              value={filters[`max_${k}`] ?? null}
              onChange={(v) => onChange({ ...filters, [`max_${k}`]: v })}
              spec={specFromFilterDef({ suf: meta?.suffix, units: meta?.units, defU: meta?.defU })}
              ariaLabel={`${meta?.label ?? k} max`}
            />
          </div>
        );
      })}
    </div>
  );
}

/* ── Resultados ─────────────────────────────────────────────────────────── */

function TriggersResults({ r }: { r: TriggersResult }) {
  const hours = Object.entries(r.by_hour_et).map(([h, n]) => [Number(h), n] as const);
  const maxHour = Math.max(1, ...hours.map(([, n]) => n));
  const days = Object.entries(r.per_day);
  const fwd = r.forward_returns;

  return (
    <div className="flex flex-col gap-5 pt-1 border-t" style={{ borderColor: RULE }}>

      {/* Titulares */}
      <div className="flex items-baseline gap-6 pt-3 flex-wrap">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wider text-foreground/45">Disparos</span>
          <span className="font-mono tabular-nums text-[22px] leading-tight">{r.triggers_total.toLocaleString('es-ES')}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wider text-foreground/45">Días</span>
          <span className="font-mono tabular-nums text-[22px] leading-tight">{r.range.days_analyzed.length}</span>
        </div>
        {fwd.sampled ? <Badge>Muestreado</Badge> : null}
      </div>

      {/* Forward returns */}
      <section className="flex flex-col gap-1.5">
        <SectionHead title="Qué hizo el precio después" />
        <div className="grid grid-cols-[64px_repeat(5,minmax(56px,1fr))] gap-x-3 text-[11px]">
          <span />
          <span className="text-right text-foreground/45">media</span>
          <span className="text-right text-foreground/45">mediana</span>
          <span className="text-right text-foreground/45">acierto</span>
          <span className="text-right text-foreground/45">p10</span>
          <span className="text-right text-foreground/45">p90</span>
          {HORIZONS.map(h => {
            const s = fwd[h] as FwdStat | undefined;
            return (
              <FwdRow key={h} label={HORIZON_LABEL[h]} s={s} />
            );
          })}
        </div>
        {fwd.sampled && (
          <p className="m-0 text-[11px] text-foreground/45">
            Población de {fwd.population_n?.toLocaleString('es-ES')} disparos: retornos sobre muestra aleatoria uniforme. Los recuentos usan la población completa.
          </p>
        )}
      </section>

      {/* Por hora */}
      <section className="flex flex-col gap-1.5">
        <SectionHead title="Distribución por hora (ET)" />
        <div className="flex items-end gap-1 h-14">
          {hours.map(([h, n]) => (
            <div key={h} className="flex flex-col items-center gap-0.5 flex-1 min-w-0" title={`${h}:00 — ${n.toLocaleString('es-ES')}`}>
              <div className="w-full rounded-sm bg-foreground/25" style={{ height: `${Math.max(4, (n / maxHour) * 44)}px` }} />
              <span className="text-[9px] font-mono text-foreground/45">{h}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Por día — la honestidad va aquí */}
      <section className="flex flex-col gap-1.5">
        <SectionHead title="Por día" />
        <div className="grid grid-cols-[92px_1fr_1fr_1fr] gap-x-3 text-[11px]">
          <span className="text-foreground/45">día</span>
          <span className="text-right text-foreground/45">disparos</span>
          <span className="text-right text-foreground/45">escaneados</span>
          <span className="text-right text-foreground/45">estado</span>
          {days.map(([d, st]) => {
            const flags: string[] = [];
            if (st.data_holes) flags.push(`agujero: ${Object.keys(st.data_holes).join(', ')}`);
            if (!st.snapshot) flags.push('sin snapshot');
            if (st.index_rejected) flags.push(`índice −${st.index_rejected.toLocaleString('es-ES')}`);
            return (
              <DayRow key={d} d={d} st={st} flags={flags} />
            );
          })}
        </div>
      </section>

      {/* Top símbolos */}
      <section className="flex flex-col gap-1.5">
        <SectionHead title="Símbolos más frecuentes" />
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(r.top_symbols).slice(0, 14).map(([sym, n]) => (
            <span key={sym} className="inline-flex items-baseline gap-1 h-6 px-2 rounded text-[11px] bg-foreground/[0.05] border" style={{ borderColor: RULE }}>
              <span className="font-mono font-medium">{sym}</span>
              <span className="text-foreground/45 font-mono tabular-nums">{n.toLocaleString('es-ES')}</span>
            </span>
          ))}
        </div>
      </section>

      {/* Avisos del motor — SIEMPRE visibles */}
      {r.warnings.length > 0 && (
        <section className="flex flex-col gap-1.5 pb-2">
          <SectionHead title="Fidelidad" />
          <ul className="m-0 pl-4 flex flex-col gap-1">
            {r.warnings.map((w, i) => (
              <li key={i} className="text-[11px] text-foreground/60 leading-snug">
                {w.detail}
                {w.days ? ` (${w.days.join(', ')})` : ''}
              </li>
            ))}
          </ul>
          {r.provenance && (
            <p className="m-0 text-[10px] text-foreground/40">{r.provenance.source}</p>
          )}
        </section>
      )}
    </div>
  );
}

function FwdRow({ label, s }: { label: string; s?: FwdStat }) {
  return (
    <>
      <span className="text-foreground/60 py-1">{label}</span>
      <span className={cn('text-right font-mono tabular-nums py-1', pctColor(s?.mean_pct))}>{pct(s?.mean_pct)}</span>
      <span className={cn('text-right font-mono tabular-nums py-1', pctColor(s?.median_pct))}>{pct(s?.median_pct)}</span>
      <span className="text-right font-mono tabular-nums py-1">{s?.win_rate === undefined ? '—' : `${(s.win_rate * 100).toFixed(0)}%`}</span>
      <span className="text-right font-mono tabular-nums py-1 text-foreground/60">{pct(s?.p10_pct)}</span>
      <span className="text-right font-mono tabular-nums py-1 text-foreground/60">{pct(s?.p90_pct)}</span>
    </>
  );
}

function DayRow({ d, st, flags }: { d: string; st: DayStatus; flags: string[] }) {
  return (
    <>
      <span className="font-mono py-1">{d.slice(5)}</span>
      <span className="text-right font-mono tabular-nums py-1">{st.triggers.toLocaleString('es-ES')}</span>
      <span className="text-right font-mono tabular-nums py-1 text-foreground/45">{st.events_scanned.toLocaleString('es-ES')}</span>
      <span className={cn('text-right py-1', flags.length ? 'text-foreground/60' : 'text-foreground/35')}>
        {flags.length ? flags.join(' · ') : 'ok'}
      </span>
    </>
  );
}
