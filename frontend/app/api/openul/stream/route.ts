import { NextRequest } from 'next/server';

const OPENUL_URL = process.env.OPENUL_URL || 'http://localhost:8070';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: NextRequest) {
  const abortController = new AbortController();

  request.signal.addEventListener('abort', () => {
    abortController.abort();
  });

  // Native EventSource sends Last-Event-ID on auto-reconnect after the
  // server emits `id:` lines. Forward it (and accept the query-param
  // fallback for any client that cannot set the header) so the upstream
  // can replay missed events.
  const lastEventIdHeader = request.headers.get('last-event-id');
  const lastEventIdQuery = new URL(request.url).searchParams.get('last_event_id');
  const lastEventId = lastEventIdHeader || lastEventIdQuery;

  const upstreamUrl = new URL(`${OPENUL_URL}/api/v1/stream`);
  if (lastEventIdQuery && !lastEventIdHeader) {
    upstreamUrl.searchParams.set('last_event_id', lastEventIdQuery);
  }

  try {
    const upstream = await fetch(upstreamUrl, {
      headers: {
        Accept: 'text/event-stream',
        ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
      },
      signal: abortController.signal,
      cache: 'no-store',
    });

    if (!upstream.ok || !upstream.body) {
      return new Response(JSON.stringify({ error: 'Upstream unavailable' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const reader = upstream.body.getReader();
    const stream = new ReadableStream({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            controller.enqueue(value);
          }
          controller.close();
        } catch {
          try { controller.close(); } catch { /* already closed */ }
        }
      },
      cancel() {
        reader.cancel();
        abortController.abort();
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return new Response(null, { status: 499 });
    }
    return new Response(JSON.stringify({ error: err.message || 'SSE proxy error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
