'use client';

/**
 * Bundle de Plotly a medida para el Backtester.
 *
 * ATENCIÓN: este módulo importa `plotly.js/lib/core` en el nivel superior.
 * Solo debe cargarse mediante `next/dynamic`, nunca con un `import` estático,
 * o la librería entra en el bundle de la ventana. Los ayudantes puros —tema,
 * configuración, umbral de WebGL— viven en `plotly-theme.ts` justamente para
 * poder usarse sin arrastrar esto.
 *
 * Por qué Plotly y no SVG a mano: esta ventana es para quants. Zoom sobre un
 * tramo, escala logarítmica, hover unificado sobre los tres paneles y WebGL
 * para series de cientos de miles de barras no son adornos, son el trabajo.
 *
 * Por qué a medida: `dist/plotly.min.js` son 4,6 MB porque trae mapas, 3D y
 * financieras. `lib/core` ya incluye `scatter` (src/core.js:29 — "scatter is
 * the only trace included by default"), así que encima solo hacen falta
 * `scattergl` y `bar`.
 */

import Plotly from 'plotly.js/lib/core';
import scattergl from 'plotly.js/lib/scattergl';
import bar from 'plotly.js/lib/bar';
import createPlotlyComponent from 'react-plotly.js/factory';

Plotly.register([scattergl, bar]);

export const Plot = createPlotlyComponent(Plotly);
export { Plotly };
