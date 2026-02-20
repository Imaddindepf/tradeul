'use client';

import { useEffect, useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { Terminal, Zap, XCircle } from 'lucide-react';

const DILUTION_API = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'https://dilution.tradeul.com';

interface PreliminaryTerminalProps {
  ticker: string;
  companyName?: string;
  onComplete?: (success: boolean) => void;
  onClose?: () => void;
  autoStart?: boolean;
}

export function PreliminaryTerminal({
  ticker,
  companyName,
  onComplete,
  onClose,
  autoStart = true,
}: PreliminaryTerminalProps) {
  // Usar un solo string para el output completo en vez de array de líneas
  const [output, setOutput] = useState<string>(`[INIT] Connecting to ${ticker}...\n`);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingTime, setThinkingTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef(false);
  const receivedDataRef = useRef(false);

  // Auto-scroll
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [output]);

  // Main streaming effect - runs once
  useEffect(() => {
    if (!autoStart || !ticker || startedRef.current) return;
    startedRef.current = true;

    const url = `${DILUTION_API}/api/sec-dilution/${ticker}/preliminary/stream${companyName ? `?company_name=${encodeURIComponent(companyName)}` : ''}`;

    const abortController = new AbortController();
    abortRef.current = abortController;

    setIsStreaming(true);
    setIsThinking(true);
    receivedDataRef.current = false;

    // Thinking timer - show elapsed time while waiting for first response
    const thinkingInterval = setInterval(() => {
      if (!receivedDataRef.current) {
        setThinkingTime(prev => prev + 1);
      }
    }, 1000);

    let sseBuffer = '';

    fetch(url, {
      signal: abortController.signal,
      headers: { 'Accept': 'text/event-stream' },
      cache: 'no-store',
      credentials: 'omit', // No credentials for CORS
    })
      .then(async response => {

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader');

        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          sseBuffer += chunk;

          // Process complete SSE lines
          const parts = sseBuffer.split('\n');
          sseBuffer = parts.pop() || '';

          for (const part of parts) {
            if (part.startsWith('data: ')) {
              const data = part.slice(6); // Don't trim - preserve formatting

              if (data.trim() === '[STREAM_END]') {
                setIsComplete(true);
                setIsStreaming(false);
                onComplete?.(true);
                return;
              }

              if (data.startsWith('[ERROR]')) {
                setError(data);
                setIsStreaming(false);
                onComplete?.(false);
                return;
              }

              // First real data received - stop thinking indicator
              if (!receivedDataRef.current && data.trim()) {
                receivedDataRef.current = true;
                setIsThinking(false);
                clearInterval(thinkingInterval);
              }

              // Append text to output
              // Empty data = newline from the original content
              if (data === '') {
                setOutput(prev => prev + '\n');
              } else {
                setOutput(prev => prev + data);
              }
            }
          }
        }

        setIsComplete(true);
        setIsStreaming(false);
        onComplete?.(true);
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('[Terminal] Error:', err);
        setError(`Connection failed: ${err.message}`);
        setIsStreaming(false);
        onComplete?.(false);
      });

    // Timeout - extended to 180s for deep analysis
    const timeout = setTimeout(() => {
      abortController.abort();
      setIsComplete(true);
      setIsStreaming(false);
      setIsThinking(false);
      clearInterval(thinkingInterval);
    }, 180000);

    return () => {
      clearTimeout(timeout);
      clearInterval(thinkingInterval);
      abortController.abort();
    };
  }, [ticker, companyName, autoStart, onComplete]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      className="w-full bg-slate-900 rounded-lg overflow-hidden border border-slate-700 shadow-lg"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-green-400" />
          <span className="text-[11px] text-green-400 font-medium" style={{ fontFamily: 'var(--font-mono-selected)' }}>
            AI Analysis • {ticker}
          </span>
          {isStreaming && (
            <motion.div
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              className="flex items-center gap-1"
            >
              <Zap className="w-3 h-3 text-amber-400" />
              <span className="text-[10px] text-amber-400 font-medium">LIVE</span>
            </motion.div>
          )}
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 hover:bg-slate-700 rounded transition-colors">
            <XCircle className="w-3.5 h-3.5 text-slate-400 hover:text-slate-300" />
          </button>
        )}
      </div>

      {/* Terminal Body */}
      <div
        ref={terminalRef}
        className="p-3 h-[350px] overflow-y-auto overflow-x-hidden text-[11px] leading-relaxed bg-slate-900"
        style={{ fontFamily: 'var(--font-mono-selected)' }}
      >
        <pre className="whitespace-pre-wrap break-words text-green-400 m-0">
          {output}
          {isThinking && (
            <motion.span
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 2, repeat: Infinity }}
              className="text-cyan-400"
            >
              {'\n'}[THINKING] Tradeul AI analyzing SEC filings... ({thinkingTime}s)
              {thinkingTime > 10 && '\n[INFO] Deep analysis in progress - this may take 30-60 seconds'}
            </motion.span>
          )}
          {isStreaming && !isThinking && (
            <motion.span
              animate={{ opacity: [1, 0] }}
              transition={{ duration: 0.8, repeat: Infinity }}
              className="inline-block w-1.5 h-4 bg-green-500 ml-0.5"
            />
          )}
        </pre>

        {error && <div className="mt-2 text-red-400 text-[10px]">{error}</div>}

        {isComplete && (
          <div className="mt-3 pt-2 border-t border-slate-700 text-emerald-400 text-[10px]">
            ✓ Analysis complete
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 bg-slate-800 border-t border-slate-700 flex items-center justify-between">
        <span className={`text-[9px] ${isThinking ? 'text-cyan-400' : isStreaming ? 'text-amber-400' : isComplete ? 'text-emerald-400' : 'text-slate-500'}`}>
          ● {isThinking ? `Thinking (${thinkingTime}s)` : isStreaming ? 'Streaming' : isComplete ? 'Complete' : 'Ready'}
        </span>
        <span className="text-[9px] text-slate-500">Powered by Tradeul AI</span>
      </div>
    </motion.div>
  );
}

export default PreliminaryTerminal;
