'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { RefreshCw, AlertTriangle, ExternalLink, Loader2, HelpCircle, ChevronDown, BarChart3, Table2, TrendingUp, TrendingDown } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { getUserTimezone } from '@/lib/date-utils';
import { useFloatingWindow, useWindowState } from '@/contexts/FloatingWindowContext';
import { InsiderChartContent } from './InsiderChartContent';
import { InsiderGlossaryContent } from './InsiderGlossaryContent';

// ============================================================================
// Types
// ============================================================================

interface Transaction {
  date: string;
  security: string;
  transaction_type: 'A' | 'D';
  transaction_code: string | null;
  transaction_code_desc: string | null;
  is_market_trade: boolean;
  shares: number;
  price: number;
  total_value: number;
  is_derivative: boolean;
}

interface InsiderFiling {
  id: string;
  ticker: string | null;
  company: string | null;
  insider_name: string | null;
  insider_title: string | null;
  is_director: boolean;
  is_officer: boolean;
  is_ten_percent_owner?: boolean;
  filed_at: string;
  period_of_report: string | null;
  url: string | null;
  transactions: Transaction[];
}

interface InsiderCluster {
  ticker: string;
  company: string;
  total_trades: number;
  unique_insiders: number;
  insiders: string[];
}

type ViewMode = 'ticker' | 'clusters';
type DisplayMode = 'table' | 'chart';
type TransactionFilter = 'all' | 'market' | 'buy' | 'sell' | 'exercise' | 'grants' | 'other';
type ShareholderFilter = 'all' | 'directors' | 'officers' | 'ten_percent';

// ============================================================================
// Constants
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

// Transaction filter options (Bloomberg style)
const TRANSACTION_FILTERS: { value: TransactionFilter; label: string; codes: string[] }[] = [
  { value: 'all', label: 'All Transactions', codes: ['P', 'S', 'M', 'A', 'F', 'G', 'J', 'C', 'W', 'D', 'E', 'I', 'L'] },
  { value: 'market', label: 'Open Market Buy/Sell', codes: ['P', 'S'] },
  { value: 'buy', label: 'Purchases Only', codes: ['P'] },
  { value: 'sell', label: 'Sales Only', codes: ['S'] },
  { value: 'exercise', label: 'Option Exercises', codes: ['M'] },
  { value: 'grants', label: 'Grants & Awards', codes: ['A'] },
  { value: 'other', label: 'Other (Gift, Tax, Transfer)', codes: ['F', 'G', 'J', 'C', 'W', 'D', 'E', 'I', 'L'] },
];

// Shareholder filter options
const SHAREHOLDER_FILTERS: { value: ShareholderFilter; label: string }[] = [
  { value: 'all', label: 'All Shareholders' },
  { value: 'directors', label: 'Directors Only' },
  { value: 'officers', label: 'Officers Only' },
  { value: 'ten_percent', label: '10%+ Owners' },
];

// Action label mapping
const ACTION_LABELS: Record<string, string> = {
  'P': 'BUY', 'S': 'SELL', 'M': 'EXERCISE', 'A': 'GRANT', 'F': 'TAX',
  'G': 'GIFT', 'J': 'TRANSFER', 'C': 'CONVERT', 'W': 'INHERIT',
  'D': 'RETURN', 'E': 'EXPIRE', 'I': 'DISCR', 'L': 'SMALL'
};

// ============================================================================
// Compact Dropdown Component
// ============================================================================

interface DropdownProps<T extends string> {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  className?: string;
}

