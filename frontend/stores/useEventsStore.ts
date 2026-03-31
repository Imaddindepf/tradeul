import { create } from 'zustand';

interface CachedEventEntry {
  id: string;
  [key: string]: any;
}

interface EventsCacheState {
  cache: Map<string, CachedEventEntry[]>;
  timestamps: Map<string, number>;
}

interface EventsCacheActions {
  setEvents: (categoryId: string, events: CachedEventEntry[]) => void;
  appendEvent: (categoryId: string, event: CachedEventEntry) => void;
  getEvents: (categoryId: string) => CachedEventEntry[];
  getTimestamp: (categoryId: string) => number | undefined;
  clearCategory: (categoryId: string) => void;
}

export const useEventsStore = create<EventsCacheState & EventsCacheActions>()((set, get) => ({
  cache: new Map(),
  timestamps: new Map(),

  setEvents: (categoryId, events) => {
    set((state) => {
      const newCache = new Map(state.cache);
      const newTs = new Map(state.timestamps);
      newCache.set(categoryId, events);
      newTs.set(categoryId, Date.now());
      return { cache: newCache, timestamps: newTs };
    });
  },

  appendEvent: (categoryId, event) => {
    set((state) => {
      const newCache = new Map(state.cache);
      const existing = newCache.get(categoryId) || [];
      if (existing.some(e => e.id === event.id)) return state;
      newCache.set(categoryId, [event, ...existing]);
      return { cache: newCache };
    });
  },

  getEvents: (categoryId) => get().cache.get(categoryId) || [],

  getTimestamp: (categoryId) => get().timestamps.get(categoryId),

  clearCategory: (categoryId) => {
    set((state) => {
      const newCache = new Map(state.cache);
      const newTs = new Map(state.timestamps);
      newCache.delete(categoryId);
      newTs.delete(categoryId);
      return { cache: newCache, timestamps: newTs };
    });
  },
}));
