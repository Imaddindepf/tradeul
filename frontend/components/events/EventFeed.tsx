'use client';

/**
 * EventFeed - Real-time market events feed component
 * 
 * Displays a scrollable list of market events:
 * - New highs/lows
 * - VWAP crosses
 * - RVOL spikes
 * - Trading halts/resumes
 */

import React, { useEffect, useRef, useState, useMemo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  useMarketEvents,
  MarketEvent,
  MarketEventType,
  EVENT_TYPE_LABELS,
  EVENT_TYPE_COLORS,
  EVENT_TYPE_ICONS,
  MarketEventsFilter,
} from '@/hooks/useMarketEvents';
import { cn } from '@/lib/utils';

// ============================================================================
// TYPES
// ============================================================================

interface EventFeedProps {
  /** Maximum events to display */
  maxEvents?: number;
  /** Filter events by type, symbol, etc. */
  filter?: MarketEventsFilter;
  /** Show filters UI */
  showFilters?: boolean;
  /** Compact mode (less padding, smaller text) */
  compact?: boolean;
  /** Custom class name */
  className?: string;
  /** Callback when event is clicked */
  onEventClick?: (event: MarketEvent) => void;
}

// ============================================================================
// EVENT ROW COMPONENT
// ============================================================================

interface EventRowProps {
  event: MarketEvent;
  compact?: boolean;
  onClick?: () => void;
}

function EventRow({ event, compact, onClick }: EventRowProps) {
  const timeAgo = useMemo(() => {
    try {
      return formatDistanceToNow(new Date(event.timestamp), { addSuffix: true });
    } catch {
      return '';
    }
  }, [event.timestamp]);

  const priceFormatted = event.price?.toFixed(2) ?? '-';
  const changeFormatted = event.change_percent
    ? `${event.change_percent > 0 ? '+' : ''}${event.change_percent.toFixed(2)}%`
    : '';
  const rvolFormatted = event.rvol ? `${event.rvol.toFixed(1)}x` : '';
  const volumeFormatted = event.volume
    ? event.volume >= 1_000_000
      ? `${(event.volume / 1_000_000).toFixed(1)}M`
      : event.volume >= 1_000
        ? `${(event.volume / 1_000).toFixed(0)}K`
        : event.volume.toString()
    : '';

  const icon = EVENT_TYPE_ICONS[event.event_type] || '📊';
  const colorClass = EVENT_TYPE_COLORS[event.event_type] || 'text-gray-400';
  const label = EVENT_TYPE_LABELS[event.event_type] || event.event_type;

  const isPositive = ['new_high', 'vwap_cross_up', 'resume', 'crossed_above_open', 'crossed_above_prev_close',
    'running_up', 'percent_up_5', 'percent_up_10', 'pullback_75_from_low', 'pullback_25_from_low', 'gap_down_reversal'].includes(event.event_type);
  const isNegative = ['new_low', 'vwap_cross_down', 'halt', 'crossed_below_open', 'crossed_below_prev_close',
    'running_down', 'percent_down_5', 'percent_down_10', 'pullback_75_from_high', 'pullback_25_from_high', 'gap_up_reversal'].includes(event.event_type);

  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 border-b border-zinc-800/50 transition-colors',
        'hover:bg-zinc-800/30 cursor-pointer',
        compact ? 'py-1.5 px-2' : 'py-2 px-3',
      )}
    >
      {/* Icon */}
      <span className="text-lg flex-shrink-0">{icon}</span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Symbol + Event Type */}
        <div className="flex items-center gap-2">
          <span className="font-bold text-white">{event.symbol}</span>
          <span className={cn('text-xs font-medium', colorClass)}>{label}</span>
        </div>

        {/* Price + Change */}
        <div className={cn(
          'flex items-center gap-2',
          compact ? 'text-xs' : 'text-sm',
          'text-zinc-400'
        )}>
          <span className={cn(
            'font-mono',
            isPositive && 'text-green-400',
            isNegative && 'text-red-400',
          )}>
            ${priceFormatted}
          </span>
          {changeFormatted && (
            <span className={cn(
              event.change_percent && event.change_percent > 0 ? 'text-green-400' : 'text-red-400'
            )}>
              {changeFormatted}
            </span>
          )}
          {rvolFormatted && (
            <span className="text-purple-400">{rvolFormatted}</span>
          )}
          {volumeFormatted && (
            <span className="text-zinc-500">{volumeFormatted}</span>
          )}
        </div>
      </div>

      {/* Time */}
      <span className={cn(
        'flex-shrink-0 text-zinc-500',
        compact ? 'text-[10px]' : 'text-xs'
      )}>
        {timeAgo}
      </span>
    </div>
  );
}

