import { NextRequest, NextResponse } from 'next/server';

const BACKTESTER_URL = process.env.BACKTESTER_URL || 'http://localhost:8060';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const res = await fetch(`${BACKTESTER_URL}/api/v1/backtest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(300_000),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }

    return NextResponse.json(data);
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return NextResponse.json({ error: 'Backtest timeout (5 min)' }, { status: 504 });
    }
    return NextResponse.json(
      { error: err.message || 'Failed to run backtest' },
      { status: 500 }
    );
  }
}
