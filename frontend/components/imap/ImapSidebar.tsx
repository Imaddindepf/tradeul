'use client';

import { memo, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { Virtuoso } from 'react-virtuoso';
import { cn } from '@/lib/utils';
import { formatLocalTime } from './geo';
import type { ImapVenue } from './types';

interface ImapSidebarProps {
  venues: ImapVenue[];
  filter: string;
  selectedExchange: string | null;
  now: Date;
  onFilterChange: (value: string) => void;
  onSelectVenue: (exchange: string) => void;
  className?: string;
}

type ListItem =
  | { kind: 'header'; key: string; label: string; count?: number; tone?: 'open' | 'muted' }
  | { kind: 'venue'; key: string; venue: ImapVenue };

function sortVenues(list: ImapVenue[]): ImapVenue[] {
  return [...list].sort((a, b) => a.exchange.localeCompare(b.exchange));
}

function ImapSidebarInner({
  venues,
  filter,
  selectedExchange,
  now,
  onFilterChange,
  onSelectVenue,
  className,
}: ImapSidebarProps) {
  const { t } = useTranslation();

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return venues;
    return venues.filter(
      (v) =>
        v.exchange.toLowerCase().includes(q) ||
        (v.mic || '').toLowerCase().includes(q) ||
        v.name.toLowerCase().includes(q) ||
        v.city?.toLowerCase().includes(q) ||
        v.country?.toLowerCase().includes(q),
    );
  }, [venues, filter]);

  const openVenues = useMemo(
    () => sortVenues(filtered.filter((v) => v.isMarketOpen)),
    [filtered],
  );
  const extendedVenues = useMemo(
    () =>
      sortVenues(
        filtered.filter(
          (v) => !v.isMarketOpen && (v.status === 'pre' || v.status === 'post' || v.status === 'break'),
        ),
      ),
    [filtered],
  );
  const closedVenues = useMemo(
    () =>
      sortVenues(
        filtered.filter(
          (v) => !v.isMarketOpen && v.status !== 'pre' && v.status !== 'post' && v.status !== 'break',
        ),
      ),
    [filtered],
  );

  const items = useMemo<ListItem[]>(() => {
    const out: ListItem[] = [];
    if (openVenues.length > 0) {
      out.push({
        kind: 'header',
        key: 'h-open',
        label: t('imap.openNow'),
        count: openVenues.length,
        tone: 'open',
      });
      for (const venue of openVenues) {
        out.push({ kind: 'venue', key: `o-${venue.exchange}`, venue });
      }
    }
    if (extendedVenues.length > 0) {
      out.push({
        kind: 'header',
        key: 'h-extended',
        label: 'PRE/POST',
        count: extendedVenues.length,
        tone: 'muted',
      });
      for (const venue of extendedVenues) {
        out.push({ kind: 'venue', key: `e-${venue.exchange}`, venue });
      }
    }
    if (closedVenues.length > 0) {
      out.push({
        kind: 'header',
        key: 'h-closed',
        label: t('imap.closed'),
        count: closedVenues.length,
        tone: 'muted',
      });
      for (const venue of closedVenues) {
        out.push({ kind: 'venue', key: `c-${venue.exchange}`, venue });
      }
    }
    return out;
  }, [openVenues, extendedVenues, closedVenues, t]);

  const renderItem = useCallback(
    (index: number) => {
      const item = items[index];
      if (!item) return null;
      if (item.kind === 'header') {
        return (
          <div className="sticky top-0 z-[1] flex items-center justify-between bg-surface px-2.5 py-1.5">
            <span className="text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-fg">
              {item.label}
            </span>
            {item.count != null && (
              <span
                className={cn(
                  'text-[9px] font-semibold tabular-nums',
                  item.tone === 'open' ? 'text-success' : 'text-muted-fg/70',
                )}
              >
                {item.count}
              </span>
            )}
          </div>
        );
      }
      const v = item.venue;
      const selected = selectedExchange === v.exchange;
      return (
        <button
          type="button"
          onClick={() => onSelectVenue(v.exchange)}
          className={cn(
            'flex w-full items-center gap-1.5 px-2.5 py-[5px] text-left transition-colors',
            'hover:bg-surface-hover focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary/40',
            selected && 'bg-surface-hover',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 shrink-0 rounded-full',
              v.isMarketOpen
                ? 'bg-[#34d399]'
                : v.status === 'pre' || v.status === 'post' || v.status === 'break'
                  ? 'bg-[#fbbf24]'
                  : 'bg-muted-fg/40',
            )}
            aria-hidden
          />
          <span className="w-[54px] shrink-0 text-[10px] font-semibold tabular-nums tracking-tight text-foreground">
            {v.mic || v.exchange}
          </span>
          <span className="min-w-0 flex-1 truncate text-[9px] text-muted-fg">{v.name}</span>
          <span className="shrink-0 text-[9px] tabular-nums text-muted-fg/80">
            {formatLocalTime(v.timezone, now)}
          </span>
        </button>
      );
    },
    [items, now, onSelectVenue, selectedExchange],
  );

  return (
    <aside
      className={cn(
        'flex h-full w-[272px] shrink-0 flex-col border-r border-border bg-surface',
        className,
      )}
    >
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-border-subtle shrink-0">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-fg">
          {t('imap.venues')}
        </span>
      </div>

      <div className="relative px-2 py-1.5 border-b border-border-subtle shrink-0">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-fg/55" />
        <input
          type="text"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
          placeholder={t('imap.filterPlaceholder')}
          className={cn(
            'w-full rounded border border-border bg-surface-inset py-1 pl-7 pr-2',
            'text-[10px] text-foreground placeholder:text-muted-fg/55',
            'focus:outline-none focus:ring-1 focus:ring-primary/40',
          )}
          aria-label={t('imap.filterPlaceholder')}
        />
      </div>

      <div className="min-h-0 flex-1">
        {filtered.length === 0 ? (
          <div className="px-3 py-6 text-center text-[10px] text-muted-fg">
            {t('imap.noResults')}
          </div>
        ) : (
          <Virtuoso
            style={{ height: '100%' }}
            totalCount={items.length}
            itemContent={renderItem}
            overscan={48}
          />
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border-subtle px-2.5 py-1.5 shrink-0 text-[9px]">
        <span className="text-muted-fg tabular-nums">
          {t('imap.venuesCount', { count: filtered.length })}
        </span>
        <span className="font-medium tabular-nums text-success">
          {t('imap.openCount', { count: openVenues.length })}
        </span>
      </div>
    </aside>
  );
}

export const ImapSidebar = memo(ImapSidebarInner);
export default ImapSidebar;
