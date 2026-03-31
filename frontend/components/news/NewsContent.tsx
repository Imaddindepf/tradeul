'use client';

/**
 * NewsContent - Componente de PRESENTACIÓN de noticias
 * 
 * Arquitectura Enterprise:
 * - SOLO consume del NewsStore global (modo Live)
 * - Modo Search: query directa a Polygon API con filtros completos
 * - VIRTUALIZADO con react-virtuoso para rendimiento óptimo
 */

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { TableVirtuoso, Virtuoso } from 'react-virtuoso';
import { useNewsStore, NewsArticle, selectArticles, selectIsPaused, selectIsConnected, selectHasMore, selectIsLoadingMore, PAGE_SIZE } from '@/stores/useNewsStore';
import { useSquawk } from '@/contexts/SquawkContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { TickerSearch } from '@/components/common/TickerSearch';
import { ExternalLink, Search, ArrowLeft, X, Loader2 } from 'lucide-react';
import { getUserTimezone } from '@/lib/date-utils';
import { useWindowState, useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { decodeHtmlEntities } from '@/lib/html-utils';

// Mapeo de fuentes a font-family CSS
const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

interface NewsWindowState {
  ticker?: string;
  [key: string]: unknown;
}

interface NewsContentProps {
  initialTicker?: string;
  highlightArticleId?: string;
}

interface SearchFilters {
  tickers: string;
  channels: string;
  tags: string;
  author: string;
  dateFrom: string;
  dateTo: string;
}

const EMPTY_FILTERS: SearchFilters = { tickers: '', channels: '', tags: '', author: '', dateFrom: '', dateTo: '' };

// Quick date range helpers
function getQuickDateRange(days: number): { from: string; to: string } {
  const today = new Date();
  const to = today.toISOString().split('T')[0];
  if (days === 0) return { from: to, to };
  if (days === -1) return { from: `${today.getFullYear()}-01-01`, to }; // YTD
  const from = new Date();
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().split('T')[0], to };
}

