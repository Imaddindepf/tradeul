/**
 * NewsStore v2 — Optimized global news store
 *
 * Fixes over v1:
 * 1. Module-level _seenIds Set → O(1) dedup, ZERO Set copy per article
 * 2. Automatic compaction → strips body/teaser/images from old articles (~80% RAM saved)
 * 3. Hard cap MAX_ARTICLES=2000 → bounded memory, FIFO eviction
 * 4. Pagination (loadOlderArticles) → user never loses history, loads on scroll
 * 5. useArticlesByTicker selector → cleaner API for per-ticker consumers
 */

import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';

// ============================================================================
// CONSTANTS
// ============================================================================

const MAX_ARTICLES = 2000;
const COMPACT_AFTER = 500;
export const PAGE_SIZE = 100;

// ============================================================================
// TYPES
// ============================================================================

export interface NewsArticle {
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
  receivedAt?: number;
  tickerPrices?: Record<string, number>;
  _compacted?: boolean;
}

interface NewsState {
  articles: NewsArticle[];
  isConnected: boolean;
  isSubscribed: boolean;
  isPaused: boolean;
  pausedBuffer: NewsArticle[];
  hasMore: boolean;
  isLoadingMore: boolean;
  stats: {
    totalReceived: number;
    liveCount: number;
    lastUpdate: Date | null;
    initialLoadComplete: boolean;
  };
}

interface NewsActions {
  addArticle: (article: NewsArticle) => boolean;
  addArticlesBatch: (articles: NewsArticle[], markAsLive?: boolean) => number;
  loadOlderArticles: (articles: NewsArticle[]) => number;
  setPaused: (paused: boolean) => void;
  resumeWithBuffer: () => void;
  setConnected: (connected: boolean) => void;
  setSubscribed: (subscribed: boolean) => void;
  markInitialLoadComplete: () => void;
  getArticleById: (id: string | number) => NewsArticle | undefined;
  hasSeenId: (id: string | number) => boolean;
  setHasMore: (hasMore: boolean) => void;
  setLoadingMore: (loading: boolean) => void;
  reset: () => void;
}

// ============================================================================
// MODULE-LEVEL INTERNALS
// O(1) dedup without copying Sets on every addArticle call.
// These live outside Zustand state because no component subscribes to them.
// ============================================================================

const _seenIds = new Set<string>();

function getKey(article: NewsArticle): string | null {
  const raw = article.benzinga_id ?? article.id;
  return raw != null ? String(raw) : null;
}

function compactArticle(a: NewsArticle): NewsArticle {
  if (a._compacted) return a;
  return {
    id: a.id,
    benzinga_id: a.benzinga_id,
    title: a.title,
    author: a.author,
    published: a.published,
    url: a.url,
    tickers: a.tickers,
    isLive: a.isLive,
    receivedAt: a.receivedAt,
    tickerPrices: a.tickerPrices,
    _compacted: true,
  };
}

function enforceMemoryLimits(articles: NewsArticle[]): NewsArticle[] {
  let result = articles;

  if (result.length > COMPACT_AFTER) {
    result = result.map((a, i) => (i < COMPACT_AFTER ? a : compactArticle(a)));
  }

  if (result.length > MAX_ARTICLES) {
    const evicted = result.slice(MAX_ARTICLES);
    result = result.slice(0, MAX_ARTICLES);
    for (const a of evicted) {
      const id = getKey(a);
      if (id) _seenIds.delete(id);
    }
  }

  return result;
}

function resetInternals() {
  _seenIds.clear();
}

// ============================================================================
// INITIAL STATE
// ============================================================================

const initialState: NewsState = {
  articles: [],
  isConnected: false,
  isSubscribed: false,
  isPaused: false,
  pausedBuffer: [],
  hasMore: true,
  isLoadingMore: false,
  stats: {
    totalReceived: 0,
    liveCount: 0,
    lastUpdate: null,
    initialLoadComplete: false,
  },
};

// ============================================================================
// STORE
// ============================================================================

