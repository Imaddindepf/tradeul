'use client';

/**
 * Ayudantes del gráfico SIN importar Plotly.
 *
 * Están separados de `plotly-quant.ts` a propósito: aquel importa
 * `plotly.js/lib/core` en el nivel superior, así que cualquier módulo que lo
 * importe de forma estática se arrastra Plotly al bundle y el `next/dynamic`
 * del componente deja de servir para nada. Aquí solo hay funciones puras, de
 * modo que `ResultsChart` puede usarlas sin cargar la librería hasta que se
 * monta el gráfico de verdad.
 */

/**
 * Por encima de este número de puntos se cambia a WebGL. El SVG de Plotly se
 * arrastra a partir de unos pocos miles de nodos; `scattergl` aguanta cientos
 * de miles. Un año de barras de 1 minuto son ~98.000.
 */
export const GL_THRESHOLD = 6_000;

export function traceType(points: number): 'scatter' | 'scattergl' {
  return points > GL_THRESHOLD ? 'scattergl' : 'scatter';
}

/** Lee una variable del tema: el gráfico sigue a claro/oscuro como el resto. */
export function themeVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export interface QuantTheme {
  fg: string; muted: string; grid: string; surface: string;
  up: string; down: string; neutral: string;
}

export function readTheme(): QuantTheme {
  return {
    fg: themeVar('--color-fg', '#f5f5f7'),
    muted: themeVar('--color-muted-fg', '#86868b'),
    grid: themeVar('--color-border', '#1d1d1f'),
    surface: themeVar('--color-surface', '#0a0a0a'),
    up: themeVar('--color-chart-up', '#22c55e'),
    down: themeVar('--color-chart-down', '#f87171'),
    neutral: themeVar('--color-muted-fg', '#86868b'),
  };
}

/**
 * Configuración común. La barra de Plotly se queda con lo que un quant usa de
 * verdad; el resto de controles (escala, rango, superposición) van fuera, en el
 * lenguaje de la ventana.
 */
export function quantConfig(filename: string) {
  return {
    displaylogo: false,
    responsive: true,
    scrollZoom: true,
    doubleClick: 'reset' as const,
    modeBarButtonsToRemove: [
      'lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines',
      'hoverClosestCartesian', 'hoverCompareCartesian',
    ],
    toImageButtonOptions: { format: 'png' as const, filename, scale: 2 },
    locale: 'es',
  };
}

/** Ejes y guías comunes a los tres paneles. */
export function axisBase(t: QuantTheme) {
  return {
    gridcolor: t.grid,
    zerolinecolor: t.grid,
    linecolor: t.grid,
    tickfont: { size: 10, color: t.muted },
    showspikes: true,
    spikemode: 'across' as const,
    spikethickness: 1,
    spikedash: 'dot' as const,
    spikecolor: t.muted,
  };
}
