'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import python from 'react-syntax-highlighter/dist/esm/languages/hljs/python';
import javascript from 'react-syntax-highlighter/dist/esm/languages/hljs/javascript';
import bash from 'react-syntax-highlighter/dist/esm/languages/hljs/bash';

SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('bash', bash);

const HIGHLIGHT_LANG: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  curl: 'bash',
};

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
        # Receive ALL news (default — no subscribe needed)
        # To filter by tickers, send:
        # await ws.send(json.dumps({"action":"subscribe","tickers":["TSLA","NVDA"]}))

        async for message in ws:
            item = json.loads(message)
            if item["type"] == "news":
                print(f"[{item['created_at']}] {item['text']}")
                print(f"  Tickers: {item.get('tickers', [])}")
            elif item["type"] == "ping":
                pass  # keepalive, no response needed

asyncio.run(main())`,

  javascript: `import WebSocket from 'ws';

const ws = new WebSocket('${ENDPOINT}', {
  headers: { Authorization: 'Bearer <your-api-key>' }
});

ws.on('open', () => {
  // Receive ALL news — no subscribe message needed.
  // To filter by specific tickers:
  // ws.send(JSON.stringify({ action: 'subscribe', tickers: ['TSLA', 'NVDA'] }));
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

# Default: receives ALL news — no message needed.

# To filter by specific tickers only, send after connecting:
# {"action":"subscribe","tickers":["TSLA","NVDA"]}

# To reset and receive everything again:
# {"action":"subscribe","tickers":[]}`,
};

// Tema minimalista que encaja con el diseño dark de la app
const tradeulTheme: Record<string, React.CSSProperties> = {
  'hljs':                    { color: 'hsl(var(--foreground) / 0.75)', background: 'transparent' },
  'hljs-comment':            { color: 'hsl(var(--muted-foreground) / 0.4)', fontStyle: 'italic' },
  'hljs-keyword':            { color: '#7aa2f7' },
  'hljs-built_in':           { color: '#7dcfff' },
  'hljs-type':               { color: '#7dcfff' },
  'hljs-string':             { color: '#9ece6a' },
  'hljs-number':             { color: '#ff9e64' },
  'hljs-literal':            { color: '#ff9e64' },
  'hljs-title':              { color: '#e0af68' },
  'hljs-title.function_':    { color: '#e0af68' },
  'hljs-params':             { color: 'hsl(var(--foreground) / 0.75)' },
  'hljs-attr':               { color: '#73daca' },
  'hljs-variable':           { color: 'hsl(var(--foreground) / 0.75)' },
  'hljs-variable.language_': { color: '#7aa2f7' },
  'hljs-subst':              { color: 'hsl(var(--foreground) / 0.75)' },
  'hljs-punctuation':        { color: 'hsl(var(--muted-foreground) / 0.6)' },
  'hljs-operator':           { color: '#89ddff' },
  'hljs-meta':               { color: 'hsl(var(--muted-foreground) / 0.4)' },
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

        <div className="flex-1 overflow-y-auto rounded border border-border min-h-0 text-[10px] leading-relaxed [&>pre]:!m-0 [&>pre]:!rounded [&>pre]:!text-[10px] [&>pre]:!leading-relaxed [&>pre]:!h-full [&>pre]:!bg-transparent">
          <SyntaxHighlighter
            language={HIGHLIGHT_LANG[lang]}
            useInlineStyles={true}
            style={tradeulTheme}
            customStyle={{
              background: 'transparent',
              padding: '10px 12px',
              margin: 0,
              fontSize: '10px',
              lineHeight: '1.6',
              height: '100%',
              overflow: 'auto',
            }}
            codeTagProps={{ style: { fontFamily: 'var(--font-mono, ui-monospace, monospace)' } }}
          >
            {SNIPPETS[lang]}
          </SyntaxHighlighter>
        </div>
      </div>
    </div>
  );
}
