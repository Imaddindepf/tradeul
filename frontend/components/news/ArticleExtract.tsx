'use client';

/**
 * ArticleExtract — lector nativo de artículos (estilo terminal, como Godel)
 *
 * El cuerpo del artículo se extrae en el servidor (news-persister/trafilatura,
 * vía gateway /news/api/v1/news/extract) y se renderiza aquí con la tipografía
 * de la app: nada de iframes ni de mandar al usuario al periódico.
 *
 * Si el publisher bloquea la extracción (p. ej. Reuters) o falla, degrada al
 * teaser + un enlace discreto al original.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2 } from 'lucide-react';

export interface ExtractResult {
  ok: boolean;
  title?: string;
  byline?: string;
  date?: string;
  site?: string;
  text?: string;
  reason?: string;
}

const cache = new Map<string, ExtractResult>();

export function useArticleExtract(url: string | null | undefined): { data: ExtractResult | null; loading: boolean } {
  const [data, setData] = useState<ExtractResult | null>(url ? cache.get(url) || null : null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!url) { setData(null); return; }
    const hit = cache.get(url);
    if (hit) { setData(hit); return; }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    let cancelled = false;
    setLoading(true);
    setData(null);

    fetch(`${apiUrl}/news/api/v1/news/extract?url=${encodeURIComponent(url)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((json: ExtractResult) => {
        cache.set(url, json);
        if (!cancelled) setData(json);
      })
      .catch(() => {
        const fail: ExtractResult = { ok: false, reason: 'unavailable' };
        cache.set(url, fail);
        if (!cancelled) setData(fail);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [url]);

  return { data, loading };
}

/**
 * Cuerpo del artículo renderizado nativo. Usado por el visor de News y por el
 * lector del Newswire. El teaser (si existe) ya lo pinta el contenedor.
 */
export function ExtractedBody({ url, teaser }: { url: string; teaser?: string | null }) {
  const { t } = useTranslation();
  const { data, loading } = useArticleExtract(url);

  if (loading || (!data && url)) {
    return (
      <div className="flex items-center gap-2 py-6 text-muted-fg text-xs">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('common.loading')}
      </div>
    );
  }

  if (data?.ok && data.text) {
    const paragraphs = data.text.split('\n').map((p) => p.trim()).filter(Boolean);
    return (
      <div>
        {paragraphs.map((p, i) => (
          <p key={i} className="text-[13px] leading-relaxed text-foreground mb-3">{p}</p>
        ))}
        {data.byline && (
          <p className="text-[11px] text-muted-fg mt-4">{data.byline}</p>
        )}
      </div>
    );
  }

  // Fallback: el publisher no se deja extraer — teaser (si no se pintó ya) + enlace discreto
  return (
    <div>
      {teaser && <p className="text-[13px] leading-relaxed text-foreground mb-4">{teaser}</p>}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[12px] text-muted-fg hover:text-foreground underline underline-offset-2 transition-colors"
      >
        {t('news.readMore')} <ExternalLink className="w-3 h-3" />
      </a>
    </div>
  );
}
