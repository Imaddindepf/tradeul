'use client';

/**
 * NewsFiltersPanel — Panel "Configure Filters" de la ventana de News
 *
 * Dos capas de filtros, combinadas en cada request:
 * - GLOBAL (compartida por todas las ventanas, persistida): fuentes,
 *   publishers (tri-estado incluir/excluir), keywords include/exclude,
 *   filtro de spam de class actions.
 * - THIS WINDOW: rango de fechas + tags/author/channels (búsqueda histórica
 *   server-side, local a esta ventana).
 */

import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@clerk/nextjs';
import { X, Check, Minus } from 'lucide-react';
import {
  useNewsFiltersStore,
  NewsGlobalFilters,
  EMPTY_GLOBAL_FILTERS,
  RECOMMENDED_FILTERS,
  NEWS_FEEDS,
  saveNewsFiltersToBackend,
} from '@/stores/useNewsFiltersStore';
import { authFetchStandalone } from '@/hooks/useAuthFetch';

// ============================================================================
// TYPES (capa por-ventana)
// ============================================================================

export interface NewsWindowFilters {
  dateFrom: string;
  dateTo: string;
  tags: string;
  author: string;
  channels: string;
}

export const EMPTY_WINDOW_FILTERS: NewsWindowFilters = {
  dateFrom: '', dateTo: '', tags: '', author: '', channels: '',
};

export function countWindowFilters(f: NewsWindowFilters): number {
  let n = 0;
  if (f.dateFrom || f.dateTo) n++;
  if (f.tags.trim()) n++;
  if (f.author.trim()) n++;
  if (f.channels.trim()) n++;
  return n;
}

/** true si hay filtros que requieren búsqueda server-side */
export function isServerSearch(f: NewsWindowFilters): boolean {
  return !!(f.dateFrom || f.dateTo || f.tags.trim() || f.author.trim() || f.channels.trim());
}

export interface PublisherEntry {
  name: string;
  count: number;
}

const MAX_KEYWORDS = 20;

function getQuickDateRange(days: number): { from: string; to: string } {
  const today = new Date();
  const to = today.toISOString().split('T')[0];
  if (days === 0) return { from: to, to };
  if (days === -1) return { from: `${today.getFullYear()}-01-01`, to }; // YTD
  const from = new Date();
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().split('T')[0], to };
}

// ============================================================================
// SUBCOMPONENTES
// ============================================================================

/** Chip list editable con input (Enter añade, X quita, cap MAX_KEYWORDS) */
function KeywordList({ label, hint, values, onChange, fontFamily, accent }: {
  label: string;
  hint: string;
  values: string[];
  onChange: (next: string[]) => void;
  fontFamily: string;
  accent: 'include' | 'exclude';
}) {
  const [input, setInput] = useState('');

  const add = () => {
    const term = input.trim();
    if (!term || values.length >= MAX_KEYWORDS) return;
    if (values.some(v => v.toLowerCase() === term.toLowerCase())) { setInput(''); return; }
    onChange([...values, term]);
    setInput('');
  };

  const chipCls = accent === 'include'
    ? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
    : 'border-rose-500/40 text-rose-600 dark:text-rose-400 bg-rose-500/10';

  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-foreground">{label}</span>
        <span className="text-[9px] text-muted-fg">{values.length}/{MAX_KEYWORDS}</span>
      </div>
      <p className="text-[9px] text-muted-fg mt-0.5">{hint}</p>
      <div className="flex items-center gap-1 mt-1">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder="Enter ↵"
          disabled={values.length >= MAX_KEYWORDS}
          className="w-40 px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface text-foreground disabled:opacity-50"
          style={{ fontFamily }}
        />
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {values.map(v => (
            <span key={v} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] ${chipCls}`}>
              {v}
              <button onClick={() => onChange(values.filter(x => x !== v))} className="hover:opacity-70">
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Checkbox tri-estado: vacío → ✓ incluir → ✗ excluir → vacío */
function TriState({ state, onCycle }: { state: 'none' | 'include' | 'exclude'; onCycle: () => void }) {
  return (
    <button
      type="button"
      onClick={onCycle}
      className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors ${
        state === 'include'
          ? 'bg-emerald-600 border-emerald-600 text-white'
          : state === 'exclude'
            ? 'bg-rose-600 border-rose-600 text-white'
            : 'border-border bg-surface hover:border-foreground/40'
      }`}
    >
      {state === 'include' && <Check className="w-2.5 h-2.5" />}
      {state === 'exclude' && <Minus className="w-2.5 h-2.5" />}
    </button>
  );
}

