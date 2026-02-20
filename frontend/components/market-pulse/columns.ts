export type RenderMode = 'bar' | 'numeric' | 'heatmap';

export interface ColumnDef {
  key: string;
  label: string;
  shortLabel: string;
  defaultMode: RenderMode;
  format: (v: number) => string;
  colorScale: 'diverging' | 'positive' | 'neutral';
  domain?: [number, number];
  description: string;
}

const pct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
const pct1 = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
const num1 = (v: number) => v.toFixed(1);
const num0 = (v: number) => v.toFixed(0);
const mult = (v: number) => `${v.toFixed(1)}x`;
const bps = (v: number) => `${(v * 100).toFixed(0)}%`;
const price = (v: number) => v >= 1 ? v.toFixed(2) : v.toFixed(4);
const vol = (v: number) => {
  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toFixed(0);
};

// ── Group-level columns (sectors, industries, themes) ──

export const ALL_COLUMNS: ColumnDef[] = [
  { key: 'weighted_change', label: 'Wt. Change', shortLabel: 'Wt.Chg', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Market-cap weighted % change' },
  { key: 'avg_change', label: 'Avg Change', shortLabel: 'AvgChg', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Average % change' },
  { key: 'median_change', label: 'Med Change', shortLabel: 'MedChg', defaultMode: 'numeric', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Median % change' },
  { key: 'breadth', label: 'Breadth', shortLabel: 'Breadth', defaultMode: 'bar', format: bps, colorScale: 'positive', domain: [0, 1], description: 'Advancing / Total ratio' },
  { key: 'avg_rvol', label: 'RVOL', shortLabel: 'RVOL', defaultMode: 'numeric', format: mult, colorScale: 'positive', domain: [0, 5], description: 'Avg relative volume' },
  { key: 'count', label: 'Tickers', shortLabel: 'Count', defaultMode: 'numeric', format: num0, colorScale: 'neutral', description: 'Number of tickers' },
  { key: 'avg_rsi', label: 'RSI 1m', shortLabel: 'RSI', defaultMode: 'heatmap', format: num1, colorScale: 'diverging', domain: [30, 70], description: 'Avg 1-min RSI(14)' },
  { key: 'avg_daily_rsi', label: 'RSI Daily', shortLabel: 'dRSI', defaultMode: 'heatmap', format: num1, colorScale: 'diverging', domain: [30, 70], description: 'Avg daily RSI' },
  { key: 'avg_atr_pct', label: 'ATR %', shortLabel: 'ATR%', defaultMode: 'numeric', format: pct1, colorScale: 'positive', domain: [0, 10], description: 'Avg ATR as % of price' },
  { key: 'avg_gap_pct', label: 'Gap', shortLabel: 'Gap', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-3, 3], description: 'Avg gap %' },
  { key: 'avg_adx', label: 'ADX', shortLabel: 'ADX', defaultMode: 'numeric', format: num1, colorScale: 'positive', domain: [0, 60], description: 'Avg ADX (trend strength)' },
  { key: 'avg_dist_vwap', label: 'Dist VWAP', shortLabel: 'dVWAP', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-2, 2], description: 'Avg distance from VWAP' },
  { key: 'avg_change_5d', label: 'Chg 5D', shortLabel: '5D', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-10, 10], description: 'Avg 5-day change' },
  { key: 'avg_change_10d', label: 'Chg 10D', shortLabel: '10D', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-15, 15], description: 'Avg 10-day change' },
  { key: 'avg_change_20d', label: 'Chg 20D', shortLabel: '20D', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-20, 20], description: 'Avg 20-day change' },
  { key: 'avg_from_52w_high', label: 'From 52wH', shortLabel: '52wH', defaultMode: 'bar', format: pct1, colorScale: 'diverging', domain: [-50, 0], description: 'Avg distance from 52-week high' },
  { key: 'avg_pos_in_range', label: 'Range Pos', shortLabel: 'RPos', defaultMode: 'heatmap', format: num0, colorScale: 'positive', domain: [0, 100], description: "Avg position in today's range" },
  { key: 'avg_bb_position', label: 'BB Pos', shortLabel: 'BB', defaultMode: 'heatmap', format: num0, colorScale: 'diverging', domain: [0, 100], description: 'Avg Bollinger Band position' },
  { key: 'avg_dist_sma20', label: 'Dist SMA20', shortLabel: 'dSMA20', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Avg dist from daily SMA 20' },
  { key: 'avg_dist_sma50', label: 'Dist SMA50', shortLabel: 'dSMA50', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-10, 10], description: 'Avg dist from daily SMA 50' },
  { key: 'avg_vol_today_pct', label: 'Vol Done', shortLabel: 'Vol%', defaultMode: 'heatmap', format: num0, colorScale: 'positive', domain: [0, 100], description: 'Avg % of daily avg volume done' },
  { key: 'total_dollar_volume', label: '$ Volume', shortLabel: '$Vol', defaultMode: 'numeric', format: vol, colorScale: 'neutral', description: 'Total dollar volume' },
  { key: 'total_market_cap', label: 'Market Cap', shortLabel: 'MCap', defaultMode: 'numeric', format: vol, colorScale: 'neutral', description: 'Total market cap' },
];

