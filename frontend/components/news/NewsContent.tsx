'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useRxWebSocket } from '@/hooks/useRxWebSocket';
import { useSquawk } from '@/hooks/useSquawk';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { ExternalLink } from 'lucide-react';

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

export function NewsContent() {
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [pausedBuffer, setPausedBuffer] = useState<NewsArticle[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const seenIdsRef = useRef<Set<string | number>>(new Set());

  // WebSocket connection
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useRxWebSocket(wsUrl, false);

  // Squawk (text-to-speech)
  const squawk = useSquawk();

  // Fetch initial news
  useEffect(() => {
    const fetchNews = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/news/api/v1/news?limit=200`);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.results) {
          const articles = data.results.map((a: NewsArticle) => ({ ...a, isLive: false }));
          setNews(articles);
          articles.forEach((a: NewsArticle) => {
            seenIdsRef.current.add(a.benzinga_id || a.id || '');
          });
        }
        setLoading(false);
      } catch (err) {
        console.error('Error fetching news:', err);
        setError('Error loading news');
        setLoading(false);
      }
    };

    fetchNews();
  }, []);

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

          if (isPaused) {
            setPausedBuffer(prev => [liveArticle, ...prev]);
          } else {
            setNews(prev => [liveArticle, ...prev]);

            // Squawk: leer la noticia en español
            const ticker = article.tickers?.[0] || '';
            // Prefijo en español para forzar el idioma
            const decodedTitle = decodeHtmlEntities(article.title);
            const squawkText = ticker
              ? `Noticia de ${ticker}. ${decodedTitle}`
              : `Noticia. ${decodedTitle}`;
            console.log('🎙️ Squawk:', { isEnabled: squawk.isEnabled, text: squawkText.substring(0, 50) });
            squawk.speak(squawkText);
          }
        }
      }
    });

    return () => subscription.unsubscribe();
  }, [ws.messages$, isPaused, squawk]);

  // Toggle pause
  const handleTogglePause = useCallback(() => {
    if (isPaused && pausedBuffer.length > 0) {
      // Resume: merge buffered items
      setNews(prev => [...pausedBuffer, ...prev]);
      setPausedBuffer([]);
    }
    setIsPaused(!isPaused);
  }, [isPaused, pausedBuffer]);

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
          <p className="text-slate-600 text-sm">Cargando noticias...</p>
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
            onClick={() => setSelectedArticle(null)}
            className="px-2 py-1 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 text-xs font-medium flex items-center gap-1"
          >
            ← Back
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
            Open Original
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
                  Read full article on Benzinga
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-slate-500 mb-4">Full article content not available</p>
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
                >
                  <ExternalLink className="w-4 h-4" />
                  Open on Benzinga
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
              {ws.isConnected ? 'Live' : 'Offline'}
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
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600 font-mono">{news.length}</span>
          {liveCount > 0 && <span className="text-xs text-emerald-600">({liveCount} live)</span>}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="bg-slate-100 sticky top-0">
            <tr className="text-left text-slate-600 uppercase tracking-wide">
              <th className="px-2 py-1.5 font-medium">Headline</th>
              <th className="px-2 py-1.5 font-medium w-24 text-center">Date</th>
              <th className="px-2 py-1.5 font-medium w-20 text-center">Time</th>
              <th className="px-2 py-1.5 font-medium w-16 text-center">Ticker</th>
              <th className="px-2 py-1.5 font-medium w-36">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {news.map((article, i) => {
              const dt = formatDateTime(article.published);
              const ticker = article.tickers?.[0] || '—';

              return (
                <tr
                  key={article.benzinga_id || article.id || i}
                  className={`cursor-pointer hover:bg-slate-50 transition-colors ${article.isLive ? 'bg-emerald-50/50' : ''}`}
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
                    <span className="text-blue-600 font-mono font-semibold">{ticker}</span>
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
