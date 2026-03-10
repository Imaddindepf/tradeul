/**
 * TickerNewsMini - Mini ventana de noticias de un ticker
 * 
 * Muestra las noticias de un ticker específico extraídas del store principal
 * Filtra por ticker de las noticias ya cargadas
 */

'use client';

import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import { useArticlesByTicker } from '@/stores/useNewsStore';
import { getUserTimezone } from '@/lib/date-utils';
import { decodeHtmlEntities } from '@/lib/html-utils';

interface TickerNewsMiniProps {
  ticker: string;
}

export function TickerNewsMini({ ticker }: TickerNewsMiniProps) {
  const { t } = useTranslation();

  const articles = useArticlesByTicker(ticker);

  // Format dates in Eastern Time (ET) - standard for US markets
  const formatDateTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return {
        date: d.toLocaleDateString('en-US', { timeZone: getUserTimezone(), month: '2-digit', day: '2-digit' }),
        time: d.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', hour12: false })
      };
    } catch {
      return { date: '—', time: '—' };
    }
  };

  if (articles.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-surface p-4">
        <p className="text-muted-fg text-sm">{t('news.noNewsForTicker', { ticker })}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-surface-hover border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-blue-600">{ticker}</span>
          <span className="text-xs text-muted-fg">
            {articles.length} {t('news.articles', { count: articles.length })}
          </span>
        </div>
      </div>

      {/* Lista de noticias */}
      <div className="flex-1 overflow-auto">
        <div className="divide-y divide-border-subtle">
          {articles.map((article, index) => {
            const dt = formatDateTime(article.published);

            return (
              <a
                key={article.id || index}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block px-3 py-2 hover:bg-surface-hover transition-colors group"
              >
                {/* Título */}
                <div className="flex items-start gap-2">
                  <span className="text-xs text-foreground leading-snug flex-1">
                    {decodeHtmlEntities(article.title)}
                  </span>
                  <ExternalLink className="w-3 h-3 text-muted-fg group-hover:text-primary flex-shrink-0 mt-0.5" />
                </div>

                {/* Metadata */}
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-fg">
                  <span className="font-mono">{dt.time}</span>
                  <span>·</span>
                  <span className="font-mono">{dt.date}</span>
                  {article.author && (
                    <>
                      <span>·</span>
                      <span className="truncate max-w-[120px]">{article.author}</span>
                    </>
                  )}
                </div>

                {/* Teaser (si existe) */}
                {article.teaser && (
                  <p className="mt-1 text-xs text-muted-fg line-clamp-2">
                    {decodeHtmlEntities(article.teaser)}
                  </p>
                )}
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
}

