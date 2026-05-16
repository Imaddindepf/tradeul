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

const ENDPOINT = 'wss://stream.tradeul.com/stream';

const SNIPPETS: Record<Lang, string> = {
  python: `import asyncio, json, websockets
from websockets.exceptions import ConnectionClosed

URL    = "wss://tradeul.com/stream"
APIKEY = "<your-api-key>"
TICKERS = []  # [] = all news  |  ["TSLA","NVDA"] = filtered

async def connect():
    headers = {"Authorization": f"Bearer {APIKEY}"}
    backoff = 1  # seconds, doubles on each retry (max 60s)

    while True:
        try:
            async with websockets.connect(URL, additional_headers=headers) as ws:
                backoff = 1  # reset on successful connection
                async for raw in ws:
                    msg = json.loads(raw)

                    if msg["type"] == "connected":
                        print(f"Connected  key={msg['key_id']}")
                        await ws.send(json.dumps({
                            "action": "subscribe", "tickers": TICKERS
                        }))

                    elif msg["type"] == "subscribed":
                        print(f"Subscribed tickers={msg['tickers']}")

                    elif msg["type"] == "ping":
                        await ws.send(json.dumps({"action": "pong"}))

                    elif msg["type"] == "news":
                        print(f"[{msg['created_at']}] {msg['text']}")
                        print(f"  Tickers: {msg.get('tickers', [])}")

        except (ConnectionClosed, OSError) as e:
            print(f"Disconnected ({e}). Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

asyncio.run(connect())`,

  javascript: `import WebSocket from 'ws';

const URL    = 'wss://tradeul.com/stream';
const APIKEY = '<your-api-key>';
const TICKERS = [];  // [] = all news  |  ['TSLA','NVDA'] = filtered

let backoff = 1000; // ms, doubles on each retry (max 60s)

function connect() {
  const ws = new WebSocket(URL, {
    headers: { Authorization: \`Bearer \${APIKEY}\` }
  });

  ws.on('open', () => {
    backoff = 1000; // reset on successful connection
  });

  ws.on('message', (data) => {
    const msg = JSON.parse(data);

    if (msg.type === 'connected') {
      console.log('Connected  key=' + msg.key_id);
      ws.send(JSON.stringify({ action: 'subscribe', tickers: TICKERS }));

    } else if (msg.type === 'subscribed') {
      console.log('Subscribed tickers=' + msg.tickers);

    } else if (msg.type === 'ping') {
      ws.send(JSON.stringify({ action: 'pong' }));

    } else if (msg.type === 'news') {
      console.log(\`[\${msg.created_at}] \${msg.text}\`);
      console.log('Tickers:', msg.tickers);
    }
  });

  ws.on('close', (code, reason) => {
    console.log(\`Disconnected (\${code}). Reconnecting in \${backoff / 1000}s...\`);
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, 60_000);
  });

  ws.on('error', () => ws.terminate());
}

connect();`,

  curl: `# Interactive test via wscat (npm install -g wscat)
wscat \\
  --connect "${ENDPOINT}" \\
  --header "Authorization: Bearer <your-api-key>"

# After connecting, subscribe to all news:
# > {"action":"subscribe","tickers":[]}

# Filter by specific tickers:
# > {"action":"subscribe","tickers":["TSLA","NVDA"]}

# Respond to server pings (keeps connection alive):
# > {"action":"pong"}`,
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

type TestState = 'idle' | 'testing' | 'ok' | 'error';

const FEED_STATUS_URL = 'https://stream.tradeul.com/feed-status';

export function StreamSection() {
  const [lang, setLang] = useState<Lang>('python');
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [testState, setTestState] = useState<TestState>('idle');
  const [testResult, setTestResult] = useState<string | null>(null);

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

  const testConnection = async () => {
    if (testState === 'testing') return;
    setTestState('testing');
    setTestResult(null);

    try {
      const res = await fetch(FEED_STATUS_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const ago = data.last_news_ago_seconds as number | null;
      const agoText = ago == null
        ? 'no news since service start'
        : ago < 60
          ? `last news ${ago}s ago`
          : ago < 3600
            ? `last news ${Math.round(ago / 60)}m ago`
            : `last news ${Math.round(ago / 3600)}h ago`;

      if (data.feed === 'live') {
        setTestState('ok');
        setTestResult(`Stream live — ${agoText}`);
      } else {
        setTestState('error');
        setTestResult(`Feed degraded — ${data.feed}`);
      }
    } catch {
      setTestState('error');
      setTestResult('Could not reach stream endpoint.');
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">

      {/* Endpoint + Test */}
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

        {/* Test Connection */}
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={testConnection}
            disabled={testState === 'testing'}
            className={cn(
              'px-2 py-1 text-[9px] font-medium border rounded transition-colors flex-shrink-0',
              testState === 'testing'
                ? 'border-border text-muted-foreground/40 cursor-wait'
                : 'border-border text-muted-foreground hover:text-foreground'
            )}
          >
            {testState === 'testing' ? 'TESTING...' : 'TEST CONNECTION'}
          </button>
          {testResult && (
            <span className={cn(
              'text-[9px] font-mono',
              testState === 'ok' ? 'text-emerald-500' : 'text-red-400'
            )}>
              {testState === 'ok' ? '● ' : '✕ '}{testResult}
            </span>
          )}
        </div>
      </div>

      {/* Message schema */}
      <div className="border-b border-border px-2 py-2 flex-shrink-0">
        <div className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 mb-1.5">
          Message Format
        </div>
        <div className="space-y-1">
          {[
            { type: 'connected', desc: 'Sent once on connect. Contains key_id and timestamp.' },
            { type: 'news',      desc: 'Breaking news. Fields: id, text, tickers[], created_at, media? (image url), urls? (links).' },
            { type: 'reaction',  desc: 'Price reaction after a headline. Adds: direction, change_pct, price, ref_price, delay_seconds.' },
            { type: 'subscribed',desc: 'Confirms your ticker filter. Send { action: subscribe, tickers: [] } for all.' },
            { type: 'status',    desc: 'Feed health check. Send { action: "status" } anytime to verify the stream is live.' },
            { type: 'ping',      desc: 'Keepalive every 30s from server.' },
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
