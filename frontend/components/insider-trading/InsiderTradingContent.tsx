'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { RefreshCw, AlertTriangle, ExternalLink, Loader2, HelpCircle, Filter, LineChart } from 'lucide-react';
import { TickerSearch } from '@/components/common/TickerSearch';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { getUserTimezone } from '@/lib/date-utils';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
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

// Transaction type filters
const TRANSACTION_TYPES = [
  { code: 'P', label: 'BUY', color: '#10b981', desc: 'Open market purchase' },
  { code: 'S', label: 'SELL', color: '#ef4444', desc: 'Open market sale' },
  { code: 'M', label: 'EXERCISE', color: '#8b5cf6', desc: 'Option exercise' },
  { code: 'A', label: 'GRANT', color: '#3b82f6', desc: 'Stock award/grant' },
  { code: 'F', label: 'TAX', color: '#f59e0b', desc: 'Tax withholding' },
  { code: 'G', label: 'GIFT', color: '#06b6d4', desc: 'Gift/donation' },
  { code: 'J', label: 'TRANSFER', color: '#64748b', desc: 'Other transfer' },
] as const;


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
  // For small numbers, show decimals if fractional, otherwise whole number
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

export function InsiderTradingContent() {
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
  const { openWindow } = useFloatingWindow();

  // State
  const [viewMode, setViewMode] = useState<ViewMode>('ticker');
  const [ticker, setTicker] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [filings, setFilings] = useState<InsiderFiling[]>([]);
  const [clusters, setClusters] = useState<InsiderCluster[]>([]);
  const [priceData, setPriceData] = useState<Array<{ date: string; open: number; high: number; low: number; close: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set(['P', 'S', 'M', 'A', 'F', 'G', 'J']));
  const [showFilters, setShowFilters] = useState(false);

  // Fetch detailed insider data for a ticker
  const fetchTickerData = useCallback(async (symbol: string) => {
    setLoading(true);
    setError(null);

    try {
      // Fetch insider filings with details (more for chart)
      const response = await fetch(`${API_URL}/api/v1/insider-trading/${symbol}/details?size=200`); // SEC-API max is 200
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setFilings(data.filings || []);

      // Also fetch price data for the chart
      const priceResponse = await fetch(`${API_URL}/api/v1/chart/${symbol}?interval=1day&limit=1095`); // 3 years
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

  // Initial load
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

  // Flatten all transactions for table (filtered)
  const allTransactions = useMemo(() => {
    const txs: Array<Transaction & { insider_name: string; insider_title: string | null; filing_url: string | null }> = [];
    
    filings.forEach(f => {
      f.transactions.forEach(tx => {
        const code = tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D');
        // Apply filter
        if (!activeFilters.has(code)) return;
        
        txs.push({
          ...tx,
          insider_name: f.insider_name || 'Unknown',
          insider_title: f.insider_title,
          filing_url: f.url
        });
      });
    });

    return txs.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [filings, activeFilters]);

  // Toggle filter
  const toggleFilter = (code: string) => {
    setActiveFilters(prev => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  };

  // Select only market trades (P/S)
  const selectMarketOnly = () => {
    setActiveFilters(new Set(['P', 'S']));
  };

  // Select all
  const selectAll = () => {
    setActiveFilters(new Set(['P', 'S', 'M', 'A', 'F', 'G', 'J']));
  };

  return (
    <div className={`h-full flex flex-col bg-white text-slate-800 ${fontClass}`}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-100">
        {/* View Toggle */}
        <div className="flex items-center gap-0.5 bg-slate-100 rounded p-0.5">
          <button
            onClick={() => setViewMode('ticker')}
            className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
              viewMode === 'ticker' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            By Ticker
          </button>
          <button
            onClick={() => setViewMode('clusters')}
            className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
              viewMode === 'clusters' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
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
              className="px-2 py-0.5 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Go'}
            </button>
          </form>
        )}

        <div className="flex-1" />

        {/* Ticker badge */}
        {ticker && viewMode === 'ticker' && (
          <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 rounded">
            {ticker}
          </span>
        )}

        {/* Chart button - only show when ticker is selected and price data loaded */}
        {viewMode === 'ticker' && ticker && priceData.length > 0 && (
          <button
            onClick={() => {
              // Prepare transactions for chart with insider names
              const chartTransactions = filings.flatMap(f => 
                f.transactions.map(tx => ({
                  date: tx.date,
                  code: tx.transaction_code || (tx.transaction_type === 'A' ? 'A' : 'D'),
                  shares: tx.shares,
                  value: tx.total_value,
                  insider_name: f.insider_name || undefined
                }))
              );
              const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
              const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
              openWindow({
                title: `Insider Activity - ${ticker}`,
                content: <InsiderChartContent ticker={ticker} priceData={priceData} transactions={chartTransactions} />,
                width: 700,
                height: 450,
                x: Math.max(50, screenWidth / 2 - 350),
                y: Math.max(70, screenHeight / 2 - 225),
                minWidth: 400,
                minHeight: 300,
              });
            }}
            className="p-1 text-slate-400 hover:text-blue-600 transition-colors"
            title="Open chart in new window"
          >
            <LineChart className="w-3.5 h-3.5" />
          </button>
        )}

        {/* Filter toggle */}
        {viewMode === 'ticker' && (
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-1 transition-colors ${showFilters ? 'text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}
            title="Filter by transaction type"
          >
            <Filter className="w-3.5 h-3.5" />
          </button>
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
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filter bar */}
      {showFilters && viewMode === 'ticker' && (
        <div className="flex items-center gap-1 px-2 py-1 bg-slate-50 border-b border-slate-100 flex-wrap">
          {TRANSACTION_TYPES.map(t => (
            <button
              key={t.code}
              onClick={() => toggleFilter(t.code)}
              className={`px-1.5 py-0.5 text-[9px] font-medium rounded border transition-colors ${
                activeFilters.has(t.code)
                  ? 'border-transparent text-white'
                  : 'border-slate-200 text-slate-400 bg-white'
              }`}
              style={activeFilters.has(t.code) ? { backgroundColor: t.color } : {}}
              title={t.desc}
            >
              {t.label}
            </button>
          ))}
          <div className="flex-1" />
          <button
            onClick={selectMarketOnly}
            className="px-1.5 py-0.5 text-[8px] text-slate-500 hover:text-slate-700"
          >
            Market only
          </button>
          <span className="text-slate-300">|</span>
          <button
            onClick={selectAll}
            className="px-1.5 py-0.5 text-[8px] text-slate-500 hover:text-slate-700"
          >
            All
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mx-3 mt-2 px-2 py-1.5 bg-red-50 border border-red-200 rounded flex items-center gap-2 text-red-700">
          <AlertTriangle className="w-3 h-3" />
          <span className="text-[10px]">{error}</span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {viewMode === 'ticker' ? (
          <>
            {/* Transactions Table */}
            <div className="flex-1 overflow-auto">
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
                    allTransactions.map((tx, i) => (
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
                            className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                              tx.transaction_code === 'P' ? 'bg-emerald-100 text-emerald-800' :
                              tx.transaction_code === 'S' ? 'bg-red-100 text-red-800' :
                              tx.transaction_code === 'M' ? 'bg-violet-100 text-violet-800' :
                              tx.transaction_code === 'F' ? 'bg-amber-100 text-amber-800' :
                              tx.transaction_type === 'A' ? 'bg-sky-50 text-sky-700' :
                              'bg-orange-50 text-orange-700'
                            }`}
                            title={tx.transaction_code_desc || (tx.transaction_type === 'A' ? 'Acquisition' : 'Disposition')}
                          >
                            {tx.transaction_code === 'P' ? 'BUY' :
                             tx.transaction_code === 'S' ? 'SELL' :
                             tx.transaction_code === 'M' ? 'EXERCISE' :
                             tx.transaction_code === 'F' ? 'TAX' :
                             tx.transaction_code === 'G' ? 'GIFT' :
                             tx.transaction_code === 'A' ? 'GRANT' :
                             tx.transaction_code === 'J' ? 'TRANSFER' :
                             tx.transaction_code === 'C' ? 'CONVERT' :
                             tx.transaction_code === 'W' ? 'INHERIT' :
                             tx.transaction_code === 'D' ? 'RETURN' :
                             tx.transaction_code === 'E' ? 'EXPIRE' :
                             tx.transaction_code === 'I' ? 'DISCR' :
                             tx.transaction_code === 'L' ? 'SMALL' :
                             tx.transaction_type === 'A' ? '+' : '−'}
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
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
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
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                        cluster.total_trades >= 10 ? 'bg-red-100 text-red-700' :
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
      <div className="px-3 py-1 border-t border-slate-100 text-[8px] text-slate-400 flex justify-between">
        <span>Form 4 Data</span>
        <span>{viewMode === 'ticker' && allTransactions.length > 0 ? `${allTransactions.length} transactions` : ''}</span>
      </div>
    </div>
  );
}
