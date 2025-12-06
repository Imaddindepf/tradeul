'use client';

/**
 * NewsContent - Componente de PRESENTACIÓN de noticias
 * 
 * Arquitectura Enterprise:
 * - SOLO consume del NewsStore global
 * - NO tiene lógica de ingesta (WebSocket, fetch, etc.)
 * - La ingesta se hace en NewsProvider (montado globalmente)
 * 
 * Beneficios:
 * - Puede montarse/desmontarse sin perder noticias
 * - Filtros son solo vistas sobre los datos del store
 * - Mejor separación de responsabilidades
 */

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNewsStore, NewsArticle, selectArticles, selectIsPaused, selectIsConnected } from '@/stores/useNewsStore';
import { useSquawkService } from '@/hooks/useSquawkService';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { TickerSearch } from '@/components/common/TickerSearch';
import { ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react';

// Decodifica entidades HTML como &#39; &amp; &quot; etc.
function decodeHtmlEntities(text: string): string {
  if (!text) return text;
  if (typeof window === 'undefined') return text;
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

interface NewsContentProps {
  initialTicker?: string;
  highlightArticleId?: string;
}

const ITEMS_PER_PAGE = 200;

export function NewsContent({ initialTicker, highlightArticleId }: NewsContentProps = {}) {
  const { t } = useTranslation();
  
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
  const squawk = useSquawkService();
  
  // ================================================================
  // ESTADO LOCAL (solo UI)
  // ================================================================
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [tickerFilter, setTickerFilter] = useState<string>(initialTicker || '');
  const [tickerInputValue, setTickerInputValue] = useState<string>(initialTicker || '');
  const [currentPage, setCurrentPage] = useState(1);
  const [highlightedId, setHighlightedId] = useState<string | null>(highlightArticleId || null);
  const highlightRowRef = useRef<HTMLTableRowElement | null>(null);

  // ================================================================
  // FILTRADO Y PAGINACIÓN (memoizado)
  // ================================================================
  const filteredNews = useMemo(() => {
    if (!tickerFilter) return articles;
    const upperFilter = tickerFilter.toUpperCase();
    return articles.filter(article =>
      article.tickers?.some(t => t.toUpperCase() === upperFilter)
    );
  }, [articles, tickerFilter]);

  const totalPages = Math.ceil(filteredNews.length / ITEMS_PER_PAGE);
  
  const paginatedNews = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    return filteredNews.slice(start, end);
  }, [filteredNews, currentPage]);

  const liveCount = useMemo(() => 
    articles.filter(a => a.isLive).length
  , [articles]);

  // ================================================================
  // EFECTOS
  // ================================================================
  
  // Scroll al artículo destacado
  useEffect(() => {
    if (highlightedId && highlightRowRef.current) {
      highlightRowRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const timer = setTimeout(() => setHighlightedId(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [highlightedId, articles]);

  // Reset página si excede total
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(1);
    }
  }, [currentPage, totalPages]);

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
    setCurrentPage(1);
  }, [tickerInputValue]);

  const formatDateTime = useCallback((isoString: string) => {
    try {
      const d = new Date(isoString);
      return {
        date: d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }),
        time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
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
  // MAIN VIEW - TABLE
  // ================================================================
  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center gap-3">
          {/* Connection Status */}
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span className={`text-xs font-medium ${isConnected ? 'text-emerald-600' : 'text-slate-500'}`}>
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
            <span className="text-amber-600 text-xs font-medium">(+{pausedBuffer.length})</span>
          )}

          {/* Ticker Filter */}
          <form
            onSubmit={(e) => { e.preventDefault(); handleApplyFilter(); }}
            className="flex items-center gap-1.5 ml-3 pl-3 border-l border-slate-300"
          >
            <TickerSearch
              value={tickerInputValue}
              onChange={(value) => {
                setTickerInputValue(value);
                if (!value) {
                  setTickerFilter('');
                  setCurrentPage(1);
                }
              }}
              onSelect={(ticker) => {
                setTickerInputValue(ticker.symbol);
                setTickerFilter(ticker.symbol.toUpperCase());
                setCurrentPage(1);
              }}
              placeholder={t('news.ticker')}
              className="w-24"
            />
            <button
              type="submit"
              className="px-2.5 py-0.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 font-medium transition-colors"
            >
              {t('common.filter')}
            </button>
          </form>
        </div>

        <div className="flex items-center gap-3">
          {/* Stats */}
          <div className="flex items-center gap-2 text-xs">
            {tickerFilter && (
              <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded font-mono font-medium">
                {tickerFilter}
              </span>
            )}
            <span className="text-slate-600 font-mono">
              {filteredNews.length}{tickerFilter ? ` / ${articles.length}` : ''}
            </span>
            {liveCount > 0 && <span className="text-emerald-600">({liveCount} live)</span>}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center gap-1 border-l border-slate-300 pl-3">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 rounded hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4 text-slate-600" />
              </button>
              <span className="text-xs text-slate-600 font-mono min-w-[60px] text-center">
                {currentPage} / {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1 rounded hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4 text-slate-600" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="bg-slate-100 sticky top-0">
            <tr className="text-left text-slate-600 uppercase tracking-wide">
              <th className="px-2 py-1.5 font-medium">{t('news.headline')}</th>
              <th className="px-2 py-1.5 font-medium w-24 text-center">{t('news.date')}</th>
              <th className="px-2 py-1.5 font-medium w-20 text-center">{t('news.time')}</th>
              <th className="px-2 py-1.5 font-medium w-16 text-center">{t('news.ticker')}</th>
              <th className="px-2 py-1.5 font-medium w-36">{t('news.source')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {paginatedNews.map((article, i) => {
              const dt = formatDateTime(article.published);
              const displayTicker = tickerFilter 
                ? (article.tickers?.find(t => t.toUpperCase() === tickerFilter) || article.tickers?.[0] || '—')
                : (article.tickers?.[0] || '—');
              const hasMultipleTickers = (article.tickers?.length || 0) > 1;
              const articleId = String(article.benzinga_id || article.id || '');
              const isHighlighted = highlightedId && highlightedId.includes(articleId);

              return (
                <tr
                  key={article.benzinga_id || article.id || i}
                  ref={isHighlighted ? highlightRowRef : null}
                  className={`cursor-pointer hover:bg-slate-50 transition-colors ${
                    isHighlighted 
                      ? 'animate-highlight-pulse bg-rose-100' 
                      : article.isLive ? 'bg-emerald-50/50' : ''
                  }`}
                  onClick={() => setSelectedArticle(article)}
                >
                  <td className="px-2 py-1">
                    <div className="flex items-center gap-1.5">
                      {article.isLive && (
                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse flex-shrink-0" />
                      )}
                      <span className="text-slate-800 truncate" style={{ maxWidth: '500px' }}>
                        {decodeHtmlEntities(article.title)}
                      </span>
                    </div>
                  </td>
                  <td className="px-2 py-1 text-center text-slate-500 font-mono">{dt.date}</td>
                  <td className="px-2 py-1 text-center text-slate-500 font-mono">{dt.time}</td>
                  <td className="px-2 py-1 text-center">
                    <span className="text-blue-600 font-mono font-semibold">
                      {displayTicker}
                      {hasMultipleTickers && (
                        <span className="text-slate-400 text-[10px] ml-0.5">
                          +{(article.tickers?.length || 1) - 1}
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-slate-500 truncate" style={{ maxWidth: '140px' }}>
                    {article.author}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
