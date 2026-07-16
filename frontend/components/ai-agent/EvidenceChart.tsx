'use client';

/**
 * EvidenceChart — real candles of a dry-run day with the exact fire
 * moments marked on the chart. This is the "see it to believe it" layer
 * of the alert trust loop: the paraphrase says what the alert means, the
 * table says when it fired, THIS shows it on the tape.
 */
import { memo, useEffect, useRef } from 'react';
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type UTCTimestamp,
  type SeriesMarker,
} from 'lightweight-charts';
import type { ChartEvidence } from '@/lib/aiAlerts';

const _cssVar = (v: string, fallback: string) =>
  typeof window !== 'undefined'
    ? getComputedStyle(document.documentElement).getPropertyValue(v).trim() || fallback
    : fallback;

interface EvidenceChartProps {
  evidence: ChartEvidence;
  height?: number;
}

export const EvidenceChart = memo(function EvidenceChart({
  evidence,
  height = 180,
}: EvidenceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !evidence.bars.length) return;

    const up = _cssVar('--color-chart-up', '#10b981');
    const down = _cssVar('--color-chart-down', '#ef4444');
    const text = _cssVar('--color-muted-fg', '#64748b');
    const grid = _cssVar('--color-chart-grid', '#f1f5f9');
    const border = _cssVar('--color-border', '#e2e8f0');
    const accent = _cssVar('--color-chart-crosshair', '#3b82f6');

    const chart = createChart(el, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: text,
        fontSize: 9,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: grid, style: LineStyle.Solid },
        horzLines: { color: grid, style: LineStyle.Solid },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: accent, width: 1, style: LineStyle.Dashed, labelBackgroundColor: accent },
        horzLine: { color: accent, width: 1, style: LineStyle.Dashed, labelBackgroundColor: accent },
      },
      rightPriceScale: { borderColor: border, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: {
        borderColor: border,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 2,
      },
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      wickUpColor: up,
      wickDownColor: down,
      borderVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    series.setData(
      evidence.bars.map(b => ({
        time: b.t as UTCTimestamp,
        open: b.o, high: b.h, low: b.l, close: b.c,
      })),
    );

    // Horizontal lines for absolute price levels ("reclaim 502 / lose 500")
    for (const lvl of evidence.levels || []) {
      series.createPriceLine({
        price: lvl.value,
        color: lvl.direction === 'above' ? up : down,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: lvl.direction === 'above' ? '↑ reclaim' : '↓ pérdida',
      });
    }

    // Fire markers — snap each fire to the nearest bar time
    const barTimes = evidence.bars.map(b => b.t);
    const snap = (t: number): number => {
      let best = barTimes[0];
      let bd = Math.abs(t - best);
      for (const bt of barTimes) {
        const d = Math.abs(t - bt);
        if (d < bd) { bd = d; best = bt; }
      }
      return best;
    };
    const markers: SeriesMarker<UTCTimestamp>[] = (evidence.fires || [])
      .filter(f => f.t)
      .map((f, i) => ({
        time: snap(f.t) as UTCTimestamp,
        position: 'aboveBar' as const,
        color: accent,
        shape: 'arrowDown' as const,
        text: evidence.fires.length > 1 ? `${i + 1}` : '⚡',
        size: 1,
      }));
    if (markers.length) createSeriesMarkers(series, markers);

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [evidence, height]);

  if (!evidence.bars.length) return null;

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border-subtle">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-foreground">{evidence.symbol}</span>
          <span className="text-[9px] font-mono text-muted-fg">{evidence.date}</span>
        </div>
        <span className="text-[8.5px] text-muted-fg">
          {evidence.fires.length > 0
            ? `${evidence.fires.length} ${evidence.fires.length === 1 ? 'disparo marcado' : 'disparos marcados'}`
            : 'sin disparos este día'}
          {' · velas 1m'}
        </span>
      </div>
      <div ref={containerRef} style={{ height }} />
    </div>
  );
});
