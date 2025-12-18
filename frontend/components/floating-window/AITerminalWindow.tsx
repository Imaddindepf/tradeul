'use client';

import { useEffect, useState, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';

const DILUTION_API = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'https://dilution.tradeul.com';

interface AITerminalWindowProps {
    ticker: string;
    companyName?: string;
    onComplete?: (success: boolean) => void;
}

/**
 * Parsea el output y convierte tablas markdown a HTML y formatea bullets
 */
function parseOutput(text: string): JSX.Element[] {
    const lines = text.split('\n');
    const elements: JSX.Element[] = [];
    let tableBuffer: string[] = [];
    let inTable = false;
    let key = 0;

    const flushTable = () => {
        if (tableBuffer.length > 0) {
            const headers = tableBuffer[0].split('|').filter(c => c.trim()).map(c => c.trim());
            const rows = tableBuffer.slice(2).filter(row => row.includes('|') && !row.match(/^[\s|:-]+$/));

            elements.push(
                <div key={key++} className="my-3 overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                        <thead>
                            <tr className="bg-slate-100">
                                {headers.map((h, i) => (
                                    <th key={i} className="px-3 py-2 text-left font-semibold text-slate-700 border-b border-slate-200 uppercase text-[10px] tracking-wide">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((row, ri) => {
                                const cells = row.split('|').filter(c => c.trim() !== '').map(c => c.trim());
                                return (
                                    <tr key={ri} className="border-b border-slate-100 hover:bg-slate-50">
                                        {cells.map((cell, ci) => (
                                            <td key={ci} className="px-3 py-2 text-slate-600">
                                                {cell}
                                            </td>
                                        ))}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            );
            tableBuffer = [];
        }
    };

    for (const line of lines) {
        // Detectar inicio de tabla
        if (line.trim().startsWith('|') && line.includes('|')) {
            inTable = true;
            tableBuffer.push(line);
            continue;
        }

        // Si estábamos en tabla pero ya no
        if (inTable && !line.trim().startsWith('|')) {
            flushTable();
            inTable = false;
        }

        // Líneas de separación (━━━)
        if (line.match(/^[━═─]+$/)) {
            elements.push(<hr key={key++} className="my-4 border-slate-200" />);
            continue;
        }

        // Headers con [BRACKETS]
        if (line.match(/^\[[\w\s\.\-&]+\]/)) {
            const match = line.match(/^\[([\w\s\.\-&]+)\](.*)/);
            if (match) {
                elements.push(
                    <div key={key++} className="mt-4 mb-2">
                        <span className="font-bold text-blue-600">[{match[1]}]</span>
                        <span className="text-slate-700">{match[2]}</span>
                    </div>
                );
                continue;
            }
        }

        // Bullets con ▸
        if (line.trim().startsWith('▸')) {
            const content = line.trim().slice(1).trim();
            // Detectar si tiene formato "Label: Value"
            const colonMatch = content.match(/^([^:]+):\s*(.+)$/);
            if (colonMatch) {
                // Detectar palabras clave importantes
                const isUrgent = /CRITICAL|URGENT|TOXIC|ALERT|ACTIVE|YES/i.test(colonMatch[2]);
                const isPositive = /STABLE|LOW|NONE|NO\b/i.test(colonMatch[2]) && !/NO\s+/i.test(colonMatch[2]);

                elements.push(
                    <div key={key++} className="flex items-start gap-2 my-1.5 ml-2">
                        <span className="text-slate-400 mt-0.5">▸</span>
                        <div>
                            <span className="font-medium text-slate-700">{colonMatch[1]}:</span>{' '}
                            <span className={`${isUrgent ? 'text-red-600 font-semibold' : isPositive ? 'text-emerald-600' : 'text-slate-600'}`}>
                                {colonMatch[2]}
                            </span>
                        </div>
                    </div>
                );
            } else {
                elements.push(
                    <div key={key++} className="flex items-start gap-2 my-1.5 ml-2">
                        <span className="text-slate-400 mt-0.5">▸</span>
                        <span className="text-slate-600">{content}</span>
                    </div>
                );
            }
            continue;
        }

        // Sub-bullets con └─
        if (line.trim().startsWith('└─')) {
            const content = line.trim().slice(2).trim();
            elements.push(
                <div key={key++} className="flex items-start gap-2 my-1 ml-6 text-slate-500">
                    <span className="text-slate-300">└─</span>
                    <span>{content}</span>
                </div>
            );
            continue;
        }

        // Texto en **bold**
        const boldMatches = [...line.matchAll(/\*\*([^*]+)\*\*/g)];
        if (boldMatches.length > 0) {
            const parts: (string | JSX.Element)[] = [];
            let lastIndex = 0;
            boldMatches.forEach((match, i) => {
                if (match.index! > lastIndex) {
                    parts.push(line.slice(lastIndex, match.index));
                }
                parts.push(<strong key={`b${i}`} className="font-semibold text-slate-800">{match[1]}</strong>);
                lastIndex = match.index! + match[0].length;
            });
            if (lastIndex < line.length) {
                parts.push(line.slice(lastIndex));
            }
            elements.push(
                <div key={key++} className="my-1 text-slate-600">
                    {parts}
                </div>
            );
            continue;
        }

        // Líneas vacías
        if (line.trim() === '') {
            elements.push(<div key={key++} className="h-2" />);
            continue;
        }

        // Texto normal
        elements.push(
            <div key={key++} className="my-0.5 text-slate-600">
                {line}
            </div>
        );
    }

    // Flush cualquier tabla pendiente
    flushTable();

    return elements;
}

/**
 * Terminal de análisis AI en ventana flotante independiente.
 * Tema SIEMPRE claro con tablas markdown parseadas.
 */
export function AITerminalWindow({
    ticker,
    companyName,
    onComplete,
}: AITerminalWindowProps) {
    const [output, setOutput] = useState<string>('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [isComplete, setIsComplete] = useState(false);
    const [isThinking, setIsThinking] = useState(false);
    const [thinkingTime, setThinkingTime] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const terminalRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);
    const startedRef = useRef(false);
    const receivedDataRef = useRef(false);

    // Parsear output a elementos JSX
    const parsedOutput = useMemo(() => parseOutput(output), [output]);

    // Auto-scroll
    useEffect(() => {
        if (terminalRef.current) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
        }
    }, [parsedOutput]);

    // Main streaming effect
    useEffect(() => {
        if (!ticker || startedRef.current) return;
        startedRef.current = true;

        const url = `${DILUTION_API}/api/sec-dilution/${ticker}/preliminary/stream${companyName ? `?company_name=${encodeURIComponent(companyName)}` : ''}`;
        console.log('[AITerminal] Starting stream:', url);

        const abortController = new AbortController();
        abortRef.current = abortController;

        setIsStreaming(true);
        setIsThinking(true);
        receivedDataRef.current = false;

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
            credentials: 'omit',
        })
            .then(async response => {
                console.log('[AITerminal] Response:', response.status);

                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const reader = response.body?.getReader();
                if (!reader) throw new Error('No reader');

                const decoder = new TextDecoder();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    sseBuffer += chunk;

                    const parts = sseBuffer.split('\n');
                    sseBuffer = parts.pop() || '';

                    for (const part of parts) {
                        if (part.startsWith('data: ')) {
                            const data = part.slice(6);

                            if (data.trim() === '[STREAM_END]') {
                                setIsComplete(true);
                                setIsStreaming(false);
                                setIsThinking(false);
                                clearInterval(thinkingInterval);
                                onComplete?.(true);
                                return;
                            }

                            if (data.startsWith('[ERROR]')) {
                                setError(data);
                                setIsStreaming(false);
                                setIsThinking(false);
                                clearInterval(thinkingInterval);
                                onComplete?.(false);
                                return;
                            }

                            if (!receivedDataRef.current && data.trim()) {
                                receivedDataRef.current = true;
                                setIsThinking(false);
                                clearInterval(thinkingInterval);
                            }

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
                setIsThinking(false);
                clearInterval(thinkingInterval);
                onComplete?.(true);
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                console.error('[AITerminal] Error:', err);
                setError(`Connection failed: ${err.message}`);
                setIsStreaming(false);
                setIsThinking(false);
                clearInterval(thinkingInterval);
                onComplete?.(false);
            });

        const timeout = setTimeout(() => {
            abortController.abort();
            setIsComplete(true);
            setIsStreaming(false);
            setIsThinking(false);
            clearInterval(thinkingInterval);
        }, 330000); // 5.5 min timeout

        return () => {
            clearTimeout(timeout);
            clearInterval(thinkingInterval);
            abortController.abort();
        };
    }, [ticker, companyName, onComplete]);

    return (
        <div className="flex flex-col h-full bg-white overflow-hidden">
            {/* Content Body - sin header interno, usa el del FloatingWindow */}
            <div
                ref={terminalRef}
                className="flex-1 p-4 overflow-y-auto overflow-x-hidden text-sm leading-relaxed bg-white"
            >
                {/* Thinking state */}
                {isThinking && (
                    <motion.div
                        animate={{ opacity: [0.5, 1, 0.5] }}
                        transition={{ duration: 2, repeat: Infinity }}
                        className="flex items-center gap-3 p-4 bg-blue-50 rounded-lg mb-4"
                    >
                        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                        <div>
                            <div className="font-medium text-blue-700">
                                Analyzing SEC filings for {ticker}...
                            </div>
                            <div className="text-xs text-blue-500 mt-1">
                                {thinkingTime}s elapsed {thinkingTime > 10 && '• Deep analysis in progress'}
                            </div>
                        </div>
                    </motion.div>
                )}

                {/* Parsed content */}
                <div className="space-y-0">
                    {parsedOutput}
                </div>

                {/* Streaming cursor */}
                {isStreaming && !isThinking && (
                    <motion.span
                        animate={{ opacity: [1, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                        className="inline-block w-2 h-4 bg-blue-500 ml-0.5"
                    />
                )}

                {error && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-xs">
                        {error}
                    </div>
                )}

                {isComplete && (
                    <div className="mt-4 pt-3 border-t border-slate-200 flex items-center gap-2 text-emerald-600 text-xs font-medium">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        Analysis complete
                    </div>
                )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 bg-slate-50 border-t border-slate-200 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${isThinking ? 'bg-blue-500 animate-pulse' : isStreaming ? 'bg-amber-500 animate-pulse' : isComplete ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                    <span className="text-[11px] text-slate-500">
                        {isThinking ? `Thinking (${thinkingTime}s)` : isStreaming ? 'Streaming' : isComplete ? 'Complete' : 'Ready'}
                    </span>
                </div>
                <span className="text-[10px] text-slate-400">Powered by Tradeul AI</span>
            </div>
        </div>
    );
}

export default AITerminalWindow;
