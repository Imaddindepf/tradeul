import type { PerformanceEntry, PulseTab } from '@/hooks/useMarketPulse';

export type PulseViewType = 'overview' | 'table' | 'treemap' | 'bubble' | 'rotation' | 'breadth';

export interface PulseViewProps {
  data: PerformanceEntry[];
  activeTab: PulseTab;
  onSelect: (entry: PerformanceEntry) => void;
}
