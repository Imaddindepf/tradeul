'use client';

import { useState, useCallback, useRef } from 'react';
import type { BacktestResult, BacktestResponse } from '@/components/ai-agent/backtest/BacktestTypes';

/** Use same-origin API proxy to avoid CORS and expose only one origin in production */
function getApiBase(): string {
  if (typeof window !== 'undefined') return '';
  return process.env.NEXT_PUBLIC_APP_URL || process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL || ''}`.replace(/\/$/, '') : '';
}
const TIMEOUT_MS = 300_000;
const POLL_INTERVAL_MS = 2000;

export type BacktesterStatus = 'idle' | 'queued' | 'running' | 'complete' | 'error';

export interface JobProgress {
  jobId: string;
  status: string;
  progressPct: number;
  message: string | null;
}

interface UseBacktesterReturn {
  status: BacktesterStatus;
  result: BacktestResult | null;
  error: string | null;
  progressText: string;
  jobProgress: JobProgress | null;
  runBacktest: (prompt: string, tickers?: string[]) => Promise<BacktestResult | null>;
  reset: () => void;
}

async function pollJobUntilDone(
  jobId: string,
  onProgress: (p: JobProgress) => void,
  signal: AbortSignal
): Promise<BacktestResult | null> {
  const base = getApiBase();
  const poll = async (): Promise<BacktestResult | null> => {
    const res = await fetch(`${base}/api/backtest/jobs/${jobId}`, { signal });
    if (!res.ok) throw new Error(`Job status ${res.status}`);
    const data = await res.json();
    onProgress({
      jobId: data.job_id,
      status: data.status,
      progressPct: data.progress_pct ?? 0,
      message: data.message ?? null,
    });
    if (data.status === 'completed' && data.result) return data.result as BacktestResult;
    if (data.status === 'failed') throw new Error(data.error || 'Backtest failed');
    return null;
  };
  while (true) {
    const out = await poll();
    if (out != null) return out;
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
}

export function useBacktester(): UseBacktesterReturn {
  const [status, setStatus] = useState<BacktesterStatus>('idle');
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressText, setProgressText] = useState('');
  const [jobProgress, setJobProgress] = useState<JobProgress | null>(null);
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
    setJobProgress(null);
  }, []);

  const runBacktest = useCallback(
    async (prompt: string, tickers: string[] = ['SPY']): Promise<BacktestResult | null> => {
      reset();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        setStatus('running');
        setProgressText('Encolando backtest en el Agent...');

        const submitRes = await fetch(`${getApiBase()}/api/backtest/submit-natural`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, tickers }),
          signal: controller.signal,
        });

        if (!submitRes.ok) {
          const body = await submitRes.text().catch(() => '');
          throw new Error(body || `Agent ${submitRes.status}`);
        }

        const { job_id } = (await submitRes.json()) as { job_id: string };
        if (!job_id) throw new Error('Agent did not return job_id');

        setProgressText('Backtest en cola. Esperando resultado...');
        setStatus('queued');

        const finalResult = await pollJobUntilDone(
          job_id,
          (p) => {
            setJobProgress(p);
            if (p.message) setProgressText(p.message);
          },
          controller.signal
        );

        setResult(finalResult);
        setStatus('complete');
        setProgressText('');
        setJobProgress(null);
        return finalResult;
      } catch (err: any) {
        if (err.name === 'AbortError') return null;
        setError(err.message || 'Error al ejecutar backtest');
        setStatus('error');
        setProgressText('');
        setJobProgress(null);
        return null;
      }
    },
    [reset]
  );

  return { status, result, error, progressText, jobProgress, runBacktest, reset };
}
