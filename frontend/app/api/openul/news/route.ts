import { NextRequest, NextResponse } from 'next/server';

const OPENUL_URL = process.env.OPENUL_URL || 'http://localhost:8070';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get('limit') || '50';
    const beforeTs = searchParams.get('before_ts') || '';

    const qs = new URLSearchParams({ limit });
    if (beforeTs) qs.set('before_ts', beforeTs);

    const res = await fetch(`${OPENUL_URL}/api/v1/news?${qs}`, {
      signal: AbortSignal.timeout(10_000),
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
      { error: err.message || 'Failed to fetch news' },
      { status: 500 },
    );
  }
}
