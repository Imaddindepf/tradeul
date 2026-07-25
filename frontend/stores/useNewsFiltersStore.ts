/**
 * useNewsFiltersStore — Filtros GLOBALES de noticias
 *
 * Capa global compartida por todas las ventanas de News (persistida en
 * localStorage): fuentes, publishers (tri-estado incluir/excluir),
 * keywords include/exclude y filtro de spam de class actions.
 *
 * La capa por-ventana (búsqueda de texto, ticker/watchlist, rango de fechas)
 * vive en el windowState de cada ventana. Ambas capas se combinan al filtrar.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { NewsArticle } from '@/stores/useNewsStore';

// ============================================================================
// FEEDS (fuentes de primer nivel)
// ============================================================================

export interface FeedDef {
  key: string;
  label: string;
  channel?: string; // tag en article.channels para los feeds FMP
}

export const NEWS_FEEDS: FeedDef[] = [
  { key: 'benzinga', label: 'Benzinga' },
  { key: 'stock', label: 'Stock News', channel: 'Stock' },
  { key: 'press', label: 'Press Releases', channel: 'Press Releases' },
  { key: 'general', label: 'General News', channel: 'General' },
  { key: 'forex', label: 'Forex News', channel: 'Forex' },
  { key: 'articles', label: 'FMP Articles', channel: 'FMP' },
  { key: 'polygon', label: 'Polygon News', channel: 'Polygon' },
];

const FEED_BY_KEY: Record<string, FeedDef> = Object.fromEntries(NEWS_FEEDS.map(f => [f.key, f]));

export function matchesFeeds(article: NewsArticle, feeds: string[]): boolean {
  if (feeds.length === 0) return true;
  const isFmp = article.source === 'fmp' || String(article.id || '').startsWith('fmp_');
  if (!isFmp) return feeds.includes('benzinga');
  const channels = article.channels || [];
  return feeds.some(key => {
    const feed = FEED_BY_KEY[key];
    return feed?.channel ? channels.includes(feed.channel) : false;
  });
}

// ============================================================================
// CLASS ACTION SPAM
// ============================================================================

export type ClassActionMode = 'show' | 'hide' | 'only';

const CLASS_ACTION_RE = new RegExp(
  [
    'class action',
    'class-action',
    'lead plaintiff',
    'securities litigation',
    'securities fraud (investigation|lawsuit)',
    'investor rights law',
    'shareholder rights (law|firm)',
    'investors? (with|to) (substantial )?loss',
    'deadline (alert|reminder)',
    'rosen law',
    'pomerantz',
    'kaplan fox',
    'glancy prongay',
    'bronstein, gewirtz',
    'levi & korsinsky',
    'robbins geller',
    'hagens berman',
    'schall law',
    'kessler topaz',
    'bernstein liebhard',
    'faruqi & faruqi',
    'kahn swick',
    'johnson fistel',
    'portnoy law',
    'gross law firm',
    'howard g\\. smith',
  ].join('|'),
  'i'
);

export function isClassAction(article: Pick<NewsArticle, 'title'>): boolean {
  return CLASS_ACTION_RE.test(article.title || '');
}

// ============================================================================
// STORE
// ============================================================================

export interface NewsGlobalFilters {
  feeds: string[];               // [] = todas las fuentes
  publishersInclude: string[];   // si hay alguno, solo esos publishers
  publishersExclude: string[];   // siempre ocultos
  includes: string[];            // el titular debe contener al menos uno (max 20)
  excludes: string[];            // ocultar si contiene alguno (max 20)
  classAction: ClassActionMode;
}

export const EMPTY_GLOBAL_FILTERS: NewsGlobalFilters = {
  feeds: [],
  publishersInclude: [],
  publishersExclude: [],
  includes: [],
  excludes: [],
  classAction: 'show',
};

/** Defaults curados: máxima cobertura, spam de class actions fuera */
export const RECOMMENDED_FILTERS: NewsGlobalFilters = {
  feeds: [],
  publishersInclude: [],
  publishersExclude: [],
  includes: [],
  excludes: [],
  classAction: 'hide',
};