// ============================================================================
// FILTER BAR COMPONENT
// ============================================================================

interface FilterBarProps {
  selectedTypes: MarketEventType[];
  onTypesChange: (types: MarketEventType[]) => void;
}

function FilterBar({ selectedTypes, onTypesChange }: FilterBarProps) {
  const allTypes: MarketEventType[] = [
    'new_high', 'new_low', 'vwap_cross_up', 'vwap_cross_down',
    'rvol_spike', 'volume_surge', 'halt', 'resume'
  ];

  const toggleType = (type: MarketEventType) => {
    if (selectedTypes.includes(type)) {
      onTypesChange(selectedTypes.filter(t => t !== type));
    } else {
      onTypesChange([...selectedTypes, type]);
    }
  };

  const selectAll = () => onTypesChange([]);
  const selectNone = () => onTypesChange([...allTypes]); // All filtered = none shown

  return (
    <div className="flex flex-wrap items-center gap-1 p-2 border-b border-zinc-800 bg-zinc-900/50">
      <button
        onClick={selectAll}
        className={cn(
          'px-2 py-0.5 text-xs rounded transition-colors',
          selectedTypes.length === 0
            ? 'bg-blue-600 text-white'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
        )}
      >
        All
      </button>

      {allTypes.map(type => (
        <button
          key={type}
          onClick={() => toggleType(type)}
          className={cn(
            'px-2 py-0.5 text-xs rounded transition-colors flex items-center gap-1',
            selectedTypes.includes(type)
              ? 'bg-zinc-700 text-zinc-300'
              : 'bg-zinc-800 text-zinc-500 hover:bg-zinc-700',
          )}
        >
          <span>{EVENT_TYPE_ICONS[type]}</span>
          <span className="hidden sm:inline">{EVENT_TYPE_LABELS[type]}</span>
        </button>
      ))}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function EventFeed({
  maxEvents = 50,
  filter: externalFilter,
  showFilters = false,
  compact = false,
  className,
  onEventClick,
}: EventFeedProps) {
  const [selectedTypes, setSelectedTypes] = useState<MarketEventType[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Combine external filter with local type filter
  const combinedFilter = useMemo((): MarketEventsFilter => ({
    ...externalFilter,
    eventTypes: selectedTypes.length > 0 ? selectedTypes : externalFilter?.eventTypes,
  }), [externalFilter, selectedTypes]);

  const { events, isSubscribed, subscribe } = useMarketEvents({
    autoSubscribe: true,
    filter: selectedTypes.length > 0 ? combinedFilter : externalFilter,
    maxEvents,
  });

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [events, autoScroll]);

  // Detect manual scroll
  const handleScroll = () => {
    if (containerRef.current) {
      setAutoScroll(containerRef.current.scrollTop < 50);
    }
  };

  return (
    <div className={cn('flex flex-col h-full bg-zinc-900', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">Market Events</span>
          <span className={cn(
            'w-2 h-2 rounded-full',
            isSubscribed ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'
          )} />
        </div>
        <span className="text-xs text-zinc-500">{events.length} events</span>
      </div>

      {/* Filters */}
      {showFilters && (
        <FilterBar
          selectedTypes={selectedTypes}
          onTypesChange={setSelectedTypes}
        />
      )}

      {/* Events List */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500">
            <span className="text-2xl mb-2">📊</span>
            <span className="text-sm">Waiting for events...</span>
            <span className="text-xs mt-1">Events will appear here in real-time</span>
          </div>
        ) : (
          events.map(event => (
            <EventRow
              key={event.id}
              event={event}
              compact={compact}
              onClick={() => onEventClick?.(event)}
            />
          ))
        )}
      </div>

      {/* Auto-scroll indicator */}
      {!autoScroll && events.length > 0 && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (containerRef.current) {
              containerRef.current.scrollTop = 0;
            }
          }}
          className="absolute bottom-4 right-4 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-full shadow-lg hover:bg-blue-500 transition-colors"
        >
          ↑ New events
        </button>
      )}
    </div>
  );
}

export default EventFeed;
