'use client';

/**
 * IMAP — World Venue Map
 * Sidebar + responsive equirectangular map (viewBox-fit, no distortion).
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { cn } from '@/lib/utils';
import { ImapSidebar } from './ImapSidebar';
import { ImapMap } from './ImapMap';
import { useImapData } from './useImapData';
import type { ImapWindowState, VenueCluster } from './types';

const FONT_CLASS_MAP: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

export function ImapContent() {
  const { t } = useTranslation();
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const { state, updateState } = useWindowState<ImapWindowState>();
  const { venues, loading, error, now, refresh } = useImapData();

  const filter = state.filter ?? '';
  const selectedExchange = state.selectedExchange ?? null;
  const selectedClusterId = state.selectedClusterId ?? null;

  const handleFilterChange = useCallback(
    (value: string) => updateState({ filter: value }),
    [updateState],
  );

  const handleSelectVenue = useCallback(
    (exchange: string) => {
      updateState({ selectedExchange: exchange, selectedClusterId: null });
    },
    [updateState],
  );

  const handleSelectCluster = useCallback(
    (cluster: VenueCluster) => {
      updateState({
        selectedClusterId: cluster.id,
        selectedExchange: cluster.venues.length === 1 ? cluster.venues[0].exchange : null,
      });
    },
    [updateState],
  );

  const handleClearSelection = useCallback(() => {
    updateState({ selectedClusterId: null, selectedExchange: null });
  }, [updateState]);

  if (loading && venues.length === 0) {
    return (
      <div
        className={cn(
          'flex h-full items-center justify-center bg-background text-muted-fg',
          fontClass,
        )}
      >
        <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
        <span className="text-[11px]">{t('imap.loading')}</span>
      </div>
    );
  }

  if (error && venues.length === 0) {
    return (
      <div
        className={cn(
          'flex h-full flex-col items-center justify-center gap-2 bg-background',
          fontClass,
        )}
      >
        <span className="text-[11px] text-danger">{t('imap.error')}</span>
        <button
          type="button"
          onClick={refresh}
          className="rounded border border-border px-2.5 py-1 text-[10px] hover:bg-surface-hover focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
        >
          {t('imap.retry')}
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex h-full w-full overflow-hidden bg-background text-foreground select-none',
        fontClass,
      )}
    >
      <ImapSidebar
        venues={venues}
        filter={filter}
        selectedExchange={selectedExchange}
        now={now}
        onFilterChange={handleFilterChange}
        onSelectVenue={handleSelectVenue}
      />

      <div className="relative min-w-0 flex-1">
        <ImapMap
          venues={venues}
          selectedClusterId={selectedClusterId}
          selectedExchange={selectedExchange}
          onSelectCluster={handleSelectCluster}
          onClearSelection={handleClearSelection}
        />
      </div>
    </div>
  );
}

export default ImapContent;
