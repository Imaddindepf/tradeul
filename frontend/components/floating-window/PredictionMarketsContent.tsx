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

const FONT = {
  header: 'text-[11px]',
  label: 'text-[10px]',
  body: 'text-[11px]',
  small: 'text-[10px]',
  tiny: 'text-[9px]',
};

// Shared column widths so the sticky header and every data row line up exactly.
const COL = {
  chevron: 'w-4',
  prob: 'w-[58px]',
  change: 'w-[56px]',
  vol: 'w-[70px]',
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
    const hasChildren = (event.markets?.length ?? 0) > 1;
    const polymarketUrl = event.slug ? `https://polymarket.com/event/${event.slug}` : null;

    return (
      <div key={event.id}>
        <div
          onClick={() => hasChildren && toggleEvent(event.id)}
          className={cn(
            'group flex items-center px-2 py-1 relative transition-colors',
            idx % 2 === 1 ? 'bg-muted/40' : 'bg-transparent',
            'hover:bg-primary/10',
            hasChildren && 'cursor-pointer'
          )}
        >
          {/* Probability fill — visual gauge behind the row */}
          <div
            className="absolute left-0 top-0 bottom-0 opacity-[0.07] group-hover:opacity-[0.12] transition-opacity pointer-events-none"
            style={{
              width: `${Math.min(prob, 100)}%`,
              background: 'linear-gradient(90deg, rgb(168, 85, 247) 0%, rgb(99, 102, 241) 100%)',
            }}
          />
          <div className={cn(COL.chevron, 'relative z-10 text-muted-fg/70 shrink-0', FONT.small)}>
            {hasChildren && (isExpanded ? '−' : '+')}
          </div>
          <div className="flex-1 min-w-0 mr-2 relative z-10 flex items-center gap-1.5">
            <span className={cn(FONT.body, 'truncate block leading-tight')}>{event.title}</span>
            {polymarketUrl && (
              <a
                href={polymarketUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-muted-fg/30 hover:text-purple-400 transition-colors opacity-0 group-hover:opacity-100"
                title="Polymarket"
              >
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </div>
          <div className={cn(COL.prob, 'text-right relative z-10 tabular-nums shrink-0')}>
            <span className={cn(FONT.body, 'font-semibold text-amber-500')}>
              {formatProbability(mainMarket?.probability_pct)}
            </span>
          </div>
          <div className={cn(COL.change, 'text-right relative z-10 tabular-nums shrink-0')}>
            <span
              className={cn(FONT.small, 'font-medium')}
              style={{ color: change && change > 0 ? up : change && change < 0 ? down : undefined }}
            >
              {formatChange(change)}
            </span>
          </div>
          <div className={cn(COL.vol, 'text-right relative z-10 tabular-nums shrink-0')}>
            <span className={cn(FONT.small, 'text-muted-fg')}>
              {formatVolume(event.total_volume)}
            </span>
          </div>
        </div>

        {isExpanded && hasChildren && (
          <div className="bg-muted/10">
            {event.markets.map((market) => {
              const marketChange = market.change_1d;
              return (
                <div
                  key={market.id}
                  className="flex items-center px-2 py-0.5 relative transition-colors hover:bg-primary/10"
                >
                  <div className={cn(COL.chevron, 'shrink-0')} />
                  <div className="flex-1 min-w-0 mr-2 relative z-10 flex items-center gap-1.5 pl-2 border-l-2 border-purple-500/40">
                    <span className={cn('truncate text-muted-fg', FONT.small)}>
                      {market.question}
                    </span>
                  </div>
                  <div className={cn(COL.prob, 'text-right relative z-10 tabular-nums shrink-0')}>
                    <span className={cn('text-amber-500/85', FONT.small)}>
                      {formatProbability(market.probability_pct)}
                    </span>
                  </div>
                  <div className={cn(COL.change, 'text-right relative z-10 tabular-nums shrink-0')}>
                    <span
                      className={FONT.small}
                      style={{ color: marketChange && marketChange > 0 ? up : marketChange && marketChange < 0 ? down : undefined }}
                    >
                      {formatChange(marketChange)}
                    </span>
                  </div>
                  <div className={cn(COL.vol, 'text-right relative z-10 tabular-nums shrink-0 text-muted-fg/70', FONT.tiny)}>
                    {formatRange(market.change_30d_low, market.change_30d_high)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // Single sortable column header cell. Aligns with the data columns and
  // doubles as the sort control, so every number has a clear label.
  const renderSortCell = (
    field: typeof sortBy,
    label: string,
    widthClass: string,
    align: 'left' | 'right' = 'right'
  ) => {
    const active = sortBy === field;
    return (
      <button
        onClick={() => handleSort(field)}
        className={cn(
          'group/h flex items-center gap-0.5 transition-colors',
          align === 'right' ? cn('justify-end shrink-0', widthClass) : 'justify-start flex-1 min-w-0 mr-2',
          FONT.tiny,
          'uppercase tracking-wider font-semibold',
          active ? 'text-foreground' : 'text-muted-fg hover:text-foreground/80'
        )}
        title={`${label}`}
      >
        <span className="truncate">{label}</span>
        <ArrowUpDown
          className={cn(
            'w-2.5 h-2.5 shrink-0 transition-all',
            active ? 'opacity-100 text-primary' : 'opacity-0 group-hover/h:opacity-40'
          )}
          style={{ transform: active && sortAsc ? 'rotate(180deg)' : undefined }}
        />
      </button>
    );
  };

  // Sticky column header row — shared between browse and ticker modes.
  const renderColumnHeader = () => (
    <div className="flex items-center px-2 py-1 bg-surface-hover select-none">
      <div className={cn(COL.chevron, 'shrink-0')} />
      {renderSortCell('relevance', isSpanish ? 'Mercado' : 'Market', '', 'left')}
      {renderSortCell('prob', 'Prob', COL.prob)}
      {renderSortCell('change', '1D', COL.change)}
      {renderSortCell('volume', 'Vol', COL.vol)}
    </div>
  );

  // ============================================================================
  // RENDER
  // ============================================================================

  if (loading && !data) {
    return (
      <div className={cn('flex items-center justify-center h-full bg-background text-muted-fg', fontClass)}>
        <RefreshCw className="w-4 h-4 animate-spin mr-2" />
        <span className={FONT.body}>{t('common.loading')}</span>
      </div>
    );
  }

  const isTickerMode = !!(searchTicker && tickerData);

  return (
    <div className={cn('flex flex-col h-full select-none bg-background text-foreground', fontClass)}>
      {/* Search Bar */}
      <div className="flex items-center gap-2 px-2 py-1.5 bg-surface-hover shrink-0">
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
              'px-2 py-1 rounded bg-primary text-white hover:bg-primary-hover disabled:opacity-40 transition-colors shrink-0'
            )}
            title={isSpanish ? 'Buscar' : 'Search'}
          >
            {tickerLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
          </button>
        </form>
        {isTickerMode && (
          <div className="flex items-center gap-1.5 ml-auto min-w-0">
            <span className={cn(FONT.small, 'font-semibold text-purple-400 shrink-0')}>{tickerData!.ticker}</span>
            <span className={cn(FONT.tiny, 'text-muted-fg shrink-0')}>
              {tickerData!.total} {isSpanish ? 'mercados' : 'markets'}
            </span>
            <button
              onClick={clearTickerSearch}
              className="p-0.5 rounded hover:bg-muted text-muted-fg hover:text-foreground transition-colors shrink-0"
              title={isSpanish ? 'Ver todos' : 'Show all'}
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* Category tabs — own scrollable row (browse mode only) */}
      {!isTickerMode && (
        <div className="flex items-center gap-1 px-2 py-1 bg-surface-hover overflow-x-auto pulse-scroll shrink-0">
          <button
            onClick={() => setSelectedTag(null)}
            className={cn(
              'px-2 py-0.5 rounded whitespace-nowrap transition-colors', FONT.small,
              !selectedTag ? 'bg-primary/20 text-primary font-medium' : 'hover:bg-muted text-muted-fg'
            )}
          >
            {isSpanish ? 'TODOS' : 'ALL'}
          </button>
          {availableTags.map(tag => (
            <button
              key={tag.slug}
              onClick={() => setSelectedTag(tag.slug)}
              className={cn(
                'px-2 py-0.5 rounded whitespace-nowrap flex items-center gap-1 transition-colors', FONT.small,
                selectedTag === tag.slug ? 'bg-muted text-foreground font-medium' : 'hover:bg-muted/50 text-muted-fg'
              )}
            >
              {tag.label}
              <span className={cn(FONT.tiny, 'opacity-50 tabular-nums')}>{tag.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Column header (shared) */}
      {renderColumnHeader()}

      {/* Body */}
      <div className="flex-1 overflow-y-auto pulse-scroll">
        {isTickerMode ? (
          tickerLoading ? (
            <div className="flex items-center justify-center py-10">
              <RefreshCw className="w-4 h-4 animate-spin mr-2 text-purple-400" />
              <span className={cn(FONT.body, 'text-muted-fg')}>
                {isSpanish ? 'Buscando en Polymarket...' : 'Searching Polymarket...'}
              </span>
            </div>
          ) : sortedTickerEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-2">
              <span className={cn(FONT.body, 'text-muted-fg')}>
                {isSpanish ? 'Sin predicciones para' : 'No predictions for'} {tickerData!.ticker}
              </span>
              <button
                onClick={clearTickerSearch}
                className={cn(FONT.small, 'px-2.5 py-1 rounded border border-border hover:bg-muted transition-colors')}
              >
                {isSpanish ? 'Ver todos los mercados' : 'Show all markets'}
              </button>
            </div>
          ) : (
            sortedTickerEvents.map((event, idx) => renderEventRow(event, idx))
          )
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <span className={cn(FONT.body, 'text-danger')}>{error}</span>
            <button onClick={() => fetchData()} className={cn(FONT.small, 'px-2.5 py-1 rounded border border-border hover:bg-muted transition-colors')}>
              {t('common.retry')}
            </button>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <span className={cn(FONT.body, 'text-muted-fg')}>
              {isSpanish ? 'Sin mercados en esta categoría' : 'No markets in this category'}
            </span>
          </div>
        ) : (
          filteredEvents.map((event, idx) => renderEventRow(event, idx))
        )}
      </div>

      {/* Footer */}
      <div className={cn('flex items-center justify-between px-2 py-1 bg-surface-hover text-muted-fg shrink-0', FONT.tiny)}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium text-foreground/70">Polymarket</span>
          {data && (
            <span className="truncate tabular-nums">{data.total_events} {isSpanish ? 'eventos' : 'events'} · {data.total_markets} {isSpanish ? 'mercados' : 'markets'}</span>
          )}
        </div>
        <button
          onClick={() => fetchData(true)}
          className="p-0.5 rounded hover:bg-muted hover:text-foreground transition-colors shrink-0"
          title={isSpanish ? 'Actualizar' : 'Refresh'}
          disabled={loading}
        >
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
        </button>
      </div>
    </div>
  );
}