function stripHtml(raw: string): string {
  return raw
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildNewsSnippet(article: NewsArticle, maxChars = 190): string {
  const teaser = (article.teaser || '').trim();
  if (teaser) {
    const decodedTeaser = decodeHtmlEntities(teaser);
    return decodedTeaser.length > maxChars ? `${decodedTeaser.slice(0, maxChars - 1)}…` : decodedTeaser;
  }

  const body = (article.body || '').trim();
  if (!body) return '';
  const cleanedBody = decodeHtmlEntities(stripHtml(body));
  if (!cleanedBody) return '';
  return cleanedBody.length > maxChars ? `${cleanedBody.slice(0, maxChars - 1)}…` : cleanedBody;
}

// Row height for virtualization
const ROW_HEIGHT = 24;

export function NewsContent({ initialTicker, highlightArticleId }: NewsContentProps = {}) {
  const { t } = useTranslation();
  const { state: windowState, updateState: updateWindowState } = useWindowState<NewsWindowState>();
  const windowId = useCurrentWindowId();
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);

  // Find the portal target in the window title bar
  useEffect(() => {
    if (windowId) {
      const el = document.getElementById(`window-header-extra-${windowId}`);
      setPortalTarget(el);
    }
  }, [windowId]);

  // Fuente del usuario
  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const newsViewMode = useUserPreferencesStore((s) => s.theme.newsViewMode || 'table');
  const setNewsViewMode = useUserPreferencesStore((s) => s.setNewsViewMode);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];

  // Use persisted ticker
  const savedTicker = windowState.ticker || initialTicker || '';

  // ================================================================
  // CONSUMIR DEL STORE GLOBAL (Live mode)
  // ================================================================
  const articles = useNewsStore(selectArticles);
  const isPaused = useNewsStore(selectIsPaused);
  const isConnected = useNewsStore(selectIsConnected);
  const pausedBuffer = useNewsStore((state) => state.pausedBuffer);
  const stats = useNewsStore((state) => state.stats);
  const hasMore = useNewsStore(selectHasMore);
  const isLoadingMore = useNewsStore(selectIsLoadingMore);

  const setPaused = useNewsStore((state) => state.setPaused);
  const resumeWithBuffer = useNewsStore((state) => state.resumeWithBuffer);
  const loadOlderArticles = useNewsStore((state) => state.loadOlderArticles);
  const setLoadingMore = useNewsStore((state) => state.setLoadingMore);

  const squawk = useSquawk();

  // ================================================================
  // ESTADO LOCAL (UI)
  // ================================================================
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [tickerFilter, setTickerFilter] = useState<string>(savedTicker);
  const [tickerInputValue, setTickerInputValue] = useState<string>(savedTicker);
  const [highlightedId, setHighlightedId] = useState<string | null>(highlightArticleId || null);

  // Column visibility & context menu
  const NEWS_COLS = ['ticker', 'headline', 'date', 'time', 'source'] as const;
  const COL_LABELS: Record<string, string> = { ticker: t('news.ticker'), headline: t('news.headline'), date: t('news.date'), time: t('news.time'), source: t('news.source') };
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [newsMenu, setNewsMenu] = useState<{ x: number; y: number } | null>(null);
  const [colPanel, setColPanel] = useState<{ x: number; y: number } | null>(null);
  const newsMenuRef = useRef<HTMLDivElement>(null);
  const colPanelRef = useRef<HTMLDivElement>(null);
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const virtuosoRef = useRef<any>(null);

  // ================================================================
  // SEARCH MODE STATE
  // ================================================================
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [searchResults, setSearchResults] = useState<NewsArticle[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchNextUrl, setSearchNextUrl] = useState<string | null>(null);
  const [searchLoadingMore, setSearchLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchExecuted, setSearchExecuted] = useState(false);

  // Persist ticker changes
  useEffect(() => {
    updateWindowState({ ticker: tickerFilter });
  }, [tickerFilter, updateWindowState]);

  // ================================================================
  // LIVE MODE: filtrado memoizado
  // ================================================================
  const filteredNews = useMemo(() => {
    if (!tickerFilter) return articles;
    const upperFilter = tickerFilter.toUpperCase();
    return articles.filter(article =>
      article.tickers?.some(t => t.toUpperCase() === upperFilter)
    );
  }, [articles, tickerFilter]);

  const liveCount = useMemo(() =>
    articles.filter(a => a.isLive).length
    , [articles]);

  // Data source: search mode vs live mode
  const displayedArticles = isSearchMode ? searchResults : filteredNews;

  // ================================================================
  // SEARCH HANDLERS
  // ================================================================
  const handleSearch = useCallback(async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    setSearchLoading(true);
    setSearchError(null);
    setSearchExecuted(true);

    try {
      const params = new URLSearchParams();
      if (searchFilters.tickers) params.set('tickers', searchFilters.tickers.toUpperCase());
      if (searchFilters.channels) params.set('channels', searchFilters.channels);
      if (searchFilters.tags) params.set('tags', searchFilters.tags);
      if (searchFilters.author) params.set('author', searchFilters.author);
      if (searchFilters.dateFrom) params.set('published_after', searchFilters.dateFrom);
      if (searchFilters.dateTo) params.set('published_before', searchFilters.dateTo);
      params.set('limit', '200');

      const response = await fetch(`${apiUrl}/news/api/v1/news/search?${params}`);
      if (!response.ok) throw new Error(`Search failed: ${response.status}`);

      const data = await response.json();
      setSearchResults(data.results || []);
      setSearchNextUrl(data.next_url || null);
    } catch (e: any) {
      console.error('[NewsContent] Search error:', e);
      setSearchError(e.message || 'Search failed');
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [searchFilters]);

  const handleLoadMoreSearch = useCallback(async () => {
    if (!searchNextUrl || searchLoadingMore) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    setSearchLoadingMore(true);

    try {
      const response = await fetch(`${apiUrl}/news/api/v1/news/search/cursor?cursor_url=${encodeURIComponent(searchNextUrl)}`);
      if (!response.ok) throw new Error('Cursor fetch failed');

      const data = await response.json();
      setSearchResults(prev => [...prev, ...(data.results || [])]);
      setSearchNextUrl(data.next_url || null);
    } catch (e) {
      console.error('[NewsContent] Load more error:', e);
    } finally {
      setSearchLoadingMore(false);
    }
  }, [searchNextUrl, searchLoadingMore]);

  const handleExitSearch = useCallback(() => {
    setIsSearchMode(false);
    setSearchResults([]);
    setSearchNextUrl(null);
    setSearchError(null);
    setSearchExecuted(false);
    setSearchFilters(EMPTY_FILTERS);
  }, []);

  const handleEnterSearch = useCallback(() => {
    setIsSearchMode(true);
  }, []);

  const updateSearchFilter = useCallback((key: keyof SearchFilters, value: string) => {
    setSearchFilters(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleQuickDate = useCallback((days: number) => {
    const { from, to } = getQuickDateRange(days);
    setSearchFilters(prev => ({ ...prev, dateFrom: from, dateTo: to }));
  }, []);

  // ================================================================
  // LIVE MODE: Infinite scroll
  // ================================================================
  const loadMoreRef = useRef(false);
  const handleEndReached = useCallback(async () => {
    if (isSearchMode) return; // Don't load live articles in search mode
    if (loadMoreRef.current || !hasMore || isLoadingMore || tickerFilter) return;
    loadMoreRef.current = true;
    setLoadingMore(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const offset = articles.length;
      const response = await fetch(`${apiUrl}/news/api/v1/news?limit=${PAGE_SIZE}&offset=${offset}`);
      if (response.ok) {
        const data = await response.json();
        if (data.results && Array.isArray(data.results)) {
          loadOlderArticles(data.results);
        }
      }
    } catch (e) {
      console.error('[NewsContent] Failed to load more:', e);
    } finally {
      loadMoreRef.current = false;
    }
  }, [isSearchMode, hasMore, isLoadingMore, tickerFilter, articles.length, setLoadingMore, loadOlderArticles]);

  // ================================================================
  // EFFECTS
  // ================================================================
  useEffect(() => {
    if (highlightedId && virtuosoRef.current) {
      const index = filteredNews.findIndex(a => {
        const articleId = String(a.benzinga_id || a.id || '');
        return highlightedId.includes(articleId);
      });
      if (index >= 0) {
        virtuosoRef.current.scrollToIndex({ index, align: 'center', behavior: 'smooth' });
      }
      const timer = setTimeout(() => setHighlightedId(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [highlightedId, filteredNews]);

  useEffect(() => {
    if (!newsMenu) return;
    const handle = (e: MouseEvent) => {
      if (newsMenuRef.current && !newsMenuRef.current.contains(e.target as Node)) setNewsMenu(null);
    };
    const tid = setTimeout(() => document.addEventListener('mousedown', handle), 0);
    return () => { clearTimeout(tid); document.removeEventListener('mousedown', handle); };
  }, [newsMenu]);

  useEffect(() => {
    if (!colPanel) return;
    const handle = (e: MouseEvent) => {
      if (colPanelRef.current && !colPanelRef.current.contains(e.target as Node)) setColPanel(null);
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [colPanel]);

  // ================================================================
  // HANDLERS (existing)
  // ================================================================
  const handleTogglePause = useCallback(() => {
    if (isPaused) { resumeWithBuffer(); } else { setPaused(true); }
  }, [isPaused, setPaused, resumeWithBuffer]);

  const handleNewsMenuBtn = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setNewsMenu(prev => prev ? null : { x: rect.left, y: rect.bottom + 2 });
    setColPanel(null);
  }, []);

  const openColPanel = useCallback(() => {
    if (menuBtnRef.current) {
      const rect = menuBtnRef.current.getBoundingClientRect();
      setColPanel({ x: rect.right - 170, y: rect.bottom + 2 });
    }
    setNewsMenu(null);
  }, []);

  const toggleCol = useCallback((col: string) => {
    if (col === 'headline') return;
    setHiddenCols(prev => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col); else next.add(col);
      return next;
    });
  }, []);

  const resetCols = useCallback(() => {
    setHiddenCols(new Set());
    setNewsMenu(null);
    setColPanel(null);
  }, []);

  const handleApplyFilter = useCallback(() => {
    const newFilter = tickerInputValue.toUpperCase().trim();
    setTickerFilter(newFilter);
  }, [tickerInputValue]);

  const formatDateTime = useCallback((isoString: string) => {
    try {
      const d = new Date(isoString);
      return {
        date: d.toLocaleDateString('en-US', { timeZone: getUserTimezone(), month: '2-digit', day: '2-digit', year: '2-digit' }),
        time: d.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      };
    } catch {
      return { date: '—', time: '—' };
    }
  }, []);

  // ================================================================
  // LOADING STATE
  // ================================================================
  if (!stats.initialLoadComplete && !isSearchMode) {
    return (
      <div className="flex items-center justify-center h-full bg-surface">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary mx-auto mb-3" />
          <p className="text-foreground/80 text-sm">{t('news.loadingNews')}</p>
        </div>
      </div>
    );
  }

  // ================================================================
  // ARTICLE VIEWER
  // ================================================================
  if (selectedArticle) {
    const dt = formatDateTime(selectedArticle.published);
    const ticker = selectedArticle.tickers?.[0] || '';
    const hasBody = selectedArticle.body && selectedArticle.body.trim().length > 0;
    const hasTeaser = selectedArticle.teaser && selectedArticle.teaser.trim().length > 0;

    return (
      <div className="flex flex-col h-full bg-surface">
        <div className="flex items-center justify-between px-3 py-2 bg-surface-hover border-b border-border">
          <button
            onClick={() => setSelectedArticle(null)}
            className="px-2 py-1 bg-muted text-foreground rounded hover:bg-muted/80 text-xs font-medium flex items-center gap-1"
          >
            <ArrowLeft className="w-3 h-3" /> {t('common.back')}
          </button>
          <div className="text-xs text-foreground/80 font-mono flex items-center gap-2">
            {ticker && (
              <>
                <span className="font-semibold text-primary">{ticker}</span>
                <span>·</span>
              </>
            )}
            <span>{dt.date}</span>
            <span>·</span>
            <span>{dt.time}</span>
          </div>
          <a
            href={selectedArticle.url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs font-medium flex items-center gap-1"
          >
            <ExternalLink className="w-3 h-3" />
            {t('news.openOriginal')}
          </a>
        </div>

        <div className="flex-1 overflow-auto">
          <div className="p-4">
            <h1 className="text-lg font-semibold text-foreground mb-3">
              {decodeHtmlEntities(selectedArticle.title)}
            </h1>

            <div className="flex items-center gap-3 text-xs text-muted-fg mb-4">
              <span>By {selectedArticle.author}</span>
              {selectedArticle.channels && selectedArticle.channels.length > 0 && (
                <span className="text-muted-fg">
                  {selectedArticle.channels.join(', ')}
                </span>
              )}
            </div>

            {hasBody ? (
              <div
                className="prose prose-sm max-w-none text-foreground leading-relaxed"
                dangerouslySetInnerHTML={{ __html: selectedArticle.body || '' }}
              />
            ) : hasTeaser ? (
              <div className="text-foreground leading-relaxed">
                <p className="mb-4">{decodeHtmlEntities(selectedArticle.teaser || '')}</p>
                <a href={selectedArticle.url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:text-primary-hover font-medium text-sm">
                  {t('news.readMore')} <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-muted-fg mb-4">{t('news.fullContentNotAvailable')}</p>
                <a href={selectedArticle.url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-hover font-medium text-sm">
                  <ExternalLink className="w-4 h-4" /> {t('news.openOnBenzinga')}
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ================================================================
  // MAIN VIEW
  // ================================================================
  return (
    <div className="flex flex-col h-full bg-surface" style={{ fontFamily }}>
      {/* Title bar toggle via portal */}
      {portalTarget && createPortal(
        <div className="flex items-center bg-muted rounded p-0.5 mr-1.5" style={{ fontFamily }}>
          <button
            onClick={isSearchMode ? handleExitSearch : undefined}
            className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${!isSearchMode ? 'bg-surface text-emerald-700 shadow-sm font-medium' : 'text-muted-fg hover:text-foreground'}`}
          >
            {t('news.liveMode')}
          </button>
          <button
            onClick={!isSearchMode ? handleEnterSearch : undefined}
            className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${isSearchMode ? 'bg-surface text-foreground shadow-sm font-medium' : 'text-muted-fg hover:text-foreground'}`}
          >
            {t('news.searchMode')}
          </button>
        </div>,
        portalTarget
      )}

      {/* Header Row 1 */}
      <div className={`flex items-center justify-between px-2 py-1 border-b border-border bg-surface-hover`}>
        <div className="flex items-center gap-2">
          {!isSearchMode ? (
            <>
              {/* Live mode controls */}
              <div className="flex items-center gap-1">
                <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-muted'}`} />
                <span className={`text-[10px] ${isConnected ? 'text-emerald-600' : 'text-muted-fg'}`} style={{ fontFamily }}>
                  {isConnected ? t('common.live') : t('common.offline')}
                </span>
              </div>

              <StreamPauseButton isPaused={isPaused} onToggle={handleTogglePause} size="sm" />

              <SquawkButton
                isEnabled={squawk.isEnabled}
                isSpeaking={squawk.isSpeaking}
                queueSize={squawk.queueSize}
                onToggle={squawk.toggleEnabled}
                size="sm"
              />

              {isPaused && pausedBuffer.length > 0 && (
                <span className="text-muted-fg text-[10px]" style={{ fontFamily }}>(+{pausedBuffer.length})</span>
              )}

              {/* Ticker Filter (live mode) */}
              <form
                onSubmit={(e) => { e.preventDefault(); handleApplyFilter(); }}
                className="flex items-center gap-1 ml-2 pl-2 border-l border-border"
              >
                <TickerSearch
                  value={tickerInputValue}
                  onChange={(value) => { setTickerInputValue(value); if (!value) setTickerFilter(''); }}
                  onSelect={(ticker) => { setTickerInputValue(ticker.symbol); setTickerFilter(ticker.symbol.toUpperCase()); }}
                  placeholder={t('news.ticker')}
                  className="w-20"
                />
                <button type="submit" className="px-2 py-0.5 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-700 transition-colors" style={{ fontFamily }}>
                  {t('common.filter')}
                </button>
              </form>
            </>
          ) : (
            <span className="text-[10px] text-muted-fg" style={{ fontFamily }}>
              {searchExecuted ? `${searchResults.length} ${t('news.searchResults').toLowerCase()}` : ''}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <div className="flex items-center bg-muted rounded p-0.5">
            <button
              onClick={() => setNewsViewMode('table')}
              className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${newsViewMode === 'table' ? 'bg-surface text-foreground shadow-sm font-medium' : 'text-muted-fg hover:text-foreground'}`}
              style={{ fontFamily }}
              title={t('news.tableView')}
            >
              {t('news.tableView')}
            </button>
            <button
              onClick={() => setNewsViewMode('feed')}
              className={`px-1.5 py-0.5 text-[10px] rounded transition-colors ${newsViewMode === 'feed' ? 'bg-surface text-foreground shadow-sm font-medium' : 'text-muted-fg hover:text-foreground'}`}
              style={{ fontFamily }}
              title={t('news.feedView')}
            >
              {t('news.feedView')}
            </button>
          </div>

          {!isSearchMode && (
            <div className="flex items-center gap-1.5 text-[10px]" style={{ fontFamily }}>
              {tickerFilter && (
                <span className="px-1 py-0.5 bg-blue-500/15 text-blue-700 dark:text-blue-400 rounded">{tickerFilter}</span>
              )}
              <span className="text-foreground/80">
                {filteredNews.length}{tickerFilter ? ` / ${articles.length}` : ''}
              </span>
              {liveCount > 0 && <span className="text-emerald-600">({liveCount} live)</span>}
            </div>
          )}

          <button ref={menuBtnRef} onClick={handleNewsMenuBtn}
            className="p-0.5 rounded text-muted-fg hover:text-foreground/80 hover:bg-surface-hover transition-colors" title="Menu">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
            </svg>
          </button>
        </div>
      </div>

      {/* Search Filters Row (only in search mode) */}
      {isSearchMode && (
        <div className="px-2 py-1.5 bg-surface-hover border-b border-border">
          <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }} className="flex flex-wrap items-center gap-1.5">
            {/* Ticker */}
            <input
              type="text"
              value={searchFilters.tickers}
              onChange={(e) => updateSearchFilter('tickers', e.target.value)}
              placeholder={t('news.ticker')}
              className="w-16 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface"
              style={{ fontFamily }}
            />

            {/* Date From */}
            <div className="flex items-center gap-0.5">
              <span className="text-[9px] text-muted-fg">{t('news.dateFrom')}</span>
              <input
                type="date"
                value={searchFilters.dateFrom}
                onChange={(e) => updateSearchFilter('dateFrom', e.target.value)}
                className="w-[105px] px-1 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface"
                style={{ fontFamily }}
              />
            </div>

            {/* Date To */}
            <div className="flex items-center gap-0.5">
              <span className="text-[9px] text-muted-fg">{t('news.dateTo')}</span>
              <input
                type="date"
                value={searchFilters.dateTo}
                onChange={(e) => updateSearchFilter('dateTo', e.target.value)}
                className="w-[105px] px-1 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface"
                style={{ fontFamily }}
              />
            </div>

            {/* Quick dates */}
            <div className="flex items-center gap-0.5">
              {[
                { label: t('news.today'), days: 0 },
                { label: '7d', days: 7 },
                { label: '30d', days: 30 },
                { label: '90d', days: 90 },
                { label: 'YTD', days: -1 },
              ].map(r => (
                <button key={r.label} type="button" onClick={() => handleQuickDate(r.days)}
                  className="px-1.5 py-0.5 text-[9px] text-blue-600 dark:text-blue-400 border border-blue-500/30 hover:border-blue-500/50 hover:bg-blue-500/10 rounded transition-colors"
                  style={{ fontFamily }}>
                  {r.label}
                </button>
              ))}
              {(searchFilters.dateFrom || searchFilters.dateTo) && (
                <button type="button" onClick={() => setSearchFilters(prev => ({ ...prev, dateFrom: '', dateTo: '' }))}
                  className="p-0.5 text-muted-fg hover:text-foreground/80">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            <span className="text-muted-fg/50">|</span>

            {/* Tags */}
            <input
              type="text"
              value={searchFilters.tags}
              onChange={(e) => updateSearchFilter('tags', e.target.value)}
              placeholder={t('news.tags')}
              className="w-20 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-primary bg-surface"
              style={{ fontFamily }}
            />

            {/* Channels */}
            <input
              type="text"
              value={searchFilters.channels}
              onChange={(e) => updateSearchFilter('channels', e.target.value)}
              placeholder={t('news.channels')}
              className="w-20 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-primary bg-surface"
              style={{ fontFamily }}
            />

            {/* Author */}
            <input
              type="text"
              value={searchFilters.author}
              onChange={(e) => updateSearchFilter('author', e.target.value)}
              placeholder={t('news.author')}
              className="w-20 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-primary bg-surface"
              style={{ fontFamily }}
            />

            {/* Search button */}
            <button
              type="submit"
              disabled={searchLoading}
              className="flex items-center gap-1 px-2.5 py-0.5 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
              style={{ fontFamily }}
            >
              {searchLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
              {t('common.search')}
            </button>

            {/* Clear filters */}
            {searchExecuted && (
              <button type="button" onClick={() => { setSearchFilters(EMPTY_FILTERS); setSearchResults([]); setSearchNextUrl(null); setSearchExecuted(false); }}
                className="px-1.5 py-0.5 text-[10px] text-muted-fg hover:text-foreground" style={{ fontFamily }}>
                {t('common.clear')}
              </button>
            )}
          </form>
        </div>
      )}

      {/* Context menu */}
      {newsMenu && (
        <div ref={newsMenuRef}
          className="fixed z-[9999] bg-surface border border-border rounded shadow-lg py-1 min-w-[160px]"
          style={{ left: newsMenu.x, top: newsMenu.y }}>
          <button onClick={openColPanel}
            className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-primary/10 hover:text-primary">
            Configure...
          </button>
          <div className="border-t border-border-subtle my-0.5" />
          <button onClick={resetCols}
            className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-primary/10 hover:text-primary">
            Reset columns
          </button>
        </div>
      )}

      {/* Column config panel */}
      {colPanel && (
        <div ref={colPanelRef}
          className="fixed z-[9999] bg-surface border border-border rounded-lg shadow-xl w-[170px]"
          style={{ left: colPanel.x, top: colPanel.y }}>
          <div className="px-3 py-1.5 border-b border-border-subtle flex items-center justify-between">
            <span className="text-[11px] font-medium text-foreground">Columns</span>
            <span className="text-[10px] text-muted-fg">{5 - hiddenCols.size}/5</span>
          </div>
          <div className="py-1">
            {NEWS_COLS.map(col => (
              <label key={col} className="flex items-center gap-2 px-3 py-1 cursor-pointer hover:bg-surface-hover">
                <input type="checkbox" checked={!hiddenCols.has(col)}
                  onChange={() => toggleCol(col)} disabled={col === 'headline'}
                  className="w-3 h-3 rounded border-border text-primary focus:ring-0 focus:ring-offset-0" />
                <span className={`text-[11px] ${hiddenCols.has(col) ? 'text-muted-fg' : 'text-foreground'}`}>
                  {COL_LABELS[col]}
                </span>
              </label>
            ))}
          </div>
          <div className="px-3 py-1.5 border-t border-border-subtle">
            <button onClick={resetCols}
              className="w-full py-0.5 rounded border border-border text-[10px] text-foreground/80 hover:bg-surface-hover transition-colors">
              Reset defaults
            </button>
          </div>
        </div>
      )}

      {/* Search: loading/error/empty states */}
      {isSearchMode && searchLoading && (
        <div className="flex items-center justify-center py-8 bg-surface">
          <Loader2 className="w-6 h-6 animate-spin text-muted-fg mr-2" />
          <span className="text-sm text-muted-fg">{t('news.searching')}</span>
        </div>
      )}

      {isSearchMode && searchError && (
        <div className="flex items-center justify-center py-8 bg-surface">
          <span className="text-sm text-red-500">{searchError}</span>
        </div>
      )}

      {isSearchMode && searchExecuted && !searchLoading && !searchError && searchResults.length === 0 && (
        <div className="flex items-center justify-center py-8 bg-surface">
          <span className="text-sm text-muted-fg">{t('news.noSearchResults')}</span>
        </div>
      )}

      {/* Virtualized Content */}
      {(!isSearchMode || (isSearchMode && searchResults.length > 0)) && !searchLoading && (
        <div className="flex-1 flex flex-col">
          {newsViewMode === 'table' ? (
            <TableVirtuoso
              ref={virtuosoRef}
              style={{ height: '100%' }}
              data={displayedArticles}
              overscan={20}
              endReached={isSearchMode ? undefined : handleEndReached}
              fixedHeaderContent={() => (
                <tr className="text-left uppercase tracking-wide text-foreground/80 bg-surface-inset">
                  {!hiddenCols.has('ticker') && <th className="px-1.5 py-1 font-medium w-14 text-center text-[11px]" style={{ fontFamily }}>{t('news.ticker')}</th>}
                  <th className="px-1.5 py-1 font-medium text-[11px]" style={{ fontFamily }}>{t('news.headline')}</th>
                  {!hiddenCols.has('date') && <th className="px-1.5 py-1 font-medium w-20 text-center text-[11px]" style={{ fontFamily }}>{t('news.date')}</th>}
                  {!hiddenCols.has('time') && <th className="px-1.5 py-1 font-medium w-16 text-center text-[11px]" style={{ fontFamily }}>{t('news.time')}</th>}
                  {!hiddenCols.has('source') && <th className="px-1.5 py-1 font-medium w-28 text-[11px]" style={{ fontFamily }}>{t('news.source')}</th>}
                </tr>
              )}
              itemContent={(index, article) => {
                const dt = formatDateTime(article.published);
                const displayTicker = tickerFilter && !isSearchMode
                  ? (article.tickers?.find(t => t.toUpperCase() === tickerFilter) || article.tickers?.[0] || '—')
                  : (article.tickers?.[0] || '—');
                const hasMultipleTickers = (article.tickers?.length || 0) > 1;
                const articleId = String(article.benzinga_id || article.id || '');
                const isHighlighted = highlightedId && highlightedId.includes(articleId);

                return (
                  <>
                    {!hiddenCols.has('ticker') && (
                      <td
                        className={`px-1.5 py-0.5 text-center text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                        style={{ fontFamily, height: ROW_HEIGHT }}
                        onClick={() => setSelectedArticle(article)}
                      >
                        <span className="text-primary font-semibold">
                          {displayTicker}
                          {hasMultipleTickers && <span className="text-foreground/60 dark:text-foreground/85 text-[9px] ml-0.5">+{(article.tickers?.length || 1) - 1}</span>}
                        </span>
                      </td>
                    )}
                    <td
                      className={`px-1.5 py-0.5 text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                      style={{ fontFamily, height: ROW_HEIGHT }}
                      onClick={() => setSelectedArticle(article)}
                    >
                      <div className="flex items-center gap-1">
                        {article.isLive && <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse flex-shrink-0" />}
                        <span className="text-foreground truncate" style={{ maxWidth: '450px' }}>{decodeHtmlEntities(article.title)}</span>
                      </div>
                    </td>
                    {!hiddenCols.has('date') && (
                      <td className={`px-1.5 py-0.5 text-center text-foreground/70 dark:text-foreground/90 text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                        style={{ fontFamily, height: ROW_HEIGHT }} onClick={() => setSelectedArticle(article)}>
                        {dt.date}
                      </td>
                    )}
                    {!hiddenCols.has('time') && (
                      <td className={`px-1.5 py-0.5 text-center text-foreground/70 dark:text-foreground/90 text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                        style={{ fontFamily, height: ROW_HEIGHT }} onClick={() => setSelectedArticle(article)}>
                        {dt.time}
                      </td>
                    )}
                    {!hiddenCols.has('source') && (
                      <td className={`px-1.5 py-0.5 text-foreground/70 dark:text-foreground/90 truncate text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                        style={{ fontFamily, maxWidth: '110px', height: ROW_HEIGHT }} onClick={() => setSelectedArticle(article)}>
                        {article.author}
                      </td>
                    )}
                  </>
                );
              }}
              components={{
                Table: ({ style, ...props }) => (
                  <table {...props} style={{ ...style, width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }} className="text-[11px]" />
                ),
                TableHead: React.forwardRef(({ style, ...props }, ref) => (
                  <thead {...props} ref={ref} style={{ ...style, position: 'sticky', top: 0, zIndex: 1 }} />
                )),
                TableRow: ({ style, ...props }) => (
                  <tr {...props} style={{ ...style }} className="hover:bg-surface-hover transition-colors border-b border-border-subtle" />
                ),
                TableFoot: React.forwardRef(({ style, ...props }, ref) => (
                  <tfoot {...props} ref={ref} style={style}>
                    {/* Live mode: loading more */}
                    {!isSearchMode && isLoadingMore && (
                      <tr>
                        <td colSpan={5 - hiddenCols.size} className="text-center py-2 text-xs text-muted-fg" style={{ fontFamily }}>
                          Loading more...
                        </td>
                      </tr>
                    )}
                    {/* Search mode: load more button */}
                    {isSearchMode && searchNextUrl && (
                      <tr>
                        <td colSpan={5 - hiddenCols.size} className="text-center py-2">
                          <button
                            onClick={handleLoadMoreSearch}
                            disabled={searchLoadingMore}
                            className="px-3 py-1 text-[10px] bg-surface-inset text-foreground rounded hover:bg-surface-hover disabled:opacity-50 transition-colors"
                            style={{ fontFamily }}
                          >
                            {searchLoadingMore ? (
                              <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</span>
                            ) : t('news.loadMore')}
                          </button>
                        </td>
                      </tr>
                    )}
                  </tfoot>
                )),
              }}
            />
          ) : (
            <>
              <Virtuoso
                ref={virtuosoRef}
                style={{ height: '100%' }}
                data={displayedArticles}
                overscan={20}
                endReached={isSearchMode ? undefined : handleEndReached}
                itemContent={(index, article) => {
                  const dt = formatDateTime(article.published);
                  const articleId = String(article.benzinga_id || article.id || '');
                  const isHighlighted = highlightedId && highlightedId.includes(articleId);
                  const snippet = buildNewsSnippet(article);
                  const tickerLine = (article.tickers || [])
                    .slice(0, 8)
                    .map((tk) => (tk.startsWith('$') ? tk : `$${tk}`))
                    .join(', ');

                  return (
                    <button
                      type="button"
                      onClick={() => setSelectedArticle(article)}
                      className={`w-full text-left px-2 py-1.5 border-b border-border-subtle hover:bg-surface-hover transition-colors ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                      style={{ fontFamily }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[11px] text-foreground dark:text-white leading-snug">
                          {decodeHtmlEntities(article.title)}
                        </span>
                        <span className="text-[10px] text-foreground/70 dark:text-foreground/90 font-mono whitespace-nowrap">{dt.time}</span>
                      </div>
                      {snippet && (
                        <p className="mt-1 text-[10px] text-foreground/75 dark:text-foreground/90 leading-snug line-clamp-2">
                          {snippet}
                        </p>
                      )}
                      {tickerLine && (
                        <p className="mt-1 text-[10px] text-primary font-medium truncate">
                          {tickerLine}
                        </p>
                      )}
                    </button>
                  );
                }}
              />
              {!isSearchMode && isLoadingMore && (
                <div className="text-center py-2 text-xs text-muted-fg" style={{ fontFamily }}>
                  Loading more...
                </div>
              )}
              {isSearchMode && searchNextUrl && (
                <div className="text-center py-2 border-t border-border-subtle">
                  <button
                    onClick={handleLoadMoreSearch}
                    disabled={searchLoadingMore}
                    className="px-3 py-1 text-[10px] bg-surface-inset text-foreground rounded hover:bg-surface-hover disabled:opacity-50 transition-colors"
                    style={{ fontFamily }}
                  >
                    {searchLoadingMore ? (
                      <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Loading...</span>
                    ) : t('news.loadMore')}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
