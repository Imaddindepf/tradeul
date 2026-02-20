'use client';

import { useState, useCallback, useRef } from 'react';
import type { BacktestResult, BacktestResponse } from '@/components/ai-agent/backtest/BacktestTypes';

const BACKTESTER_URL = process.env.NEXT_PUBLIC_BACKTESTER_URL || 'https://backtester.tradeul.com';
const TIMEOUT_MS = 300_000; // 5 min max for long backtests

export type BacktesterStatus = 'idle' | 'parsing' | 'running' | 'complete' | 'error';

interface UseBacktesterReturn {
  status: BacktesterStatus;
  result: BacktestResult | null;
  error: string | null;
  progressText: string;
  runBacktest: (naturalLanguagePrompt: string) => Promise<BacktestResult | null>;
  reset: () => void;
}

export function useBacktester(): UseBacktesterReturn {
  const [status, setStatus] = useState<BacktesterStatus>('idle');
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressText, setProgressText] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setStatus('idle');
    setResult(null);
    setError(null);
    setProgressText('');
  }, []);

  const runBacktest = useCallback(async (prompt: string): Promise<BacktestResult | null> => {
    reset();

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      setStatus('running');
      setProgressText('Ejecutando backtest...');

      const res = await fetch(`${BACKTESTER_URL}/api/v1/backtest/natural`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const body = await res.text().catch(() => '');
        throw new Error(`Error ${res.status}: ${body || res.statusText}`);
      }

      const data: BacktestResponse = await res.json();

      if (data.status === 'error' || !data.result) {
        throw new Error(data.error || 'Backtest failed without result');
      }

      setResult(data.result);
      setStatus('complete');
      setProgressText('');
      return data.result;
    } catch (err: any) {
      if (err.name === 'AbortError') return null;
      const msg = err.message || 'Error desconocido al ejecutar backtest';
      setError(msg);
      setStatus('error');
      setProgressText('');
      return null;
    }
  }, [reset]);

  return { status, result, error, progressText, runBacktest, reset };
}
