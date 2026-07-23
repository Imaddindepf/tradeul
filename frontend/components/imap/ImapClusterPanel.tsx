'use client';

/**
 * Hover/click popup for a venue cluster — Godel-style: the venues in the
 * cluster with their live local clock and a 24h session timeline + now marker.
 */

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { formatLocalTime, localMinutesNow, minutesToLabel } from './geo';
import type { ImapVenue, SessionSegment, VenueCluster } from './types';

/** Status pill + dot styling per venue (includes pre/post market phases). */
function venueStatusUi(v: ImapVenue) {
  const s = v.status ?? (v.isMarketOpen ? 'open' : 'closed');
  if (s === 'open')
    return { label: 'Open', pill: 'bg-[#34d399]/15 text-[#34d399]', dot: 'bg-[#34d399]' };
  if (s === 'pre')
    return { label: 'Pre', pill: 'bg-[#fbbf24]/15 text-[#fbbf24]', dot: 'bg-[#fbbf24]' };
  if (s === 'post')
    return { label: 'Post', pill: 'bg-[#fbbf24]/15 text-[#fbbf24]', dot: 'bg-[#fbbf24]' };
  if (s === 'break')
    return { label: 'Break', pill: 'bg-[#fbbf24]/15 text-[#fbbf24]', dot: 'bg-[#fbbf24]' };
  return { label: 'Closed', pill: 'bg-muted-fg/15 text-muted-fg', dot: 'bg-muted-fg/40' };
}

interface ImapClusterPanelProps {
  cluster: VenueCluster;
  now: Date;
  /** cluster centre in map-container px */
  anchor: { x: number; y: number };
  containerWidth: number;
  containerHeight: number;
}

interface BarSegment {
  left: number;
  width: number;
  kind: 'regular' | 'break' | 'pre' | 'post' | 'closed';
}

const PANEL_W = 250;

function buildSegments(sessions: SessionSegment[]): BarSegment[] {
  const DAY = 1440;
  const sorted = [...(sessions ?? [])]
    .filter((s) => Number.isFinite(s.startMin) && Number.isFinite(s.endMin) && s.endMin > s.startMin)
    .sort((a, b) => a.startMin - b.startMin);
  const out: BarSegment[] = [];
  let cursor = 0;
  const kindOf = (t: SessionSegment['type']): BarSegment['kind'] => {
    if (t === 'break' || t === 'lunch') return 'break';
    if (t === 'pre') return 'pre';
    if (t === 'post') return 'post';
    return 'regular';
  };
  for (const s of sorted) {
    const start = Math.max(0, Math.min(DAY, s.startMin));
    const end = Math.max(0, Math.min(DAY, s.endMin));
    if (start > cursor) out.push({ left: (cursor / DAY) * 100, width: ((start - cursor) / DAY) * 100, kind: 'closed' });
    out.push({ left: (start / DAY) * 100, width: ((end - start) / DAY) * 100, kind: kindOf(s.type) });
    cursor = Math.max(cursor, end);
  }
  if (cursor < DAY) out.push({ left: (cursor / DAY) * 100, width: ((DAY - cursor) / DAY) * 100, kind: 'closed' });
  return out;
}

