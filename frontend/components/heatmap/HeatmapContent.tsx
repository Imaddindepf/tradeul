/**
 * HeatmapContent Component
 * 
 * Main container for the market heatmap visualization.
 * Follows the app's minimalist light theme.
 * Optimized for performance with responsive sizing.
 */

'use client';

import React, { useState, useCallback, useMemo, memo, useRef, useEffect } from 'react';
import { RefreshCw, Clock } from 'lucide-react';
import { useHeatmapData } from './useHeatmapData';
import HeatmapTreemap from './HeatmapTreemap';
import HeatmapControls from './HeatmapControls';
import HeatmapLegend from './HeatmapLegend';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { 
  useMarketSessionStore, 
  selectIsClosed, 
  selectSession,
  getSessionLabel 
} from '@/stores/useMarketSessionStore';

// Custom hook for container dimensions with debounce
// Only updates when user STOPS resizing (500ms delay) - prevents render spam
function useContainerSize(ref: React.RefObject<HTMLDivElement>) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSizeRef = useRef({ width: 0, height: 0 });
  
  useEffect(() => {
    if (!ref.current) return;
    
    const updateSize = () => {
      if (ref.current) {
        const newWidth = ref.current.offsetWidth;
        const newHeight = ref.current.offsetHeight;
        
        // Only update if size actually changed significantly (>5px)
        if (
          Math.abs(newWidth - lastSizeRef.current.width) > 5 ||
          Math.abs(newHeight - lastSizeRef.current.height) > 5
        ) {
          lastSizeRef.current = { width: newWidth, height: newHeight };
          setSize({ width: newWidth, height: newHeight });
        }
      }
    };
    
    // Initial size - immediate
    updateSize();
    
    // Debounced resize handler - only fires after 400ms of no resize activity
    const debouncedUpdate = () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(updateSize, 400);
    };
    
    const resizeObserver = new ResizeObserver(debouncedUpdate);
    resizeObserver.observe(ref.current);
    
    return () => {
      resizeObserver.disconnect();
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [ref]);
  
  return size;
}

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

interface HeatmapContentProps {
  onClose?: () => void;
}

// Format timestamp for display
const formatTime = (date: Date | null): string => {
  if (!date) return '--:--:--';
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
};

