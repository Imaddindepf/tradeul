'use client';

/**
 * Ventana Backtester.
 *
 * Rediseñada al lenguaje de ERN: sin iconos, monocromo por alfa sobre
 * `foreground`, color solo en subida/bajada, campos sin borde hasta el foco.
 *
 * El cambio de fondo no es estético sino de flujo: antes los resultados
 * SUSTITUÍAN la configuración entera (`if (showResults) return <ResultsView/>`),
 * así que ajustar y relanzar era a ciegas. Ahora conviven en un split y el
 * ciclo real —tocar, relanzar, comparar— ocurre sin cambiar de vista.
 *
 * Lo que se arregla de paso, todo medido contra el motor:
 *   · Los eventos que el motor no ejecuta dejan de ofrecerse como si sí.
 *   · Los 34 filtros del motor, no los 21 que había cableados a mano.
 *   · Los 5 modos de universo y las 7 temporalidades del contrato.
 *   · El `0` en un filtro deja de descartarse en silencio.
 *   · Historial de corridas en la sesión, con superposición de curvas.
 *   · `result.warnings`, que el backend devolvía y nadie pintaba.
 */

import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { useBacktestFloating } from '@/contexts/BacktestFloatingContext';
import type {
  StrategyConfig, Signal, ExitRule, Timeframe, SignalOperator,
  ExitType, SlippageModel, BacktestResult,
} from '@/components/ai-agent/backtest/BacktestTypes';
import { cn } from '@/lib/utils';
import {
  ActionButton, Badge, CenterMessage, Field, FieldGroup, NumInput, RULE, SectionHead,
  Seg, SplitHandle, TextButton, TextInput, WindowFooter, useNarrow, useSplitWidth,
} from './ui';
import { useCatalog, eventLabel, INDICATORS, type CatalogEntry, type EntryKind } from './catalog';
import { CatalogPicker } from './CatalogPicker';
import { TriggersPanel } from './TriggersPanel';
import { ResultsPane } from './ResultsPane';
import { Sparkline } from './Sparkline';
import type { Overlay } from './ResultsChart';

/* ── Constantes del contrato (core/models.py) ─────────────────────────── */

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1d' as Timeframe, label: '1d' },
  { value: '4h' as Timeframe, label: '4h' },
  { value: '1h' as Timeframe, label: '1h' },
  { value: '30min' as Timeframe, label: '30m' },
  { value: '15min' as Timeframe, label: '15m' },
  { value: '5min' as Timeframe, label: '5m' },
  { value: '1min' as Timeframe, label: '1m' },
];

const UNIVERSE_METHODS = [
  { value: 'ticker_list', label: 'Lista' },
  { value: 'all_us', label: 'Toda la bolsa US' },
  { value: 'sector', label: 'Sector' },
  { value: 'industry', label: 'Industria' },
  { value: 'sql_filter', label: 'SQL' },
] as const;
type UniverseMethod = typeof UNIVERSE_METHODS[number]['value'];

const OPERATORS: { value: SignalOperator; label: string }[] = [
  { value: '>' as SignalOperator, label: '>' },
  { value: '>=' as SignalOperator, label: '≥' },
  { value: '<' as SignalOperator, label: '<' },
  { value: '<=' as SignalOperator, label: '≤' },
  { value: '==' as SignalOperator, label: '=' },
  { value: 'crosses_above' as SignalOperator, label: 'cruza arriba' },
  { value: 'crosses_below' as SignalOperator, label: 'cruza abajo' },
];

const EXIT_TYPES: { value: ExitType; label: string; unit?: string }[] = [
  { value: 'stop_loss' as ExitType, label: 'Stop loss', unit: '%' },
  { value: 'target' as ExitType, label: 'Objetivo', unit: '%' },
  { value: 'trailing_stop' as ExitType, label: 'Stop dinámico', unit: '%' },
  { value: 'time' as ExitType, label: 'Tiempo', unit: 'barras' },
  { value: 'eod' as ExitType, label: 'Cierre de sesión' },
  { value: 'signal' as ExitType, label: 'Señal' },
];

const SLIPPAGE_MODELS: { value: SlippageModel; label: string }[] = [
  { value: 'fixed_bps' as SlippageModel, label: 'Fijo (bps)' },
  { value: 'volume_based' as SlippageModel, label: 'Por volumen' },
  { value: 'spread_based' as SlippageModel, label: 'Por spread' },
];

const todayStr = () => new Date().toISOString().slice(0, 10);
const yearAgoStr = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
};
const INTRADAY: string[] = ['1min', '5min', '15min', '30min', '1h'];

const defaultSignal = (): Signal => ({ indicator: 'rsi_14', operator: '<' as SignalOperator, value: 30 });

interface RunEntry {
  id: string;
  label: string;
  at: string;
  result: BacktestResult;
}

const MAX_RUNS = 6;
const SPLIT_KEY = 'tradeul.backtest.definePaneWidth';

/* ══════════════════════════════════════════════════════════════════════ */

