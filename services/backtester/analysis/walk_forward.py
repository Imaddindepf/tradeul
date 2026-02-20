"""Walk-Forward Analysis for overfitting detection."""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd
from core.engine import BacktestEngine
from core.models import StrategyConfig, WalkForwardResult, WalkForwardSplit


class WalkForwardAnalyzer:
    def __init__(self, engine: BacktestEngine) -> None:
        self.engine = engine

    async def analyze(
        self, strategy: StrategyConfig, bars_df: pd.DataFrame,
        n_splits: int = 5, train_ratio: float = 0.70,
    ) -> WalkForwardResult:
        date_col = "date" if "date" in bars_df.columns else "timestamp"
        unique_dates = sorted(bars_df[date_col].unique())
        total = len(unique_dates)
        split_size = total // n_splits
        splits: list[WalkForwardSplit] = []
        for s in range(n_splits):
            start_idx = s * split_size
            end_idx = min((s + 1) * split_size, total) if s < n_splits - 1 else total
            if end_idx - start_idx < 20:
                continue
            split_dates = unique_dates[start_idx:end_idx]
            train_end = int(len(split_dates) * train_ratio)
            train_dates = set(split_dates[:train_end])
            test_dates = set(split_dates[train_end:])
            train_df = bars_df[bars_df[date_col].isin(train_dates)].copy()
            test_df = bars_df[bars_df[date_col].isin(test_dates)].copy()
            if train_df.empty or test_df.empty:
                continue
            try:
                train_result = await self.engine.run(strategy, bars_df=train_df)
                test_result = await self.engine.run(strategy, bars_df=test_df)
            except ValueError:
                continue
            ts = train_result.core_metrics.sharpe_ratio
            xs = test_result.core_metrics.sharpe_ratio
            deg = ((ts - xs) / abs(ts) * 100 if ts != 0 else 0.0)
            td = sorted(train_dates)
            ted = sorted(test_dates)
            def _d(v):
                return v if isinstance(v, date) else pd.Timestamp(v).date()
            splits.append(WalkForwardSplit(
                split_idx=s, train_start=_d(td[0]), train_end=_d(td[-1]),
                test_start=_d(ted[0]), test_end=_d(ted[-1]),
                train_sharpe=float(ts), test_sharpe=float(xs),
                train_trades=train_result.core_metrics.total_trades,
                test_trades=test_result.core_metrics.total_trades,
                degradation_pct=float(deg)))
        if not splits:
            raise ValueError("Walk-forward produced no valid splits")
        mt = float(np.mean([s.train_sharpe for s in splits]))
        mx = float(np.mean([s.test_sharpe for s in splits]))
        md = float(np.mean([s.degradation_pct for s in splits]))
        op = sum(1 for s in splits if s.test_sharpe < 0) / len(splits)
        return WalkForwardResult(
            n_splits=len(splits), splits=splits, mean_train_sharpe=mt,
            mean_test_sharpe=mx, mean_degradation_pct=md, overfitting_probability=op)