interface NewsFiltersState extends NewsGlobalFilters {
  setGlobalFilters: (filters: NewsGlobalFilters) => void;
  clearGlobalFilters: () => void;
  applyRecommended: () => void;
}

export const useNewsFiltersStore = create<NewsFiltersState>()(
  persist(
    (set) => ({
      ...EMPTY_GLOBAL_FILTERS,
      setGlobalFilters: (filters) => set({ ...filters }),
      clearGlobalFilters: () => set({ ...EMPTY_GLOBAL_FILTERS }),
      applyRecommended: () => set({ ...RECOMMENDED_FILTERS }),
    }),
    { name: 'news-global-filters' }
  )
);

export function selectGlobalFilters(s: NewsFiltersState): NewsGlobalFilters {
  return {
    feeds: s.feeds,
    publishersInclude: s.publishersInclude,
    publishersExclude: s.publishersExclude,
    includes: s.includes,
    excludes: s.excludes,
    classAction: s.classAction,
  };
}

// ============================================================================
// MATCHING
// ============================================================================

export function countGlobalFilters(f: NewsGlobalFilters): number {
  let n = 0;
  if (f.feeds.length > 0) n++;
  if (f.publishersInclude.length > 0) n++;
  if (f.publishersExclude.length > 0) n++;
  if (f.includes.length > 0) n++;
  if (f.excludes.length > 0) n++;
  if (f.classAction !== 'show') n++;
  return n;
}

// ============================================================================
// SYNC CON LA CUENTA (user_preferences.saved_filters.newsGlobal)
//
// localStorage es el caché local inmediato; la BD (por usuario, vía JWT) es
// la fuente de verdad: se carga al montar NewsProvider y se guarda en cada
// Save del panel de filtros. Así los filtros globales viajan con la cuenta.
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const SAVED_FILTERS_KEY = 'newsGlobal';

export type AuthedFetch = (url: string, options?: RequestInit) => Promise<Response>;

export async function loadNewsFiltersFromBackend(authedFetch: AuthedFetch): Promise<void> {
  try {
    const res = await authedFetch(`${API_URL}/api/v1/user/preferences`, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    const stored = data?.savedFilters?.[SAVED_FILTERS_KEY];
    if (stored && typeof stored === 'object') {
      useNewsFiltersStore.setState({ ...EMPTY_GLOBAL_FILTERS, ...stored });
    }
  } catch (e) {
    console.error('[NewsFilters] Error loading from backend:', e);
  }
}

export async function saveNewsFiltersToBackend(authedFetch: AuthedFetch, filters: NewsGlobalFilters): Promise<void> {
  try {
    // Read-merge-write: saved_filters es un JSONB compartido con otras features
    const res = await authedFetch(`${API_URL}/api/v1/user/preferences`, { cache: 'no-store' });
    const current = res.ok ? (await res.json())?.savedFilters || {} : {};
    const put = await authedFetch(`${API_URL}/api/v1/user/preferences`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ savedFilters: { ...current, [SAVED_FILTERS_KEY]: filters } }),
    });
    if (!put.ok) console.error('[NewsFilters] Backend save failed:', put.status);
  } catch (e) {
    console.error('[NewsFilters] Error saving to backend:', e);
  }
}

export function matchesGlobalFilters(article: NewsArticle, f: NewsGlobalFilters): boolean {
  if (!matchesFeeds(article, f.feeds)) return false;

  const publisher = (article.author || '').toLowerCase();
  if (f.publishersExclude.length > 0 && f.publishersExclude.some(p => p.toLowerCase() === publisher)) return false;
  if (f.publishersInclude.length > 0 && !f.publishersInclude.some(p => p.toLowerCase() === publisher)) return false;

  const title = (article.title || '').toLowerCase();
  if (f.excludes.length > 0 && f.excludes.some(k => title.includes(k.toLowerCase()))) return false;
  if (f.includes.length > 0 && !f.includes.some(k => title.includes(k.toLowerCase()))) return false;

  if (f.classAction !== 'show') {
    const ca = isClassAction(article);
    if (f.classAction === 'hide' && ca) return false;
    if (f.classAction === 'only' && !ca) return false;
  }

  return true;
}
