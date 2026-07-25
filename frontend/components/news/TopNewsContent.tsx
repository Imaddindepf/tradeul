'use client';

/**
 * TopNewsContent — Top News (Reuters)
 *
 * Feed compacto de titulares de Reuters:
 * - Backfill inicial por REST (gateway /news/api/v1/news/top)
 * - Tiempo real: filtra los artículos de Reuters que llegan al NewsStore global
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2 } from 'lucide-react';
import { useNewsStore, NewsArticle, selectArticles } from '@/stores/useNewsStore';
import { decodeHtmlEntities } from '@/lib/html-utils';
import { getUserTimezone } from '@/lib/date-utils';

const isReuters = (a: Pick<NewsArticle, 'author'>) =>
  (a.author || '').toLowerCase().includes('reuters');

export function TopNewsContent() {
  const { t } = useTranslation();
  const storeArticles = useNewsStore(selectArticles);
  const [backfill, setBackfill] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<boolean>(false);

  // Backfill inicial (cache Reuters del backend)
  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    let cancelled = false;

    fetch(`${apiUrl}/news/api/v1/news/top?limit=150`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data) => {
        if (!cancelled && Array.isArray(data?.results)) setBackfill(data.results);
      })
      .catch((err) => {
        console.error('[TopNewsContent] Error fetching top news:', err);
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Merge backfill + store (live), dedup por id/url, orden desc por fecha
  const articles = useMemo(() => {
    const seen = new Set<string>();
    const merged: NewsArticle[] = [];
    for (const a of [...storeArticles.filter(isReuters), ...backfill]) {
      const key = String(a.id ?? a.url ?? '');
      if (!key || seen.has(key)) continue;
      seen.add(key);
      merged.push(a);
    }
    return merged.sort(
      (x, y) => new Date(y.published).getTime() - new Date(x.published).getTime()
    );
  }, [storeArticles, backfill]);

  const liveCount = useMemo(() => articles.filter((a) => a.isLive).length, [articles]);

  const { timeFmt, dayFmt } = useMemo(() => {
    const tz = getUserTimezone();
    return {
      timeFmt: new Intl.DateTimeFormat(undefined, {
        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
      }),
      dayFmt: new Intl.DateTimeFormat(undefined, {
        month: 'short', day: 'numeric', timeZone: tz,
      }),
    };
  }, []);

  const formatWhen = (published: string): string => {
    const date = new Date(published);
    if (isNaN(date.getTime())) return '';
    const now = new Date();
    const sameDay = dayFmt.format(date) === dayFmt.format(now);
    return sameDay ? timeFmt.format(date) : dayFmt.format(date);
  };

  return (
    <div className="flex flex-col h-full bg-surface text-foreground">
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-border/50 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide">
            {t('topNews.subtitle')}
          </span>
          {liveCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-500">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {liveCount}
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-fg">{articles.length}</span>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {loading && articles.length === 0 && (
          <div className="flex items-center justify-center h-full text-muted-fg">
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        )}

        {!loading && articles.length === 0 && (
          <div className="flex items-center justify-center h-full text-[11px] text-muted-fg px-4 text-center">
            {error ? t('topNews.error') : t('topNews.empty')}
          </div>
        )}

        {articles.map((article) => (
          <button
            key={String(article.id ?? article.url)}
            onClick={() => window.open(article.url, '_blank', 'noopener,noreferrer')}
            className={`w-full flex items-start gap-2 px-2 py-1.5 text-left border-b border-border/30 hover:bg-foreground/5 transition-colors group ${
              article.isLive ? 'bg-emerald-500/10' : ''
            }`}
          >
            <span className="text-[10px] text-muted-fg tabular-nums shrink-0 pt-[1px] w-11">
              {formatWhen(article.published)}
            </span>
            <span className="text-[11px] leading-snug flex-1">
              {decodeHtmlEntities(article.title)}
            </span>
            <ExternalLink className="w-3 h-3 text-muted-fg opacity-0 group-hover:opacity-100 shrink-0 mt-[1px]" />
          </button>
        ))}
      </div>
    </div>
  );
}
