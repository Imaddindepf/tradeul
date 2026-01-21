'use client';

/**
 * PredictionMarketsContent
 * Bloomberg-style prediction markets window with search, filters, and sparklines.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useUserPreferencesStore, selectFont, selectColors } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { RefreshCw, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

// ============================================================================
// TYPES
// ============================================================================

interface ProcessedMarket {
  id: string;
  question: string;
  probability_pct: number;
  change_1d: number | null;
  change_5d: number | null;
  change_30d_low: number | null;
  change_30d_high: number | null;
  end_date: string | null;
  clob_token_id?: string;
}

interface ProcessedEvent {
  id: string;
  title: string;
  slug: string;
  category: string;
  subcategory: string | null;
  total_volume: number;
  volume_24h: number | null;
  relevance_score: number;
  markets: ProcessedMarket[];
}

interface CategoryGroup {
  category: string;
  subcategory: string | null;
  display_name: string;
  total_events: number;
  total_volume: number;
  events: ProcessedEvent[];
}

interface PredictionMarketsResponse {
  total_events: number;
  total_markets: number;
  categories: CategoryGroup[];
  last_updated: string;
}

interface WindowState {
  selectedCategory: string | null;
  expandedEvents: string[];
  sortBy: 'relevance' | 'volume' | 'change' | 'prob';
  sortAsc: boolean;
  [key: string]: unknown;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const FONT_CLASS_MAP: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

const SORT_OPTIONS = [
  { value: 'relevance', label: 'Rel' },
  { value: 'volume', label: 'Vol' },
  { value: 'change', label: '1D' },
  { value: 'prob', label: 'Prob' },
] as const;

// Font sizes - increased for readability
const FONT = {
  header: 'text-[11px]',
  label: 'text-[10px]',
  body: 'text-[11px]',
  small: 'text-[10px]',
  tiny: 'text-[9px]',
};

// ============================================================================
// HELPERS
// ============================================================================

function formatVolume(volume: number | null | undefined): string {
  if (volume === null || volume === undefined) return '-';
  if (volume >= 1_000_000_000) return `$${(volume / 1_000_000_000).toFixed(1)}B`;
  if (volume >= 1_000_000) return `$${(volume / 1_000_000).toFixed(1)}M`;
  if (volume >= 1_000) return `$${(volume / 1_000).toFixed(0)}K`;
  return `$${volume.toFixed(0)}`;
}

function formatProbability(prob: number | null | undefined): string {
  if (prob === null || prob === undefined) return '-';
  return `${prob.toFixed(1)}%`;
}

function formatChange(change: number | null): string {
  if (change === null || change === undefined) return '-';
  if (change > 0) return `+${change.toFixed(1)}%`;
  return `${change.toFixed(1)}%`;
}

function formatRange(low: number | null | undefined, high: number | null | undefined): string {
  if (low === null || low === undefined || high === null || high === undefined) return '-';
  return `${low.toFixed(0)}-${high.toFixed(0)}%`;
}

// Mini sparkline component
function Sparkline({ data, width = 40, height = 12, color = '#a855f7' }: {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ============================================================================
// COMPONENT
// ============================================================================

export function PredictionMarketsContent() {
  const { t } = useTranslation();
  const font = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);
  const { state: windowState, updateState } = useWindowState<WindowState>();

  const [data, setData] = useState<PredictionMarketsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedCategory = windowState.selectedCategory || null;
  const expandedEvents = new Set(windowState.expandedEvents || []);
  const sortBy = windowState.sortBy || 'relevance';
  const sortAsc = windowState.sortAsc ?? false;

  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const up = colors.tickUp || '#22c55e';
  const down = colors.tickDown || '#ef4444';

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Fetch main data
  const fetchData = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);

    try {
      const url = forceRefresh
        ? `${apiUrl}/api/v1/predictions?refresh=true`
        : `${apiUrl}/api/v1/predictions`;

      const response = await fetch(url);
      if (!response.ok) throw new Error(`Error ${response.status}`);

      const result: PredictionMarketsResponse = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading predictions');
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Category selection
  const setSelectedCategory = useCallback((cat: string | null) => {
    updateState({ selectedCategory: cat });
  }, [updateState]);

  // Toggle event expansion
  const toggleEvent = useCallback((eventId: string) => {
    const current = windowState.expandedEvents || [];
    const next = current.includes(eventId)
      ? current.filter(id => id !== eventId)
      : [...current, eventId];
    updateState({ expandedEvents: next });
  }, [windowState.expandedEvents, updateState]);

  // Sort handler
  const handleSort = useCallback((field: typeof sortBy) => {
    if (sortBy === field) {
      updateState({ sortAsc: !sortAsc });
    } else {
      updateState({ sortBy: field, sortAsc: false });
    }
  }, [sortBy, sortAsc, updateState]);

  // Filter and sort categories
  const filteredCategories = useMemo(() => {
    if (!data) return [];

    const cats = selectedCategory
      ? data.categories.filter(c => c.category === selectedCategory)
      : data.categories;

    // Sort events within each category
    return cats.map(cat => ({
      ...cat,
      events: [...cat.events].sort((a, b) => {
        const aMarket = a.markets?.[0];
        const bMarket = b.markets?.[0];

        let cmp = 0;
        switch (sortBy) {
          case 'volume':
            cmp = (b.total_volume || 0) - (a.total_volume || 0);
            break;
          case 'change':
            cmp = Math.abs(bMarket?.change_1d || 0) - Math.abs(aMarket?.change_1d || 0);
            break;
          case 'prob':
            cmp = (bMarket?.probability_pct || 0) - (aMarket?.probability_pct || 0);
            break;
          default:
            cmp = b.relevance_score - a.relevance_score;
        }
        return sortAsc ? -cmp : cmp;
      }),
    }));
  }, [data, selectedCategory, sortBy, sortAsc]);

  // Get unique main categories
  const mainCategories = useMemo(() => {
    if (!data) return [];
    const seen = new Set<string>();
    return data.categories
      .filter(c => {
        if (seen.has(c.category)) return false;
        seen.add(c.category);
        return true;
      })
      .map(c => c.category);
  }, [data]);

  // ============================================================================
  // RENDER
  // ============================================================================

  if (loading && !data) {
    return (
      <div className={cn('flex items-center justify-center h-full bg-background text-foreground', fontClass)}>
        <RefreshCw className="w-4 h-4 animate-spin mr-2" />
        <span className={FONT.body}>{t('common.loading')}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn('flex flex-col items-center justify-center h-full gap-2 bg-background text-foreground', fontClass)}>
        <span className={cn(FONT.body, 'text-destructive')}>{error}</span>
        <button
          onClick={() => fetchData()}
          className={cn(FONT.small, 'px-2 py-1 rounded border border-border hover:bg-muted')}
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col h-full select-none bg-background text-foreground', fontClass)}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/40">
        <div className="flex items-center gap-2">
          <span className={cn(FONT.header, 'font-semibold text-amber-500')}>PREDICT</span>
          <span className={cn(FONT.small, 'text-muted-foreground')}>
            {data?.total_events} events | {data?.total_markets} markets
          </span>
        </div>

        <button
          onClick={() => fetchData(true)}
          className="p-1 rounded hover:bg-muted"
          title="Refresh"
          disabled={loading}
        >
          <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      {/* Category Tabs + Sort */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/40">
        <div className="flex items-center gap-1 overflow-x-auto">
          <button
            onClick={() => setSelectedCategory(null)}
            className={cn(
              'px-2 py-0.5 rounded whitespace-nowrap',
              FONT.small,
              !selectedCategory ? 'bg-primary/20 text-primary' : 'hover:bg-muted text-muted-foreground'
            )}
          >
            ALL
          </button>
          {mainCategories.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={cn(
                'px-2 py-0.5 rounded whitespace-nowrap',
                FONT.small,
                selectedCategory === cat ? 'bg-muted text-foreground' : 'hover:bg-muted/50 text-muted-foreground'
              )}
            >
              {cat.split(' ')[0]}
            </button>
          ))}
        </div>

        {/* Sort Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {SORT_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => handleSort(opt.value as typeof sortBy)}
              className={cn(
                'px-1.5 py-0.5 rounded flex items-center gap-0.5',
                FONT.tiny,
                sortBy === opt.value ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50'
              )}
            >
              {opt.label}
              {sortBy === opt.value && (
                <ArrowUpDown className="w-2.5 h-2.5" style={{ transform: sortAsc ? 'rotate(180deg)' : undefined }} />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {filteredCategories.map(categoryGroup => (
          <div key={`${categoryGroup.category}-${categoryGroup.subcategory}`}>
            {/* Category Header */}
            <div className="flex items-center justify-between px-2 py-1 sticky top-0 bg-muted/60 backdrop-blur-sm border-b border-border/20">
              <span className={cn(FONT.small, 'font-medium uppercase tracking-wide')}>{categoryGroup.display_name}</span>
              <span className={cn(FONT.small, 'text-muted-foreground')}>{formatVolume(categoryGroup.total_volume)}</span>
            </div>

            {/* Events */}
            {categoryGroup.events.slice(0, 20).map((event, idx) => {
              const isExpanded = expandedEvents.has(event.id);
              const mainMarket = event.markets?.[0];
              const prob = mainMarket?.probability_pct ?? 0;
              const change = mainMarket?.change_1d;
              const isOdd = idx % 2 === 1;

              return (
                <div key={event.id}>
                  {/* Event Row */}
                  <div
                    onClick={() => event.markets?.length > 1 && toggleEvent(event.id)}
                    className={cn(
                      'flex items-center px-2 py-0.5 relative',
                      isOdd ? 'bg-muted/10' : 'bg-transparent',
                      event.markets?.length > 1 && 'cursor-pointer hover:bg-muted/20'
                    )}
                  >
                    {/* Probability Bar */}
                    <div
                      className="absolute left-0 top-0 bottom-0 opacity-10"
                      style={{
                        width: `${Math.min(prob, 100)}%`,
                        background: 'linear-gradient(90deg, rgb(168, 85, 247) 0%, rgb(139, 92, 246) 100%)',
                      }}
                    />

                    <div className={cn('w-4 relative z-10 text-muted-foreground', FONT.small)}>
                      {event.markets?.length > 1 && (isExpanded ? '-' : '+')}
                    </div>

                    <div className="flex-1 min-w-0 mr-1 relative z-10">
                      <span className={cn(FONT.body, 'truncate block leading-tight')}>{event.title}</span>
                    </div>

                    {/* Prob */}
                    <div className="w-12 text-right relative z-10">
                      <span className={cn(FONT.body, 'font-medium text-amber-500')}>
                        {formatProbability(mainMarket?.probability_pct)}
                      </span>
                    </div>

                    {/* 1D Change */}
                    <div className="w-12 text-right relative z-10">
                      <span
                        className={FONT.small}
                        style={{ color: change && change > 0 ? up : change && change < 0 ? down : undefined }}
                      >
                        {formatChange(change)}
                      </span>
                    </div>

                    {/* Volume */}
                    <div className="w-14 text-right relative z-10">
                      <span className={cn(FONT.small, 'text-muted-foreground')}>
                        {formatVolume(event.total_volume)}
                      </span>
                    </div>
                  </div>

                  {/* Expanded Markets */}
                  {isExpanded && event.markets?.length > 1 && (
                    <div className="border-l-2 border-purple-500/30 ml-3">
                      {event.markets.map((market, mIdx) => {
                        const marketProb = market.probability_pct ?? 0;
                        const marketChange = market.change_1d;
                        const isMarketOdd = mIdx % 2 === 1;
                        return (
                          <div
                            key={market.id}
                            className={cn(
                              'flex items-center px-2 py-0.5 pl-3 relative',
                              isMarketOdd ? 'bg-muted/5' : 'bg-transparent'
                            )}
                          >
                            <div
                              className="absolute left-0 top-0 bottom-0 opacity-8"
                              style={{
                                width: `${Math.min(marketProb, 100)}%`,
                                background: 'linear-gradient(90deg, rgb(236, 72, 153) 0%, rgb(168, 85, 247) 100%)',
                              }}
                            />
                            <span className={cn('flex-1 truncate text-muted-foreground relative z-10', FONT.small)}>
                              {market.question}
                            </span>
                            <span className={cn('w-12 text-right text-amber-500/80 relative z-10', FONT.small)}>
                              {formatProbability(market.probability_pct)}
                            </span>
                            <span
                              className={cn('w-12 text-right relative z-10', FONT.tiny)}
                              style={{ color: marketChange && marketChange > 0 ? up : marketChange && marketChange < 0 ? down : undefined }}
                            >
                              {formatChange(marketChange)}
                            </span>
                            <span className={cn('w-14 text-right text-muted-foreground relative z-10', FONT.tiny)}>
                              {formatRange(market.change_30d_low, market.change_30d_high)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className={cn('flex items-center justify-between px-2 py-1 border-t border-border/40 text-muted-foreground', FONT.tiny)}>
        <span>Source: Polymarket</span>
        {data?.last_updated && <span>Updated: {new Date(data.last_updated).toLocaleTimeString()}</span>}
      </div>
    </div>
  );
}
