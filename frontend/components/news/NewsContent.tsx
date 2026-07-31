'use client';

/**
 * NewsContent - Componente de PRESENTACIÓN de noticias
 * 
 * Arquitectura:
 * - SIEMPRE en vivo (WS → NewsStore global); solo se detiene con el botón de pausa.
 * - Búsqueda unificada, sin modos: filtra lo vivo en memoria Y consulta el
 *   histórico persistido (/news/api/v1/news/history → news-persister/TimescaleDB),
 *   fusionando ambos con dedupe por id/url. Lo nuevo que casa sigue entrando.
 * - VIRTUALIZADO con react-virtuoso para rendimiento óptimo
 */

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { TableVirtuoso, Virtuoso } from 'react-virtuoso';
import { useNewsStore, NewsArticle, selectArticles, selectIsPaused, selectIsConnected, selectHasMore, selectIsLoadingMore, PAGE_SIZE } from '@/stores/useNewsStore';
import { useSquawk } from '@/contexts/SquawkContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { TickerSearch } from '@/components/common/TickerSearch';
import { ExternalLink, ArrowLeft, Loader2, SlidersHorizontal, Trash2 } from 'lucide-react';
import { getUserTimezone } from '@/lib/date-utils';
import { useWindowState, useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { decodeHtmlEntities } from '@/lib/html-utils';
import { ExtractedBody } from '@/components/news/ArticleExtract';
import {
  NewsFiltersPanel,
  NewsWindowFilters,
  EMPTY_WINDOW_FILTERS,
  countWindowFilters,
  PublisherEntry,
} from '@/components/news/NewsFiltersPanel';
import {
  useNewsFiltersStore,
  matchesGlobalFilters,
  countGlobalFilters,
  NewsGlobalFilters,
} from '@/stores/useNewsFiltersStore';

// Mapeo de fuentes a font-family CSS
const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

interface NewsWindowState {
  ticker?: string;
  search?: string;
  [key: string]: unknown;
}

interface NewsContentProps {
  initialTicker?: string;
  highlightArticleId?: string;
}

/** Capa de filtros por-ventana aplicada también a lo vivo (fechas, autor, canales, tags) */
function matchesWindowLayer(article: NewsArticle, wf: NewsWindowFilters): boolean {
  const ts = Date.parse(article.published);
  if (wf.dateFrom && !isNaN(ts) && ts < Date.parse(`${wf.dateFrom}T00:00:00`)) return false;
  if (wf.dateTo && !isNaN(ts) && ts > Date.parse(`${wf.dateTo}T23:59:59`)) return false;
  if (wf.author && !(article.author || '').toLowerCase().includes(wf.author.toLowerCase())) return false;
  if (wf.channels) {
    const wanted = wf.channels.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
    if (wanted.length && !(article.channels || []).some(c => wanted.includes(c.toLowerCase()))) return false;
  }
  if (wf.tags) {
    const wanted = wf.tags.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
    const tags = ((article as { tags?: string[] }).tags) || [];
    if (wanted.length && !tags.some(tg => wanted.includes(tg.toLowerCase()))) return false;
  }
  return true;
}

// Los identificadores internos de feed jamás se muestran al usuario
const CHANNEL_MASK: Record<string, string> = { Polygon: 'Newswire', FMP: 'Analysis' };
function displayChannels(channels?: string[]): string {
  return (channels || []).map((c) => CHANNEL_MASK[c] || c).join(', ');
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

// Badge de sentimiento (insights de la fuente, p. ej. Polygon)
function SentimentBadge({ sentiment }: { sentiment?: string }) {
  if (sentiment === 'positive') return <span className="text-emerald-500">▲</span>;
  if (sentiment === 'negative') return <span className="text-rose-500">▼</span>;
  if (sentiment === 'neutral') return <span className="text-muted-fg">•</span>;
  return null;
}

export function NewsContent({ initialTicker, highlightArticleId }: NewsContentProps = {}) {
  const { t } = useTranslation();
  const { state: windowState, updateState: updateWindowState } = useWindowState<NewsWindowState>();
  const windowId = useCurrentWindowId();

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
  const NEWS_COLS = ['headline', 'sentiment', 'date', 'time', 'ticker', 'source'] as const;
  const COL_LABELS: Record<string, string> = { ticker: t('news.ticker'), headline: t('news.headline'), sentiment: t('news.sentiment'), date: t('news.date'), time: t('news.time'), source: t('news.source') };
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [newsMenu, setNewsMenu] = useState<{ x: number; y: number } | null>(null);
  const [colPanel, setColPanel] = useState<{ x: number; y: number } | null>(null);
  const newsMenuRef = useRef<HTMLDivElement>(null);
  const colPanelRef = useRef<HTMLDivElement>(null);
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const virtuosoRef = useRef<any>(null);

  // ================================================================
  // HISTORY STATE (búsqueda unificada sobre lo persistido; lo vivo no se para)
  // ================================================================
  const [historyResults, setHistoryResults] = useState<NewsArticle[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyCursor, setHistoryCursor] = useState<{ before: string; before_id: string } | null>(null);

  // ================================================================
  // FILTROS: capa por-ventana + capa global (store persistido)
  // ================================================================
  const [windowFilters, setWindowFilters] = useState<NewsWindowFilters>(EMPTY_WINDOW_FILTERS);
  const [searchText, setSearchText] = useState<string>(windowState.search || '');
  const [showFilters, setShowFilters] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const gFeeds = useNewsFiltersStore(s => s.feeds);
  const gPubInc = useNewsFiltersStore(s => s.publishersInclude);
  const gPubExc = useNewsFiltersStore(s => s.publishersExclude);
  const gIncludes = useNewsFiltersStore(s => s.includes);
  const gExcludes = useNewsFiltersStore(s => s.excludes);
  const gClassAction = useNewsFiltersStore(s => s.classAction);
  const globalFilters: NewsGlobalFilters = useMemo(() => ({
    feeds: gFeeds,
    publishersInclude: gPubInc,
    publishersExclude: gPubExc,
    includes: gIncludes,
    excludes: gExcludes,
    classAction: gClassAction,
  }), [gFeeds, gPubInc, gPubExc, gIncludes, gExcludes, gClassAction]);

  const activeFilterCount = countGlobalFilters(globalFilters) + countWindowFilters(windowFilters);

  // "/" enfoca la búsqueda (si no estás escribiendo en otro input)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/') return;
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;
      e.preventDefault();
      searchInputRef.current?.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  // Persist ticker + search changes
  useEffect(() => {
    updateWindowState({ ticker: tickerFilter, search: searchText });
  }, [tickerFilter, searchText, updateWindowState]);

  // ================================================================
  // LIVE MODE: filtrado memoizado
  // ================================================================
  const filteredNews = useMemo(() => {
    const upperFilter = tickerFilter.toUpperCase();
    const textFilter = searchText.trim().toLowerCase();
    return articles.filter(article => {
      if (tickerFilter && !article.tickers?.some(t => t.toUpperCase() === upperFilter)) return false;
      if (!matchesGlobalFilters(article, globalFilters)) return false;
      if (!matchesWindowLayer(article, windowFilters)) return false;
      if (textFilter
        && !article.title.toLowerCase().includes(textFilter)
        && !(article.teaser || '').toLowerCase().includes(textFilter)) return false;
      return true;
    });
  }, [articles, tickerFilter, searchText, globalFilters, windowFilters]);

  // Publishers observados en el feed cargado (para el panel de filtros)
  const publisherEntries: PublisherEntry[] = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of articles) {
      const name = (a.author || '').trim();
      if (!name) continue;
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [articles]);

  const liveCount = useMemo(() =>
    articles.filter(a => a.isLive).length
    , [articles]);

  // ¿Hay criterios que ameritan consultar el pasado?
  const historyOn = useMemo(() =>
    searchText.trim().length >= 2 || !!tickerFilter || countWindowFilters(windowFilters) > 0,
    [searchText, tickerFilter, windowFilters]);

  // Una sola lista: lo vivo filtrado + el histórico, dedupe por id y por url
  const displayedArticles = useMemo(() => {
    if (!historyOn || historyResults.length === 0) return filteredNews;
    const seen = new Set<string>();
    const out: NewsArticle[] = [];
    for (const a of [...filteredNews, ...historyResults]) {
      const idKey = String(a.id ?? a.benzinga_id ?? a.url);
      const urlKey = a.url || idKey;
      if (seen.has(idKey) || seen.has(urlKey)) continue;
      seen.add(idKey);
      seen.add(urlKey);
      out.push(a);
    }
    out.sort((x, y) => (Date.parse(y.published) || 0) - (Date.parse(x.published) || 0));
    return out;
  }, [historyOn, filteredNews, historyResults]);

  // ================================================================
  // HISTORY ENGINE — consulta lo persistido; lo vivo nunca se detiene
  // ================================================================
  const buildHistoryParams = useCallback((cursor?: { before: string; before_id: string } | null) => {
    const params = new URLSearchParams();
    const q = searchText.trim();
    if (q.length >= 2) params.set('q', q);
    if (tickerFilter) params.set('tickers', tickerFilter);
    if (windowFilters.channels) params.set('channels', windowFilters.channels);
    if (windowFilters.tags) params.set('tags', windowFilters.tags);
    if (windowFilters.author) params.set('publisher', windowFilters.author);
    if (windowFilters.dateFrom) params.set('date_from', windowFilters.dateFrom);
    if (windowFilters.dateTo) params.set('date_to', windowFilters.dateTo);
    if (globalFilters.feeds.length) params.set('sources', globalFilters.feeds.join(','));
    if (cursor) {
      params.set('before', cursor.before);
      params.set('before_id', cursor.before_id);
    }
    params.set('limit', '150');
    return params;
  }, [searchText, tickerFilter, windowFilters, globalFilters.feeds]);

  const runHistorySearch = useCallback(async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await fetch(`${apiUrl}/news/api/v1/news/history?${buildHistoryParams()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setHistoryResults(data.results || []);
      setHistoryCursor(data.next_cursor || null);
    } catch (e) {
      console.error('[NewsContent] History search error:', e);
      setHistoryError('unavailable');
      setHistoryResults([]);
      setHistoryCursor(null);
    } finally {
      setHistoryLoading(false);
    }
  }, [buildHistoryParams]);

  const loadMoreHistory = useCallback(async () => {
    if (!historyCursor || historyLoadingMore) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    setHistoryLoadingMore(true);
    try {
      const response = await fetch(`${apiUrl}/news/api/v1/news/history?${buildHistoryParams(historyCursor)}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setHistoryResults(prev => [...prev, ...(data.results || [])]);
      setHistoryCursor(data.next_cursor || null);
    } catch (e) {
      console.error('[NewsContent] History load more error:', e);
    } finally {
      setHistoryLoadingMore(false);
    }
  }, [historyCursor, historyLoadingMore, buildHistoryParams]);

  // Debounce: 400ms tras el último cambio de criterios; sin criterios, se limpia
  useEffect(() => {
    if (!historyOn) {
      setHistoryResults([]);
      setHistoryCursor(null);
      setHistoryError(null);
      return;
    }
    const timer = setTimeout(runHistorySearch, 400);
    return () => clearTimeout(timer);
  }, [historyOn, runHistorySearch]);

  // Aplicar configuración del panel de filtros (capa por-ventana;
  // la capa global la guarda el propio panel en el store)
  const handleApplyFilters = useCallback((next: NewsWindowFilters) => {
    setWindowFilters(next);
    setShowFilters(false);
  }, []);

  // Limpia la capa por-ventana (los filtros globales se mantienen)
  const handleClearAll = useCallback(() => {
    setTickerInputValue('');
    setTickerFilter('');
    setSearchText('');
    setWindowFilters(EMPTY_WINDOW_FILTERS);
  }, []);

  // ================================================================
  // LIVE MODE: Infinite scroll
  // ================================================================
  const loadMoreRef = useRef(false);
  const handleEndReached = useCallback(async () => {
    if (historyOn) { loadMoreHistory(); return; } // hacia el pasado persistido
    if (loadMoreRef.current || !hasMore || isLoadingMore) return;
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
  }, [historyOn, loadMoreHistory, hasMore, isLoadingMore, articles.length, setLoadingMore, loadOlderArticles]);

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
  if (!stats.initialLoadComplete && articles.length === 0) {
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
          <span className="w-16 shrink-0" />
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
                  {displayChannels(selectedArticle.channels)}
                </span>
              )}
              {selectedArticle.sentiment && (
                <span className="flex items-center gap-1">
                  <SentimentBadge sentiment={selectedArticle.sentiment} />
                  <span className="capitalize">{selectedArticle.sentiment}</span>
                </span>
              )}
            </div>

            {/* Sentimiento por ticker (insights de la fuente) */}
            {selectedArticle.insights && selectedArticle.insights.length > 0 && (
              <div className="mb-4 border border-border rounded-lg p-3 bg-surface-hover/50">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-fg mb-2">
                  {t('news.sentimentByTicker')}
                </div>
                <div className="space-y-1.5">
                  {selectedArticle.insights.map((ins, i) => (
                    <div key={`${ins.ticker}-${i}`} className="text-xs">
                      <span className="font-mono font-semibold text-primary mr-1.5">{ins.ticker}</span>
                      <SentimentBadge sentiment={ins.sentiment} />
                      {ins.reasoning && (
                        <span className="text-foreground/75 ml-1.5">{ins.reasoning}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {hasBody ? (
              <div
                className="prose prose-sm max-w-none text-foreground leading-relaxed"
                dangerouslySetInnerHTML={{ __html: selectedArticle.body || '' }}
              />
            ) : (
              <div className="text-foreground leading-relaxed">
                {hasTeaser && (
                  <p className="text-[13px] leading-relaxed text-muted-fg mb-4">
                    {decodeHtmlEntities(selectedArticle.teaser || '')}
                  </p>
                )}
                {/* Cuerpo extraído en servidor y renderizado nativo (estilo terminal) */}
                <ExtractedBody url={selectedArticle.url} />
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
    <div className="relative flex flex-col h-full bg-surface" style={{ fontFamily }}>
      {/* Filters panel overlay */}
      {showFilters && (
        <NewsFiltersPanel
          windowValue={windowFilters}
          publishers={publisherEntries}
          fontFamily={fontFamily}
          onApply={handleApplyFilters}
          onCancel={() => setShowFilters(false)}
        />
      )}

      {/* Header Row 1 */}
      <div className={`flex items-center justify-between px-2 py-1 border-b border-border bg-surface-hover`}>
        <div className="flex items-center gap-2">
          {/* Ticker Filter (nuestro buscador, se mantiene tal cual) */}
          <form
            onSubmit={(e) => { e.preventDefault(); handleApplyFilter(); }}
            className="flex items-center gap-1"
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

          {/* Búsqueda de texto (por ventana): "/" para enfocar, Esc limpia */}
          <div className="flex items-center gap-0.5 ml-1 pl-2 border-l border-border">
            <input
              ref={searchInputRef}
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') { setSearchText(''); (e.target as HTMLInputElement).blur(); } }}
              placeholder={t('news.filters.searchPlaceholder')}
              className="w-36 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface text-foreground"
              style={{ fontFamily }}
            />
            {searchText && (
              <button onClick={() => setSearchText('')}
                className="p-0.5 text-muted-fg hover:text-foreground/80" title={t('common.clear')}>
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>

          {(tickerFilter || searchText || countWindowFilters(windowFilters) > 0) && (
            <button onClick={handleClearAll}
              className="px-1.5 py-0.5 text-[10px] rounded border border-border text-foreground/80 hover:bg-surface-hover transition-colors"
              style={{ fontFamily }}>
              {t('common.clear')}
            </button>
          )}

          <div className="flex items-center gap-1 ml-1 pl-2 border-l border-border">
            <StreamPauseButton isPaused={isPaused} onToggle={handleTogglePause} size="sm" />
            <SquawkButton
              isEnabled={squawk.isEnabled}
              isSpeaking={squawk.isSpeaking}
              queueSize={squawk.queueSize}
              onToggle={squawk.toggleEnabled}
              size="sm"
            />
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setShowFilters(v => !v)}
            className={`flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
              activeFilterCount > 0
                ? 'border-blue-500/50 text-blue-600 dark:text-blue-400 bg-blue-500/10'
                : 'border-border text-foreground/80 hover:bg-surface-hover'
            }`}
            style={{ fontFamily }}
            title={t('news.filters.title')}
          >
            <SlidersHorizontal className="w-3 h-3" />
            {activeFilterCount > 0 ? `${activeFilterCount} ${t('news.filters.filters')}` : t('news.filters.filters')}
          </button>

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

          <button ref={menuBtnRef} onClick={handleNewsMenuBtn}
            className="p-0.5 rounded text-muted-fg hover:text-foreground/80 hover:bg-surface-hover transition-colors" title="Menu">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
            </svg>
          </button>
        </div>
      </div>

      {/* Estado de búsqueda unificada: histórico + live simultáneos */}
      {historyOn && (
        <div className="flex items-center gap-1.5 flex-wrap px-2 py-1 bg-surface-hover border-b border-border text-[10px]" style={{ fontFamily }}>
          {historyLoading ? (
            <span className="flex items-center gap-1 text-foreground/80">
              <Loader2 className="w-3 h-3 animate-spin" /> {t('news.searching')}
            </span>
          ) : (
            <span className="text-foreground/80">
              {displayedArticles.length} {t('news.filters.results')}
              {historyResults.length > 0 && <span className="text-muted-fg"> · {historyResults.length} hist</span>}
            </span>
          )}
          <span className="flex items-center gap-1 text-emerald-600">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" /> live
          </span>
          {(windowFilters.dateFrom || windowFilters.dateTo) && (
            <span className="px-1.5 py-0.5 rounded border border-border text-foreground/80">
              {windowFilters.dateFrom || '…'} → {windowFilters.dateTo || '…'}
            </span>
          )}
          {windowFilters.tags && <span className="px-1.5 py-0.5 rounded border border-border text-foreground/80">{windowFilters.tags}</span>}
          {windowFilters.author && <span className="px-1.5 py-0.5 rounded border border-border text-foreground/80">{windowFilters.author}</span>}
          {windowFilters.channels && <span className="px-1.5 py-0.5 rounded border border-border text-foreground/80">{windowFilters.channels}</span>}
          {historyError && (
            <span className="text-amber-500" title="El histórico no respondió; se muestra solo lo cargado en vivo">
              {t('common.offline')}: hist
            </span>
          )}
          <button onClick={() => setShowFilters(true)}
            className="ml-auto px-1.5 py-0.5 rounded border border-border text-foreground/80 hover:bg-surface transition-colors">
            {t('news.filters.editFilters')}
          </button>
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
            <span className="text-[10px] text-muted-fg">{NEWS_COLS.length - hiddenCols.size}/{NEWS_COLS.length}</span>
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

      {/* Virtualized Content (lista única, vacío inline) */}
      {displayedArticles.length === 0 && !historyLoading ? (
        <div className="flex flex-1 items-center justify-center bg-surface">
          <span className="text-sm text-muted-fg">{t('news.noSearchResults')}</span>
        </div>
      ) : (
        <div className="flex-1 flex flex-col">
          {newsViewMode === 'table' ? (
            <TableVirtuoso
              ref={virtuosoRef}
              style={{ height: '100%' }}
              data={displayedArticles}
              overscan={20}
              endReached={handleEndReached}
              fixedHeaderContent={() => (
                <tr className="text-left uppercase tracking-wide text-foreground/80 bg-surface-inset">
                  <th className="px-1.5 py-1 font-medium text-[11px]" style={{ fontFamily }}>{t('news.headline')}</th>
                  {!hiddenCols.has('sentiment') && <th className="px-1 py-1 font-medium w-10 text-center text-[11px]" style={{ fontFamily }} title={t('news.sentiment')}>{t('news.sentiment')}</th>}
                  {!hiddenCols.has('date') && <th className="px-1.5 py-1 font-medium w-20 text-center text-[11px]" style={{ fontFamily }}>{t('news.date')}</th>}
                  {!hiddenCols.has('time') && <th className="px-1.5 py-1 font-medium w-16 text-center text-[11px]" style={{ fontFamily }}>{t('news.time')}</th>}
                  {!hiddenCols.has('ticker') && <th className="px-1.5 py-1 font-medium w-14 text-center text-[11px]" style={{ fontFamily }}>{t('news.ticker')}</th>}
                  {!hiddenCols.has('source') && <th className="px-1.5 py-1 font-medium w-28 text-[11px]" style={{ fontFamily }}>{t('news.source')}</th>}
                </tr>
              )}
              itemContent={(index, article) => {
                const dt = formatDateTime(article.published);
                const displayTicker = tickerFilter
                  ? (article.tickers?.find(t => t.toUpperCase() === tickerFilter) || article.tickers?.[0] || '—')
                  : (article.tickers?.[0] || '—');
                const hasMultipleTickers = (article.tickers?.length || 0) > 1;
                const articleId = String(article.benzinga_id || article.id || '');
                const isHighlighted = highlightedId && highlightedId.includes(articleId);

                return (
                  <>
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
                    {!hiddenCols.has('sentiment') && (
                      <td className={`px-1 py-0.5 text-center text-[11px] cursor-pointer ${isHighlighted ? 'bg-rose-500/15' : article.isLive ? 'bg-emerald-500/10' : ''}`}
                        style={{ fontFamily, height: ROW_HEIGHT }} onClick={() => setSelectedArticle(article)}
                        title={article.sentiment || undefined}>
                        <SentimentBadge sentiment={article.sentiment} />
                      </td>
                    )}
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
                    {(isLoadingMore || historyLoadingMore) && (
                      <tr>
                        <td colSpan={NEWS_COLS.length - hiddenCols.size} className="text-center py-2 text-xs text-muted-fg" style={{ fontFamily }}>
                          Loading more...
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
                endReached={handleEndReached}
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
              {(isLoadingMore || historyLoadingMore) && (
                <div className="text-center py-2 text-xs text-muted-fg" style={{ fontFamily }}>
                  Loading more...
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Info panel: auditoría de filtros activos (por ventana vs globales) */}
      {showInfo && (
        <div className="absolute bottom-8 left-2 z-10 bg-surface border border-border rounded-lg shadow-xl p-3 w-80 text-[10px] space-y-2" style={{ fontFamily }}>
          <div>
            <div className="font-semibold text-foreground mb-1 uppercase tracking-wide text-[9px]">{t('news.filters.thisWindow')}</div>
            <div className="space-y-0.5 text-foreground/80">
              <div>{t('common.search')}: {searchText || '—'}</div>
              <div>{t('news.ticker')}: {tickerFilter || '—'}</div>
              <div>{t('news.filters.dateRange')}: {(windowFilters.dateFrom || windowFilters.dateTo) ? `${windowFilters.dateFrom || '…'} → ${windowFilters.dateTo || '…'}` : t('news.filters.all')}</div>
              {windowFilters.tags && <div>{t('news.tags')}: {windowFilters.tags}</div>}
              {windowFilters.author && <div>{t('news.author')}: {windowFilters.author}</div>}
              {windowFilters.channels && <div>{t('news.channels')}: {windowFilters.channels}</div>}
            </div>
          </div>
          <div className="border-t border-border-subtle pt-1.5">
            <div className="font-semibold text-foreground mb-1 uppercase tracking-wide text-[9px]">{t('news.filters.global')}</div>
            <div className="space-y-0.5 text-foreground/80">
              <div>{t('news.filters.sources')}: {globalFilters.feeds.length ? globalFilters.feeds.join(', ') : t('news.filters.all')}</div>
              <div>
                {t('news.filters.publishers')}: {(globalFilters.publishersInclude.length || globalFilters.publishersExclude.length)
                  ? [...globalFilters.publishersInclude.map(p => `✓ ${p}`), ...globalFilters.publishersExclude.map(p => `✗ ${p}`)].join(', ')
                  : t('news.filters.all')}
              </div>
              <div>{t('news.filters.includesLabel')}: {globalFilters.includes.join(', ') || '—'}</div>
              <div>{t('news.filters.excludesLabel')}: {globalFilters.excludes.join(', ') || '—'}</div>
              <div>{t('news.filters.classAction')}: {
                globalFilters.classAction === 'show' ? t('news.filters.caShow')
                  : globalFilters.classAction === 'hide' ? t('news.filters.caHide')
                    : t('news.filters.caOnly')
              }</div>
            </div>
          </div>
        </div>
      )}

      {/* Footer: estado + resultados */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-border bg-surface-hover text-[10px] shrink-0" style={{ fontFamily }}>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowInfo(v => !v)}
            className={`px-1.5 py-0.5 rounded border transition-colors ${showInfo ? 'border-blue-500/50 text-blue-600 dark:text-blue-400 bg-blue-500/10' : 'border-border text-foreground/80 hover:bg-surface'}`}>
            Info {showInfo ? '˅' : '˄'}
          </button>
          <div className="flex items-center gap-1">
            <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-muted'}`} />
            <span className={isConnected ? 'text-emerald-600' : 'text-muted-fg'}>
              {isConnected ? t('common.live') : t('common.offline')}
            </span>
          </div>
          {liveCount > 0 && <span className="text-emerald-600">({liveCount} live)</span>}
          {isPaused && pausedBuffer.length > 0 && (
            <span className="text-muted-fg">(+{pausedBuffer.length})</span>
          )}
          {tickerFilter && (
            <span className="px-1 py-0.5 bg-blue-500/15 text-blue-700 dark:text-blue-400 rounded">{tickerFilter}</span>
          )}
        </div>
        <span className="text-foreground/80">
          {t('news.filters.showing', { n: displayedArticles.length })}
          {!historyOn && (tickerFilter || activeFilterCount > 0) ? ` / ${articles.length}` : ''}
        </span>
      </div>
    </div>
  );
}
