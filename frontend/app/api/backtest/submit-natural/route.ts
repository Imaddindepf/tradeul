import { NextRequest, NextResponse } from 'next/server';

const AGENT_URL = process.env.AGENT_URL || process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8031';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { prompt, tickers } = body as { prompt?: string; tickers?: string[] };
    if (!prompt || typeof prompt !== 'string') {
      return NextResponse.json({ error: 'prompt required' }, { status: 400 });
    }

    const res = await fetch(`${AGENT_URL}/api/backtest/submit-natural`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt.trim(),
        tickers: Array.isArray(tickers) ? tickers : [tickers].filter(Boolean) || ['SPY'],
        user_id: null,
      }),
      signal: AbortSignal.timeout(60_000),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(
        { error: (data as { detail?: string }).detail || `Agent ${res.status}` },
        { status: res.status >= 500 ? 502 : res.status }
      );
    }

    const jobId = (data as { job_id?: string }).job_id;
    if (!jobId) {
      return NextResponse.json({ error: 'Agent did not return job_id' }, { status: 502 });
    }

    return NextResponse.json({ job_id: jobId });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return NextResponse.json({ error: 'Request timeout' }, { status: 504 });
    }
    return NextResponse.json(
      { error: err.message || 'Failed to submit backtest' },
      { status: 500 }
    );
  }
}
