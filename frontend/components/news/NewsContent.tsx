'use client';

/**
 * NewsContent - Componente de PRESENTACIÓN de noticias
 * 
 * Arquitectura Enterprise:
 * - SOLO consume del NewsStore global
 * - NO tiene lógica de ingesta (WebSocket, fetch, etc.)
 * - La ingesta se hace en NewsProvider (montado globalmente)
 * - VIRTUALIZADO con react-virtuoso para rendimiento óptimo
 * 
 * Beneficios:
 * - Puede montarse/desmontarse sin perder noticias
 * - Filtros son solo vistas sobre los datos del store
 * - Mejor separación de responsabilidades
 * - Escala a miles de noticias sin memory leaks
 */

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { TableVirtuoso } from 'react-virtuoso';
import { useNewsStore, NewsArticle, selectArticles, selectIsPaused, selectIsConnected } from '@/stores/useNewsStore';
import { useSquawk } from '@/contexts/SquawkContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { TickerSearch } from '@/components/common/TickerSearch';
import { ExternalLink } from 'lucide-react';
import { getUserTimezone } from '@/lib/date-utils';
import { useWindowState } from '@/contexts/FloatingWindowContext';

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

// Decodifica entidades HTML como &#39; &amp; &quot; etc.
// Memoizado para evitar crear elementos DOM innecesarios
const htmlDecodeCache = new Map<string, string>();
function decodeHtmlEntities(text: string): string {
  if (!text) return text;
  if (typeof window === 'undefined') return text;

  // Check cache first
  const cached = htmlDecodeCache.get(text);
  if (cached !== undefined) return cached;

  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  const decoded = textarea.value;

  // Cache result (limit cache size to prevent memory issues)
  if (htmlDecodeCache.size > 5000) {
    // Clear oldest entries (simple approach: clear all when too big)
    htmlDecodeCache.clear();
  }
  htmlDecodeCache.set(text, decoded);

  return decoded;
}

interface NewsContentProps {
  initialTicker?: string;
  highlightArticleId?: string;
}

// Row height for virtualization
const ROW_HEIGHT = 24;

