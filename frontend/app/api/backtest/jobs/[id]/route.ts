import { NextRequest, NextResponse } from 'next/server';

const BACKTESTER_URL = process.env.BACKTESTER_URL || 'http://localhost:8060';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id: jobId } = await params;
  if (!jobId) {
    return NextResponse.json({ error: 'job id required' }, { status: 400 });
  }

  try {
    const res = await fetch(`${BACKTESTER_URL}/api/v1/jobs/${jobId}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15_000),
      cache: 'no-store',
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    return NextResponse.json(data);
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return NextResponse.json({ error: 'Timeout' }, { status: 504 });
    }
    return NextResponse.json(
      { error: err.message || 'Failed to fetch job status' },
      { status: 500 }
    );
  }
}
