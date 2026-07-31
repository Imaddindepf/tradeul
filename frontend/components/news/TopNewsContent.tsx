'use client';

/**
 * TopNewsContent — Newswire (comando WIRE; TOP se mantiene como alias)
 *
 * Titulares curados de Reuters, siempre en vivo:
 * - Backfill inicial por REST (gateway /news/api/v1/news/top)
 * - Tiempo real: filtra los artículos de Reuters que llegan al NewsStore global
 * - Lectura DENTRO de la ventana: iframe vía el proxy del gateway (sin CORS),
 *   sin mandar al usuario fuera. Diseño alineado con la ventana de News.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useNewsStore, NewsArticle, selectArticles } from '@/stores/useNewsStore';
import { ExtractedBody } from '@/components/news/ArticleExtract';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { decodeHtmlEntities } from '@/lib/html-utils';
import { getUserTimezone } from '@/lib/date-utils';

const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

const isReuters = (a: Pick<NewsArticle, 'author'>) =>
  (a.author || '').toLowerCase().includes('reuters');

export function TopNewsContent() {
  const { t } = useTranslation();
  const storeArticles = useNewsStore(selectArticles);
  const [backfill, setBackfill] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<boolean>(false);
  const [selected, setSelected] = useState<NewsArticle | null>(null);

  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Backfill inicial (cache Reuters del backend)
  useEffect(() => {
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
  }, [apiUrl]);

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

  // ── Lector nativo: el artículo se lee aquí, con nuestra tipografía ──
  if (selected) {
    return (
      <div className="flex flex-col h-full bg-surface" style={{ fontFamily }}>
        <div className="flex items-center gap-2 px-2 py-1.5 bg-surface-hover border-b border-border shrink-0">
          <button
            onClick={() => setSelected(null)}
            className="px-2 py-1 bg-muted text-foreground rounded hover:bg-muted/80 text-xs font-medium flex items-center gap-1 shrink-0"
          >
            <ArrowLeft className="w-3 h-3" /> {t('common.back')}
          </button>
          <span className="flex-1" />
          <span className="text-[10px] text-muted-fg font-mono shrink-0">
            {formatWhen(selected.published)}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 py-4 max-w-[760px]">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-fg mb-2">
              {(selected.author || 'Newswire')} · {formatWhen(selected.published)}
            </div>
            <h1 className="text-[19px] font-bold leading-snug text-foreground mb-3">
              {decodeHtmlEntities(selected.title)}
            </h1>
            {selected.teaser && (
              <p className="text-[13px] leading-relaxed text-muted-fg mb-4">
                {decodeHtmlEntities(selected.teaser)}
              </p>
            )}
            <div className="border-t border-border-subtle pt-4">
              <ExtractedBody url={selected.url} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Lista ──
  return (
    <div className="flex flex-col h-full bg-surface text-foreground" style={{ fontFamily }}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-border bg-surface-hover shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wide">
          {t('topNews.subtitle')}
        </span>
        {liveCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-emerald-500">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {liveCount} live
          </span>
        )}
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
            onClick={() => setSelected(article)}
            className={`w-full flex items-start gap-2 px-2 py-1.5 text-left border-b border-border-subtle hover:bg-surface-hover transition-colors ${
              article.isLive ? 'bg-emerald-500/10' : ''
            }`}
          >
            <span className="text-[10px] text-muted-fg tabular-nums shrink-0 pt-[1px] w-11">
              {formatWhen(article.published)}
            </span>
            <span className="text-[11px] leading-snug flex-1">
              {article.isLive && (
                <span className="inline-block w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse mr-1 align-middle" />
              )}
              {decodeHtmlEntities(article.title)}
            </span>
          </button>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-border bg-surface-hover text-[10px] shrink-0">
        <span className="flex items-center gap-1 text-emerald-600">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {t('common.live')}
        </span>
        <span className="text-foreground/80">{articles.length}</span>
      </div>
    </div>
  );
}
