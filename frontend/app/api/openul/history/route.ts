import { NextRequest, NextResponse } from 'next/server';

// El persister expone el historial paginado leyendo de Postgres.
// Corre en network_mode: host => alcanzable en localhost:8071.
const PERSISTER_URL = process.env.OPENUL_PERSISTER_URL || 'http://localhost:8071';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get('limit') || '50';
    const beforeTs = searchParams.get('before_ts') || '';

    const qs = new URLSearchParams({ limit });
    if (beforeTs) qs.set('before_ts', beforeTs);

    const res = await fetch(`${PERSISTER_URL}/api/v1/history?${qs}`, {
      signal: AbortSignal.timeout(10_000),
      cache: 'no-store',
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(
        { error: (data as { detail?: string }).detail || `Upstream ${res.status}` },
        { status: res.status >= 500 ? 502 : res.status },
      );
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch history' },
      { status: 500 },
    );
  }
}
