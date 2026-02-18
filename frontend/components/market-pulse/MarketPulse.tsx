'use client';

import { useState, useCallback, useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useMarketPulse, useDrilldown, type PulseTab, type PerformanceEntry, type DrilldownTicker } from '@/hooks/useMarketPulse';
import { ArrowLeft, RefreshCw, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '-';
  if (Math.abs(n) >= 1e12) return `${(n / 1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(0);
}

function formatVolume(n: number | null | undefined): string {
  if (n == null) return '-';
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

function formatPrice(p: number | null | undefined): string {
  if (p == null) return '-';
  return p >= 1 ? p.toFixed(2) : p.toFixed(4);
}

function formatThemeName(name: string): string {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

const TABS: { key: PulseTab; label: string }[] = [
  { key: 'sectors', label: 'Sectors' },
  { key: 'industries', label: 'Industries' },
  { key: 'themes', label: 'Themes' },
];

function ChangeBar({ value, maxAbsValue }: { value: number; maxAbsValue: number }) {
  const pct = maxAbsValue > 0 ? Math.min(Math.abs(value) / maxAbsValue, 1) : 0;
  const width = `${pct * 100}%`;
  const isPositive = value >= 0;

  return (
    <div className="relative h-[14px] w-[80px] bg-slate-100 rounded-sm overflow-hidden">
      <div
        className={`absolute top-0 h-full rounded-sm transition-all duration-300 ${
          isPositive ? 'bg-emerald-500/30 left-1/2' : 'bg-red-500/30 right-1/2'
        }`}
        style={{ width }}
      />
    </div>
  );
}

function BreadthBar({ advancing, declining, count }: { advancing: number; declining: number; count: number }) {
  if (count === 0) return null;
  const advPct = (advancing / count) * 100;
  const decPct = (declining / count) * 100;

  return (
    <div className="flex h-[4px] w-full rounded-full overflow-hidden bg-slate-200">
      <div className="bg-emerald-500" style={{ width: `${advPct}%` }} />
      <div className="bg-slate-300 flex-1" />
      <div className="bg-red-500" style={{ width: `${decPct}%` }} />
    </div>
  );
}

function PerformanceRow({
  entry,
  maxAbsChange,
  onClick,
  isTheme,
}: {
  entry: PerformanceEntry;
  maxAbsChange: number;
  onClick: () => void;
  isTheme?: boolean;
}) {
  const change = entry.weighted_change;
  const isPositive = change >= 0;

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2 px-3 py-[7px] hover:bg-slate-50 transition-colors border-b border-slate-100 text-left group"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] font-medium text-slate-800 truncate">
            {isTheme ? formatThemeName(entry.name) : entry.name}
          </span>
          <span className="text-[10px] text-slate-400 shrink-0">
            {entry.count}
          </span>
        </div>
        <BreadthBar advancing={entry.advancing} declining={entry.declining} count={entry.count} />
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <ChangeBar value={change} maxAbsValue={maxAbsChange} />
        <span
          className={`text-[12px] font-mono w-[52px] text-right ${
            isPositive ? 'text-emerald-600' : 'text-red-600'
          }`}
        >
          {isPositive ? '+' : ''}{change.toFixed(2)}%
        </span>
        <div className="flex flex-col items-end w-[36px]">
          <span className="text-[9px] text-slate-400 leading-none">RVOL</span>
          <span className="text-[10px] font-mono text-slate-600 leading-none">
            {entry.avg_rvol.toFixed(1)}x
          </span>
        </div>
        <ChevronRight className="w-3 h-3 text-slate-300 group-hover:text-slate-500 transition-colors" />
      </div>
    </button>
  );
}

function DrilldownRow({ ticker }: { ticker: DrilldownTicker }) {
  const change = ticker.change_percent || 0;
  const isPositive = change >= 0;

  return (
    <div className="flex items-center gap-2 px-3 py-[6px] border-b border-slate-50 hover:bg-slate-50 transition-colors">
      <div className="w-[52px]">
        <span className="text-[11px] font-semibold text-slate-800">{ticker.symbol}</span>
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-[10px] text-slate-400 truncate block">
          {ticker.industry || ticker.sector || ''}
        </span>
      </div>
      <span className="text-[11px] font-mono text-slate-600 w-[56px] text-right">
        {formatPrice(ticker.price)}
      </span>
      <span
        className={`text-[11px] font-mono w-[52px] text-right ${
          isPositive ? 'text-emerald-600' : 'text-red-600'
        }`}
      >
        {isPositive ? '+' : ''}{change.toFixed(2)}%
      </span>
      <span className="text-[10px] font-mono text-slate-500 w-[48px] text-right">
        {formatVolume(ticker.volume)}
      </span>
      <span className="text-[10px] font-mono text-slate-400 w-[44px] text-right">
        {formatNumber(ticker.market_cap)}
      </span>
    </div>
  );
}

function ListHeader({ tab }: { tab: PulseTab }) {
  return (
    <div className="flex items-center gap-2 px-3 py-[5px] bg-slate-50/80 border-b border-slate-200 text-[9px] font-medium text-slate-400 uppercase tracking-wider">
      <div className="flex-1">
        {tab === 'themes' ? 'Theme' : tab === 'industries' ? 'Industry' : 'Sector'}
      </div>
      <div className="w-[80px] text-center">Change</div>
      <div className="w-[52px] text-right">Wt. %</div>
      <div className="w-[36px] text-right">RVOL</div>
      <div className="w-3" />
    </div>
  );
}

function DrilldownHeader() {
  return (
    <div className="flex items-center gap-2 px-3 py-[5px] bg-slate-50/80 border-b border-slate-200 text-[9px] font-medium text-slate-400 uppercase tracking-wider">
      <div className="w-[52px]">Symbol</div>
      <div className="flex-1">Industry</div>
      <div className="w-[56px] text-right">Price</div>
      <div className="w-[52px] text-right">Change</div>
      <div className="w-[48px] text-right">Volume</div>
      <div className="w-[44px] text-right">MCap</div>
    </div>
  );
}

function VirtualizedList({
  data,
  maxAbsChange,
  onSelect,
  isTheme,
}: {
  data: PerformanceEntry[];
  maxAbsChange: number;
  onSelect: (entry: PerformanceEntry) => void;
  isTheme?: boolean;
}) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 42,
    overscan: 10,
  });

  return (
    <div ref={parentRef} className="flex-1 overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
        {virtualizer.getVirtualItems().map((vItem) => {
          const entry = data[vItem.index];
          return (
            <div
              key={entry.name}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: `${vItem.size}px`,
                transform: `translateY(${vItem.start}px)`,
              }}
            >
              <PerformanceRow
                entry={entry}
                maxAbsChange={maxAbsChange}
                onClick={() => onSelect(entry)}
                isTheme={isTheme}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VirtualizedDrilldown({ data }: { data: DrilldownTicker[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 15,
  });

  return (
    <div ref={parentRef} className="flex-1 overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
        {virtualizer.getVirtualItems().map((vItem) => {
          const ticker = data[vItem.index];
          return (
            <div
              key={ticker.symbol}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: `${vItem.size}px`,
                transform: `translateY(${vItem.start}px)`,
              }}
            >
              <DrilldownRow ticker={ticker} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function MarketPulseContent() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<PulseTab>('sectors');
  const [drilldown, setDrilldown] = useState<{ type: string; name: string; displayName: string } | null>(null);
  const [sectorFilter, setSectorFilter] = useState<string | undefined>();

  const { data, loading, error, lastUpdate, totalTickers, refetch } = useMarketPulse({
    tab: activeTab,
    refreshInterval: 15000,
    sectorFilter,
  });

  const { data: drilldownData, loading: drilldownLoading, total: drilldownTotal, fetchDrilldown } = useDrilldown();

  const maxAbsChange = useMemo(() => {
    if (!data.length) return 1;
    return Math.max(...data.map(d => Math.abs(d.weighted_change)), 0.5);
  }, [data]);

  const handleSelect = useCallback((entry: PerformanceEntry) => {
    const groupType = activeTab === 'themes' ? 'theme' : activeTab === 'industries' ? 'industry' : 'sector';
    setDrilldown({
      type: groupType,
      name: entry.name,
      displayName: activeTab === 'themes' ? formatThemeName(entry.name) : entry.name,
    });
    fetchDrilldown(groupType, entry.name);
  }, [activeTab, fetchDrilldown]);

  const handleBack = useCallback(() => {
    setDrilldown(null);
  }, []);

  const handleTabChange = useCallback((tab: PulseTab) => {
    setActiveTab(tab);
    setDrilldown(null);
    setSectorFilter(undefined);
  }, []);

  const lastUpdateStr = lastUpdate
    ? new Date(lastUpdate * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '';

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50/50 shrink-0">
        <div className="flex items-center gap-1">
          {drilldown ? (
            <button
              onClick={handleBack}
              className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-700 transition-colors"
            >
              <ArrowLeft className="w-3 h-3" />
              <span>{t('common.back', 'Back')}</span>
            </button>
          ) : (
            <span className="text-[11px] font-semibold text-slate-700 tracking-wide uppercase">
              Market Pulse
            </span>
          )}
          {drilldown && (
            <span className="text-[12px] font-medium text-slate-800 ml-1">
              {drilldown.displayName}
              <span className="text-slate-400 ml-1 text-[10px]">{drilldownTotal}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!drilldown && (
            <span className="text-[9px] text-slate-400">
              {totalTickers > 0 && `${totalTickers.toLocaleString()} tickers`}
            </span>
          )}
          <span className="text-[9px] text-slate-400">{lastUpdateStr}</span>
          <button
            onClick={refetch}
            className="p-0.5 hover:bg-slate-200 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3 h-3 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      {!drilldown && (
        <div className="flex border-b border-slate-200 shrink-0">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => handleTabChange(tab.key)}
              className={`flex-1 py-1.5 text-[10px] font-medium tracking-wide uppercase transition-colors ${
                activeTab === tab.key
                  ? 'text-slate-800 border-b-2 border-slate-800'
                  : 'text-slate-400 hover:text-slate-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {error && (
        <div className="px-3 py-6 text-center text-[11px] text-slate-400">{error}</div>
      )}

      {!error && !drilldown && (
        <>
          <ListHeader tab={activeTab} />
          {loading && data.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <RefreshCw className="w-4 h-4 text-slate-300 animate-spin" />
            </div>
          ) : (
            <VirtualizedList
              data={data}
              maxAbsChange={maxAbsChange}
              onSelect={handleSelect}
              isTheme={activeTab === 'themes'}
            />
          )}
        </>
      )}

      {!error && drilldown && (
        <>
          <DrilldownHeader />
          {drilldownLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <RefreshCw className="w-4 h-4 text-slate-300 animate-spin" />
            </div>
          ) : (
            <VirtualizedDrilldown data={drilldownData} />
          )}
        </>
      )}
    </div>
  );
}
