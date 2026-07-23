'use client';

import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getUserTimezone } from '@/lib/date-utils';

export interface NewsArticle {
    benzinga_id?: string;
    id?: string;
    title: string;
    url: string;
    published: string;
    author?: string;
}

export function ChartNewsPopup({ ticker, articles }: { ticker: string; articles: NewsArticle[] }) {
    const { t, i18n } = useTranslation();
    const locale = i18n.language?.startsWith('es') ? 'es-ES' : 'en-US';

    const formatTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            const tz = getUserTimezone();
            return d.toLocaleTimeString(locale, { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
        } catch {
            return '—';
        }
    };

    if (articles.length === 0) {
        return (
            <div className="flex items-center justify-center h-full bg-surface p-4">
                <p className="text-muted-fg text-sm">{t('chart.noNewsFor', { ticker })}</p>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full bg-surface">
            <div className="px-3 py-2 bg-surface-hover border-b border-border">
                <span className="text-sm font-bold text-primary">{ticker}</span>
                <span className="text-xs text-muted-fg ml-2">
                    {t(articles.length === 1 ? 'chart.article_one' : 'chart.article_other', { count: articles.length })}
                </span>
            </div>
            <div className="flex-1 overflow-auto divide-y divide-border">
                {articles.map((article, i) => (
                    <a
                        key={article.benzinga_id || article.id || i}
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block px-3 py-2 hover:bg-surface-hover group"
                    >
                        <div className="flex items-start gap-2">
                            <span className="text-xs text-foreground flex-1 leading-snug">{article.title}</span>
                            <ExternalLink className="w-3 h-3 text-muted-fg group-hover:text-primary flex-shrink-0" />
                        </div>
                        <div className="text-xs text-muted-fg mt-1">
                            {formatTime(article.published)} · {article.author || 'Benzinga'}
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
}
