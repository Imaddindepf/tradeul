import { NextRequest, NextResponse } from 'next/server';

// Servicio ai-news-brief (Claude Opus 4.8), publicado en localhost:8072.
const BRIEF_URL = process.env.OPENUL_BRIEF_URL || 'http://localhost:8072';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const text = (body?.text || '').toString().trim();
    if (!text) {
      return NextResponse.json({ error: 'text is required' }, { status: 400 });
    }

    const res = await fetch(`${BRIEF_URL}/api/v1/brief`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        text,
        tickers: Array.isArray(body?.tickers) ? body.tickers : [],
        created_at: body?.created_at ?? null,
        received_at: body?.received_at ?? null,
        id: body?.id ?? null,
      }),
      // El brief con Opus 4.8 + web search + thinking puede tardar ~60s.
      signal: AbortSignal.timeout(150_000),
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
    const isTimeout = err?.name === 'TimeoutError' || /timeout/i.test(err?.message || '');
    return NextResponse.json(
      { error: isTimeout ? 'El análisis tardó demasiado. Inténtalo de nuevo.' : (err.message || 'Failed to generate brief') },
      { status: isTimeout ? 504 : 500 },
    );
  }
}
