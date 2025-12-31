/**
 * Pattern Real-Time WebSocket Hook
 * ================================
 * 
 * Manages WebSocket connection for real-time pattern scanning updates.
 * Handles subscriptions, reconnections, and message parsing.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// ============================================================================
// Types
// ============================================================================

export interface PredictionResult {
    id: string;
    job_id: string;
    symbol: string;
    scan_time: string;
    horizon: number;
    prob_up: number;
    prob_down: number;
    mean_return: number;
    edge: number;
    direction: 'UP' | 'DOWN';
    n_neighbors: number;
    dist1: number | null;
    p10: number | null;
    p90: number | null;
    price_at_scan: number;
    price_at_horizon: number | null;
    actual_return: number | null;
    was_correct: boolean | null;
    pnl: number | null;
    verified_at: string | null;
}

export interface VerificationUpdate {
    prediction_id: string;
    symbol: string;
    actual_return: number;
    was_correct: boolean;
    pnl: number;
}

export interface PriceUpdate {
    prediction_id: string;
    job_id: string;
    symbol: string;
    current_price: number;
    price_at_scan: number;
    unrealized_return: number;
    unrealized_pnl: number;
    direction: 'UP' | 'DOWN';
    is_currently_correct: boolean;
    minutes_remaining: number;
    timestamp: string;
}

export interface WSMessage {
    type: 'subscribed' | 'progress' | 'result' | 'verification' | 'job_complete' | 'error' | 'pong' | 'price_update';
    job_id?: string;
    data?: PredictionResult;
    prediction?: PredictionResult;
    price_update?: PriceUpdate;
    completed?: number;
    total?: number;
    results?: PredictionResult[];
    total_results?: number;
    total_failures?: number;
    error?: string;
}

export interface JobProgress {
    completed: number;
    total: number;
    failed: number;
}

interface UsePatternRealtimeWSOptions {
    onResult?: (prediction: PredictionResult) => void;
    onVerification?: (update: VerificationUpdate) => void;
    onPriceUpdate?: (update: PriceUpdate) => void;
    onJobComplete?: (jobId: string, results: PredictionResult[]) => void;
    onProgress?: (jobId: string, progress: JobProgress) => void;
    onError?: (error: string) => void;
}

interface UsePatternRealtimeWSReturn {
    isConnected: boolean;
    isConnecting: boolean;
    subscribe: (jobId: string) => void;
    unsubscribe: (jobId: string) => void;
    reconnect: () => void;
    subscribedJobs: string[];
}

// ============================================================================
// Hook
// ============================================================================

const WS_URL = process.env.NEXT_PUBLIC_PATTERN_WS_URL || 'wss://api.tradeul.com/patterns/ws/pattern-realtime';

export function usePatternRealtimeWS(options: UsePatternRealtimeWSOptions = {}): UsePatternRealtimeWSReturn {
    const { onResult, onVerification, onPriceUpdate, onJobComplete, onProgress, onError } = options;
    
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);
    const [subscribedJobs, setSubscribedJobs] = useState<string[]>([]);
    
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const reconnectAttempts = useRef(0);
    const maxReconnectAttempts = 5;
    
    // Callbacks refs to avoid stale closures
    const onResultRef = useRef(onResult);
    const onVerificationRef = useRef(onVerification);
    const onPriceUpdateRef = useRef(onPriceUpdate);
    const onJobCompleteRef = useRef(onJobComplete);
    const onProgressRef = useRef(onProgress);
    const onErrorRef = useRef(onError);
    
    useEffect(() => {
        onResultRef.current = onResult;
        onVerificationRef.current = onVerification;
        onPriceUpdateRef.current = onPriceUpdate;
        onJobCompleteRef.current = onJobComplete;
        onProgressRef.current = onProgress;
        onErrorRef.current = onError;
    }, [onResult, onVerification, onPriceUpdate, onJobComplete, onProgress, onError]);
    
    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;
        if (isConnecting) return;
        
        setIsConnecting(true);
        
        try {
            const ws = new WebSocket(WS_URL);
            wsRef.current = ws;
            
            ws.onopen = () => {
                setIsConnected(true);
                setIsConnecting(false);
                reconnectAttempts.current = 0;
                
                // Start ping interval
                pingIntervalRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: 'ping' }));
                    }
                }, 30000);
                
                // Re-subscribe to previous jobs
                subscribedJobs.forEach(jobId => {
                    ws.send(JSON.stringify({ type: 'subscribe', job_id: jobId }));
                });
            };
            
            ws.onmessage = (event) => {
                try {
                    const msg: WSMessage = JSON.parse(event.data);
                    
                    switch (msg.type) {
                        case 'result':
                            if (msg.data || msg.prediction) {
                                onResultRef.current?.(msg.data || msg.prediction!);
                            }
                            break;
                            
                        case 'verification':
                            if (msg.data) {
                                onVerificationRef.current?.({
                                    prediction_id: msg.data.id,
                                    symbol: msg.data.symbol,
                                    actual_return: msg.data.actual_return!,
                                    was_correct: msg.data.was_correct!,
                                    pnl: msg.data.pnl!,
                                });
                            }
                            break;
                        
                        case 'price_update':
                            if (msg.price_update) {
                                onPriceUpdateRef.current?.(msg.price_update);
                            }
                            break;
                            
                        case 'job_complete':
                            if (msg.job_id) {
                                onJobCompleteRef.current?.(msg.job_id, msg.results || []);
                            }
                            break;
                            
                        case 'progress':
                            if (msg.job_id && msg.completed !== undefined && msg.total !== undefined) {
                                onProgressRef.current?.(msg.job_id, {
                                    completed: msg.completed,
                                    total: msg.total,
                                    failed: 0,
                                });
                            }
                            break;
                            
                        case 'error':
                            onErrorRef.current?.(msg.error || 'Unknown WebSocket error');
                            break;
                            
                        case 'pong':
                        case 'subscribed':
                            // Ignore these
                            break;
                    }
                } catch (e) {
                    console.error('[PatternRealtimeWS] Failed to parse message:', e);
                }
            };
            
            ws.onclose = () => {
                setIsConnected(false);
                setIsConnecting(false);
                
                if (pingIntervalRef.current) {
                    clearInterval(pingIntervalRef.current);
                }
                
                // Auto-reconnect with backoff
                if (reconnectAttempts.current < maxReconnectAttempts) {
                    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
                    reconnectTimeoutRef.current = setTimeout(() => {
                        reconnectAttempts.current++;
                        connect();
                    }, delay);
                }
            };
            
            ws.onerror = (error) => {
                console.error('[PatternRealtimeWS] WebSocket error:', error);
                onErrorRef.current?.('WebSocket connection error');
            };
            
        } catch (error) {
            setIsConnecting(false);
            console.error('[PatternRealtimeWS] Failed to connect:', error);
        }
    }, [isConnecting, subscribedJobs]);
    
    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
        }
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
        setIsConnecting(false);
    }, []);
    
    const subscribe = useCallback((jobId: string) => {
        if (!subscribedJobs.includes(jobId)) {
            setSubscribedJobs(prev => [...prev, jobId]);
        }
        
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'subscribe', job_id: jobId }));
        }
    }, [subscribedJobs]);
    
    const unsubscribe = useCallback((jobId: string) => {
        setSubscribedJobs(prev => prev.filter(id => id !== jobId));
        
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'unsubscribe', job_id: jobId }));
        }
    }, []);
    
    const reconnect = useCallback(() => {
        reconnectAttempts.current = 0;
        disconnect();
        connect();
    }, [disconnect, connect]);
    
    // Connect on mount
    useEffect(() => {
        connect();
        return () => disconnect();
    }, []);
    
    return {
        isConnected,
        isConnecting,
        subscribe,
        unsubscribe,
        reconnect,
        subscribedJobs,
    };
}