export const useNewsStore = create<NewsState & NewsActions>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      ...initialState,

      // ============================================================
      // ADD SINGLE ARTICLE (WebSocket — hot path, must be fast)
      // ============================================================
      addArticle: (article) => {
        const id = getKey(article);
        if (!id || _seenIds.has(id)) return false;

        _seenIds.add(id);

        const enriched: NewsArticle = {
          ...article,
          isLive: true,
          receivedAt: Date.now(),
        };

        set((state) => {
          if (state.isPaused) {
            return {
              pausedBuffer: [enriched, ...state.pausedBuffer],
              stats: {
                ...state.stats,
                totalReceived: state.stats.totalReceived + 1,
              },
            };
          }

          let articles = [enriched, ...state.articles];

          if (articles.length > MAX_ARTICLES) {
            const last = articles[articles.length - 1];
            const lastId = getKey(last);
            if (lastId) _seenIds.delete(lastId);
            articles = articles.slice(0, MAX_ARTICLES);
          }

          return {
            articles,
            stats: {
              ...state.stats,
              totalReceived: state.stats.totalReceived + 1,
              liveCount: state.stats.liveCount + 1,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addArticle');

        return true;
      },

      // ============================================================
      // ADD BATCH (initial load — runs once, can be heavier)
      // ============================================================
      addArticlesBatch: (articles, markAsLive = false) => {
        if (!articles || articles.length === 0) return 0;

        let addedCount = 0;
        const now = Date.now();

        set((state) => {
          const newArticles: NewsArticle[] = [];

          for (const article of articles) {
            const id = getKey(article);
            if (!id || _seenIds.has(id)) continue;

            _seenIds.add(id);
            newArticles.push({
              ...article,
              isLive: markAsLive,
              receivedAt: now,
            });
            addedCount++;
          }

          if (addedCount === 0) return state;

          const merged = enforceMemoryLimits([...newArticles, ...state.articles]);

          return {
            articles: merged,
            stats: {
              ...state.stats,
              totalReceived: state.stats.totalReceived + addedCount,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addArticlesBatch');

        return addedCount;
      },

      // ============================================================
      // LOAD OLDER ARTICLES (pagination — appends at END)
      // ============================================================
      loadOlderArticles: (articles) => {
        if (!articles || articles.length === 0) {
          set({ hasMore: false, isLoadingMore: false }, false, 'loadOlderArticles:empty');
          return 0;
        }

        let addedCount = 0;
        const now = Date.now();

        set((state) => {
          const olderArticles: NewsArticle[] = [];

          for (const article of articles) {
            const id = getKey(article);
            if (!id || _seenIds.has(id)) continue;

            _seenIds.add(id);
            olderArticles.push({
              ...article,
              isLive: false,
              receivedAt: now,
            });
            addedCount++;
          }

          if (addedCount === 0) {
            return { hasMore: false, isLoadingMore: false };
          }

          const merged = enforceMemoryLimits([...state.articles, ...olderArticles]);

          return {
            articles: merged,
            hasMore: addedCount >= PAGE_SIZE,
            isLoadingMore: false,
            stats: {
              ...state.stats,
              totalReceived: state.stats.totalReceived + addedCount,
              lastUpdate: new Date(),
            },
          };
        }, false, 'loadOlderArticles');

        return addedCount;
      },

      // ============================================================
      // PAUSE CONTROL
      // ============================================================
      setPaused: (paused) => {
        set({ isPaused: paused }, false, 'setPaused');
      },

      resumeWithBuffer: () => {
        set((state) => {
          if (state.pausedBuffer.length === 0) {
            return { isPaused: false };
          }

          const merged = enforceMemoryLimits([...state.pausedBuffer, ...state.articles]);

          return {
            articles: merged,
            pausedBuffer: [],
            isPaused: false,
            stats: {
              ...state.stats,
              liveCount: state.stats.liveCount + state.pausedBuffer.length,
              lastUpdate: new Date(),
            },
          };
        }, false, 'resumeWithBuffer');
      },

      // ============================================================
      // CONNECTION STATE
      // ============================================================
      setConnected: (connected) => {
        set({ isConnected: connected }, false, 'setConnected');
      },

      setSubscribed: (subscribed) => {
        set({ isSubscribed: subscribed }, false, 'setSubscribed');
      },

      // ============================================================
      // UTILITIES
      // ============================================================
      markInitialLoadComplete: () => {
        set((state) => ({
          stats: { ...state.stats, initialLoadComplete: true },
        }), false, 'markInitialLoadComplete');
      },

      getArticleById: (id) => {
        const key = String(id);
        return get().articles.find(a => getKey(a) === key);
      },

      hasSeenId: (id) => _seenIds.has(String(id)),

      setHasMore: (hasMore) => {
        set({ hasMore }, false, 'setHasMore');
      },

      setLoadingMore: (loading) => {
        set({ isLoadingMore: loading }, false, 'setLoadingMore');
      },

      // ============================================================
      // RESET
      // ============================================================
      reset: () => {
        resetInternals();
        set(initialState, false, 'reset');
      },
    })),
    {
      name: 'news-store',
      enabled: process.env.NODE_ENV === 'development',
    }
  )
);

// ============================================================================
// SELECTORS
// ============================================================================

export const selectArticles = (state: NewsState & NewsActions) => state.articles;
export const selectIsPaused = (state: NewsState & NewsActions) => state.isPaused;
export const selectPausedBuffer = (state: NewsState & NewsActions) => state.pausedBuffer;
export const selectIsConnected = (state: NewsState & NewsActions) => state.isConnected;
export const selectStats = (state: NewsState & NewsActions) => state.stats;
export const selectHasMore = (state: NewsState & NewsActions) => state.hasMore;
export const selectIsLoadingMore = (state: NewsState & NewsActions) => state.isLoadingMore;

export function useArticlesByTicker(ticker: string): NewsArticle[] {
  return useNewsStore((state) => {
    if (!ticker) return state.articles;
    const upper = ticker.toUpperCase();
    return state.articles.filter(a =>
      a.tickers?.some(t => t.toUpperCase() === upper)
    );
  });
}

/** @deprecated Use useArticlesByTicker */
export const useFilteredArticles = (tickerFilter: string) => {
  return useArticlesByTicker(tickerFilter);
};

export const useLiveCount = () => {
  return useNewsStore((state) => state.stats.liveCount);
};