export function NewsContent({ initialTicker, highlightArticleId }: NewsContentProps = {}) {
  const { t } = useTranslation();
  const { state: windowState, updateState: updateWindowState } = useWindowState<NewsWindowState>();

  // Fuente del usuario
  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];

  // Use persisted ticker
  const savedTicker = windowState.ticker || initialTicker || '';

  // ================================================================
  // CONSUMIR DEL STORE GLOBAL
  // ================================================================
  const articles = useNewsStore(selectArticles);
  const isPaused = useNewsStore(selectIsPaused);
  const isConnected = useNewsStore(selectIsConnected);
  const pausedBuffer = useNewsStore((state) => state.pausedBuffer);
  const stats = useNewsStore((state) => state.stats);

  // Acciones del store
  const setPaused = useNewsStore((state) => state.setPaused);
  const resumeWithBuffer = useNewsStore((state) => state.resumeWithBuffer);

  // Squawk Service (para UI de botón, la lógica de speak está en NewsProvider)
  const squawk = useSquawk();

  // ================================================================
  // ESTADO LOCAL (solo UI)
  // ================================================================
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [tickerFilter, setTickerFilter] = useState<string>(savedTicker);
  const [tickerInputValue, setTickerInputValue] = useState<string>(savedTicker);
  const [highlightedId, setHighlightedId] = useState<string | null>(highlightArticleId || null);

  // Ref para virtuoso (para scroll programático)
  const virtuosoRef = useRef<any>(null);

  // Persist ticker changes (including when cleared)
  useEffect(() => {
    updateWindowState({ ticker: tickerFilter });
  }, [tickerFilter, updateWindowState]);

  // ================================================================
  // FILTRADO (memoizado) - Sin paginación, virtualización maneja todo
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

  // ================================================================
  // EFECTOS
  // ================================================================

  // Scroll al artículo destacado
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

  // ================================================================
  // HANDLERS
  // ================================================================

  const handleTogglePause = useCallback(() => {
    if (isPaused) {
      resumeWithBuffer();
    } else {
      setPaused(true);
    }
  }, [isPaused, setPaused, resumeWithBuffer]);

  const handleApplyFilter = useCallback(() => {
    const newFilter = tickerInputValue.toUpperCase().trim();
    setTickerFilter(newFilter);
  }, [tickerInputValue]);

  // Format dates in Eastern Time (ET) - standard for US markets
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
  // LOADING STATE (solo en carga inicial)
  // ================================================================
  if (!stats.initialLoadComplete) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3" />
          <p className="text-slate-600 text-sm">{t('news.loadingNews')}</p>
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
      <div className="flex flex-col h-full bg-white">
        <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
          <button
            onClick={() => setSelectedArticle(null)}
            className="px-2 py-1 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 text-xs font-medium flex items-center gap-1"
          >
            ← {t('common.back')}
          </button>
          <div className="text-xs text-slate-600 font-mono flex items-center gap-2">
            {ticker && (
              <>
                <span className="font-semibold text-blue-600">{ticker}</span>
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
            <h1 className="text-lg font-semibold text-slate-900 mb-3">
              {decodeHtmlEntities(selectedArticle.title)}
            </h1>

            <div className="flex items-center gap-3 text-xs text-slate-500 mb-4">
              <span>By {selectedArticle.author}</span>
              {selectedArticle.channels && selectedArticle.channels.length > 0 && (
                <span className="text-slate-400">
                  {selectedArticle.channels.join(', ')}
                </span>
              )}
            </div>

            {hasBody ? (
              <div
                className="prose prose-sm max-w-none text-slate-700 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: selectedArticle.body || '' }}
              />
            ) : hasTeaser ? (
              <div className="text-slate-700 leading-relaxed">
                <p className="mb-4">{decodeHtmlEntities(selectedArticle.teaser || '')}</p>
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium text-sm"
                >
                  {t('news.readMore')}
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-slate-500 mb-4">{t('news.fullContentNotAvailable')}</p>
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
                >
                  <ExternalLink className="w-4 h-4" />
                  {t('news.openOnBenzinga')}
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ================================================================
  // MAIN VIEW - VIRTUALIZED TABLE
  // ================================================================
  return (
    <div className="flex flex-col h-full bg-white" style={{ fontFamily }}>
      {/* Header - Compacto */}
      <div className="flex items-center justify-between px-2 py-1 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center gap-2">
          {/* Connection Status */}
          <div className="flex items-center gap-1">
            <div
              className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span className={`text-[10px] ${isConnected ? 'text-emerald-600' : 'text-slate-500'}`} style={{ fontFamily }}>
              {isConnected ? t('common.live') : t('common.offline')}
            </span>
          </div>

          {/* Pause Button */}
          <StreamPauseButton isPaused={isPaused} onToggle={handleTogglePause} size="sm" />

          {/* Squawk Button */}
          <SquawkButton
            isEnabled={squawk.isEnabled}
            isSpeaking={squawk.isSpeaking}
            queueSize={squawk.queueSize}
            onToggle={squawk.toggleEnabled}
            size="sm"
          />

          {/* Paused Buffer Count */}
          {isPaused && pausedBuffer.length > 0 && (
            <span className="text-amber-600 text-[10px]" style={{ fontFamily }}>(+{pausedBuffer.length})</span>
          )}

          {/* Ticker Filter */}
          <form
            onSubmit={(e) => { e.preventDefault(); handleApplyFilter(); }}
            className="flex items-center gap-1 ml-2 pl-2 border-l border-slate-300"
          >
            <TickerSearch
              value={tickerInputValue}
              onChange={(value) => {
                setTickerInputValue(value);
                if (!value) {
                  setTickerFilter('');
                }
              }}
              onSelect={(ticker) => {
                setTickerInputValue(ticker.symbol);
                setTickerFilter(ticker.symbol.toUpperCase());
              }}
              placeholder={t('news.ticker')}
              className="w-20"
            />
            <button
              type="submit"
              className="px-2 py-0.5 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-700 transition-colors"
              style={{ fontFamily }}
            >
              {t('common.filter')}
            </button>
          </form>
        </div>

        <div className="flex items-center gap-2">
          {/* Stats */}
          <div className="flex items-center gap-1.5 text-[10px]" style={{ fontFamily }}>
            {tickerFilter && (
              <span className="px-1 py-0.5 bg-blue-100 text-blue-700 rounded">
                {tickerFilter}
              </span>
            )}
            <span className="text-slate-600">
              {filteredNews.length}{tickerFilter ? ` / ${articles.length}` : ''}
            </span>
            {liveCount > 0 && <span className="text-emerald-600">({liveCount} live)</span>}
          </div>
        </div>
      </div>

      {/* Virtualized Table */}
      <div className="flex-1">
        <TableVirtuoso
          ref={virtuosoRef}
          style={{ height: '100%' }}
          data={filteredNews}
          overscan={20}
          fixedHeaderContent={() => (
            <tr className="text-left text-slate-600 uppercase tracking-wide bg-slate-100">
              <th className="px-1.5 py-1 font-medium w-14 text-center text-[11px]" style={{ fontFamily }}>{t('news.ticker')}</th>
              <th className="px-1.5 py-1 font-medium text-[11px]" style={{ fontFamily }}>{t('news.headline')}</th>
              <th className="px-1.5 py-1 font-medium w-20 text-center text-[11px]" style={{ fontFamily }}>{t('news.date')}</th>
              <th className="px-1.5 py-1 font-medium w-16 text-center text-[11px]" style={{ fontFamily }}>{t('news.time')}</th>
              <th className="px-1.5 py-1 font-medium w-28 text-[11px]" style={{ fontFamily }}>{t('news.source')}</th>
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
                {/* Ticker - Primera columna */}
                <td
                  className={`px-1.5 py-0.5 text-center text-[11px] cursor-pointer ${isHighlighted
                      ? 'bg-rose-100'
                      : article.isLive ? 'bg-emerald-50/50' : ''
                    }`}
                  style={{ fontFamily, height: ROW_HEIGHT }}
                  onClick={() => setSelectedArticle(article)}
                >
                  <span className="text-blue-600 font-semibold">
                    {displayTicker}
                    {hasMultipleTickers && (
                      <span className="text-slate-400 text-[9px] ml-0.5">
                        +{(article.tickers?.length || 1) - 1}
                      </span>
                    )}
                  </span>
                </td>
                {/* Headline */}
                <td
                  className={`px-1.5 py-0.5 text-[11px] cursor-pointer ${isHighlighted
                      ? 'bg-rose-100'
                      : article.isLive ? 'bg-emerald-50/50' : ''
                    }`}
                  style={{ fontFamily, height: ROW_HEIGHT }}
                  onClick={() => setSelectedArticle(article)}
                >
                  <div className="flex items-center gap-1">
                    {article.isLive && (
                      <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse flex-shrink-0" />
                    )}
                    <span className="text-slate-800 truncate" style={{ maxWidth: '450px' }}>
                      {decodeHtmlEntities(article.title)}
                    </span>
                  </div>
                </td>
                {/* Date */}
                <td
                  className={`px-1.5 py-0.5 text-center text-slate-500 text-[11px] cursor-pointer ${isHighlighted
                      ? 'bg-rose-100'
                      : article.isLive ? 'bg-emerald-50/50' : ''
                    }`}
                  style={{ fontFamily, height: ROW_HEIGHT }}
                  onClick={() => setSelectedArticle(article)}
                >
                  {dt.date}
                </td>
                {/* Time */}
                <td
                  className={`px-1.5 py-0.5 text-center text-slate-500 text-[11px] cursor-pointer ${isHighlighted
                      ? 'bg-rose-100'
                      : article.isLive ? 'bg-emerald-50/50' : ''
                    }`}
                  style={{ fontFamily, height: ROW_HEIGHT }}
                  onClick={() => setSelectedArticle(article)}
                >
                  {dt.time}
                </td>
                {/* Source */}
                <td
                  className={`px-1.5 py-0.5 text-slate-500 truncate text-[11px] cursor-pointer ${isHighlighted
                      ? 'bg-rose-100'
                      : article.isLive ? 'bg-emerald-50/50' : ''
                    }`}
                  style={{ fontFamily, maxWidth: '110px', height: ROW_HEIGHT }}
                  onClick={() => setSelectedArticle(article)}
                >
                  {article.author}
                </td>
              </>
            );
          }}
          components={{
            Table: ({ style, ...props }) => (
              <table
                {...props}
                style={{ ...style, width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}
                className="text-[11px]"
              />
            ),
            TableHead: React.forwardRef(({ style, ...props }, ref) => (
              <thead
                {...props}
                ref={ref}
                style={{ ...style, position: 'sticky', top: 0, zIndex: 1 }}
              />
            )),
            TableRow: ({ style, ...props }) => (
              <tr
                {...props}
                style={{ ...style }}
                className="hover:bg-slate-50 transition-colors border-b border-slate-100"
              />
            ),
          }}
        />
      </div>
    </div>
  );
}
