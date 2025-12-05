'use client';

import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthWebSocket } from '@/hooks/useAuthWebSocket';
import { useSquawk } from '@/hooks/useSquawk';
import { useCatalystDetector } from '@/hooks/useCatalystDetector';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { TickerSearch } from '@/components/common/TickerSearch';
import { ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react';

// Store para tickers con noticias (intersección scanner + news)
import { useNewsTickersStore } from '@/stores/useNewsTickersStore';

// Decodifica entidades HTML como &#39; &amp; &quot; etc.
function decodeHtmlEntities(text: string): string {
  if (!text) return text;
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

interface NewsArticle {
  id?: string;
  benzinga_id?: number;
  title: string;
  author: string;
  published: string;
  url: string;
  tickers?: string[];
  channels?: string[];
  teaser?: string;
  body?: string;
  isLive?: boolean;
}

interface NewsContentProps {
  initialTicker?: string;
  highlightArticleId?: string; // ID del artículo a resaltar (benzinga_id)
}

const ITEMS_PER_PAGE = 200;

export function NewsContent({ initialTicker, highlightArticleId }: NewsContentProps = {}) {
  const { t } = useTranslation();
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [pausedBuffer, setPausedBuffer] = useState<NewsArticle[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const seenIdsRef = useRef<Set<string | number>>(new Set());
  const [tickerFilter, setTickerFilter] = useState<string>(initialTicker || '');
  const [tickerInputValue, setTickerInputValue] = useState<string>(initialTicker || '');
  const [currentPage, setCurrentPage] = useState(1);
  
  // Estado para el artículo destacado con parpadeo
  const [highlightedId, setHighlightedId] = useState<string | null>(highlightArticleId || null);
  const highlightRowRef = useRef<HTMLTableRowElement | null>(null);
  
  // Efecto para scroll automático al artículo destacado y quitar el highlight después
  useEffect(() => {
    if (highlightedId && highlightRowRef.current) {
      // Scroll suave al artículo
      highlightRowRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      
      // Quitar el highlight después de 5 segundos
      const timer = setTimeout(() => {
        setHighlightedId(null);
      }, 5000);
      
      return () => clearTimeout(timer);
    }
  }, [highlightedId, news]); // También depende de news para re-scroll cuando se cargan los datos

  // WebSocket connection con Auth
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useAuthWebSocket(wsUrl);

  // Squawk (text-to-speech)
  const squawk = useSquawk();

  // Catalyst detector for news alerts
  const { processNews: processCatalystNews } = useCatalystDetector();

  // Store para tracking de tickers con noticias (artículos completos)
  const addNewsArticle = useNewsTickersStore((state) => state.addNewsArticle);
  const addNewsArticlesBatch = useNewsTickersStore((state) => state.addNewsArticlesBatch);

  // Fetch initial news
  useEffect(() => {
    const fetchNews = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/news/api/v1/news?limit=1000`);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.results) {
          const articles = data.results.map((a: NewsArticle) => ({ ...a, isLive: false }));
          setNews(articles);
          
          // Agregar artículos al store para intersección scanner+news
          const storeArticles = articles
            .filter((a: NewsArticle) => a.tickers && a.tickers.length > 0)
            .map((a: NewsArticle) => ({
              id: a.benzinga_id || a.id || '',
              title: a.title,
              author: a.author,
              published: a.published,
              url: a.url,
              tickers: a.tickers || [],
              teaser: a.teaser,
            }));
          
          articles.forEach((a: NewsArticle) => {
            seenIdsRef.current.add(a.benzinga_id || a.id || '');
          });
          
          // Agregar batch al store
          if (storeArticles.length > 0) {
            addNewsArticlesBatch(storeArticles);
          }
        }
        setLoading(false);
      } catch (err) {
        console.error('Error fetching news:', err);
        setError(t('news.errorLoading'));
        setLoading(false);
      }
    };

    fetchNews();
  }, [addNewsArticlesBatch]);

  // Subscribe to WebSocket news
  useEffect(() => {
    if (!ws.isConnected) return;

    // Subscribe to benzinga news
    ws.send({ action: 'subscribe_benzinga_news' });

    return () => {
      ws.send({ action: 'unsubscribe_benzinga_news' });
    };
  }, [ws.isConnected, ws]);

  // Handle incoming WebSocket messages
  useEffect(() => {
    const subscription = ws.messages$.subscribe((message: any) => {
      if ((message.type === 'news' || message.type === 'benzinga_news') && message.article) {
        const article = message.article as NewsArticle;
        const id = article.benzinga_id || article.id;

        if (id && !seenIdsRef.current.has(id)) {
          seenIdsRef.current.add(id);
          const liveArticle = { ...article, isLive: true };

          // Procesar para Catalyst Alerts (detectar movimientos explosivos)
          if (message.catalyst_metrics) {
            processCatalystNews({
              ...article,
              catalyst_metrics: typeof message.catalyst_metrics === 'string' 
                ? JSON.parse(message.catalyst_metrics) 
                : message.catalyst_metrics,
            });
          }

          // Agregar artículo al store para intersección scanner+news (tiempo real)
          if (article.tickers && article.tickers.length > 0) {
            addNewsArticle({
              id: id,
              title: article.title,
              author: article.author,
              published: article.published,
              url: article.url,
              tickers: article.tickers,
              teaser: article.teaser,
            });
          }

          if (isPaused) {
            setPausedBuffer(prev => [liveArticle, ...prev]);
          } else {
            setNews(prev => [liveArticle, ...prev]);

            // Squawk: read the news aloud
            const ticker = article.tickers?.[0] || '';
            const decodedTitle = decodeHtmlEntities(article.title);
            const squawkText = ticker
              ? t('news.newsFor', { ticker }) + '. ' + decodedTitle
              : t('news.title') + '. ' + decodedTitle;
            squawk.speak(squawkText);
          }
        }
      }
    });

    return () => subscription.unsubscribe();
  }, [ws.messages$, isPaused, squawk, addNewsArticle, processCatalystNews]);

  // Toggle pause
  const handleTogglePause = useCallback(() => {
    if (isPaused && pausedBuffer.length > 0) {
      // Resume: merge buffered items
      setNews(prev => [...pausedBuffer, ...prev]);
      setPausedBuffer([]);
    }
    setIsPaused(!isPaused);
  }, [isPaused, pausedBuffer]);

  // Apply ticker filter
  const handleApplyFilter = useCallback(() => {
    const newFilter = tickerInputValue.toUpperCase().trim();
    console.log('[News Filter] Applying filter:', newFilter, 'from input:', tickerInputValue);
    setTickerFilter(newFilter);
    setCurrentPage(1); // Reset to first page when filtering
  }, [tickerInputValue]);

  // Filter news by ticker (coincidencia exacta)
  const filteredNews = useMemo(() => {
    if (!tickerFilter) return news;
    const filtered = news.filter(article =>
      article.tickers?.some(t => t.toUpperCase() === tickerFilter)
    );
    return filtered;
  }, [news, tickerFilter]);

  // Pagination
  const totalPages = Math.ceil(filteredNews.length / ITEMS_PER_PAGE);
  const paginatedNews = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    return filteredNews.slice(start, end);
  }, [filteredNews, currentPage]);

  // Reset page if it exceeds total pages after filtering
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(1);
    }
  }, [currentPage, totalPages]);

  // Format date/time
  const formatDateTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return {
        date: d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }),
        time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      };
    } catch {
      return { date: '—', time: '—' };
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3" />
          <p className="text-slate-600 text-sm">{t('news.loadingNews')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full bg-white">
        <p className="text-red-600 text-sm">{error}</p>
      </div>
    );
  }

  const liveCount = news.filter(a => a.isLive).length;

  // =====================================================
  // RENDER: ARTICLE VIEWER (cuando hay artículo seleccionado)
  // =====================================================
  if (selectedArticle) {
    const dt = formatDateTime(selectedArticle.published);
    const ticker = selectedArticle.tickers?.[0] || '';

    // Determinar qué contenido mostrar
    const hasBody = selectedArticle.body && selectedArticle.body.trim().length > 0;
    const hasTeaser = selectedArticle.teaser && selectedArticle.teaser.trim().length > 0;
    const hasContent = hasBody || hasTeaser;

    return (
      <div className="flex flex-col h-full bg-white">
        {/* Header del viewer */}
        <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
          <button
            onClick={() => {
              console.log('[News Filter] Going back. Current filter:', tickerFilter, 'Input:', tickerInputValue);
              setSelectedArticle(null);
            }}
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

        {/* Contenido del artículo */}
        <div className="flex-1 overflow-auto">
          <div className="p-4">
            {/* Título siempre visible */}
            <h1 className="text-lg font-semibold text-slate-900 mb-3">{decodeHtmlEntities(selectedArticle.title)}</h1>

            {/* Metadata */}
            <div className="flex items-center gap-3 text-xs text-slate-500 mb-4">
              <span>By {selectedArticle.author}</span>
              {selectedArticle.channels && selectedArticle.channels.length > 0 && (
                <span className="text-slate-400">
                  {selectedArticle.channels.join(', ')}
                </span>
              )}
            </div>

            {/* Contenido: body > teaser > mensaje */}
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

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${ws.isConnected ? 'bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span className={`text-xs font-medium ${ws.isConnected ? 'text-emerald-600' : 'text-slate-500'}`}>
              {ws.isConnected ? t('common.live') : t('common.offline')}
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
            <span className="text-amber-600 text-xs font-medium">(+{pausedBuffer.length})</span>
          )}

          {/* Ticker Filter - Using shared TickerSearch component */}
          <form
            onSubmit={(e) => { e.preventDefault(); handleApplyFilter(); }}
            className="flex items-center gap-1.5 ml-3 pl-3 border-l border-slate-300"
          >
            <TickerSearch
              value={tickerInputValue}
              onChange={(value) => {
                setTickerInputValue(value);
                // Clear filter when input is cleared
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
              {filteredNews.length}{tickerFilter ? ` / ${news.length}` : ''}
            </span>
            {liveCount > 0 && <span className="text-emerald-600">({liveCount} live)</span>}
          </div>

          {/* Pagination Controls */}
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
              // Si hay filtro activo, mostrar el ticker que coincide; si no, mostrar el primero
              const displayTicker = tickerFilter 
                ? (article.tickers?.find(t => t.toUpperCase() === tickerFilter) || article.tickers?.[0] || '—')
                : (article.tickers?.[0] || '—');
              const hasMultipleTickers = (article.tickers?.length || 0) > 1;
              
              // Verificar si este artículo está destacado
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
                      {hasMultipleTickers && <span className="text-slate-400 text-[10px] ml-0.5">+{(article.tickers?.length || 1) - 1}</span>}
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
