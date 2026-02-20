"""Monte Carlo simulation for trade-sequence robustness."""

import numpy as np

from core.models import MonteCarloResult, TradeRecord


class MonteCarloAnalyzer:
    """Resamples historical trades with replacement to build simulated equity
    curves and estimate probabilistic risk/return characteristics."""

    def simulate(
        self,
        trades: list[TradeRecord],
        n_simulations: int = 1000,
        initial_capital: float = 100_000,
    ) -> MonteCarloResult:
        """Run Monte Carlo resampling simulation.

        Parameters
        ----------
        trades:
            List of historical trade records.
        n_simulations:
            Number of resampled equity paths to generate.
        initial_capital:
            Starting capital for each simulated path.

        Returns
        -------
        MonteCarloResult with distribution statistics and drawdown metrics.
        """
        rng = np.random.default_rng(seed=42)

        # Extract trade returns as multiplicative factors (1 + r)
        # return_pct is a decimal fraction (0.02 = 2%)
        returns = np.array([t.return_pct for t in trades])
        n_trades = len(returns)

        # Resample trade returns with replacement: (n_simulations, n_trades)
        indices = rng.integers(0, n_trades, size=(n_simulations, n_trades))
        resampled = returns[indices]

        # Build equity curves via cumulative product of (1 + return)
        equity_curves = initial_capital * np.cumprod(1.0 + resampled, axis=1)

        # Final equity for each simulation
        final_equities = equity_curves[:, -1]

        # Core statistics
        median_final_equity = float(np.median(final_equities))
        mean_final_equity = float(np.mean(final_equities))
        prob_profit = float(np.mean(final_equities > initial_capital))
        prob_loss = float(np.mean(final_equities < initial_capital))

        # Percentiles
        p5 = float(np.percentile(final_equities, 5))
        p25 = float(np.percentile(final_equities, 25))
        p75 = float(np.percentile(final_equities, 75))
        p95 = float(np.percentile(final_equities, 95))

        # Max drawdown per simulation
        # Prepend initial capital column for correct running-max calculation
        full_equity = np.column_stack(
            [np.full(n_simulations, initial_capital), equity_curves]
        )
        running_max = np.maximum.accumulate(full_equity, axis=1)
        dd = (full_equity - running_max) / running_max
        max_dd = np.min(dd, axis=1)  # most negative value per path

        mean_max_drawdown = float(np.mean(max_dd))
        worst_max_drawdown = float(np.min(max_dd))
        best_max_drawdown = float(np.max(max_dd))

        return MonteCarloResult(
            n_simulations=n_simulations,
            median_final_equity=median_final_equity,
            mean_final_equity=mean_final_equity,
            prob_profit=prob_profit,
            prob_loss=prob_loss,
            percentile_5_equity=p5,
            percentile_25_equity=p25,
            percentile_75_equity=p75,
            percentile_95_equity=p95,
            mean_max_drawdown_pct=mean_max_drawdown,
            worst_max_drawdown_pct=worst_max_drawdown,
            best_max_drawdown_pct=best_max_drawdown,
        )