export const DEFAULT_COLUMNS = ['weighted_change', 'avg_change_5d'];

// ── Ticker-level columns (drilldown) ──

export const DD_COLUMNS: ColumnDef[] = [
  { key: 'change_percent', label: 'Change %', shortLabel: 'Chg%', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Intraday change %' },
  { key: '_relative', label: 'Relative Perf', shortLabel: 'Rel', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-3, 3], description: 'Performance vs group average' },
  { key: 'price', label: 'Price', shortLabel: 'Price', defaultMode: 'numeric', format: price, colorScale: 'neutral', description: 'Current price' },
  { key: 'volume', label: 'Volume', shortLabel: 'Vol', defaultMode: 'numeric', format: vol, colorScale: 'neutral', description: 'Trading volume' },
  { key: 'market_cap', label: 'Market Cap', shortLabel: 'MCap', defaultMode: 'numeric', format: vol, colorScale: 'neutral', description: 'Market capitalization' },
  { key: 'rsi_14', label: 'RSI 1m', shortLabel: 'RSI', defaultMode: 'heatmap', format: num1, colorScale: 'diverging', domain: [30, 70], description: '1-min RSI(14)' },
  { key: 'daily_rsi', label: 'RSI Daily', shortLabel: 'dRSI', defaultMode: 'heatmap', format: num1, colorScale: 'diverging', domain: [30, 70], description: 'Daily RSI' },
  { key: 'gap_percent', label: 'Gap %', shortLabel: 'Gap', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-5, 5], description: 'Gap from previous close' },
  { key: 'atr_percent', label: 'ATR %', shortLabel: 'ATR%', defaultMode: 'numeric', format: pct1, colorScale: 'positive', domain: [0, 10], description: 'ATR as % of price' },
  { key: 'rvol', label: 'RVOL', shortLabel: 'RVOL', defaultMode: 'numeric', format: mult, colorScale: 'positive', domain: [0, 5], description: 'Relative volume' },
  { key: 'dist_from_vwap', label: 'Dist VWAP', shortLabel: 'dVWAP', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-2, 2], description: 'Distance from VWAP' },
  { key: 'change_5d', label: 'Chg 5D', shortLabel: '5D', defaultMode: 'bar', format: pct, colorScale: 'diverging', domain: [-10, 10], description: '5-day change' },
  { key: 'change_10d', label: 'Chg 10D', shortLabel: '10D', defaultMode: 'numeric', format: pct, colorScale: 'diverging', domain: [-15, 15], description: '10-day change' },
  { key: 'change_20d', label: 'Chg 20D', shortLabel: '20D', defaultMode: 'numeric', format: pct, colorScale: 'diverging', domain: [-20, 20], description: '20-day change' },
  { key: 'from_52w_high', label: 'From 52wH', shortLabel: '52wH', defaultMode: 'bar', format: pct1, colorScale: 'diverging', domain: [-50, 0], description: 'Distance from 52-week high' },
  { key: 'pos_in_range', label: 'Range Pos', shortLabel: 'RPos', defaultMode: 'heatmap', format: num0, colorScale: 'positive', domain: [0, 100], description: "Position in today's range" },
  { key: 'daily_bb_position', label: 'BB Pos', shortLabel: 'BB', defaultMode: 'heatmap', format: num0, colorScale: 'diverging', domain: [0, 100], description: 'Bollinger Band position' },
  { key: 'dollar_volume', label: '$ Volume', shortLabel: '$Vol', defaultMode: 'numeric', format: vol, colorScale: 'neutral', description: 'Dollar volume' },
  { key: 'float_turnover', label: 'Float Turn', shortLabel: 'FTurn', defaultMode: 'numeric', format: pct1, colorScale: 'positive', domain: [0, 50], description: 'Float turnover %' },
  { key: 'adx_14', label: 'ADX', shortLabel: 'ADX', defaultMode: 'numeric', format: num1, colorScale: 'positive', domain: [0, 60], description: 'ADX (trend strength)' },
];

export const DEFAULT_DD_COLUMNS = ['change_percent', '_relative', 'volume', 'market_cap'];
