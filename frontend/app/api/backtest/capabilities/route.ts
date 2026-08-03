import { NextResponse } from 'next/server';

const BACKTESTER_URL = process.env.BACKTESTER_URL || 'http://localhost:8060';

/**
 * Qué puede ejecutar el motor: eventos registrados, filtros, temporalidades
 * con resample, modos de universo y los límites de validación.
 *
 * Cambia solo cuando se despliega el backtester, así que se cachea en el
 * servidor de Next: la ventana lo pide al abrirse y no tiene sentido que cada
 * apertura toque al servicio.
 */
export const revalidate = 300;

export async function GET() {
  try {
    const res = await fetch(`${BACKTESTER_URL}/api/v1/backtest/capabilities`, {
      signal: AbortSignal.timeout(8_000),
      next: { revalidate: 300 },
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `Backtester respondió ${res.status}` },
        { status: res.status },
      );
    }
    return NextResponse.json(await res.json(), {
      headers: { 'Cache-Control': 'public, max-age=60, stale-while-revalidate=300' },
    });
  } catch (err) {
    // Sin capacidades la ventana sigue funcionando, pero deja de poder
    // distinguir lo ejecutable de lo que no: el cliente lo trata como
    // "desconocido" y avisa, en vez de fingir que todo vale.
    const message = err instanceof Error ? err.message : 'Error desconocido';
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
