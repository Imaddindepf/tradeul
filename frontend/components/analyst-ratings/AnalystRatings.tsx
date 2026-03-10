'use client';

import { useState, useRef, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useAnalystRatings, type AnalystRating, type AnalystConsensus } from '@/hooks/useAnalystRatings';
import { TickerSearch, type TickerSearchRef } from '@/components/common/TickerSearch';
import { Search, Loader2, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';

/* ── Badge styles: outlined, not solid ── */
const RATING_STYLE: Record<string, string> = {
  'Strong Buy':     'border-emerald-500 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10',
  'Buy':            'border-emerald-400 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10',
  'Overweight':     'border-primary/60 text-primary bg-primary/10',
  'Outperform':     'border-primary/60 text-primary bg-primary/10',
  'Market Perform': 'border-border text-foreground/80 bg-surface-hover',
  'Sector Perform': 'border-border text-foreground/80 bg-surface-hover',
  'Neutral':        'border-border text-foreground/80 bg-surface-hover',
  'Hold':           'border-amber-400 text-amber-700 dark:text-amber-400 bg-amber-500/10',
  'Equal-Weight':   'border-amber-400 text-amber-700 dark:text-amber-400 bg-amber-500/10',
  'Underweight':    'border-orange-400 text-orange-700 dark:text-orange-400 bg-orange-500/10',
  'Underperform':   'border-orange-400 text-orange-700 dark:text-orange-400 bg-orange-500/10',
  'Sell':           'border-red-400 text-red-700 dark:text-red-400 bg-red-500/10',
  'Strong Sell':    'border-red-500 text-red-700 dark:text-red-400 bg-red-500/10',
};

const CONSENSUS_COLOR: Record<string, string> = {
  strong_buy:  'text-emerald-700 dark:text-emerald-400',
  buy:         'text-emerald-700 dark:text-emerald-400',
  hold:        'text-amber-700 dark:text-amber-400',
  sell:        'text-red-700 dark:text-red-400',
  strong_sell: 'text-red-700 dark:text-red-400',
};

const CONSENSUS_LABEL: Record<string, string> = {
  strong_buy:  'Strong Buy',
  buy:         'Buy',
  hold:        'Hold',
  sell:        'Sell',
  strong_sell: 'Strong Sell',
};

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
}

function fmtUSD(n: number | null | undefined) {
  if (n == null) return "--";
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/* ── Price Target Range ── */
function PriceTargetRange({ low, high, avg, median }: { low: number; high: number; avg: number; median: number }) {
  const range = (high || 0) - (low || 0) || 1;
  const avgPct = Math.min(100, Math.max(0, (((avg || 0) - (low || 0)) / range) * 100));
  const medPct = Math.min(100, Math.max(0, (((median || 0) - (low || 0)) / range) * 100));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between items-baseline">
        <div>
        <span className="text-[10px] text-muted-fg uppercase tracking-wide">Low </span>
        <span className="text-[12px] font-semibold text-foreground">{fmtUSD(low)}</span>
        </div>
        <div className="text-right">
        <span className="text-[10px] text-muted-fg uppercase tracking-wide">High </span>
        <span className="text-[12px] font-semibold text-foreground">{fmtUSD(high)}</span>
        </div>
      </div>

      <div className="relative h-[3px] bg-muted rounded-full mx-0.5">
        <div
          className="absolute inset-y-0 bg-blue-300 rounded-full"
          style={{
            left: `${Math.min(medPct, avgPct)}%`,
            right: `${100 - Math.max(medPct, avgPct)}%`,
          }}
        />
        {/* Median dot (hollow) */}
        <div className="absolute top-1/2 -translate-y-1/2" style={{ left: `${medPct}%` }}>
          <div className="w-2 h-2 rounded-full border-[1.5px] border-muted-fg bg-surface -ml-1" />
        </div>
        {/* Avg dot (filled) */}
        <div className="absolute top-1/2 -translate-y-1/2" style={{ left: `${avgPct}%` }}>
          <div className="w-2 h-2 rounded-full bg-primary -ml-1" />
        </div>
      </div>

      <div className="flex items-center justify-center gap-5 text-[10px]">
        <span className="flex items-center gap-1">
          <span className="inline-block w-[6px] h-[6px] rounded-full border-[1.5px] border-muted-fg bg-surface" />
          <span className="text-foreground/80">Med {fmtUSD(median)}</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-[6px] h-[6px] rounded-full bg-primary" />
          <span className="text-primary font-medium">Avg {fmtUSD(avg)}</span>
        </span>
      </div>
    </div>
  );
}

