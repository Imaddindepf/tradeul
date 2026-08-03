import { NextRequest, NextResponse } from 'next/server';

const BACKTESTER_URL = process.env.BACKTESTER_URL || 'http://localhost:8060';
const GATEWAY_URL = process.env.API_GATEWAY_URL || 'http://localhost:8000';

/**
 * Análisis de disparos L0 (Fase 1 §7.1): eventos REALES del lake.
 *
 * Request: {
 *   strategy_id?: number,   // estrategia BUILD guardada — se resuelve contra
 *                           // el api_gateway CON el Bearer del usuario, así
 *                           // el ownership lo decide quien ya lo decide hoy
 *   strategy?: object,      // o la estrategia inline (BUILD en edición):
 *                           // { event_types: [...], ...filtros min_/max_/aq: }
 *   date_from: 'YYYY-MM-DD',
 *   date_to:   'YYYY-MM-DD',
 * }
 *
 * Los 422 del backtester (vocabulario desconocido, rango sin datos) se
 * reenvían tal cual: llevan las listas exactas y la UI debe renderizarlas.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { strategy_id, date_from, date_to } = body;
    let strategy = body.strategy;

    if (strategy_id != null) {
      const auth = request.headers.get('authorization');
      if (!auth) {
        return NextResponse.json(
          { error: 'strategy_id requiere Authorization (Bearer)' },
          { status: 401 },
        );
      }
      const res = await fetch(
        `${GATEWAY_URL}/api/v1/alert-strategies/${encodeURIComponent(strategy_id)}`,
        {
          headers: { Authorization: auth },
          signal: AbortSignal.timeout(8_000),
          cache: 'no-store',
        },
      );
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        return NextResponse.json(
          { error: `No se pudo resolver la estrategia ${strategy_id}`, detail },
          { status: res.status },
        );
      }
      const s = await res.json();
      // La request del backtester ES la estrategia BUILD: OR de tipos + AND de
      // filtros (incluidas claves aq:). Sin traducción con pérdida.
      strategy = { event_types: s.eventTypes ?? [], ...(s.filters ?? {}) };
    }

    if (!strategy || !date_from || !date_to) {
      return NextResponse.json(
        { error: 'strategy (o strategy_id), date_from y date_to son obligatorios' },
        { status: 422 },
      );
    }

    const res = await fetch(`${BACKTESTER_URL}/api/v1/backtest/triggers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy, date_from, date_to }),
      signal: AbortSignal.timeout(120_000),
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    if (err.name === 'AbortError' || err.name === 'TimeoutError') {
      return NextResponse.json({ error: 'Análisis de disparos: timeout' }, { status: 504 });
    }
    return NextResponse.json(
      { error: err.message || 'Fallo en el análisis de disparos' },
      { status: 500 },
    );
  }
}