function VenueTimeline({ sessions, timezone, now }: { sessions: SessionSegment[]; timezone: string; now: Date }) {
  const segments = useMemo(() => buildSegments(sessions), [sessions]);
  const labels = useMemo(() => {
    const set = new Set<number>();
    for (const s of sessions ?? []) {
      if (Number.isFinite(s.startMin)) set.add(Math.round(s.startMin));
      if (Number.isFinite(s.endMin)) set.add(Math.round(s.endMin));
    }
    return [...set].filter((m) => m > 0 && m < 1440).sort((a, b) => a - b);
  }, [sessions]);
  const nowPct = (localMinutesNow(timezone, now) / 1440) * 100;

  return (
    <div className="mt-1 w-full select-none">
      <div className="relative h-[6px] w-full overflow-hidden rounded-[1px] bg-surface-inset">
        {segments.map((seg, i) => (
          <div
            key={`${seg.kind}-${i}`}
            className={cn(
              'absolute top-0 bottom-0',
              seg.kind === 'regular' && 'bg-[#34d399]/75',
              (seg.kind === 'pre' || seg.kind === 'post') && 'bg-[#fbbf24]/65',
              seg.kind === 'closed' && 'bg-transparent',
            )}
            style={{
              left: `${seg.left}%`,
              width: `${Math.max(seg.width, 0.15)}%`,
              ...(seg.kind === 'break'
                ? {
                    backgroundColor: 'var(--color-warning)',
                    backgroundImage:
                      'repeating-linear-gradient(-45deg, transparent, transparent 1.5px, rgba(0,0,0,0.3) 1.5px, rgba(0,0,0,0.3) 3px)',
                  }
                : undefined),
            }}
          />
        ))}
        <div className="absolute top-0 bottom-0 z-10 w-px bg-foreground" style={{ left: `${nowPct}%` }} aria-hidden />
      </div>
      {labels.length > 0 && (
        <div className="relative mt-[3px] h-2.5 w-full">
          {labels.map((m) => (
            <span
              key={m}
              className="absolute top-0 -translate-x-1/2 text-[7px] leading-none tabular-nums text-muted-fg/70"
              style={{ left: `${(m / 1440) * 100}%` }}
            >
              {minutesToLabel(m)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ImapClusterPanelInner({
  cluster,
  now,
  anchor,
  containerWidth,
  containerHeight,
}: ImapClusterPanelProps) {
  const venues = useMemo(() => {
    const rank = (v: ImapVenue) => {
      const s = v.status ?? (v.isMarketOpen ? 'open' : 'closed');
      if (s === 'open') return 0;
      if (s === 'pre' || s === 'post') return 1;
      if (s === 'break') return 2;
      return 3;
    };
    return [...cluster.venues].sort(
      (a, b) => rank(a) - rank(b) || a.exchange.localeCompare(b.exchange),
    );
  }, [cluster.venues]);

  // place to the right of the marker, flipping left near the right edge
  const flipLeft = anchor.x + 18 + PANEL_W > containerWidth;
  const left = flipLeft ? Math.max(6, anchor.x - 18 - PANEL_W) : anchor.x + 18;
  const estH = Math.min(340, 44 + venues.length * 46);
  const top = Math.max(6, Math.min(containerHeight - estH - 6, anchor.y - 20));

  return (
    <div
      className="pointer-events-none absolute z-20 overflow-hidden rounded border border-border bg-surface/95 shadow-lg backdrop-blur-sm"
      style={{ left, top, width: PANEL_W }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle px-2.5 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-foreground">
          {cluster.venues.length === 1
            ? cluster.venues[0].mic || cluster.venues[0].exchange
            : `${cluster.venues.length} venues`}
        </span>
        {cluster.openCount > 0 && (
          <span className="text-[9px] font-semibold tabular-nums text-[#34d399]">
            {cluster.openCount} open
          </span>
        )}
      </div>

      <div className="max-h-[300px] overflow-y-auto">
        {venues.map((v) => {
          const ui = venueStatusUi(v);
          return (
            <div
              key={v.exchange}
              className="block w-full border-b border-border-subtle px-2.5 py-1.5 text-left last:border-b-0"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="flex items-center gap-1.5 truncate">
                  <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', ui.dot)} aria-hidden />
                  <span className="text-[10px] font-semibold tabular-nums text-foreground">
                    {v.mic || v.exchange}
                  </span>
                  <span className="truncate text-[9px] text-muted-fg">{v.name}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-[1px] text-[7.5px] font-semibold uppercase tracking-[0.06em] leading-[1.4]',
                      ui.pill,
                    )}
                  >
                    {ui.label}
                  </span>
                  <span className="text-[10px] tabular-nums text-foreground">
                    {formatLocalTime(v.timezone, now)}
                  </span>
                </span>
              </div>
              <VenueTimeline sessions={v.sessions ?? []} timezone={v.timezone} now={now} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const ImapClusterPanel = memo(ImapClusterPanelInner);
export default ImapClusterPanel;
