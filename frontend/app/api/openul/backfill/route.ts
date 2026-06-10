import { NextRequest, NextResponse } from 'next/server';

const OPENUL_URL = process.env.OPENUL_URL || 'http://localhost:8070';

/**
 * Resumable SSE backfill — fills the gap left by a zombie EventSource.
 *
 * Frontend calls this when the tab becomes visible again, passing the
 * stream id of the last item it received. The backend returns every news
 * item with a strictly greater stream id, in chronological order, so the
 * UI can apply them (deduped by id) before reconnecting the EventSource.
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const sinceId = searchParams.get('since_id');
    const count = searchParams.get('count') || '500';

    if (!sinceId) {
      return NextResponse.json(
        { error: 'since_id is required' },
        { status: 400 },
      );
    }

    const qs = new URLSearchParams({ since_id: sinceId, count });

    const res = await fetch(`${OPENUL_URL}/api/v1/backfill?${qs}`, {
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
      { error: err.message || 'Failed to backfill' },
      { status: 500 },
    );
  }
}
