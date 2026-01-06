'use client';

import { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';

const DILUTION_API = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'https://dilution.tradeul.com';

interface AITerminalWindowProps {
    ticker: string;
    companyName?: string;
    onComplete?: (success: boolean) => void;
}

// ============================================
// PARTICLE DOCUMENT ANIMATION COMPONENT
// ============================================
interface Particle {
    x: number;
    y: number;
    baseX: number;
    baseY: number;
    size: number;
    color: string;
    alpha: number;
    velocity: { x: number; y: number };
    type: 'document' | 'spark' | 'scan';
    life?: number;
    maxLife?: number;
}

function SECDocumentAnimation({ ticker, thinkingTime }: { ticker: string; thinkingTime: number }) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const particlesRef = useRef<Particle[]>([]);
    const frameRef = useRef<number>(0);
    const scanLineRef = useRef<number>(0);

    const initParticles = useCallback((width: number, height: number) => {
        const particles: Particle[] = [];
        const centerX = width / 2;
        const centerY = height / 2;
        
        // Document dimensions
        const docWidth = Math.min(140, width * 0.35);
        const docHeight = docWidth * 1.35;
        const docLeft = centerX - docWidth / 2;
        const docTop = centerY - docHeight / 2;
        const spacing = 5;

        // Document border (dotted rectangle)
        // Top border
        for (let x = docLeft; x <= docLeft + docWidth; x += spacing) {
            particles.push({
                x: x, y: docTop, baseX: x, baseY: docTop,
                size: 2, color: '#3b82f6', alpha: 0.8,
                velocity: { x: 0, y: 0 }, type: 'document'
            });
        }
        // Bottom border
        for (let x = docLeft; x <= docLeft + docWidth; x += spacing) {
            particles.push({
                x: x, y: docTop + docHeight, baseX: x, baseY: docTop + docHeight,
                size: 2, color: '#3b82f6', alpha: 0.8,
                velocity: { x: 0, y: 0 }, type: 'document'
            });
        }
        // Left border
        for (let y = docTop; y <= docTop + docHeight; y += spacing) {
            particles.push({
                x: docLeft, y: y, baseX: docLeft, baseY: y,
                size: 2, color: '#3b82f6', alpha: 0.8,
                velocity: { x: 0, y: 0 }, type: 'document'
            });
        }
        // Right border
        for (let y = docTop; y <= docTop + docHeight; y += spacing) {
            particles.push({
                x: docLeft + docWidth, y: y, baseX: docLeft + docWidth, baseY: y,
                size: 2, color: '#3b82f6', alpha: 0.8,
                velocity: { x: 0, y: 0 }, type: 'document'
            });
        }

        // "SEC" text in dots at top of document
        const secText = [
            // S
            [0,0],[1,0],[2,0],[0,1],[0,2],[1,2],[2,2],[2,3],[0,4],[1,4],[2,4],
            // E
            [4,0],[5,0],[6,0],[4,1],[4,2],[5,2],[4,3],[4,4],[5,4],[6,4],
            // C
            [8,0],[9,0],[10,0],[8,1],[8,2],[8,3],[8,4],[9,4],[10,4]
        ];
        const secScale = 4;
        const secStartX = centerX - (11 * secScale) / 2;
        const secStartY = docTop + 15;
        secText.forEach(([px, py]) => {
            particles.push({
                x: secStartX + px * secScale, 
                y: secStartY + py * secScale,
                baseX: secStartX + px * secScale, 
                baseY: secStartY + py * secScale,
                size: 2.5, color: '#60a5fa', alpha: 1,
                velocity: { x: 0, y: 0 }, type: 'document'
            });
        });

        // Document content lines (dotted)
        const lineY = secStartY + 35;
        const lineSpacing = 12;
        const lineLengths = [0.85, 0.7, 0.9, 0.6, 0.75, 0.8];
        for (let i = 0; i < lineLengths.length; i++) {
            const y = lineY + i * lineSpacing;
            const lineWidth = (docWidth - 20) * lineLengths[i];
            for (let x = docLeft + 10; x < docLeft + 10 + lineWidth; x += 4) {
                particles.push({
                    x: x, y: y, baseX: x, baseY: y,
                    size: 1.5, color: '#3b82f6', alpha: 0.5,
                    velocity: { x: 0, y: 0 }, type: 'document'
                });
            }
        }

        return particles;
    }, []);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const resize = () => {
            const rect = canvas.parentElement?.getBoundingClientRect();
            if (rect) {
                canvas.width = rect.width;
                canvas.height = rect.height;
                particlesRef.current = initParticles(canvas.width, canvas.height);
            }
        };

        resize();
        window.addEventListener('resize', resize);

        let animationId: number;

        const animate = () => {
            if (!ctx || !canvas) return;
            
            ctx.fillStyle = '#0a0a0f';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            const time = Date.now() / 1000;
            scanLineRef.current = (scanLineRef.current + 1.5) % (canvas.height + 100);

            // Draw document particles with wave effect
            particlesRef.current.forEach((p, i) => {
                if (p.type === 'document') {
                    const wave = Math.sin(time * 2 + i * 0.05) * 1.5;
                    const breathe = Math.sin(time * 1.5) * 0.5;
                    
                    ctx.beginPath();
                    ctx.arc(p.baseX + wave, p.baseY + breathe, p.size, 0, Math.PI * 2);
                    ctx.fillStyle = p.color;
                    ctx.globalAlpha = p.alpha * (0.7 + Math.sin(time * 3 + i * 0.1) * 0.3);
                    ctx.fill();
                }
            });

            // Scan line effect
            const scanY = scanLineRef.current - 50;
            const gradient = ctx.createLinearGradient(0, scanY - 30, 0, scanY + 30);
            gradient.addColorStop(0, 'rgba(251, 191, 36, 0)');
            gradient.addColorStop(0.5, 'rgba(251, 191, 36, 0.15)');
            gradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
            ctx.fillStyle = gradient;
            ctx.globalAlpha = 1;
            ctx.fillRect(0, scanY - 30, canvas.width, 60);

            // Golden spark particles
            const sparksCount = 12;
            for (let i = 0; i < sparksCount; i++) {
                const sparkTime = time * 0.8 + i * (Math.PI * 2 / sparksCount);
                const radius = 80 + Math.sin(time * 2 + i) * 20;
                const sparkX = canvas.width / 2 + Math.cos(sparkTime) * radius;
                const sparkY = canvas.height / 2 + Math.sin(sparkTime * 1.5) * radius * 0.6;
                
                const sparkSize = 3 + Math.sin(time * 4 + i) * 1.5;
                const sparkAlpha = 0.6 + Math.sin(time * 3 + i * 0.5) * 0.4;
                
                // Glow
                const glowGradient = ctx.createRadialGradient(sparkX, sparkY, 0, sparkX, sparkY, sparkSize * 4);
                glowGradient.addColorStop(0, `rgba(251, 191, 36, ${sparkAlpha * 0.5})`);
                glowGradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
                ctx.fillStyle = glowGradient;
                ctx.globalAlpha = 1;
                ctx.fillRect(sparkX - sparkSize * 4, sparkY - sparkSize * 4, sparkSize * 8, sparkSize * 8);
                
                // Core
                ctx.beginPath();
                ctx.arc(sparkX, sparkY, sparkSize, 0, Math.PI * 2);
                ctx.fillStyle = '#fbbf24';
                ctx.globalAlpha = sparkAlpha;
                ctx.fill();
            }

            // Flying sparks (random directions)
            for (let i = 0; i < 6; i++) {
                const flyTime = (time * 1.2 + i * 1.5) % 3;
                const startX = canvas.width / 2 + (i % 2 === 0 ? 60 : -60);
                const startY = canvas.height / 2;
                const angle = (i / 6) * Math.PI * 2 + time * 0.3;
                const distance = flyTime * 50;
                
                const fx = startX + Math.cos(angle) * distance;
                const fy = startY + Math.sin(angle) * distance;
                const fAlpha = Math.max(0, 1 - flyTime / 2);
                
                ctx.beginPath();
                ctx.arc(fx, fy, 2, 0, Math.PI * 2);
                ctx.fillStyle = '#f59e0b';
                ctx.globalAlpha = fAlpha;
                ctx.fill();
            }

            ctx.globalAlpha = 1;
            frameRef.current++;
            animationId = requestAnimationFrame(animate);
        };

        animate();

        return () => {
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(animationId);
        };
    }, [initParticles]);

    return (
        <div className="relative w-full h-64 rounded-lg overflow-hidden bg-[#0a0a0f]">
            <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
            
            {/* Ticker label */}
            <div className="absolute top-3 left-3 font-mono text-xs tracking-widest text-amber-400/80 uppercase">
                {ticker}
            </div>
            
            {/* Status text */}
            <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#0a0a0f] to-transparent">
                <div className="text-center">
                    <p className="text-blue-400 text-sm font-medium">
                        Analyzing SEC Filings
                    </p>
                    <p className="text-slate-500 text-xs mt-1 font-mono">
                        {thinkingTime}s • Deep analysis in progress
                    </p>
                </div>
            </div>
        </div>
    );
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
                {/* Thinking state - Beautiful particle animation */}
                {isThinking && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.5 }}
                        className="mb-4"
                    >
                        <SECDocumentAnimation ticker={ticker} thinkingTime={thinkingTime} />
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
