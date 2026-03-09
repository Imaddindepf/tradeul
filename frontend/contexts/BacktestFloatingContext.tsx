'use client';

import React, { createContext, useCallback, useContext, useState, useRef } from 'react';
import type { BacktestResult, StrategyConfig } from '@/components/ai-agent/backtest/BacktestTypes';

export type BacktesterStatus = 'idle' | 'running' | 'complete' | 'error';

interface BacktestFloatingContextValue {
  status: BacktesterStatus;
  result: BacktestResult | null;
  error: string | null;
  progressText: string;
  runStructured: (strategy: StrategyConfig, opts?: RunOpts) => Promise<BacktestResult | null>;
  reset: () => void;
}

interface RunOpts {
  includeWalkForward?: boolean;
  walkForwardSplits?: number;
  includeMonteCarlo?: boolean;
  monteCarloSimulations?: number;
  includeAdvancedMetrics?: boolean;
}

const BacktestFloatingContext = createContext<BacktestFloatingContextValue | null>(null);

function getApiBase(): string {
  if (typeof window !== 'undefined') return '';
  return '';
}

export function BacktestFloatingProvider({ children }: { children: React.ReactNode }) {
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

  const runStructured = useCallback(
    async (strategy: StrategyConfig, opts: RunOpts = {}): Promise<BacktestResult | null> => {
      reset();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        setStatus('running');
        setProgressText('Sending strategy to backtester…');

        const body = {
          strategy,
          include_walk_forward: opts.includeWalkForward ?? true,
          walk_forward_splits: opts.walkForwardSplits ?? 5,
          include_monte_carlo: opts.includeMonteCarlo ?? true,
          monte_carlo_simulations: opts.monteCarloSimulations ?? 1000,
          include_advanced_metrics: opts.includeAdvancedMetrics ?? true,
          n_trials_for_dsr: 1,
        };

        const base = getApiBase();
        const res = await fetch(`${base}/api/backtest/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
          const detail = (data as any).detail || (data as any).error || `HTTP ${res.status}`;
          throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }

        const response = data as { status: string; result?: BacktestResult; error?: string };
        if (response.status === 'error') {
          throw new Error(response.error || 'Backtest failed');
        }

        if (!response.result) {
          throw new Error('Backtester returned no result');
        }

        setResult(response.result);
        setStatus('complete');
        setProgressText('');
        return response.result;
      } catch (err: any) {
        if (err.name === 'AbortError') return null;
        setError(err.message || 'Error running backtest');
        setStatus('error');
        setProgressText('');
        return null;
      }
    },
    [reset]
  );

  const value: BacktestFloatingContextValue = {
    status,
    result,
    error,
    progressText,
    runStructured,
    reset,
  };

  return (
    <BacktestFloatingContext.Provider value={value}>
      {children}
    </BacktestFloatingContext.Provider>
  );
}

export function useBacktestFloating() {
  const ctx = useContext(BacktestFloatingContext);
  if (!ctx) throw new Error('useBacktestFloating must be used within BacktestFloatingProvider');
  return ctx;
}
