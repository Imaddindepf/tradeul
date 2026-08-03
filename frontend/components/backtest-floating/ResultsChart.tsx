'use client';

/**
 * El gráfico de resultados: equity, drawdown y PnL diario en tres paneles que
 * comparten un único eje de tiempo.
 *
 * Un solo `xaxis` con tres `yaxis` por dominios, en vez de tres figuras: así el
 * zoom es literalmente el mismo objeto y no hay que sincronizar nada a mano.
 * Arrastrar sobre el drawdown amplía también la equity y las barras.
 *
 * Lo que aporta frente a lo que había (cuatro gráficos sueltos, cada uno con su
 * zoom y sin drawdown):
 *   · hover unificado — una fecha, los tres valores
 *   · escala logarítmica en la equity, que es como se mira una curva compuesta
 *   · superposición de corridas anteriores para comparar sin cambiar de vista
 *   · WebGL automático por encima de 6.000 puntos
 *   · `drawdown_curve`, que el backend ya devolvía y nadie pintaba
 */

import { memo, useMemo, useState, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';
import { Seg, CenterMessage } from './ui';
// Ayudantes puros: no importan Plotly, así que no lo meten en el bundle.
import { readTheme, traceType, quantConfig, axisBase, type QuantTheme } from './plotly-theme';

/** El bundle a medida entra aquí y solo aquí: abrir la ventana no lo carga. */
const Plot = dynamic(() => import('./plotly-quant').then(m => m.Plot as any), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-foreground/[0.03]" />,
}) as any;

type Point = readonly [string, number];

export interface Overlay {
  id: string;
  label: string;
  equity: Point[];
}

type Scale = 'lin' | 'log';
type Span = '1m' | '3m' | '6m' | '1y' | 'all';

const SPANS: { value: Span; label: string; days: number | null }[] = [
  { value: '1m', label: '1M', days: 30 },
  { value: '3m', label: '3M', days: 90 },
  { value: '6m', label: '6M', days: 180 },
  { value: '1y', label: '1A', days: 365 },
  { value: 'all', label: 'Todo', days: null },
];