export function BacktestPanelContent({
  initialEvents, initialFilters, initialName,
}: {
  initialEvents?: string[];
  initialFilters?: Record<string, any>;
  initialName?: string;
} = {}) {
  const { status, result, error, progressText, runStructured, reset } = useBacktestFloating();
  const { entries: catalog, eventCapability, stats, caps } = useCatalog();

  /* ── Estrategia ─────────────────────────────────────────────────────── */
  const [name, setName] = useState(initialName || 'Estrategia sin nombre');
  const [method, setMethod] = useState<UniverseMethod>('ticker_list');
  const [tickersStr, setTickersStr] = useState('SPY');
  const [sqlWhere, setSqlWhere] = useState('');
  const [criteria, setCriteria] = useState('');
  const [direction, setDirection] = useState<'long' | 'short' | 'both'>('long');
  const [timeframe, setTimeframe] = useState<Timeframe>('1d' as Timeframe);
  const [entryTiming, setEntryTiming] = useState<'open' | 'close' | 'next_open'>('next_open');
  const [startDate, setStartDate] = useState(yearAgoStr());
  const [endDate, setEndDate] = useState(todayStr());

  const [entries, setEntries] = useState<Signal[]>([defaultSignal()]);
  const [entryEvents, setEntryEvents] = useState<string[]>(initialEvents ?? []);
  const [combine, setCombine] = useState<'or' | 'and'>('or');
  const [exits, setExits] = useState<ExitRule[]>([
    { type: 'stop_loss' as ExitType, value: 0.05 },
    { type: 'target' as ExitType, value: 0.10 },
  ]);
  const [entryFilters, setEntryFilters] = useState<Record<string, number | null>>(initialFilters ?? {});
  const [universeFilters, setUniverseFilters] = useState<Record<string, number | null>>({});

  const [capital, setCapital] = useState<number | null>(100_000);
  const [maxPositions, setMaxPositions] = useState<number | null>(10);
  const [positionSizePct, setPositionSizePct] = useState<number | null>(10);
  const [slippageModel, setSlippageModel] = useState<SlippageModel>('fixed_bps' as SlippageModel);
  const [slippageBps, setSlippageBps] = useState<number | null>(10);
  const [commission, setCommission] = useState<number | null>(0);
  const [walkForward, setWalkForward] = useState(true);
  const [monteCarlo, setMonteCarlo] = useState(true);

  /* ── UI ─────────────────────────────────────────────────────────────── */
  const { ref: rootRef, narrow } = useNarrow(680);
  /* Dos productos, dos fidelidades (§7 del diseño): 'triggers' = análisis de
     disparos L0 (eventos reales, vocabulario BUILD completo, exacto por
     construcción); 'portfolio' = simulador vectorizado legacy (73 eventos /
     34 filtros hasta la Fase 2). Por defecto, el que no miente. */
  const [mode, setMode] = useState<'triggers' | 'portfolio'>('triggers');
  const [tab, setTab] = useState<'define' | 'results'>('define');
  const { width: paneW, setWidth: setPaneW, persist } = useSplitWidth(SPLIT_KEY, 452, 340, 760);
  const [picker, setPicker] = useState<null | { kinds: readonly EntryKind[]; target: 'entryEvents' | 'entryFilters' | 'universeFilters' | 'signal' }>(null);
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [compare, setCompare] = useState<Set<string>>(new Set());
  const runCounter = useRef(0);

  const isRunning = status === 'running';

  /* ── Historial de corridas ──────────────────────────────────────────
     El contexto guarda un único resultado y `runStructured` llama a `reset()`
     antes de lanzar, así que cada corrida borraba la anterior. Aquí se
     conservan las últimas de la sesión para poder comparar. ─────────────── */
  useEffect(() => {
    if (status !== 'complete' || !result) return;
    runCounter.current += 1;
    const n = runCounter.current;
    setRuns(prev => [
      {
        id: `run-${n}`,
        label: `#${n}`,
        at: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
        result,
      },
      ...prev,
    ].slice(0, MAX_RUNS));
  }, [status, result]);

  const current = runs[0];

  const overlays = useMemo<Overlay[]>(
    () => runs
      .slice(1)
      .filter(r => compare.has(r.id))
      .map(r => ({ id: r.id, label: r.label, equity: r.result.equity_curve ?? [] })),
    [runs, compare],
  );

  /* ── Validación: sin botón deshabilitado, con campo culpable ──────────── */
  const tickers = useMemo(
    () => tickersStr.split(/[\s,;]+/).map(t => t.trim().toUpperCase()).filter(Boolean),
    [tickersStr],
  );

  const problems = useMemo(() => {
    const p: { field: string; message: string }[] = [];
    if (method === 'ticker_list' && tickers.length === 0) {
      p.push({ field: 'tickers', message: 'Añade al menos un símbolo' });
    }
    if (method === 'sql_filter' && !sqlWhere.trim()) {
      p.push({ field: 'sql', message: 'Escribe una condición SQL' });
    }
    if (!entries.length && !entryEvents.length) {
      p.push({ field: 'entry', message: 'Define al menos una señal o un evento de entrada' });
    }
    if (!startDate || !endDate) {
      p.push({ field: 'dates', message: 'Faltan fechas' });
    } else {
      const days = (new Date(endDate).getTime() - new Date(startDate).getTime()) / 86_400_000;
      if (days <= 0) {
        p.push({ field: 'dates', message: 'La fecha final debe ser posterior a la inicial' });
      } else {
        // El backend valida esto y devuelve un 422; mejor decirlo antes.
        const min = INTRADAY.includes(String(timeframe)) ? 5 : 30;
        if (days < min) {
          p.push({ field: 'dates', message: `El periodo mínimo es de ${min} días (llevas ${Math.floor(days)})` });
        }
      }
    }
    return p;
  }, [method, tickers, sqlWhere, entries, entryEvents, startDate, endDate, timeframe]);

  const problemFor = useCallback(
    (field: string) => problems.find(p => p.field === field)?.message,
    [problems],
  );

  /* ── Diagnóstico: lo que el cliente puede saber sin preguntar ─────────── */
  const diagnostics = useMemo(() => {
    const out: string[] = [];

    const dead = entryEvents.filter(e => eventCapability.get(e)?.capability === 'unsupported');
    if (dead.length) {
      out.push(
        `${dead.length === 1 ? 'El evento' : 'Los eventos'} ${dead.map(eventLabel).join(', ')} ` +
        `no ${dead.length === 1 ? 'está implementado' : 'están implementados'} en el motor: ` +
        `${combine === 'and' ? 'con «todas» la entrada nunca se cumple' : 'se ignoran en silencio'}.`,
      );
    }
    const partial = entryEvents.filter(e => eventCapability.get(e)?.capability === 'degraded');
    for (const e of partial) {
      out.push(`«${eventLabel(e)}»: ${eventCapability.get(e)?.reason}.`);
    }
    if (INTRADAY.includes(String(timeframe))) {
      out.push('El motor no reagrupa barras: esta temporalidad devuelve el mismo resultado que el diario.');
    }
    if (tickers.length > 1) {
      out.push('Con varios símbolos la curva de equity, el Sharpe y el drawdown no son de fiar: el motor recorre los símbolos uno tras otro en vez de avanzar por fechas. El retorno total y la tabla de operaciones sí lo son.');
    }
    if (direction === 'both') {
      out.push('La dirección «ambas» se ejecuta como largo.');
    }
    if (entryTiming === 'open') {
      out.push('Entrar en la apertura de la misma barra usa información que aún no existía en ese momento.');
    }
    if (!stats.known) {
      out.push('No se ha podido consultar qué puede ejecutar el motor, así que no se distingue lo soportado de lo que no.');
    }
    /* La estrategia se comparte con el modo Disparos, cuyo catálogo de
       filtros es el de BUILD entero; el motor de cartera solo implementa su
       subconjunto y devolvería un 422. Mejor decirlo aquí que en el error. */
    if (caps) {
      const legacyKeys = new Set(caps.filters.keys);
      const foreign = [...new Set(
        [...Object.keys(entryFilters), ...Object.keys(universeFilters)]
          .map(k => k.replace(/^(min|max)_/, '')),
      )].filter(k => !legacyKeys.has(k));
      if (foreign.length) {
        out.push(`El motor de cartera no implementa ${foreign.length === 1 ? 'el filtro' : 'los filtros'} ${foreign.join(', ')} (válido${foreign.length === 1 ? '' : 's'} en Disparos): quítalo o la petición fallará con 422.`);
      }
    }
    return out;
  }, [entryEvents, eventCapability, combine, timeframe, tickers.length, direction, entryTiming, stats.known, caps, entryFilters, universeFilters]);

  const reliable = tickers.length <= 1
    && !INTRADAY.includes(String(timeframe))
    && direction !== 'both'
    && entryTiming !== 'open'
    && !entryEvents.some(e => eventCapability.get(e)?.capability !== 'ok');

  /* ── Lanzar ─────────────────────────────────────────────────────────── */
  const buildConfig = useCallback((): StrategyConfig => {
    const clean = (f: Record<string, number | null>) =>
      Object.fromEntries(Object.entries(f).filter(([, v]) => v !== null && v !== undefined));
    return {
      name, description: '',
      universe: {
        method,
        criteria: criteria ? { value: criteria } : {},
        tickers: method === 'ticker_list' ? tickers : null,
        sql_where: method === 'sql_filter' ? sqlWhere.trim() : null,
      },
      entry_signals: entries,
      entry_timing: entryTiming,
      entry_events: entryEvents,
      entry_events_combine: combine,
      exit_rules: exits,
      exit_events: [],
      entry_filters: clean(entryFilters),
      universe_filters: clean(universeFilters),
      timeframe,
      start_date: startDate,
      end_date: endDate,
      initial_capital: capital ?? 100_000,
      max_positions: maxPositions ?? 1,
      position_size_pct: (positionSizePct ?? 10) / 100,
      direction,
      slippage_model: slippageModel,
      slippage_bps: slippageBps ?? 0,
      commission_per_trade: commission ?? 0,
      risk_free_rate: 0.05,
    } as StrategyConfig;
  }, [name, method, criteria, tickers, sqlWhere, entries, entryTiming, entryEvents, combine,
      exits, entryFilters, universeFilters, timeframe, startDate, endDate, capital,
      maxPositions, positionSizePct, direction, slippageModel, slippageBps, commission]);

  const run = useCallback(() => {
    if (problems.length) {
      // Un botón gris no dice dónde está el fallo. Se lleva el foco al campo.
      const el = document.querySelector<HTMLElement>(`[data-bt-field="${problems[0].field}"]`);
      el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el?.focus();
      return;
    }
    void runStructured(buildConfig(), { includeWalkForward: walkForward, includeMonteCarlo: monteCarlo });
  }, [problems, buildConfig, runStructured, walkForward, monteCarlo]);

  /* Atajo acotado a la ventana: `document` es de la paleta global de la app. */
  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!isRunning) run();
    }
  }, [isRunning, run]);

  /* ── Catálogo ───────────────────────────────────────────────────────── */
  const selectedUids = useMemo(() => {
    const s = new Set<string>();
    for (const e of entryEvents) s.add(`event:${e}`);
    for (const k of Object.keys(entryFilters)) s.add(`filter:${k.replace(/^(min|max)_/, '')}`);
    for (const k of Object.keys(universeFilters)) s.add(`filter:${k.replace(/^(min|max)_/, '')}`);
    return s;
  }, [entryEvents, entryFilters, universeFilters]);

  const onPick = useCallback((entry: CatalogEntry) => {
    const target = picker?.target;
    if (target === 'entryEvents' && entry.kind === 'event') {
      setEntryEvents(prev => (prev.includes(entry.id) ? prev : [...prev, entry.id]));
    } else if (target === 'entryFilters' && entry.kind === 'filter') {
      setEntryFilters(prev => ({ ...prev, [`min_${entry.id}`]: prev[`min_${entry.id}`] ?? null }));
    } else if (target === 'universeFilters' && entry.kind === 'filter') {
      setUniverseFilters(prev => ({ ...prev, [`min_${entry.id}`]: prev[`min_${entry.id}`] ?? null }));
    } else if (target === 'signal' && entry.kind === 'indicator') {
      setEntries(prev => [...prev, { indicator: entry.id, operator: '>' as SignalOperator, value: 0 }]);
    }
    setPicker(null);
  }, [picker]);

  /* Filtros activos, agrupados por clave base para pintar min/max en una fila. */
  const filterRows = useCallback((f: Record<string, number | null>) => {
    const keys = new Set<string>();
    for (const k of Object.keys(f)) keys.add(k.replace(/^(min|max)_/, ''));
    return [...keys];
  }, []);

  const showResults = runs.length > 0 || isRunning || status === 'error';

  const modeSeg = (
    <Seg
      value={mode}
      onChange={setMode}
      ariaLabel="Producto"
      options={[
        { value: 'triggers', label: 'Disparos' },
        { value: 'portfolio', label: 'Cartera' },
      ]}
    />
  );

  if (mode === 'triggers') {
    return (
      <div
        className="h-full flex flex-col text-foreground overflow-hidden relative"
        style={{ backgroundColor: 'var(--color-surface)' }}
      >
        <div className="shrink-0 flex items-center gap-2 px-3 h-11 border-b" style={{ borderColor: RULE }}>
          {modeSeg}
          <span className="text-[11px] text-foreground/45">
            Eventos reales del motor · vocabulario BUILD completo
          </span>
          <span className="flex-1" />
          <Badge title="Los disparos son alertas que el motor vivo emitió de verdad; el filtrado usa el matcher de producción portado y verificado">
            Exacto (L0)
          </Badge>
        </div>
        <TriggersPanel
          events={entryEvents}
          setEvents={setEntryEvents}
          filters={entryFilters}
          setFilters={setEntryFilters}
        />
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      onKeyDown={onKeyDown}
      className="h-full flex flex-col text-foreground overflow-hidden relative"
      style={{ backgroundColor: 'var(--color-surface)' }}
    >
      {/* ── Barra de herramientas ─────────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-2 px-3 h-11 border-b" style={{ borderColor: RULE }}>
        {modeSeg}
        {narrow && showResults && (
          <Seg
            value={tab}
            onChange={setTab}
            ariaLabel="Vista"
            options={[{ value: 'define', label: 'Definir' }, { value: 'results', label: 'Resultados' }]}
          />
        )}
        <TextInput
          value={name}
          onChange={setName}
          aria-label="Nombre de la estrategia"
          className="w-[168px] font-medium"
        />
        <span className="flex-1" />
        {isRunning ? (
          <Badge pulse>{progressText || 'Ejecutando'}</Badge>
        ) : (
          <Badge title={reliable
            ? 'Un símbolo, diario y sin eventos problemáticos: los números son de fiar'
            : 'Revisa el diagnóstico: parte de las métricas no son de fiar con esta configuración'}>
            {reliable ? 'Fiable' : 'Con reservas'}
          </Badge>
        )}
        <ActionButton onClick={run} disabled={isRunning} busy={isRunning} hint="⌘↵">
          {isRunning ? 'Ejecutando…' : 'Ejecutar'}
        </ActionButton>
      </div>

      {/* ── Corridas ──────────────────────────────────────────────────── */}
      {runs.length > 0 && (
        <div className="shrink-0 flex items-center gap-1.5 px-3 h-9 border-b overflow-x-auto" style={{ borderColor: RULE }}>
          {runs.map((r, i) => (
            <button
              key={r.id}
              type="button"
              aria-pressed={i === 0 ? undefined : compare.has(r.id)}
              title={i === 0 ? 'Corrida actual' : 'Superponer su curva sobre la actual'}
              onClick={() => {
                if (i === 0) return;
                setCompare(prev => {
                  const n = new Set(prev);
                  n.has(r.id) ? n.delete(r.id) : n.add(r.id);
                  return n;
                });
              }}
              className={cn(
                'shrink-0 inline-flex items-center gap-2 px-2 h-7 rounded border transition-colors',
                i === 0
                  ? 'border-foreground/45 bg-foreground/[0.10]'
                  : compare.has(r.id)
                    ? 'border-foreground/30 bg-foreground/[0.06]'
                    : 'border-foreground/20 bg-foreground/[0.04] hover:bg-foreground/[0.08]',
              )}
            >
              <span className="font-mono text-[10px] text-foreground/45">{r.label}</span>
              <Sparkline
                points={r.result.equity_curve ?? []}
                baseline={r.result.strategy.initial_capital}
                muted={i !== 0}
              />
              <span className="font-mono text-[11px] font-semibold tabular-nums">
                {r.result.core_metrics.profit_factor.toFixed(2)}
              </span>
              <span className="font-mono text-[10px] text-foreground/35">{r.at}</span>
            </button>
          ))}
        </div>
      )}

      {/* ── Cuerpo ────────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 flex">
        {(!narrow || tab === 'define' || !showResults) && (
          <div
            className="flex flex-col min-w-0 overflow-hidden"
            style={narrow || !showResults ? { flex: 1 } : { width: paneW, flex: 'none' }}
          >
            <div className="flex-1 overflow-auto px-3 py-3 flex flex-col gap-5">

              {/* Universo */}
              <section className="flex flex-col gap-2.5">
                <SectionHead title="Universo" />
                <Seg
                  value={method}
                  onChange={setMethod}
                  ariaLabel="Modo de universo"
                  options={UNIVERSE_METHODS.map(m => ({ value: m.value, label: m.label }))}
                />
                {method === 'ticker_list' && (
                  <Field label="Símbolos" error={problemFor('tickers')}
                    hint={tickers.length > 1 ? 'Con más de un símbolo las métricas de cartera dejan de ser fiables' : undefined}>
                    {({ id, describedBy, invalid }) => (
                      <TextInput
                        id={id} data-bt-field="tickers" aria-describedby={describedBy} invalid={invalid}
                        value={tickersStr} onChange={setTickersStr} mono
                        placeholder="SPY, AAPL, QQQ"
                      />
                    )}
                  </Field>
                )}
                {method === 'sql_filter' && (
                  <Field label="Condición SQL" error={problemFor('sql')}>
                    {({ id, describedBy, invalid }) => (
                      <TextInput
                        id={id} data-bt-field="sql" aria-describedby={describedBy} invalid={invalid}
                        value={sqlWhere} onChange={setSqlWhere} mono
                        placeholder="market_cap > 1e9 AND sector = 'Technology'"
                      />
                    )}
                  </Field>
                )}
                {(method === 'sector' || method === 'industry') && (
                  <Field label={method === 'sector' ? 'Sector' : 'Industria'}>
                    {({ id }) => (
                      <TextInput id={id} value={criteria} onChange={setCriteria} placeholder="Technology" />
                    )}
                  </Field>
                )}

                <FieldGroup label="Temporalidad"
                  hint={INTRADAY.includes(String(timeframe))
                    ? 'El motor no reagrupa barras: devuelve lo mismo que el diario'
                    : undefined}>
                    <Seg
                      value={String(timeframe)}
                      onChange={(v) => setTimeframe(v as Timeframe)}
                      mono
                      ariaLabel="Temporalidad"
                      options={TIMEFRAMES.map(t => ({
                        value: String(t.value),
                        label: t.label,
                        title: INTRADAY.includes(String(t.value))
                          ? 'Sin reagrupado en el motor: da el mismo resultado que 1d' : undefined,
                      }))}
                    />
                </FieldGroup>

                <div className="grid grid-cols-2 gap-2" data-bt-field="dates">
                  <Field label="Desde" error={problemFor('dates')}>
                    {({ id, describedBy, invalid }) => (
                      <TextInput id={id} aria-describedby={describedBy} invalid={invalid}
                        type="date" value={startDate} onChange={setStartDate} mono />
                    )}
                  </Field>
                  <Field label="Hasta">
                    {({ id }) => (
                      <TextInput id={id} type="date" value={endDate} onChange={setEndDate} mono />
                    )}
                  </Field>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <FieldGroup label="Dirección"
                    hint={direction === 'both' ? 'El motor la ejecuta como largo' : undefined}>
                      <Seg
                        value={direction} onChange={setDirection} ariaLabel="Dirección"
                        options={[
                          { value: 'long' as const, label: 'Largo' },
                          { value: 'short' as const, label: 'Corto' },
                          { value: 'both' as const, label: 'Ambas', title: 'El motor la ejecuta como largo' },
                        ]}
                      />
                  </FieldGroup>
                  <FieldGroup label="Momento de entrada"
                    hint={entryTiming === 'open' ? 'Usa información de la propia barra' : undefined}>
                      <Seg
                        value={entryTiming} onChange={setEntryTiming} ariaLabel="Momento de entrada"
                        options={[
                          { value: 'next_open' as const, label: 'Sig. apertura' },
                          { value: 'close' as const, label: 'Cierre' },
                          { value: 'open' as const, label: 'Apertura', title: 'Mira información que aún no existía' },
                        ]}
                      />
                  </FieldGroup>
                </div>
              </section>

              {/* Entrada */}
              <section className="flex flex-col gap-2.5" data-bt-field="entry" tabIndex={-1}>
                <SectionHead
                  title="Entrada"
                  action={
                    <TextButton onClick={() => setPicker({ kinds: ['event', 'indicator'], target: 'entryEvents' })}>
                      + Añadir
                    </TextButton>
                  }
                />
                {problemFor('entry') && (
                  <p className="m-0 text-[11px] text-rose-500 dark:text-rose-400">{problemFor('entry')}</p>
                )}

                {entryEvents.length > 0 && (
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wider">Eventos</span>
                      <Seg
                        value={combine} onChange={setCombine} size="sm" ariaLabel="Combinación de eventos"
                        options={[{ value: 'or' as const, label: 'Cualquiera' }, { value: 'and' as const, label: 'Todas' }]}
                      />
                      <span className="ml-auto font-mono text-[10px] text-foreground/45">{entryEvents.length}</span>
                    </div>
                    {entryEvents.map(ev => {
                      const cap = eventCapability.get(ev);
                      const bad = cap?.capability === 'unsupported';
                      const soso = cap?.capability === 'degraded';
                      return (
                        <div key={ev} className="flex items-center gap-2 py-1.5 border-b" style={{ borderColor: RULE }}>
                          <span className={cn('text-[12px] truncate',
                            bad ? 'text-foreground/30 line-through' : soso ? 'text-foreground/60' : 'text-foreground')}>
                            {eventLabel(ev)}
                          </span>
                          {cap?.reason && (
                            <span className="text-[10px] text-foreground/40 truncate">{cap.reason}</span>
                          )}
                          <button
                            type="button"
                            aria-label={`Quitar ${eventLabel(ev)}`}
                            onClick={() => setEntryEvents(prev => prev.filter(x => x !== ev))}
                            className="ml-auto shrink-0 text-foreground/30 hover:text-foreground text-[13px] leading-none"
                          >
                            ×
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {entryEvents.length > 0 && entries.length > 0 && (
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[10px] font-bold tracking-[0.16em] text-foreground/45">Y</span>
                    <span className="flex-1 h-px" style={{ backgroundColor: RULE }} />
                  </div>
                )}

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-wider">Señales</span>
                    <span className="text-[10px] uppercase tracking-wider text-foreground/45">todas</span>
                    <span className="ml-auto font-mono text-[10px] text-foreground/45">{entries.length}</span>
                  </div>
                  {entries.map((sig, i) => (
                    <SignalRow
                      key={i}
                      signal={sig}
                      onChange={(s) => setEntries(prev => prev.map((x, j) => (j === i ? s : x)))}
                      onRemove={() => setEntries(prev => prev.filter((_, j) => j !== i))}
                    />
                  ))}
                  <TextButton onClick={() => setEntries(prev => [...prev, defaultSignal()])} tone="quiet">
                    + Añadir señal
                  </TextButton>
                </div>
              </section>

              {/* Salida */}
              <section className="flex flex-col gap-2.5">
                <SectionHead
                  title="Salida"
                  action={
                    <TextButton onClick={() => setExits(prev => [...prev, { type: 'stop_loss' as ExitType, value: 0.05 }])}>
                      + Añadir
                    </TextButton>
                  }
                />
                {exits.map((rule, i) => (
                  <ExitRowUI
                    key={i}
                    rule={rule}
                    duplicateSignal={rule.type === 'signal' && exits.findIndex(r => r.type === 'signal') !== i}
                    onChange={(r) => setExits(prev => prev.map((x, j) => (j === i ? r : x)))}
                    onRemove={() => setExits(prev => prev.filter((_, j) => j !== i))}
                  />
                ))}
                {!exits.length && (
                  <p className="m-0 text-[11px] text-foreground/45">
                    Sin reglas de salida, las posiciones se cierran a la fuerza al acabar el periodo.
                  </p>
                )}
              </section>

              {/* Filtros */}
              <section className="flex flex-col gap-2.5">
                <SectionHead
                  title="Filtros por barra"
                  action={
                    <TextButton onClick={() => setPicker({ kinds: ['filter'], target: 'entryFilters' })}>
                      + Añadir
                    </TextButton>
                  }
                />
                <FilterRows
                  filters={entryFilters}
                  keys={filterRows(entryFilters)}
                  catalog={catalog}
                  onChange={setEntryFilters}
                />

                <SectionHead
                  title="Filtros de universo"
                  action={
                    <TextButton onClick={() => setPicker({ kinds: ['filter'], target: 'universeFilters' })}>
                      + Añadir
                    </TextButton>
                  }
                />
                <FilterRows
                  filters={universeFilters}
                  keys={filterRows(universeFilters)}
                  catalog={catalog}
                  onChange={setUniverseFilters}
                />
              </section>

              {/* Ejecución */}
              <section className="flex flex-col gap-2.5">
                <SectionHead title="Ejecución" />
                <div className="grid grid-cols-3 gap-2">
                  <Field label="Capital">
                    {({ id }) => <NumInput id={id} value={capital} onChange={setCapital} align="left" />}
                  </Field>
                  <Field label="Máx. posic.">
                    {({ id }) => <NumInput id={id} value={maxPositions} onChange={setMaxPositions} align="left" />}
                  </Field>
                  <Field label="Tamaño %">
                    {({ id }) => <NumInput id={id} value={positionSizePct} onChange={setPositionSizePct} align="left" />}
                  </Field>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <FieldGroup label="Slippage">
                      <Seg
                        value={String(slippageModel)}
                        onChange={(v) => setSlippageModel(v as SlippageModel)}
                        size="sm" ariaLabel="Modelo de slippage"
                        options={SLIPPAGE_MODELS.map(s => ({ value: String(s.value), label: s.label }))}
                      />
                  </FieldGroup>
                  <Field label="Slippage bps">
                    {({ id }) => <NumInput id={id} value={slippageBps} onChange={setSlippageBps} align="left" />}
                  </Field>
                  <Field label="Comisión">
                    {({ id }) => <NumInput id={id} value={commission} onChange={setCommission} align="left" />}
                  </Field>
                </div>
              </section>

              {/* Robustez */}
              <section className="flex flex-col gap-2">
                <SectionHead title="Robustez" />
                <Check checked={walkForward} onChange={setWalkForward}
                  label="Walk-forward (5 tramos)"
                  note="No reoptimiza parámetros entre tramos" />
                <Check checked={monteCarlo} onChange={setMonteCarlo}
                  label="Monte Carlo (1.000 simulaciones)"
                  note="Remuestrea por posición, no por cartera" />
              </section>
            </div>
          </div>
        )}

        {!narrow && showResults && (
          <SplitHandle
            ariaLabel="Ancho del panel de configuración"
            onDrag={(dx) => setPaneW(w => Math.max(340, Math.min(760, w + dx)))}
            onCommit={() => persist(paneW)}
          />
        )}

        {showResults && (!narrow || tab === 'results') && (
          <div className="flex-1 min-w-0 flex flex-col border-l" style={{ borderColor: narrow ? 'transparent' : RULE }}>
            {status === 'error' ? (
              <RunError
                message={error ?? 'Error desconocido'}
                events={entryEvents}
                capability={eventCapability}
                onOpenCatalog={() => setPicker({ kinds: ['event'], target: 'entryEvents' })}
                onDismiss={reset}
              />
            ) : isRunning && !current ? (
              <CenterMessage>{progressText || 'Ejecutando el backtest…'}</CenterMessage>
            ) : current ? (
              <ResultsPane
                result={current.result}
                overlays={overlays}
                warnings={diagnostics}
                unreliablePortfolio={tickers.length > 1}
              />
            ) : null}
          </div>
        )}
      </div>

      <WindowFooter
        left={
          current
            ? `${current.result.bars_processed?.toLocaleString('es-ES') ?? '–'} barras · ${current.result.symbols_tested ?? tickers.length} símbolos · ` +
              `${current.result.trades?.length ?? 0} operaciones · ${((current.result.execution_time_ms ?? 0) / 1000).toFixed(1)} s`
            : `${stats.known ? `${stats.eventsOk} de ${stats.eventsTotal} eventos ejecutables · ${stats.filters} filtros` : 'capacidades del motor no disponibles'}`
        }
      />

      {picker && (
        <CatalogPicker
          entries={catalog}
          kinds={picker.kinds}
          selected={selectedUids}
          onPick={onPick}
          onClose={() => setPicker(null)}
          title="Añadir al backtest"
        />
      )}
    </div>
  );
}

/* ══════════════════════════ PIEZAS ══════════════════════════ */

function SignalRow({
  signal, onChange, onRemove,
}: { signal: Signal; onChange: (s: Signal) => void; onRemove: () => void }) {
  const isCross = signal.operator === 'crosses_above' || signal.operator === 'crosses_below';
  const valueIsIndicator = isCross || INDICATORS.some(i => i.id === String(signal.value));

  return (
    <div className="flex items-center gap-1.5 py-1.5 border-b" style={{ borderColor: RULE }}>
      <select
        aria-label="Indicador"
        value={signal.indicator}
        onChange={(e) => onChange({ ...signal, indicator: e.target.value })}
        className="h-7 px-1.5 rounded-md text-[11px] bg-foreground/[0.04] border border-transparent outline-none hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] focus:border-foreground/15 max-w-[124px]"
      >
        {INDICATORS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
      </select>

      <select
        aria-label="Operador"
        value={signal.operator}
        onChange={(e) => onChange({ ...signal, operator: e.target.value as SignalOperator })}
        className="h-7 px-1.5 rounded-md text-[11px] font-mono bg-foreground/[0.04] border border-transparent outline-none hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] focus:border-foreground/15"
      >
        {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      {valueIsIndicator ? (
        <select
          aria-label="Valor de comparación"
          value={String(signal.value)}
          onChange={(e) => onChange({ ...signal, value: e.target.value })}
          className="h-7 px-1.5 rounded-md text-[11px] bg-foreground/[0.04] border border-transparent outline-none hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] focus:border-foreground/15 max-w-[124px]"
        >
          {INDICATORS.map(i => <option key={i.id} value={i.id}>{i.label}</option>)}
        </select>
      ) : (
        <NumInput
          value={typeof signal.value === 'number' ? signal.value : null}
          onChange={(v) => onChange({ ...signal, value: v ?? 0 })}
          align="left"
          className="w-[72px]"
        />
      )}

      <button
        type="button"
        aria-label="Quitar señal"
        onClick={onRemove}
        className="ml-auto shrink-0 text-foreground/30 hover:text-foreground text-[13px] leading-none"
      >
        ×
      </button>
    </div>
  );
}

function ExitRowUI({
  rule, onChange, onRemove, duplicateSignal,
}: {
  rule: ExitRule; onChange: (r: ExitRule) => void; onRemove: () => void; duplicateSignal: boolean;
}) {
  const meta = EXIT_TYPES.find(e => e.value === rule.type);
  const needsValue = rule.type !== 'eod' && rule.type !== 'signal';
  const isPct = rule.type === 'stop_loss' || rule.type === 'target' || rule.type === 'trailing_stop';

  return (
    <div className="flex flex-col gap-1 py-1.5 border-b" style={{ borderColor: RULE }}>
      <div className="flex items-center gap-1.5">
        <select
          aria-label="Tipo de salida"
          value={String(rule.type)}
          onChange={(e) => onChange({ ...rule, type: e.target.value as ExitType })}
          className="h-7 px-1.5 rounded-md text-[11px] bg-foreground/[0.04] border border-transparent outline-none hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] focus:border-foreground/15"
        >
          {EXIT_TYPES.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}
        </select>

        {needsValue && (
          <>
            <NumInput
              value={isPct ? (rule.value ?? 0) * 100 : rule.value ?? null}
              onChange={(v) => onChange({ ...rule, value: isPct ? (v ?? 0) / 100 : v })}
              align="left"
              className="w-[76px]"
            />
            <span className="text-[10px] text-foreground/45">{meta?.unit}</span>
          </>
        )}

        <button
          type="button"
          aria-label="Quitar regla de salida"
          onClick={onRemove}
          className="ml-auto shrink-0 text-foreground/30 hover:text-foreground text-[13px] leading-none"
        >
          ×
        </button>
      </div>
      {duplicateSignal && (
        <span className="text-[10px] text-foreground/45">
          El motor solo aplica la primera salida por señal: esta se descarta.
        </span>
      )}
    </div>
  );
}

function FilterRows({
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
      <div className="grid grid-cols-[1fr_78px_78px] gap-1.5 pb-1 border-b" style={{ borderColor: RULE }}>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55">Filtro</span>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55 text-right pr-1">Mín</span>
        <span className="text-[10px] uppercase tracking-wider text-foreground/55 text-right pr-1">Máx</span>
      </div>
      {keys.map(k => {
        const meta = catalog.find(c => c.uid === `filter:${k}`);
        return (
          <div key={k} className="grid grid-cols-[1fr_78px_78px] gap-1.5 items-center py-1 border-b" style={{ borderColor: RULE }}>
            <span className="text-[12px] truncate flex items-center gap-1.5">
              {meta?.label ?? k}
              {meta?.suffix && <span className="text-[10px] text-foreground/45">{meta.suffix}</span>}
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
            <NumInput
              value={filters[`min_${k}`] ?? null}
              onChange={(v) => onChange({ ...filters, [`min_${k}`]: v })}
            />
            <NumInput
              value={filters[`max_${k}`] ?? null}
              onChange={(v) => onChange({ ...filters, [`max_${k}`]: v })}
            />
          </div>
        );
      })}
    </div>
  );
}

function Check({
  checked, onChange, label, note,
}: { checked: boolean; onChange: (v: boolean) => void; label: string; note?: string }) {
  return (
    <label className="flex items-start gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-3.5 h-3.5 rounded border-foreground/25 accent-current"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-[11px]">{label}</span>
        {note && <span className="text-[10px] text-foreground/45">{note}</span>}
      </span>
    </label>
  );
}

/**
 * Error de corrida. El caso frecuente —cero operaciones— llega como
 * `ValueError` con un texto que se arma SOLO con `entry_signals`: entrando por
 * eventos sale «Entry conditions () were never triggered», con el paréntesis
 * vacío. Aquí se explica con lo que sí sabemos y se ofrece una salida.
 */
function RunError({
  message, events, capability, onOpenCatalog, onDismiss,
}: {
  message: string;
  events: string[];
  capability: Map<string, CatalogEntry>;
  onOpenCatalog: () => void;
  onDismiss: () => void;
}) {
  const zeroTrades = /zero trades/i.test(message);
  const dead = events.filter(e => capability.get(e)?.capability === 'unsupported');

  // El motor mete las cifras reales en el texto; se extraen para enseñarlas
  // como datos en vez de como una frase larga.
  const bars = message.match(/Data loaded:\s*([\d.,]+)\s*bars/i)?.[1];
  const range = message.match(/from\s+(.+?)\s+to\s+(.+?)\s+for/i);
  const symbols = message.match(/for\s+(\d+)\s+symbols?/i)?.[1];

  return (
    <div className="h-full overflow-auto px-5 py-5 flex flex-col gap-4">
      <span className="text-[13px] font-semibold text-rose-500 dark:text-rose-400">
        {zeroTrades ? 'Ninguna barra cumplió las condiciones de entrada' : 'El backtest falló'}
      </span>

      {zeroTrades && (bars || range || symbols) && (
        <div className="flex flex-col max-w-[460px]">
          {bars && <ErrRow k="Barras cargadas" v={bars} />}
          {range && <ErrRow k="Rango con datos" v={`${range[1].slice(0, 10)} → ${range[2].slice(0, 10)}`} />}
          {symbols && <ErrRow k="Símbolos" v={symbols} />}
          {dead.map(e => (
            <ErrRow key={e} k={`Disparos de «${eventLabel(e)}»`} v="0" zero />
          ))}
        </div>
      )}

      <p className="m-0 text-[12px] leading-relaxed text-foreground/65 max-w-[64ch]">
        {dead.length
          ? `${dead.length === 1 ? 'Ese evento no está implementado' : 'Esos eventos no están implementados'} en el motor: ${dead.length === 1 ? 'evalúa' : 'evalúan'} siempre a falso, así que la entrada nunca llega a probarse.`
          : message}
      </p>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={onOpenCatalog}
          className="h-7 px-3 rounded-md text-[11px] font-semibold border border-foreground/45 bg-foreground/[0.10] hover:bg-foreground/[0.16]"
        >
          Ver eventos ejecutables
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="h-7 px-3 rounded-md text-[11px] border border-foreground/20 bg-foreground/[0.04] hover:bg-foreground/[0.08]"
        >
          Descartar
        </button>
      </div>
    </div>
  );
}

function ErrRow({ k, v, zero }: { k: string; v: string; zero?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 border-b last:border-b-0" style={{ borderColor: RULE }}>
      <span className="text-[12px] text-foreground/55">{k}</span>
      <span className={cn('font-mono text-[12px] tabular-nums',
        zero && 'text-rose-500 dark:text-rose-400 font-semibold')}>{v}</span>
    </div>
  );
}

export default BacktestPanelContent;
