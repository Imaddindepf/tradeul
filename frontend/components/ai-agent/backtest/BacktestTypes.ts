export type Timeframe = '1min' | '5min' | '15min' | '30min' | '1h' | '4h' | '1d';
export type SignalOperator = '>' | '>=' | '<' | '<=' | '==' | 'crosses_above' | 'crosses_below';
export type ExitType = 'time' | 'target' | 'stop_loss' | 'trailing_stop' | 'signal' | 'eod';
export type UniverseMethod = 'all_us' | 'sector' | 'industry' | 'ticker_list' | 'sql_filter';
export type SlippageModel = 'fixed_bps' | 'volume_based' | 'spread_based';

export interface Signal {
  indicator: string;
  operator: SignalOperator;
  value: number | string;
  lookback?: number | null;
}

export interface ExitRule {
  type: ExitType;
  value?: number | null;
  signal?: Signal | null;
}

export interface UniverseFilter {
  method: UniverseMethod;
  criteria: Record<string, unknown>;
  tickers?: string[] | null;
  sql_where?: string | null;
}

export interface StrategyConfig {
  name: string;
  description: string;
  universe: UniverseFilter;
  entry_signals: Signal[];
  entry_timing: 'open' | 'close' | 'next_open';
  entry_events: string[];
  entry_events_combine: 'or' | 'and';
  exit_rules: ExitRule[];
  exit_events: string[];
  entry_filters: Record<string, number | string | null>;
  universe_filters: Record<string, number | string | null>;
  timeframe: Timeframe;
  start_date: string;
  end_date: string;
  initial_capital: number;
  max_positions: number;
  position_size_pct: number;
  direction: 'long' | 'short' | 'both';
  slippage_model: SlippageModel;
  slippage_bps: number;
  commission_per_trade: number;
  risk_free_rate: number;
}

export interface TradeRecord {
  trade_id: number;
  ticker: string;
  direction: 'long' | 'short';
  entry_date: string;
  entry_price: number;
  entry_fill_price: number;
  exit_date: string;
  exit_price: number;
  exit_fill_price: number;
  shares: number;
  position_value: number;
  pnl: number;
  return_pct: number;
  holding_bars: number;
  slippage_cost: number;
  commission_cost: number;
}

export interface CoreMetrics {
  total_return_pct: number;
  annualized_return_pct: number;
  total_pnl: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  max_drawdown_duration_days: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
  avg_return_per_trade: number;
  median_return_per_trade: number;
  std_return_per_trade: number;
  avg_winner_pct: number;
  avg_loser_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  total_trades: number;
  avg_holding_bars: number;
  recovery_factor: number;
  ulcer_index: number;
  tail_ratio: number;
  common_sense_ratio: number;
}

export interface AdvancedMetrics {
  deflated_sharpe_ratio: number;
  probabilistic_sharpe_ratio: number;
  min_track_record_length: number;
  skewness: number;
  kurtosis: number;
}

export interface WalkForwardSplit {
  split_idx: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  train_sharpe: number;
  test_sharpe: number;
  train_trades: number;
  test_trades: number;
  degradation_pct: number;
}

export interface WalkForwardResult {
  n_splits: number;
  splits: WalkForwardSplit[];
  mean_train_sharpe: number;
  mean_test_sharpe: number;
  mean_degradation_pct: number;
  overfitting_probability: number;
}

export interface MonteCarloResult {
  n_simulations: number;
  median_final_equity: number;
  mean_final_equity: number;
  prob_profit: number;
  prob_loss: number;
  percentile_5_equity: number;
  percentile_25_equity: number;
  percentile_75_equity: number;
  percentile_95_equity: number;
  mean_max_drawdown_pct: number;
  worst_max_drawdown_pct: number;
  best_max_drawdown_pct: number;
}

export interface DailyStats {
  date: string;
  pnl: number;
  trades_count: number;
  winners: number;
  losers: number;
  win_rate: number;
  avg_gain: number;
  buying_power: number;
  gross_equity: number;
  net_equity: number;
}

export interface OptimizationBucket {
  label: string;
  profit_factor: number;
  win_rate: number;
  avg_gain: number;
  total_gain: number;
  trades: number;
  pct_of_total: number;
}

export interface OptimizationBreakdown {
  filter_name: string;
  interval: number;
  buckets: OptimizationBucket[];
}

export interface BacktestResult {
  strategy: StrategyConfig;
  core_metrics: CoreMetrics;
  advanced_metrics?: AdvancedMetrics | null;
  walk_forward?: WalkForwardResult | null;
  monte_carlo?: MonteCarloResult | null;
  trades: TradeRecord[];
  equity_curve: [string, number][];
  drawdown_curve: [string, number][];
  monthly_returns: Record<string, number>;
  daily_stats?: DailyStats[] | null;
  optimization?: Record<string, OptimizationBreakdown> | null;
  execution_time_ms: number;
  symbols_tested: number;
  bars_processed: number;
  warnings: string[];
  most_winning_days_in_row?: number;
  most_losing_days_in_row?: number;
  biggest_winning_day?: { date: string; pnl: number } | null;
  biggest_losing_day?: { date: string; pnl: number } | null;
}

export interface BacktestResponse {
  status: 'success' | 'error';
  result?: BacktestResult | null;
  error?: string | null;
}