function Dropdown<T extends string>({ value, options, onChange, className = '' }: DropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selected = options.find(o => o.value === value);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 px-2 py-1 text-[10px] bg-slate-100 hover:bg-slate-200 rounded border border-slate-200 transition-colors min-w-0"
      >
        <span className="truncate">{selected?.label}</span>
        <ChevronDown className={`w-3 h-3 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 bg-white border border-slate-200 rounded shadow-lg z-50 min-w-[160px] py-1">
          {options.map(opt => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-3 py-1.5 text-[10px] hover:bg-slate-50 transition-colors ${opt.value === value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-slate-700'
                }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
      timeZone: getUserTimezone(),
      month: 'short',
      day: 'numeric',
      year: '2-digit'
    });
  } catch {
    return dateStr;
  }
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  if (num % 1 !== 0) {
    return num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 3 });
  }
  return num.toLocaleString('en-US');
}

function formatCurrency(num: number): string {
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `$${(num / 1_000).toFixed(1)}K`;
  return `$${num.toFixed(2)}`;
}

function formatPrice(num: number): string {
  return num > 0 ? `$${num.toFixed(2)}` : '—';
}

// ============================================================================
// Main Component
// ============================================================================

type InsiderTradingWindowState = {
  ticker?: string;
  viewMode?: ViewMode;
  displayMode?: DisplayMode;
  transactionFilter?: TransactionFilter;
  shareholderFilter?: ShareholderFilter;
}

export function InsiderTradingContent() {
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
  const { openWindow } = useFloatingWindow();
  const { state: windowState, updateState: updateWindowState } = useWindowState<InsiderTradingWindowState>();

  // State - restored from window state
  const [viewMode, setViewMode] = useState<ViewMode>(windowState.viewMode || 'ticker');
  const [displayMode, setDisplayMode] = useState<DisplayMode>(windowState.displayMode || 'table');
  const [ticker, setTicker] = useState(windowState.ticker || '');
  const [inputValue, setInputValue] = useState(windowState.ticker || '');
  const [filings, setFilings] = useState<InsiderFiling[]>([]);
  const [clusters, setClusters] = useState<InsiderCluster[]>([]);
  const [priceData, setPriceData] = useState<Array<{ date: string; open: number; high: number; low: number; close: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters (Bloomberg style) - restored from window state
  const [transactionFilter, setTransactionFilter] = useState<TransactionFilter>(windowState.transactionFilter || 'all');
  const [shareholderFilter, setShareholderFilter] = useState<ShareholderFilter>(windowState.shareholderFilter || 'all');

  // Fetch detailed insider data for a ticker
  const fetchTickerData = useCallback(async (symbol: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/insider-trading/${symbol}/details?size=200`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setFilings(data.filings || []);

      // Also fetch price data for the chart
      const priceResponse = await fetch(`${API_URL}/api/v1/chart/${symbol}?interval=1day&limit=1095`);
      if (priceResponse.ok) {
        const chartData = await priceResponse.json();
        const bars = chartData.data || chartData.bars || [];
        if (bars.length > 0) {
          setPriceData(bars.map((b: any) => ({
            date: b.date || (b.time ? new Date(b.time * 1000).toISOString().split('T')[0] : b.t),
            open: b.open || b.o,
            high: b.high || b.h,
            low: b.low || b.l,
            close: b.close || b.c
          })));
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading data');
      setFilings([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch clusters
  const fetchClusters = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/insider-trading/clusters?days=7&min_count=3`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setClusters(data.clusters || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading clusters');
    } finally {
      setLoading(false);
    }
  }, []);

  // Persist state changes
  useEffect(() => {
    updateWindowState({
      ticker,
      viewMode,
      displayMode,
      transactionFilter,
      shareholderFilter,
    });
  }, [ticker, viewMode, displayMode, transactionFilter, shareholderFilter, updateWindowState]);

  // Initial load - restore saved ticker or load clusters
  useEffect(() => {
    if (windowState.ticker && windowState.viewMode !== 'clusters') {
      fetchTickerData(windowState.ticker);
    } else if (viewMode === 'clusters') {
      fetchClusters();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch clusters when switching to clusters view
  useEffect(() => {
    if (viewMode === 'clusters') {
      fetchClusters();
    }
  }, [viewMode, fetchClusters]);

  // Handle search
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      setTicker(inputValue.toUpperCase());
      setViewMode('ticker');
      fetchTickerData(inputValue);
    }
  };

  const handleTickerSelect = (selected: { symbol: string }) => {
    setInputValue(selected.symbol);
    setTicker(selected.symbol);
    setViewMode('ticker');
    fetchTickerData(selected.symbol);
  };

  // Get allowed transaction codes based on filter
  const allowedCodes = useMemo(() => {
    const filter = TRANSACTION_FILTERS.find(f => f.value === transactionFilter);
    return new Set(filter?.codes || []);
  }, [transactionFilter]);

  // Filter filings by shareholder type
  const filteredFilings = useMemo(() => {
    if (shareholderFilter === 'all') return filings;
    return filings.filter(f => {
      if (shareholderFilter === 'directors') return f.is_director;
      if (shareholderFilter === 'officers') return f.is_officer;
      if (shareholderFilter === 'ten_percent') return f.is_ten_percent_owner;
      return true;
    });
  }, [filings, shareholderFilter]);

  // Flatten all transactions for table (filtered)
  const allTransactions = useMemo(() => {
    const txs: Array<Transaction & {
      insider_name: string;
      insider_title: string | null;
      filing_url: string | null;
      is_director: boolean;
      is_officer: boolean;
      is_ten_percent_owner: boolean;
    }> = [];

    filteredFilings.forEach(f => {
      f.transactions.forEach(tx => {
        const code = tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D');
        if (!allowedCodes.has(code)) return;

        txs.push({
          ...tx,
          insider_name: f.insider_name || 'Unknown',
          insider_title: f.insider_title,
          filing_url: f.url,
          is_director: f.is_director,
          is_officer: f.is_officer,
          is_ten_percent_owner: f.is_ten_percent_owner || false,
        });
      });
    });

    return txs.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [filteredFilings, allowedCodes]);

  // Calculate largest transactions (Bloomberg style)
  const largestTransactions = useMemo(() => {
    const buys = allTransactions.filter(tx => tx.transaction_code === 'P');
    const sells = allTransactions.filter(tx => tx.transaction_code === 'S');

    const maxBuy = buys.length > 0
      ? buys.reduce((max, tx) => tx.shares > max.shares ? tx : max, buys[0])
      : null;

    const maxSell = sells.length > 0
      ? sells.reduce((max, tx) => tx.shares > max.shares ? tx : max, sells[0])
      : null;

    return { maxBuy, maxSell };
  }, [allTransactions]);

  // Prepare chart transactions
  const chartTransactions = useMemo(() => {
    return filteredFilings.flatMap(f =>
      f.transactions
        .filter(tx => {
          const code = tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D');
          return allowedCodes.has(code);
        })
        .map(tx => ({
          date: tx.date,
          code: tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D'),
          shares: tx.shares,
          value: tx.total_value,
          insider_name: f.insider_name || undefined
        }))
    );
  }, [filteredFilings, allowedCodes]);

  return (
    <div className={`h-full flex flex-col bg-white text-slate-800 ${fontClass}`}>
      {/* Header Row 1 - Main controls */}
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-200 bg-slate-50">
        {/* View Toggle */}
        <div className="flex items-center bg-white rounded border border-slate-200 overflow-hidden">
          <button
            onClick={() => setViewMode('ticker')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${viewMode === 'ticker' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            By Ticker
          </button>
          <button
            onClick={() => setViewMode('clusters')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${viewMode === 'clusters' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            Clusters
          </button>
        </div>

        {/* Ticker Search */}
        {viewMode === 'ticker' && (
          <form onSubmit={handleSearch} className="flex items-center gap-1">
            <TickerSearch
              value={inputValue}
              onChange={setInputValue}
              onSelect={handleTickerSelect}
              placeholder="Ticker"
              className="w-20"
            />
            <button
              type="submit"
              disabled={loading || !inputValue.trim()}
              className="px-2 py-1 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Go'}
            </button>
          </form>
        )}

        {/* Filters - Bloomberg style dropdowns */}
        {viewMode === 'ticker' && ticker && (
          <>
            <div className="w-px h-5 bg-slate-300" />
            <Dropdown
              value={transactionFilter}
              options={TRANSACTION_FILTERS}
              onChange={setTransactionFilter}
            />
            <Dropdown
              value={shareholderFilter}
              options={SHAREHOLDER_FILTERS}
              onChange={setShareholderFilter}
            />
          </>
        )}

        <div className="flex-1" />

        {/* Ticker badge */}
        {ticker && viewMode === 'ticker' && (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-slate-100 text-slate-800 border border-slate-300 rounded">
            {ticker}
          </span>
        )}

        {/* Display mode toggle */}
        {viewMode === 'ticker' && ticker && priceData.length > 0 && (
          <div className="flex items-center bg-white rounded border border-slate-200 overflow-hidden">
            <button
              onClick={() => setDisplayMode('chart')}
              className={`p-1.5 transition-colors ${displayMode === 'chart' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-50'
                }`}
              title="Chart view"
            >
              <BarChart3 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setDisplayMode('table')}
              className={`p-1.5 transition-colors ${displayMode === 'table' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-50'
                }`}
              title="Table view"
            >
              <Table2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Help */}
        <button
          onClick={() => {
            const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
            const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
            openWindow({
              title: 'Insider Trading Guide',
              content: <InsiderGlossaryContent />,
              width: 380,
              height: 450,
              x: Math.max(50, screenWidth / 2 + 100),
              y: Math.max(70, screenHeight / 2 - 200),
              minWidth: 300,
              minHeight: 350,
            });
          }}
          className="p-1 text-slate-400 hover:text-blue-600 transition-colors"
          title="Transaction codes guide"
        >
          <HelpCircle className="w-3.5 h-3.5" />
        </button>

        {/* Refresh */}
        <button
          onClick={() => viewMode === 'clusters' ? fetchClusters() : ticker && fetchTickerData(ticker)}
          disabled={loading}
          className="p-1 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Largest Transactions Panel - Bloomberg style */}
      {viewMode === 'ticker' && ticker && allTransactions.length > 0 && (
        <div className="px-2 py-1.5 border-b border-slate-200 bg-white">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1 font-medium">Largest Transactions</div>
          <div className="flex gap-4 text-[10px]">
            {/* Max Buy */}
            <div className="flex items-center gap-2 min-w-0">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
              <span className="text-slate-500">Max bought:</span>
              {largestTransactions.maxBuy ? (
                <>
                  <span className="font-medium text-slate-800 truncate max-w-[100px]" title={largestTransactions.maxBuy.insider_name}>
                    {largestTransactions.maxBuy.insider_name}
                  </span>
                  <span className="text-slate-400">{formatDate(largestTransactions.maxBuy.date)}</span>
                  <span className="font-bold text-emerald-700 tabular-nums">{formatNumber(largestTransactions.maxBuy.shares)}</span>
                </>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </div>

            <div className="w-px bg-slate-200" />

            {/* Max Sell */}
            <div className="flex items-center gap-2 min-w-0">
              <TrendingDown className="w-3.5 h-3.5 text-red-600 flex-shrink-0" />
              <span className="text-slate-500">Max sold:</span>
              {largestTransactions.maxSell ? (
                <>
                  <span className="font-medium text-slate-800 truncate max-w-[100px]" title={largestTransactions.maxSell.insider_name}>
                    {largestTransactions.maxSell.insider_name}
                  </span>
                  <span className="text-slate-400">{formatDate(largestTransactions.maxSell.date)}</span>
                  <span className="font-bold text-red-700 tabular-nums">-{formatNumber(largestTransactions.maxSell.shares)}</span>
                </>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mx-2 mt-2 px-2 py-1.5 bg-red-50 border border-red-200 rounded flex items-center gap-2 text-red-700">
          <AlertTriangle className="w-3 h-3" />
          <span className="text-[10px]">{error}</span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto min-h-0">
        {viewMode === 'ticker' ? (
          displayMode === 'chart' && priceData.length > 0 ? (
            // Chart View
            <div className="h-full">
              <InsiderChartContent
                ticker={ticker}
                priceData={priceData}
                transactions={chartTransactions}
              />
            </div>
          ) : (
            // Table View
            <table className="w-full text-[10px]">
              <thead className="bg-slate-50 sticky top-0">
                <tr className="text-left text-[9px] text-slate-500 uppercase tracking-wide">
                  <th className="px-2 py-1.5 font-medium">Date</th>
                  <th className="px-2 py-1.5 font-medium">Insider</th>
                  <th className="px-2 py-1.5 font-medium">Role</th>
                  <th className="px-2 py-1.5 font-medium text-center">Action</th>
                  <th className="px-2 py-1.5 font-medium text-right">Shares</th>
                  <th className="px-2 py-1.5 font-medium text-right">$/Share</th>
                  <th className="px-2 py-1.5 font-medium text-right">Total</th>
                  <th className="px-2 py-1.5 font-medium w-6"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {allTransactions.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-slate-400">
                      {loading ? 'Loading...' : ticker ? 'No transactions found' : 'Enter a ticker to view insider transactions'}
                    </td>
                  </tr>
                ) : (
                  allTransactions.map((tx, i) => {
                    const code = tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D');
                    const label = ACTION_LABELS[code] || (tx.transaction_type === 'A' ? '+' : '−');

                    return (
                      <tr key={i} className="hover:bg-slate-50 group">
                        <td className="px-2 py-1.5 text-slate-600 tabular-nums whitespace-nowrap">
                          {formatDate(tx.date)}
                        </td>
                        <td className="px-2 py-1.5 text-slate-800 font-medium truncate max-w-[120px]" title={tx.insider_name}>
                          {tx.insider_name}
                        </td>
                        <td className="px-2 py-1.5 text-slate-500 truncate max-w-[100px]" title={tx.insider_title || ''}>
                          {tx.insider_title || '—'}
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <span
                            className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold ${code === 'P' ? 'bg-emerald-100 text-emerald-800' :
                                code === 'S' ? 'bg-red-100 text-red-800' :
                                  code === 'M' ? 'bg-violet-100 text-violet-800' :
                                    code === 'F' ? 'bg-amber-100 text-amber-800' :
                                      code === 'G' ? 'bg-cyan-100 text-cyan-800' :
                                        code === 'A' ? 'bg-blue-100 text-blue-800' :
                                          code === 'J' ? 'bg-slate-100 text-slate-700' :
                                            tx.transaction_type === 'A' ? 'bg-sky-50 text-sky-700' :
                                              'bg-orange-50 text-orange-700'
                              }`}
                            title={tx.transaction_code_desc || (tx.transaction_type === 'A' ? 'Acquisition' : 'Disposition')}
                          >
                            {label}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-right text-slate-700 tabular-nums">
                          {formatNumber(tx.shares)}
                        </td>
                        <td className="px-2 py-1.5 text-right text-slate-600 tabular-nums">
                          {formatPrice(tx.price)}
                        </td>
                        <td className="px-2 py-1.5 text-right text-slate-800 font-medium tabular-nums">
                          {formatCurrency(tx.total_value)}
                        </td>
                        <td className="px-2 py-1.5">
                          {tx.filing_url && (
                            <a
                              href={tx.filing_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-slate-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          )
        ) : (
          // Clusters View
          <table className="w-full text-[10px]">
            <thead className="bg-slate-50 sticky top-0">
              <tr className="text-left text-[9px] text-slate-500 uppercase tracking-wide">
                <th className="px-3 py-1.5 font-medium">Ticker</th>
                <th className="px-3 py-1.5 font-medium">Company</th>
                <th className="px-3 py-1.5 font-medium text-center">Trades</th>
                <th className="px-3 py-1.5 font-medium text-center">Insiders</th>
                <th className="px-3 py-1.5 font-medium">Top Insiders</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {clusters.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-slate-400">
                    {loading ? 'Loading...' : 'No clusters found in the last 7 days'}
                  </td>
                </tr>
              ) : (
                clusters.map((cluster, i) => (
                  <tr
                    key={i}
                    className="hover:bg-blue-50 cursor-pointer"
                    onClick={() => {
                      setInputValue(cluster.ticker);
                      setTicker(cluster.ticker);
                      setViewMode('ticker');
                      fetchTickerData(cluster.ticker);
                    }}
                  >
                    <td className="px-3 py-2">
                      <span className="font-mono font-semibold text-slate-900">{cluster.ticker}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-600 truncate max-w-[200px]">
                      {cluster.company}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold ${cluster.total_trades >= 10 ? 'bg-red-100 text-red-700' :
                          cluster.total_trades >= 6 ? 'bg-orange-100 text-orange-700' :
                            'bg-amber-100 text-amber-700'
                        }`}>
                        {cluster.total_trades}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center text-slate-700 font-medium">
                      {cluster.unique_insiders}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {cluster.insiders.slice(0, 3).map((name, j) => (
                          <span key={j} className="px-1 py-0 bg-slate-100 rounded text-[8px] text-slate-600 truncate max-w-[80px]">
                            {name.split(' ')[0]}
                          </span>
                        ))}
                        {cluster.insiders.length > 3 && (
                          <span className="text-[8px] text-slate-400">+{cluster.insiders.length - 3}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div className="px-2 py-1 border-t border-slate-200 text-[9px] text-slate-400 flex justify-between bg-slate-50">
        <span>SEC Form 4 Data</span>
        <span>{viewMode === 'ticker' && allTransactions.length > 0 ? `${allTransactions.length} transactions` : ''}</span>
      </div>
    </div>
  );
}