export const ResultsChart = memo(function ResultsChart({
  equity, drawdown, dailyPnl, initialCapital, overlays = [], className,
}: {
  equity: Point[];
  drawdown?: Point[];
  dailyPnl?: { date: string; pnl: number }[];
  initialCapital: number;
  overlays?: Overlay[];
  className?: string;
}) {
  const [scale, setScale] = useState<Scale>('lin');
  const [span, setSpan] = useState<Span>('all');
  const [theme, setTheme] = useState<QuantTheme | null>(null);

  // El tema se lee del DOM, así que hay que releerlo cuando cambia. El
  // conmutador de la app pone `data-theme` en el elemento raíz.
  useEffect(() => {
    setTheme(readTheme());
    const obs = new MutationObserver(() => setTheme(readTheme()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onMq = () => setTheme(readTheme());
    mq.addEventListener('change', onMq);
    return () => { obs.disconnect(); mq.removeEventListener('change', onMq); };
  }, []);

  const hasDd = !!drawdown?.length;
  const hasPnl = !!dailyPnl?.length;

  const data = useMemo(() => {
    if (!theme) return [];
    const finalEq = equity.length ? equity[equity.length - 1][1] : initialCapital;
    const tone = finalEq >= initialCapital ? theme.up : theme.down;
    const type = traceType(equity.length);

    const traces: any[] = [];

    // Corridas anteriores primero: quedan por debajo de la actual.
    for (const o of overlays) {
      traces.push({
        type: traceType(o.equity.length),
        mode: 'lines',
        name: o.label,
        x: o.equity.map(p => p[0]),
        y: o.equity.map(p => p[1]),
        line: { width: 1, color: theme.muted, dash: 'dot' },
        opacity: 0.75,
        hovertemplate: `${o.label}: %{y:,.0f} $<extra></extra>`,
        yaxis: 'y',
      });
    }

    traces.push({
      type,
      mode: 'lines',
      name: 'Equity',
      x: equity.map(p => p[0]),
      y: equity.map(p => p[1]),
      line: { width: 1.6, color: tone, shape: 'linear' },
      fill: overlays.length ? 'none' : 'tozeroy',
      fillcolor: overlays.length ? undefined : `${tone}22`,
      hovertemplate: 'Equity: %{y:,.0f} $<extra></extra>',
      yaxis: 'y',
    });

    if (hasDd) {
      traces.push({
        type: traceType(drawdown!.length),
        mode: 'lines',
        name: 'Drawdown',
        x: drawdown!.map(p => p[0]),
        y: drawdown!.map(p => p[1]),
        line: { width: 1, color: theme.down },
        fill: 'tozeroy',
        fillcolor: `${theme.down}26`,
        hovertemplate: 'DD: %{y:.2f} %<extra></extra>',
        yaxis: 'y2',
      });
    }

    if (hasPnl) {
      const pos = theme.up, neg = theme.down;
      traces.push({
        type: 'bar',
        name: 'PnL diario',
        x: dailyPnl!.map(d => d.date),
        y: dailyPnl!.map(d => d.pnl),
        marker: { color: dailyPnl!.map(d => (d.pnl >= 0 ? pos : neg)), line: { width: 0 } },
        hovertemplate: 'Día: %{y:,.0f} $<extra></extra>',
        yaxis: 'y3',
      });
    }

    return traces;
  }, [theme, equity, drawdown, dailyPnl, overlays, initialCapital, hasDd, hasPnl]);

  const layout = useMemo(() => {
    if (!theme) return {};
    const ax = axisBase(theme);

    // Dominios: la equity manda, el drawdown y las barras acompañan.
    const rows = 1 + (hasDd ? 1 : 0) + (hasPnl ? 1 : 0);
    const eqTop = 1;
    const eqBottom = rows === 3 ? 0.44 : rows === 2 ? 0.30 : 0;
    const ddTop = rows === 3 ? 0.40 : 0.26;
    const ddBottom = rows === 3 ? 0.22 : 0;
    const pnlTop = rows === 3 ? 0.18 : 0.26;

    let range: [string, string] | undefined;
    const days = SPANS.find(s => s.value === span)?.days ?? null;
    if (days && equity.length) {
      const end = new Date(equity[equity.length - 1][0]);
      const start = new Date(end);
      start.setDate(start.getDate() - days);
      range = [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
    }

    return {
      autosize: true,
      margin: { l: 54, r: 10, t: 6, b: 26 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { size: 10, color: theme.muted },
      showlegend: overlays.length > 0,
      legend: {
        orientation: 'h', x: 0, y: 1.04, xanchor: 'left', yanchor: 'bottom',
        font: { size: 10, color: theme.muted }, bgcolor: 'rgba(0,0,0,0)',
      },
      hovermode: 'x unified',
      hoverlabel: {
        bgcolor: theme.surface, bordercolor: theme.grid,
        font: { size: 11, color: theme.fg }, align: 'left',
      },
      dragmode: 'zoom',
      bargap: 0.15,
      xaxis: {
        ...ax,
        type: 'date',
        range,
        showgrid: false,
        anchor: rows === 3 ? 'y3' : rows === 2 ? 'y2' : 'y',
        rangeslider: { visible: false },
      },
      yaxis: {
        ...ax,
        type: scale === 'log' ? 'log' : 'linear',
        domain: [eqBottom, eqTop],
        tickformat: ',.0f',
        ticksuffix: ' $',
      },
      ...(hasDd ? {
        yaxis2: {
          ...ax, domain: [ddBottom, ddTop], ticksuffix: ' %',
          tickformat: '.0f', rangemode: 'nonpositive',
        },
      } : {}),
      ...(hasPnl ? {
        yaxis3: {
          ...ax, domain: [0, pnlTop], tickformat: ',.0f', ticksuffix: ' $',
          zeroline: true, zerolinewidth: 1,
        },
      } : {}),
      shapes: [
        {
          type: 'line', xref: 'paper', yref: 'y',
          x0: 0, x1: 1, y0: initialCapital, y1: initialCapital,
          line: { color: theme.grid, width: 1, dash: 'dot' },
        },
      ],
    } as any;
  }, [theme, scale, span, equity, overlays.length, initialCapital, hasDd, hasPnl]);

  // `revision` le dice a Plotly que actualice en sitio en vez de rehacer la
  // figura. Tiene que cambiar SOLO cuando cambian datos o layout: si se
  // incrementa en cada render, se remonta el canvas WebGL en cada hover.
  const revision = useRef(0);
  const lastKey = useRef('');
  const key = `${data.length}:${equity.length}:${overlays.length}:${scale}:${span}:${theme?.up ?? ''}`;
  if (key !== lastKey.current) { lastKey.current = key; revision.current += 1; }

  if (!equity.length) {
    return <CenterMessage>Sin curva de equity para esta corrida</CenterMessage>;
  }

  return (
    <div className={cn('flex flex-col min-h-0', className)}>
      <div className="shrink-0 flex items-center gap-2 px-3 py-1.5">
        <Seg
          value={scale}
          onChange={setScale}
          size="sm"
          ariaLabel="Escala del eje de equity"
          options={[
            { value: 'lin', label: 'Lineal' },
            { value: 'log', label: 'Log', title: 'Escala logarítmica: compara el porcentaje compuesto, no el valor absoluto' },
          ]}
        />
        <span className="flex-1" />
        <Seg
          value={span}
          onChange={setSpan}
          size="sm"
          mono
          ariaLabel="Rango temporal"
          options={SPANS.map(s => ({ value: s.value, label: s.label }))}
        />
      </div>

      <div className="flex-1 min-h-0">
        <Plot
          data={data}
          layout={layout}
          config={quantConfig('backtest')}
          revision={revision.current}
          useResizeHandler
          style={{ width: '100%', height: '100%' }}
        />
      </div>
    </div>
  );
});