/* ── Consensus Panel ── */
function ConsensusPanel({ c }: { c: AnalystConsensus }) {
  const color = CONSENSUS_COLOR[c.consensusRating] || 'text-foreground';
  const label = CONSENSUS_LABEL[c.consensusRating] || c.consensusRating;

  return (
    <div className="mx-3 mt-3 mb-1 rounded-lg border border-border overflow-hidden">
      <div className="grid grid-cols-2 divide-x divide-border">
        {/* Left: Consensus */}
        <div className="p-3">
          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wider mb-2.5">Analyst Consensus</div>
          <div className="grid grid-cols-4 gap-1">
            <div>
              <div className="text-[9px] text-muted-fg uppercase tracking-wide">Rating</div>
              <div className={`text-[13px] font-bold leading-snug mt-0.5 ${color}`}>{label}</div>
              <div className="text-[10px] text-muted-fg mt-px">({c.totalRatings})</div>
            </div>
            <div className="text-center">
              <div className="text-[9px] text-muted-fg uppercase tracking-wide">Bullish</div>
              <div className="text-[16px] font-bold text-emerald-700 leading-snug mt-0.5">{c.bullishCount}</div>
              <div className="text-[10px] text-muted-fg">{c.bullishPercentage.toFixed(1)}%</div>
            </div>
            <div className="text-center">
              <div className="text-[9px] text-muted-fg uppercase tracking-wide">Neutral</div>
              <div className="text-[16px] font-bold text-amber-600 leading-snug mt-0.5">{c.neutralCount}</div>
              <div className="text-[10px] text-muted-fg">{c.neutralPercentage.toFixed(1)}%</div>
            </div>
            <div className="text-center">
              <div className="text-[9px] text-muted-fg uppercase tracking-wide">Bearish</div>
              <div className="text-[16px] font-bold text-red-600 leading-snug mt-0.5">{c.bearishCount}</div>
              <div className="text-[10px] text-muted-fg">{c.bearishPercentage.toFixed(1)}%</div>
            </div>
          </div>
        </div>

        {/* Right: Price Targets */}
        <div className="p-3">
          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wider mb-2">Price Targets (52W)</div>
          <PriceTargetRange low={c.lowPriceTarget} high={c.highPriceTarget} avg={c.averagePriceTarget} median={c.medianPriceTarget} />
        </div>
      </div>
    </div>
  );
}

/* ── Rating Row ── */
function RatingRow({ r }: { r: AnalystRating }) {
  const badgeCls = RATING_STYLE[r.ratingCurrent] || 'border-border text-foreground/80 bg-surface-hover';
  const ptDiff = (r.priceTargetCurrent || 0) - (r.priceTargetPrior || 0);
  const ptPct = (r.priceTargetPrior || 0) > 0 ? (ptDiff / r.priceTargetPrior) * 100 : 0;
  const hasPriorChange = (r.priceTargetPrior || 0) > 0 && r.priceTargetPrior !== r.priceTargetCurrent;

  return (
    <div className="flex items-center px-4 h-full border-b border-border-subtle hover:bg-surface-hover/60 transition-colors text-[11px]">
      <span className="w-[120px] shrink-0 font-medium text-foreground truncate pr-2" title={r.firm}>{r.firm}</span>
      <span className="w-[110px] shrink-0 text-foreground/80 truncate pr-2" title={r.analystName}>{r.analystName}</span>
      <span className="w-[100px] shrink-0 pr-2">
        <span className={`inline-block px-1.5 py-[1px] rounded border text-[10px] font-semibold ${badgeCls}`}>{r.ratingCurrent}</span>
      </span>
      <span className="w-[130px] shrink-0 text-right pr-2 tabular-nums">
        <span className="font-semibold text-foreground">{fmtUSD(r.priceTargetCurrent)}</span>
        {hasPriorChange && (
          <span className="text-[9px] text-muted-fg ml-1">from {fmtUSD(r.priceTargetPrior)}</span>
        )}
      </span>
      <span className={`w-[60px] shrink-0 text-right pr-2 font-semibold tabular-nums ${
        ptDiff > 0 ? 'text-emerald-700' : ptDiff < 0 ? 'text-red-600' : 'text-muted-fg/50'
      }`}>
        {ptDiff !== 0 ? `${ptDiff > 0 ? '+' : ''}${ptPct.toFixed(1)}%` : '--'}
      </span>
      <span className="flex-1 text-right text-muted-fg tabular-nums text-[10px]">{fmtDate(r.releaseDate)}</span>
    </div>
  );
}

