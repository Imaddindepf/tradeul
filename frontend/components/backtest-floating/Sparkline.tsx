'use client';

/**
 * Miniatura de la curva de una corrida, para las pastillas del historial.
 *
 * SVG a mano y no Plotly: son 64×16 píxeles dentro de un chip, y montar una
 * figura de Plotly por cada corrida del historial cargaría el bundle y crearía
 * un canvas por chip. Plotly se queda para el gráfico grande, donde hace falta
 * zoom, escala logarítmica y WebGL.
 */

import { memo, useMemo } from 'react';

type Point = readonly [string, number];

/**
 * Largest-Triangle-Three-Buckets: conserva picos y quiebros, que es justo lo
 * que se pierde al quedarse con uno de cada N puntos.
 */
function lttb(data: Point[], threshold: number): Point[] {
  const n = data.length;
  if (threshold >= n || threshold < 3) return data;

  const out: Point[] = [data[0]];
  const every = (n - 2) / (threshold - 2);
  let a = 0;

  for (let i = 0; i < threshold - 2; i++) {
    const rangeStart = Math.floor((i + 1) * every) + 1;
    const rangeEnd = Math.min(Math.floor((i + 2) * every) + 1, n);
    const len = rangeEnd - rangeStart || 1;

    let avgX = 0, avgY = 0;
    for (let j = rangeStart; j < rangeEnd; j++) { avgX += j; avgY += data[j][1]; }
    avgX /= len; avgY /= len;

    const from = Math.floor(i * every) + 1;
    const to = Math.floor((i + 1) * every) + 1;
    const ax = a, ay = data[a][1];

    let best = -1, bestArea = -1;
    for (let j = from; j < to; j++) {
      const area = Math.abs((ax - avgX) * (data[j][1] - ay) - (ax - j) * (avgY - ay));
      if (area > bestArea) { bestArea = area; best = j; }
    }
    if (best >= 0) { out.push(data[best]); a = best; }
  }

  out.push(data[n - 1]);
  return out;
}

export const Sparkline = memo(function Sparkline({
  points, baseline, width = 64, height = 16, muted = false,
}: {
  points: Point[];
  /** Capital inicial: decide el color y ancla la escala. */
  baseline: number;
  width?: number;
  height?: number;
  muted?: boolean;
}) {
  const d = useMemo(() => {
    if (points.length < 2) return null;
    // Dos puntos por píxel es más que suficiente a este tamaño.
    const pts = lttb(points, Math.min(points.length, width * 2));

    let lo = Infinity, hi = -Infinity;
    for (const [, v] of pts) { if (v < lo) lo = v; if (v > hi) hi = v; }
    lo = Math.min(lo, baseline); hi = Math.max(hi, baseline);
    const span = hi - lo || Math.abs(hi) || 1;

    const px = (i: number) => (i / (pts.length - 1)) * (width - 2) + 1;
    const py = (v: number) => height - 1.5 - ((v - lo) / span) * (height - 3);

    let path = `M${px(0).toFixed(1)} ${py(pts[0][1]).toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) path += `L${px(i).toFixed(1)} ${py(pts[i][1]).toFixed(1)}`;

    return { path, base: py(baseline), up: pts[pts.length - 1][1] >= baseline };
  }, [points, baseline, width, height]);

  if (!d) return <span style={{ width, height }} aria-hidden="true" />;

  const stroke = muted
    ? 'currentColor'
    : d.up
      ? 'var(--color-chart-up, #22c55e)'
      : 'var(--color-chart-down, #f87171)';

  return (
    <svg
      width={width}
      height={height}
      className={muted ? 'text-foreground/35' : undefined}
      aria-hidden="true"
      focusable="false"
    >
      <line
        x1="1" x2={width - 1} y1={d.base} y2={d.base}
        stroke="currentColor" strokeOpacity={muted ? 0.4 : 0.18}
        className="text-foreground" strokeDasharray="1.5 2"
      />
      <path d={d.path} fill="none" stroke={stroke} strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
});
