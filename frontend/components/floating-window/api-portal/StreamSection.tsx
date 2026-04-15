'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

type Lang = 'python' | 'javascript' | 'curl';

const ENDPOINT = 'wss://tradeul.com/stream';

const SNIPPETS: Record<Lang, string> = {
  python: `import asyncio
import websockets
import json

async def main():
    headers = {"Authorization": "Bearer <your-api-key>"}
    url = "${ENDPOINT}"

    async with websockets.connect(url, extra_headers=headers) as ws:
        # Optional: subscribe to specific tickers only
        await ws.send(json.dumps({
            "action": "subscribe",
            "tickers": ["TSLA", "NVDA"]
        }))

        async for message in ws:
            item = json.loads(message)
            if item["type"] == "news":
                print(f"[{item['created_at']}] {item['text']}")
                print(f"  Tickers: {item.get('tickers', [])}")

asyncio.run(main())`,

  javascript: `import WebSocket from 'ws';

const ws = new WebSocket('${ENDPOINT}', {
  headers: { Authorization: 'Bearer <your-api-key>' }
});

ws.on('open', () => {
  // Optional: subscribe to specific tickers only
  ws.send(JSON.stringify({
    action: 'subscribe',
    tickers: ['TSLA', 'NVDA']
  }));
});

ws.on('message', (data) => {
  const item = JSON.parse(data);
  if (item.type === 'news') {
    console.log(\`[\${item.created_at}] \${item.text}\`);
    console.log('Tickers:', item.tickers);
  }
});

ws.on('error', console.error);`,

  curl: `# WebSocket via wscat (npm install -g wscat)
wscat \\
  --connect "${ENDPOINT}" \\
  --header "Authorization: Bearer <your-api-key>"

# Once connected, send a subscription filter:
# {"action":"subscribe","tickers":["TSLA","NVDA"]}

# To receive all news (no filter), skip the subscribe message.`,
};

export function StreamSection() {
  const [lang, setLang] = useState<Lang>('python');
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(false);

  const copyEndpoint = async () => {
    await navigator.clipboard.writeText(ENDPOINT);
    setCopiedEndpoint(true);
    setTimeout(() => setCopiedEndpoint(false), 2000);
  };

  const copySnippet = async () => {
    await navigator.clipboard.writeText(SNIPPETS[lang]);
    setCopiedSnippet(true);
    setTimeout(() => setCopiedSnippet(false), 2000);
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">

      {/* Endpoint */}
      <div className="border-b border-border px-2 py-2 flex-shrink-0">
        <div className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 mb-1.5">
          Websocket Endpoint
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 text-[10px] font-mono text-foreground">{ENDPOINT}</code>
          <button
            onClick={copyEndpoint}
            className="px-2 py-1 text-[9px] font-medium border border-border rounded text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          >
            {copiedEndpoint ? 'COPIED' : 'COPY'}
          </button>
        </div>
        <div className="mt-1 text-[9px] text-muted-foreground/40 font-mono">
          Authorization: Bearer {'<your-api-key>'}
        </div>
      </div>

      {/* Message schema */}
      <div className="border-b border-border px-2 py-2 flex-shrink-0">
        <div className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 mb-1.5">
          Message Format
        </div>
        <div className="space-y-1">
          {[
            { type: 'connected', desc: 'Sent once on connect. Contains key_id and rate_limit.' },
            { type: 'news',      desc: 'Breaking news item. Fields: id, text, tickers[], created_at.' },
            { type: 'subscribed',desc: 'Confirms your ticker filter. Send { action: subscribe, tickers: [] } for all.' },
            { type: 'ping',      desc: 'Keepalive every 30s. No response needed.' },
          ].map(row => (
            <div key={row.type} className="flex gap-2">
              <span className="text-[10px] font-mono text-foreground w-24 flex-shrink-0">{row.type}</span>
              <span className="text-[10px] text-muted-foreground">{row.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Code examples */}
      <div className="flex-1 flex flex-col px-2 py-2 min-h-0">
        <div className="flex items-center gap-0 mb-2 flex-shrink-0">
          <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 mr-3">
            Code Examples
          </span>
          {(['python', 'javascript', 'curl'] as Lang[]).map(l => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={cn(
                'px-2 py-[3px] text-[9px] font-medium border-b border-transparent transition-colors -mb-px mr-1',
                lang === l
                  ? 'text-foreground border-foreground/50'
                  : 'text-muted-foreground/50 hover:text-muted-foreground',
              )}
            >
              {l.toUpperCase()}
            </button>
          ))}
          <button
            onClick={copySnippet}
            className="ml-auto px-2 py-[3px] text-[9px] font-medium border border-border rounded text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          >
            {copiedSnippet ? 'COPIED' : 'COPY'}
          </button>
        </div>

        <pre className="flex-1 overflow-y-auto bg-muted/20 rounded border border-border px-3 py-2 text-[10px] font-mono text-foreground/80 whitespace-pre leading-relaxed min-h-0">
          {SNIPPETS[lang]}
        </pre>
      </div>
    </div>
  );
}
