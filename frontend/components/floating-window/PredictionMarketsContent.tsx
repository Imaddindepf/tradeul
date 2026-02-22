'use client';

/**
 * PredictionMarketsContent
 * Bloomberg-style prediction markets window with ticker search and category browsing.
 * Search by ticker to find related Polymarket events (e.g. AAPL, META, NVDA).
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUserPreferencesStore, selectFont, selectColors } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { RefreshCw, ArrowUpDown, Search, ExternalLink, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TickerSearch, TickerSearchRef } from '@/components/common/TickerSearch';

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
  tags: string[];           // tag slugs for filtering
  tag_labels: string[];     // display labels
  total_volume: number;
  volume_24h: number | null;
  relevance_score: number;
  markets: ProcessedMarket[];
}

interface TagInfo {
  slug: string;
  label: string;
  count: number;
  total_volume: number;
}

interface PredictionMarketsResponse {
  total_events: number;
  total_markets: number;
  events: ProcessedEvent[];  // flat list
  tags: TagInfo[];           // available tags
}

interface TickerSearchResponse {
  ticker: string;
  events: ProcessedEvent[];
  total: number;
}

interface WindowState {
  selectedTag: string | null;
  expandedEvents: string[];
  sortBy: 'relevance' | 'volume' | 'change' | 'prob';
  sortAsc: boolean;
  searchTicker: string | null;
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

// ============================================================================
// COMPONENT
// ============================================================================

export function PredictionMarketsContent() {
  const { t, i18n } = useTranslation();
  const font = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);
  const { state: windowState, updateState } = useWindowState<WindowState>();
  const isSpanish = i18n.language === 'es';

  const [data, setData] = useState<PredictionMarketsResponse | null>(null);
  const [tickerData, setTickerData] = useState<TickerSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState(windowState.searchTicker || '');
  const tickerSearchRef = useRef<TickerSearchRef>(null);

  const selectedTag = windowState.selectedTag || null;
  const expandedEvents = new Set(windowState.expandedEvents || []);
  const sortBy = windowState.sortBy || 'relevance';
  const sortAsc = windowState.sortAsc ?? false;
  const searchTicker = windowState.searchTicker || null;

  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const up = colors.tickUp || '#22c55e';
  const down = colors.tickDown || '#ef4444';

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Fetch main category data
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

  // Fetch ticker-specific predictions from Polymarket
  const fetchTickerPredictions = useCallback(async (ticker: string) => {
    const normalized = ticker.toUpperCase().trim();
    if (!normalized) return;

    setTickerLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/predictions/ticker/${normalized}`);
      if (!response.ok) throw new Error(`Error ${response.status}`);
      const result: TickerSearchResponse = await response.json();
      setTickerData(result);
      updateState({ searchTicker: normalized });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error searching predictions');
      setTickerData(null);
    } finally {
      setTickerLoading(false);
    }
  }, [apiUrl, updateState]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Restore ticker search on remount
  useEffect(() => {
    if (searchTicker && !tickerData) {
      fetchTickerPredictions(searchTicker);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTickerSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    tickerSearchRef.current?.close();
    if (inputValue.trim()) fetchTickerPredictions(inputValue.trim());
  };

  const clearTickerSearch = useCallback(() => {
    setTickerData(null);
    setInputValue('');
    updateState({ searchTicker: null });
  }, [updateState]);

  const setSelectedTag = useCallback((slug: string | null) => {
    updateState({ selectedTag: slug });
  }, [updateState]);

  const toggleEvent = useCallback((eventId: string) => {
    const current = windowState.expandedEvents || [];
    const next = current.includes(eventId)
      ? current.filter((id: string) => id !== eventId)
      : [...current, eventId];
    updateState({ expandedEvents: next });
  }, [windowState.expandedEvents, updateState]);

  const handleSort = useCallback((field: typeof sortBy) => {
    if (sortBy === field) {
      updateState({ sortAsc: !sortAsc });
    } else {
      updateState({ sortBy: field, sortAsc: false });
    }
  }, [sortBy, sortAsc, updateState]);

  const sortEvents = useCallback((events: ProcessedEvent[]) => {
    return [...events].sort((a, b) => {
      const aM = a.markets?.[0];
      const bM = b.markets?.[0];
      let cmp = 0;
      switch (sortBy) {
        case 'volume': cmp = (b.total_volume || 0) - (a.total_volume || 0); break;
        case 'change': cmp = Math.abs(bM?.change_1d || 0) - Math.abs(aM?.change_1d || 0); break;
        case 'prob': cmp = (bM?.probability_pct || 0) - (aM?.probability_pct || 0); break;
        default: cmp = b.relevance_score - a.relevance_score;
      }
      return sortAsc ? -cmp : cmp;
    });
  }, [sortBy, sortAsc]);

  const filteredEvents = useMemo(() => {
    if (!data?.events) return [];
    const events = selectedTag
      ? data.events.filter(e => e.tags?.includes(selectedTag))
      : data.events;
    return sortEvents(events);
  }, [data, selectedTag, sortEvents]);

  const availableTags = useMemo(() => {
    if (!data?.tags) return [];
    return data.tags;
  }, [data]);

  const sortedTickerEvents = useMemo(() => {
    if (!tickerData?.events) return [];
    return sortEvents(tickerData.events || []);
  }, [tickerData, sortEvents]);

  // ============================================================================
  // SHARED: Event Row
  // ============================================================================

  const renderEventRow = (event: ProcessedEvent & { category?: string }, idx: number) => {
    const isExpanded = expandedEvents.has(event.id);
    const mainMarket = event.markets?.[0];
    const prob = mainMarket?.probability_pct ?? 0;
    const change = mainMarket?.change_1d;
    const isOdd = idx % 2 === 1;
    const polymarketUrl = event.slug ? `https://polymarket.com/event/${event.slug}` : null;

    return (
      <div key={event.id}>
        <div
          onClick={() => event.markets?.length > 1 && toggleEvent(event.id)}
          className={cn(
            'flex items-center px-2 py-0.5 relative',
            isOdd ? 'bg-muted/10' : 'bg-transparent',
            event.markets?.length > 1 && 'cursor-pointer hover:bg-muted/20'
          )}
        >
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
          <div className="flex-1 min-w-0 mr-1 relative z-10 flex items-center gap-1">
            <span className={cn(FONT.body, 'truncate block leading-tight')}>{event.title}</span>
            {polymarketUrl && (
              <a
                href={polymarketUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-muted-foreground/40 hover:text-purple-400 transition-colors"
                title="Polymarket"
              >
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </div>
          <div className="w-12 text-right relative z-10">
            <span className={cn(FONT.body, 'font-medium text-amber-500')}>
              {formatProbability(mainMarket?.probability_pct)}
            </span>
          </div>
          <div className="w-12 text-right relative z-10">
            <span
              className={FONT.small}
              style={{ color: change && change > 0 ? up : change && change < 0 ? down : undefined }}
            >
              {formatChange(change)}
            </span>
          </div>
          <div className="w-14 text-right relative z-10">
            <span className={cn(FONT.small, 'text-muted-foreground')}>
              {formatVolume(event.total_volume)}
            </span>
          </div>
        </div>

        {isExpanded && event.markets?.length > 1 && (
          <div className="border-l-2 border-purple-500/30 ml-3">
            {event.markets.map((market, mIdx) => {
              const marketProb = market.probability_pct ?? 0;
              const marketChange = market.change_1d;
              return (
                <div
                  key={market.id}
                  className={cn(
                    'flex items-center px-2 py-0.5 pl-3 relative',
                    mIdx % 2 === 1 ? 'bg-muted/5' : 'bg-transparent'
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
  };

  // Sort controls (shared between modes)
  const renderSortControls = () => (
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
  );

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

  return (
    <div className={cn('flex flex-col h-full select-none bg-background text-foreground', fontClass)}>
      {/* Ticker Search Bar */}
      <div className="flex items-center gap-2 px-2 py-1 border-b border-border/40">
        <form onSubmit={handleTickerSubmit} className="flex items-center gap-1">
          <TickerSearch
            ref={tickerSearchRef}
            value={inputValue}
            onChange={(v) => { setInputValue(v); if (!v) clearTickerSearch(); }}
            onSelect={(tk) => { setInputValue(tk.symbol); fetchTickerPredictions(tk.symbol); }}
            placeholder={isSpanish ? 'Ticker...' : 'Ticker...'}
            className="w-28"
            autoFocus={false}
          />
          <button
            type="submit"
            disabled={tickerLoading || !inputValue.trim()}
            className={cn(
              FONT.small,
              'px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors shrink-0'
            )}
          >
            {tickerLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
          </button>
        </form>
      </div>

      {/* === Ticker Search Results Mode === */}
      {searchTicker && tickerData ? (
        <>
          <div className="flex items-center justify-between px-2 py-1 border-b border-border/40">
            <div className="flex items-center gap-2">
              <span className={cn(FONT.body, 'font-semibold text-purple-400')}>{tickerData.ticker}</span>
              <span className={cn(FONT.small, 'text-muted-foreground')}>
                {tickerData.total} {isSpanish ? 'mercados' : 'markets'}
              </span>
            </div>
            {renderSortControls()}
          </div>

          <div className="flex-1 overflow-y-auto">
            {tickerLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-4 h-4 animate-spin mr-2 text-purple-400" />
                <span className={cn(FONT.body, 'text-muted-foreground')}>
                  {isSpanish ? 'Buscando en Polymarket...' : 'Searching Polymarket...'}
                </span>
              </div>
            ) : sortedTickerEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <span className={cn(FONT.body, 'text-muted-foreground')}>
                  {isSpanish ? 'Sin predicciones para' : 'No predictions for'} {tickerData.ticker}
                </span>
                <button
                  onClick={clearTickerSearch}
                  className={cn(FONT.small, 'px-2 py-1 rounded border border-border hover:bg-muted')}
                >
                  {isSpanish ? 'Ver todos los mercados' : 'Show all markets'}
                </button>
              </div>
            ) : (
              sortedTickerEvents.map((event, idx) => renderEventRow(event, idx))
            )}
          </div>
        </>
      ) : (
        /* === Tag Browse Mode === */
        <>
          <div className="flex items-center justify-between px-2 py-1 border-b border-border/40">
            <div className="flex items-center gap-1 overflow-x-auto">
              <button
                onClick={() => setSelectedTag(null)}
                className={cn(
                  'px-2 py-0.5 rounded whitespace-nowrap', FONT.small,
                  !selectedTag ? 'bg-primary/20 text-primary' : 'hover:bg-muted text-muted-foreground'
                )}
              >
                ALL
              </button>
              {availableTags.map(tag => (
                <button
                  key={tag.slug}
                  onClick={() => setSelectedTag(tag.slug)}
                  className={cn(
                    'px-2 py-0.5 rounded whitespace-nowrap flex items-center gap-1', FONT.small,
                    selectedTag === tag.slug ? 'bg-muted text-foreground' : 'hover:bg-muted/50 text-muted-foreground'
                  )}
                >
                  {tag.label}
                  <span className={cn(FONT.tiny, 'opacity-50')}>{tag.count}</span>
                </button>
              ))}
            </div>
            {renderSortControls()}
          </div>

          <div className="flex-1 overflow-y-auto">
            {error ? (
              <div className="flex flex-col items-center justify-center h-full gap-2">
                <span className={cn(FONT.body, 'text-destructive')}>{error}</span>
                <button onClick={() => fetchData()} className={cn(FONT.small, 'px-2 py-1 rounded border border-border hover:bg-muted')}>
                  {t('common.retry')}
                </button>
              </div>
            ) : (
              filteredEvents.map((event, idx) => renderEventRow(event, idx))
            )}
          </div>
        </>
      )}

      {/* Footer */}
      <div className={cn('flex items-center justify-between px-2 py-1 border-t border-border/40 text-muted-foreground', FONT.tiny)}>
        <div className="flex items-center gap-2">
          <span>Polymarket</span>
          {data && (
            <span>{data.total_events} events · {data.total_markets} markets</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">

          <button
            onClick={() => fetchData(true)}
            className="p-0.5 rounded hover:bg-muted transition-colors"
            title="Refresh"
            disabled={loading}
          >
            <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
          </button>
        </div>
      </div>
    </div>
  );
}