/* ── Main Component ── */
const INITIAL_VISIBLE = 12;

export function AnalystRatingsContent({ initialTicker }: { initialTicker?: string }) {
  const { data, loading, error, ticker, search, refetch } = useAnalystRatings(initialTicker);
  const tickerSearchRef = useRef<TickerSearchRef>(null);
  const [inputValue, setInputValue] = useState(initialTicker?.toUpperCase() || '');
  const [expanded, setExpanded] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    tickerSearchRef.current?.close();
    if (inputValue.trim()) { search(inputValue.trim()); setExpanded(false); }
  }, [inputValue, search]);

  const ratings = data?.ratings || [];
  const consensus = data?.consensus;
  const visibleRatings = expanded ? ratings : ratings.slice(0, INITIAL_VISIBLE);
  const hiddenCount = ratings.length - INITIAL_VISIBLE;

  const virt = useVirtualizer({
    count: visibleRatings.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 32,
    overscan: 8,
  });

  return (
    <div className="flex flex-col h-full bg-surface overflow-hidden select-none">
      {/* Search bar */}
      <div className="px-3 py-1.5 border-b border-border bg-surface shrink-0">
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <TickerSearch
            ref={tickerSearchRef}
            value={inputValue}
            onChange={setInputValue}
            onSelect={(t) => { setInputValue(t.symbol); search(t.symbol); setExpanded(false); }}
            placeholder="Ticker..."
            className="flex-1"
            autoFocus={false}
          />
          <button
            type="submit"
            disabled={loading || !inputValue.trim()}
            className="px-3 py-1 text-[11px] font-medium bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50 transition-colors flex items-center gap-1.5"
          >
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
            Search
          </button>
          {ticker && (
            <button
              type="button"
              onClick={refetch}
              disabled={loading}
              className="p-1 rounded hover:bg-surface-hover transition-colors disabled:opacity-40"
              title="Refresh"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-muted-fg ${loading ? 'animate-spin' : ''}`} />
            </button>
          )}
        </form>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto" ref={listRef}>
        {/* Empty state */}
        {!ticker && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-muted-fg gap-1.5">
            <Search className="w-5 h-5 text-muted-fg/50" />
            <div className="text-[12px]">Enter a ticker to view analyst ratings</div>
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-5 h-5 text-primary animate-spin" />
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full text-[12px] text-red-500">{error}</div>
        )}

        {data && !error && consensus && (
          <div>
            <ConsensusPanel c={consensus} />

            {/* Table header */}
            <div className="flex items-center px-4 py-1.5 border-b border-border text-[10px] font-medium text-muted-fg italic sticky top-0 z-10 bg-surface">
              <span className="w-[120px] shrink-0">Firm</span>
              <span className="w-[110px] shrink-0">Analyst</span>
              <span className="w-[100px] shrink-0">Rating</span>
              <span className="w-[130px] shrink-0 text-right">Price Target</span>
              <span className="w-[60px] shrink-0 text-right">Change</span>
              <span className="flex-1 text-right">Date</span>
            </div>

            <div style={{ height: virt.getTotalSize(), position: 'relative' }}>
              {virt.getVirtualItems().map(vi => (
                <div key={vi.index} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: vi.size, transform: `translateY(${vi.start}px)` }}>
                  <RatingRow r={visibleRatings[vi.index]} />
                </div>
              ))}
            </div>

            {hiddenCount > 0 && (
              <button
                onClick={() => setExpanded(v => !v)}
                className="w-full py-2 text-[11px] font-medium text-primary hover:text-primary-hover hover:bg-surface-hover transition-colors flex items-center justify-center gap-1"
              >
                {expanded ? (
                  <>Show less <ChevronUp className="w-3 h-3" /></>
                ) : (
                  <>See {hiddenCount} more <ChevronDown className="w-3 h-3" /></>
                )}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