// ============================================================================
// PANEL
// ============================================================================

type Section = 'sources' | 'publishers' | 'keywords' | 'classAction' | 'dates' | 'advanced';

interface NewsFiltersPanelProps {
  windowValue: NewsWindowFilters;
  publishers: PublisherEntry[];
  fontFamily: string;
  onApply: (windowFilters: NewsWindowFilters) => void;
  onCancel: () => void;
}

export function NewsFiltersPanel({ windowValue, publishers, fontFamily, onApply, onCancel }: NewsFiltersPanelProps) {
  const { t } = useTranslation();
  const { getToken } = useAuth();
  const store = useNewsFiltersStore();

  const [globalDraft, setGlobalDraft] = useState<NewsGlobalFilters>({
    feeds: [...store.feeds],
    publishersInclude: [...store.publishersInclude],
    publishersExclude: [...store.publishersExclude],
    includes: [...store.includes],
    excludes: [...store.excludes],
    classAction: store.classAction,
  });
  const [windowDraft, setWindowDraft] = useState<NewsWindowFilters>({ ...windowValue });
  const [section, setSection] = useState<Section>('sources');
  const [publisherQuery, setPublisherQuery] = useState('');

  const setG = (patch: Partial<NewsGlobalFilters>) => setGlobalDraft(prev => ({ ...prev, ...patch }));
  const setW = (patch: Partial<NewsWindowFilters>) => setWindowDraft(prev => ({ ...prev, ...patch }));

  const toggleFeed = (key: string) => {
    setG({
      feeds: globalDraft.feeds.includes(key)
        ? globalDraft.feeds.filter(f => f !== key)
        : [...globalDraft.feeds, key],
    });
  };

  const publisherState = (name: string): 'none' | 'include' | 'exclude' => {
    if (globalDraft.publishersInclude.includes(name)) return 'include';
    if (globalDraft.publishersExclude.includes(name)) return 'exclude';
    return 'none';
  };

  const cyclePublisher = (name: string) => {
    const state = publisherState(name);
    if (state === 'none') {
      setG({ publishersInclude: [...globalDraft.publishersInclude, name] });
    } else if (state === 'include') {
      setG({
        publishersInclude: globalDraft.publishersInclude.filter(p => p !== name),
        publishersExclude: [...globalDraft.publishersExclude, name],
      });
    } else {
      setG({ publishersExclude: globalDraft.publishersExclude.filter(p => p !== name) });
    }
  };

  const visiblePublishers = useMemo(() => {
    const q = publisherQuery.trim().toLowerCase();
    // Publishers marcados que ya no están en el feed cargado siguen visibles
    const known = new Set(publishers.map(p => p.name));
    const extra = [...globalDraft.publishersInclude, ...globalDraft.publishersExclude]
      .filter(name => !known.has(name))
      .map(name => ({ name, count: 0 }));
    const all = [...publishers, ...extra];
    return (q ? all.filter(p => p.name.toLowerCase().includes(q)) : all).slice(0, 200);
  }, [publishers, publisherQuery, globalDraft.publishersInclude, globalDraft.publishersExclude]);

  const handleSave = () => {
    store.setGlobalFilters(globalDraft);
    // Persistir en la cuenta (fire-and-forget; localStorage ya es caché local)
    saveNewsFiltersToBackend(
      (url, options) => authFetchStandalone(url, getToken, options),
      globalDraft
    );
    onApply(windowDraft);
  };

  const handleClear = () => {
    setGlobalDraft({ ...EMPTY_GLOBAL_FILTERS });
    setWindowDraft({ ...EMPTY_WINDOW_FILTERS });
  };

  const SECTIONS: { key: Section; label: string; scope: 'global' | 'window' }[] = [
    { key: 'sources', label: t('news.filters.sources'), scope: 'global' },
    { key: 'publishers', label: t('news.filters.publishers'), scope: 'global' },
    { key: 'keywords', label: t('news.filters.keywords'), scope: 'global' },
    { key: 'classAction', label: t('news.filters.classAction'), scope: 'global' },
    { key: 'dates', label: t('news.filters.dateRange'), scope: 'window' },
    { key: 'advanced', label: t('news.filters.advanced'), scope: 'window' },
  ];

  const inputCls = 'px-1.5 py-0.5 text-[10px] border border-border rounded focus:outline-none focus:border-blue-400 bg-surface text-foreground';

  const activeDates = windowDraft.dateFrom || windowDraft.dateTo
    ? `${windowDraft.dateFrom || '…'} → ${windowDraft.dateTo || '…'}`
    : null;

  let lastScope: 'global' | 'window' | null = null;

  return (
    <div className="absolute inset-0 z-20 bg-surface flex flex-col" style={{ fontFamily }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-foreground">
          {t('news.filters.title')}
        </span>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setGlobalDraft({ ...RECOMMENDED_FILTERS })}
            className="px-2 py-0.5 text-[10px] rounded border border-blue-500/40 text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 transition-colors">
            {t('news.filters.recommended')}
          </button>
          <button onClick={handleClear}
            className="px-2 py-0.5 text-[10px] rounded border border-border text-foreground/80 hover:bg-surface-hover transition-colors">
            {t('news.filters.clearFilters')}
          </button>
          <button onClick={onCancel}
            className="px-2 py-0.5 text-[10px] rounded border border-border text-foreground/80 hover:bg-surface-hover transition-colors">
            {t('common.cancel')}
          </button>
          <button onClick={handleSave}
            className="px-2.5 py-0.5 text-[10px] rounded bg-emerald-600 text-white hover:bg-emerald-700 font-medium transition-colors">
            {t('common.save')}
          </button>
        </div>
      </div>

      {/* Body: sidebar + content */}
      <div className="flex flex-1 min-h-0">
        <div className="w-36 shrink-0 border-r border-border py-1 overflow-y-auto">
          {SECTIONS.map(s => {
            const showDivider = lastScope !== null && lastScope !== s.scope;
            lastScope = s.scope;
            return (
              <React.Fragment key={s.key}>
                {showDivider && (
                  <div className="px-3 pt-2 pb-0.5 text-[8px] uppercase tracking-wider text-muted-fg border-t border-border-subtle mt-1">
                    {t('news.filters.thisWindow')}
                  </div>
                )}
                <button onClick={() => setSection(s.key)}
                  className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${
                    section === s.key
                      ? 'bg-surface-inset text-foreground font-medium'
                      : 'text-muted-fg hover:text-foreground hover:bg-surface-hover'
                  }`}>
                  {s.label}
                </button>
              </React.Fragment>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {section === 'sources' && (
            <div className="space-y-0.5">
              {NEWS_FEEDS.map(feed => (
                <label key={feed.key}
                  className="flex items-center gap-2 px-1 py-1 cursor-pointer rounded hover:bg-surface-hover">
                  <input type="checkbox"
                    checked={globalDraft.feeds.includes(feed.key)}
                    onChange={() => toggleFeed(feed.key)}
                    className="w-3 h-3 rounded border-border text-primary focus:ring-0 focus:ring-offset-0" />
                  <span className="text-[11px] text-foreground">{feed.label}</span>
                </label>
              ))}
              <p className="pt-2 text-[9px] text-muted-fg">{t('news.filters.sourcesHint')}</p>
            </div>
          )}

          {section === 'publishers' && (
            <div>
              <input
                type="text"
                value={publisherQuery}
                onChange={(e) => setPublisherQuery(e.target.value)}
                placeholder={t('common.search')}
                className={`${inputCls} w-44 mb-2`}
                style={{ fontFamily }}
              />
              <p className="text-[9px] text-muted-fg mb-1.5">{t('news.filters.publishersHint')}</p>
              <div className="space-y-0.5">
                {visiblePublishers.map(p => (
                  <div key={p.name} className="flex items-center gap-2 px-1 py-0.5 rounded hover:bg-surface-hover">
                    <TriState state={publisherState(p.name)} onCycle={() => cyclePublisher(p.name)} />
                    <span className="text-[11px] text-foreground flex-1 truncate">{p.name}</span>
                    {p.count > 0 && <span className="text-[9px] text-muted-fg tabular-nums">{p.count}</span>}
                  </div>
                ))}
                {visiblePublishers.length === 0 && (
                  <p className="text-[10px] text-muted-fg px-1 py-2">—</p>
                )}
              </div>
            </div>
          )}

          {section === 'keywords' && (
            <div className="space-y-4">
              <KeywordList
                label={t('news.filters.includesLabel')}
                hint={t('news.filters.includesHint')}
                values={globalDraft.includes}
                onChange={(next) => setG({ includes: next })}
                fontFamily={fontFamily}
                accent="include"
              />
              <KeywordList
                label={t('news.filters.excludesLabel')}
                hint={t('news.filters.excludesHint')}
                values={globalDraft.excludes}
                onChange={(next) => setG({ excludes: next })}
                fontFamily={fontFamily}
                accent="exclude"
              />
            </div>
          )}

          {section === 'classAction' && (
            <div className="space-y-1">
              {([
                { value: 'show', label: t('news.filters.caShow') },
                { value: 'hide', label: t('news.filters.caHide') },
                { value: 'only', label: t('news.filters.caOnly') },
              ] as const).map(opt => (
                <label key={opt.value} className="flex items-center gap-2 px-1 py-1 cursor-pointer rounded hover:bg-surface-hover">
                  <input type="radio" name="classAction"
                    checked={globalDraft.classAction === opt.value}
                    onChange={() => setG({ classAction: opt.value })}
                    className="w-3 h-3 border-border text-primary focus:ring-0 focus:ring-offset-0" />
                  <span className="text-[11px] text-foreground">{opt.label}</span>
                </label>
              ))}
              <p className="pt-2 text-[9px] text-muted-fg">{t('news.filters.caHint')}</p>
            </div>
          )}

          {section === 'dates' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-fg w-10">{t('news.dateFrom')}</span>
                <input type="date" value={windowDraft.dateFrom}
                  onChange={(e) => setW({ dateFrom: e.target.value })}
                  className={`${inputCls} w-[120px]`} style={{ fontFamily }} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-fg w-10">{t('news.dateTo')}</span>
                <input type="date" value={windowDraft.dateTo}
                  onChange={(e) => setW({ dateTo: e.target.value })}
                  className={`${inputCls} w-[120px]`} style={{ fontFamily }} />
              </div>
              <div className="flex items-center gap-1 pt-1">
                {[
                  { label: t('news.today'), days: 0 },
                  { label: '7d', days: 7 },
                  { label: '30d', days: 30 },
                  { label: '90d', days: 90 },
                  { label: 'YTD', days: -1 },
                ].map(r => (
                  <button key={r.label} type="button"
                    onClick={() => { const { from, to } = getQuickDateRange(r.days); setW({ dateFrom: from, dateTo: to }); }}
                    className="px-1.5 py-0.5 text-[9px] text-blue-600 dark:text-blue-400 border border-blue-500/30 hover:border-blue-500/50 hover:bg-blue-500/10 rounded transition-colors">
                    {r.label}
                  </button>
                ))}
                {(windowDraft.dateFrom || windowDraft.dateTo) && (
                  <button type="button" onClick={() => setW({ dateFrom: '', dateTo: '' })}
                    className="p-0.5 text-muted-fg hover:text-foreground/80">
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
              <p className="pt-1 text-[9px] text-muted-fg">{t('news.filters.serverHint')}</p>
            </div>
          )}

          {section === 'advanced' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-fg w-14">{t('news.tags')}</span>
                <input type="text" value={windowDraft.tags} onChange={(e) => setW({ tags: e.target.value })}
                  placeholder={t('news.tags')} className={`${inputCls} w-40`} style={{ fontFamily }} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-fg w-14">{t('news.author')}</span>
                <input type="text" value={windowDraft.author} onChange={(e) => setW({ author: e.target.value })}
                  placeholder={t('news.author')} className={`${inputCls} w-40`} style={{ fontFamily }} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-fg w-14">{t('news.channels')}</span>
                <input type="text" value={windowDraft.channels} onChange={(e) => setW({ channels: e.target.value })}
                  placeholder={t('news.channels')} className={`${inputCls} w-40`} style={{ fontFamily }} />
              </div>
              <p className="pt-1 text-[9px] text-muted-fg">{t('news.filters.serverHint')}</p>
            </div>
          )}
        </div>
      </div>

      {/* Footer: resumen */}
      <div className="border-t border-border px-3 py-2 space-y-1 shrink-0 text-[10px] max-h-28 overflow-y-auto">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-muted-fg">{t('news.filters.sources')}:</span>
          {globalDraft.feeds.length === 0 ? (
            <span className="text-foreground">{t('news.filters.all')}</span>
          ) : (
            globalDraft.feeds.map(key => (
              <button key={key} onClick={() => toggleFeed(key)}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border text-foreground hover:bg-surface-hover">
                <span className="text-muted-fg">−</span> {NEWS_FEEDS.find(f => f.key === key)?.label || key}
              </button>
            ))
          )}
          {(globalDraft.publishersInclude.length > 0 || globalDraft.publishersExclude.length > 0) && (
            <>
              <span className="text-muted-fg ml-2">{t('news.filters.publishers')}:</span>
              {globalDraft.publishersInclude.map(p => (
                <span key={p} className="px-1.5 py-0.5 rounded border border-emerald-500/40 text-emerald-600 dark:text-emerald-400">✓ {p}</span>
              ))}
              {globalDraft.publishersExclude.map(p => (
                <span key={p} className="px-1.5 py-0.5 rounded border border-rose-500/40 text-rose-600 dark:text-rose-400">✗ {p}</span>
              ))}
            </>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          {globalDraft.includes.length > 0 && (
            <>
              <span className="text-muted-fg">{t('news.filters.includesLabel')}:</span>
              {globalDraft.includes.map(k => <span key={k} className="px-1.5 py-0.5 rounded border border-border text-foreground">{k}</span>)}
            </>
          )}
          {globalDraft.excludes.length > 0 && (
            <>
              <span className="text-muted-fg">{t('news.filters.excludesLabel')}:</span>
              {globalDraft.excludes.map(k => <span key={k} className="px-1.5 py-0.5 rounded border border-border text-foreground line-through">{k}</span>)}
            </>
          )}
          {globalDraft.classAction !== 'show' && (
            <span className="px-1.5 py-0.5 rounded border border-border text-foreground">
              {globalDraft.classAction === 'hide' ? t('news.filters.caHide') : t('news.filters.caOnly')}
            </span>
          )}
          <span className="text-muted-fg ml-2">{t('news.filters.dateRange')}:</span>
          <span className="text-foreground">{activeDates || t('news.filters.all')}</span>
        </div>
      </div>
    </div>
  );
}