// Format large numbers
const formatMarketCap = (num: number): string => {
  if (num >= 1e12) return `$${(num / 1e12).toFixed(1)}T`;
  if (num >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
  return `$${(num / 1e6).toFixed(0)}M`;
};

type HeatmapWindowState = {
  viewLevel?: 'market' | 'sector';
  selectedSector?: string | null;
  metric?: string;
  sizeBy?: string;
}

function HeatmapContent({ onClose }: HeatmapContentProps) {
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
  const { state: windowState, updateState: updateWindowState } = useWindowState<HeatmapWindowState>();
  
  // Market session state
  const isClosed = useMarketSessionStore(selectIsClosed);
  const session = useMarketSessionStore(selectSession);
  const startPolling = useMarketSessionStore(state => state.startPolling);
  const stopPolling = useMarketSessionStore(state => state.stopPolling);
  
  // Start market session polling on mount
  useEffect(() => {
    startPolling(30000); // Poll every 30 seconds
    return () => stopPolling();
  }, [startPolling, stopPolling]);
  
  // Container ref for responsive sizing
  const containerRef = useRef<HTMLDivElement>(null);
  const containerSize = useContainerSize(containerRef);
  
  // View state - restored from window state
  const [viewLevel, setViewLevel] = useState<'market' | 'sector'>(windowState.viewLevel || 'market');
  const [selectedSector, setSelectedSector] = useState<string | null>(windowState.selectedSector ?? null);
  
  // Command executor for opening ticker windows
  const { executeTickerCommand } = useCommandExecutor();
  
  // Fetch heatmap data with polling
  const {
    data,
    isLoading,
    isUpdating,
    error,
    lastUpdate,
    filters,
    setFilters,
    refresh,
  } = useHeatmapData({
    pollInterval: 15000,
    enabled: true,
  });
  
  // Restore saved filters on mount
  useEffect(() => {
    const savedFilters: Partial<typeof filters> = {};
    if (windowState.metric) savedFilters.metric = windowState.metric as typeof filters.metric;
    if (windowState.sizeBy) savedFilters.sizeBy = windowState.sizeBy as typeof filters.sizeBy;
    if (Object.keys(savedFilters).length > 0) {
      setFilters(savedFilters);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist state changes
  useEffect(() => {
    updateWindowState({
      viewLevel,
      selectedSector,
      metric: filters.metric,
      sizeBy: filters.sizeBy,
    });
  }, [viewLevel, selectedSector, filters.metric, filters.sizeBy, updateWindowState]);

  // Extract available sectors from data
  const availableSectors = useMemo(() => {
    if (!data?.sectors) return [];
    return data.sectors.map(s => s.sector);
  }, [data]);
  
  // Handle ticker click - open description window
  const handleTickerClick = useCallback((symbol: string) => {
    executeTickerCommand(symbol, 'fan');
  }, [executeTickerCommand]);
  
  // Handle sector click - drill down
  const handleSectorClick = useCallback((sector: string) => {
    if (viewLevel === 'market') {
      setSelectedSector(sector);
      setViewLevel('sector');
    }
  }, [viewLevel]);
  
  // Handle back to market view
  const handleBackToMarket = useCallback(() => {
    setViewLevel('market');
    setSelectedSector(null);
  }, []);
  
  return (
    <div className={`h-full flex flex-col bg-white ${fontClass}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-4">
          {/* Title and breadcrumb */}
          <div className="flex items-center gap-2">
            {viewLevel === 'sector' && selectedSector && (
              <>
                <button
                  onClick={handleBackToMarket}
                  className="text-[11px] text-blue-600 hover:text-blue-700 font-medium"
                >
                  Market
                </button>
                <span className="text-slate-300">/</span>
              </>
            )}
            <h2 className="text-[13px] font-semibold text-slate-900">
              {viewLevel === 'sector' && selectedSector ? selectedSector : 'HEATMAP'}
            </h2>
          </div>
          
          {/* Stats */}
          {data && (
            <div className="flex items-center gap-3 text-[10px] text-slate-500">
              <span>
                <span className="text-slate-400">Tickers:</span>{' '}
                <span className="text-slate-700 font-medium">{data.total_tickers.toLocaleString()}</span>
              </span>
              <span>
                <span className="text-slate-400">Cap:</span>{' '}
                <span className="text-slate-700 font-medium">{formatMarketCap(data.total_market_cap)}</span>
              </span>
              <span>
                <span className="text-slate-400">Avg:</span>{' '}
                <span className={`font-medium ${data.market_avg_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {data.market_avg_change >= 0 ? '+' : ''}{data.market_avg_change.toFixed(2)}%
                </span>
              </span>
            </div>
          )}
        </div>
        
        {/* Right side: Status and controls */}
        <div className="flex items-center gap-3">
          {/* Legend */}
          <HeatmapLegend metric={filters.metric} />
          
          {/* Market session & data status */}
          <div className="flex items-center gap-2 text-[10px]">
            {/* Market session badge */}
            {session && (
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${
                session.current_session === 'MARKET_OPEN' 
                  ? 'bg-green-100 text-green-700' 
                  : session.current_session === 'PRE_MARKET'
                  ? 'bg-blue-100 text-blue-700'
                  : session.current_session === 'POST_MARKET'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-slate-100 text-slate-600'
              }`}>
                {getSessionLabel(session)}
              </span>
            )}
            
            {/* Historical data indicator (when using last close) */}
            {data && !data.is_realtime && (
              <span 
                className="flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-[9px]"
                title={`Data from: ${data.timestamp}`}
              >
                <Clock className="w-3 h-3" />
                Last Close
              </span>
            )}
            
            {/* Live indicator */}
            <div className="flex items-center gap-1">
              <div className={`w-1.5 h-1.5 rounded-full ${
                error 
                  ? 'bg-red-500' 
                  : data?.is_realtime 
                  ? 'bg-green-500 animate-pulse' 
                  : 'bg-amber-500'
              }`} />
              <span className="text-slate-400">
                {isLoading && !data ? 'Loading...' : formatTime(lastUpdate)}
              </span>
            </div>
          </div>
          
          {/* Refresh button */}
          <button
            onClick={refresh}
            disabled={isLoading}
            className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
      
      {/* Controls */}
      <HeatmapControls
        filters={filters}
        onFiltersChange={setFilters}
        availableSectors={availableSectors}
        isCompact={false}
      />
      
      {/* Main content - responsive container */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden bg-white">
        {/* Updating overlay - subtle indicator */}
        {isUpdating && data && (
          <div className="absolute top-2 right-2 z-10 flex items-center gap-1.5 px-2 py-1 bg-white/90 border border-slate-200 rounded shadow-sm">
            <div className="w-2 h-2 border border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-[9px] text-slate-500">Updating...</span>
          </div>
        )}
        
        {/* Error state */}
        {error && !data && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <p className="text-red-500 text-[11px] mb-2">Failed to load data</p>
              <p className="text-slate-400 text-[10px] mb-3">{error}</p>
              <button
                onClick={refresh}
                className="px-3 py-1 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-500"
              >
                Retry
              </button>
            </div>
          </div>
        )}
        
        {/* Loading state (initial only) */}
        {isLoading && !data && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-slate-400 text-[11px]">Loading market data...</p>
            </div>
          </div>
        )}
        
        {/* Treemap - responsive height */}
        {data && data.sectors && data.sectors.length > 0 && containerSize.height > 0 && (
          <HeatmapTreemap
            data={data}
            colorMetric={filters.metric}
            sizeMetric={filters.sizeBy}
            onTickerClick={handleTickerClick}
            onSectorClick={handleSectorClick}
            viewLevel={viewLevel}
            selectedSector={selectedSector}
            height={containerSize.height}
            width={containerSize.width}
          />
        )}
        
        {/* Empty state */}
        {data && (!data.sectors || data.sectors.length === 0) && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <p className="text-slate-500 text-[11px]">No data available for current filters</p>
              <p className="text-slate-400 text-[10px] mt-1">Try adjusting the market cap or sector filters</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Export memoized component
export default memo(HeatmapContent);
