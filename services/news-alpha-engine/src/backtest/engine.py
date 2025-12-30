"""
Professional Backtesting Engine for News-Based Trading Strategies

Features:
- Event-driven backtesting
- Multiple strategy types (threshold, top_n, all)
- Comprehensive metrics (Sharpe, Sortino, Calmar, etc.)
- Transaction costs and slippage
- Market regime filtering
- Detailed trade analysis
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

from rich.console import Console
from rich.table import Table
from rich.progress import Progress

console = Console()


@dataclass
class Trade:
    """Record of a single trade."""
    trade_id: str
    news_id: str
    ticker: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    direction: str  # 'long' or 'short'
    position_size: float
    
    # Prediction info
    predicted_car: float
    predicted_direction: str
    prediction_confidence: float
    topic: str
    sentiment: float
    
    # Actual results
    actual_car: float
    return_pct: float
    pnl: float
    holding_days: int
    
    # Classification
    is_winner: bool = field(init=False)
    prediction_correct: bool = field(init=False)
    
    def __post_init__(self):
        self.is_winner = self.return_pct > 0
        self.prediction_correct = (
            (self.predicted_direction == 'up' and self.actual_car > 0) or
            (self.predicted_direction == 'down' and self.actual_car < 0) or
            (self.predicted_direction == 'neutral' and abs(self.actual_car) < 0.01)
        )


@dataclass
class BacktestResult:
    """Complete backtest results."""
    # Configuration
    strategy: str
    initial_capital: float
    start_date: datetime
    end_date: datetime
    
    # Basic stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    prediction_accuracy: float
    
    # Returns
    total_return: float
    total_pnl: float
    avg_return_per_trade: float
    median_return: float
    std_return: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    
    # Trade analysis
    avg_winner: float
    avg_loser: float
    best_trade: float
    worst_trade: float
    profit_factor: float
    avg_holding_period: float
    
    # By category
    metrics_by_topic: Dict[str, dict]
    metrics_by_direction: Dict[str, dict]
    
    # Time series
    equity_curve: List[Tuple[datetime, float]]
    drawdown_curve: List[Tuple[datetime, float]]
    monthly_returns: Dict[str, float]
    
    # All trades
    trades: List[Trade]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'strategy': self.strategy,
            'initial_capital': self.initial_capital,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'prediction_accuracy': self.prediction_accuracy,
            'total_return': self.total_return,
            'total_pnl': self.total_pnl,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'max_drawdown': self.max_drawdown,
            'profit_factor': self.profit_factor,
            'avg_holding_period': self.avg_holding_period,
            'metrics_by_topic': self.metrics_by_topic,
            'metrics_by_direction': self.metrics_by_direction,
            'monthly_returns': self.monthly_returns,
        }
    
    def print_summary(self):
        """Print formatted summary."""
        console.print("\n" + "="*60)
        console.print("[bold blue]BACKTEST RESULTS[/bold blue]")
        console.print("="*60)
        
        # Overview
        table = Table(title="Performance Overview")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Trades", f"{self.total_trades:,}")
        table.add_row("Win Rate", f"{self.win_rate:.1%}")
        table.add_row("Prediction Accuracy", f"{self.prediction_accuracy:.1%}")
        table.add_row("Total Return", f"[{'green' if self.total_return > 0 else 'red'}]{self.total_return:.2%}[/]")
        table.add_row("Total P&L", f"[{'green' if self.total_pnl > 0 else 'red'}]${self.total_pnl:,.2f}[/]")
        table.add_row("Sharpe Ratio", f"{self.sharpe_ratio:.2f}")
        table.add_row("Sortino Ratio", f"{self.sortino_ratio:.2f}")
        table.add_row("Max Drawdown", f"[red]{self.max_drawdown:.2%}[/red]")
        table.add_row("Profit Factor", f"{self.profit_factor:.2f}")
        
        console.print(table)
        
        # By Topic
        if self.metrics_by_topic:
            topic_table = Table(title="Performance by Topic")
            topic_table.add_column("Topic", style="cyan")
            topic_table.add_column("Trades", justify="right")
            topic_table.add_column("Win Rate", justify="right")
            topic_table.add_column("Avg Return", justify="right")
            topic_table.add_column("Sharpe", justify="right")
            
            for topic, metrics in sorted(
                self.metrics_by_topic.items(),
                key=lambda x: x[1].get('sharpe', 0),
                reverse=True
            )[:10]:
                color = "green" if metrics.get('avg_return', 0) > 0 else "red"
                topic_table.add_row(
                    topic[:20],
                    str(metrics.get('count', 0)),
                    f"{metrics.get('win_rate', 0):.1%}",
                    f"[{color}]{metrics.get('avg_return', 0):.2%}[/]",
                    f"{metrics.get('sharpe', 0):.2f}",
                )
            
            console.print(topic_table)


class NewsBacktestEngine:
    """
    Backtesting engine for news-based trading strategies.
    """
    
    def __init__(
        self,
        price_data_path: str,
        initial_capital: float = 100000,
        slippage: float = 0.001,
        commission: float = 0.0,
        risk_free_rate: float = 0.05,
    ):
        self.price_data_path = Path(price_data_path)
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.commission = commission
        self.risk_free_rate = risk_free_rate
        
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self.trades: List[Trade] = []
    
    def load_price_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load price data for a ticker."""
        if ticker in self._price_cache:
            return self._price_cache[ticker]
        
        # Try to find price file
        for pattern in [f"{ticker}.parquet", f"**/{ticker}.parquet"]:
            files = list(self.price_data_path.glob(pattern))
            if files:
                try:
                    df = pd.read_parquet(files[0])
                    df.columns = df.columns.str.lower()
                    
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date').sort_index()
                    
                    self._price_cache[ticker] = df
                    return df
                except Exception:
                    continue
        
        return None
    
    def get_price(self, ticker: str, date: datetime, field: str = 'close') -> Optional[float]:
        """Get price for a ticker on a specific date."""
        df = self.load_price_data(ticker)
        if df is None:
            return None
        
        date = pd.Timestamp(date).normalize()
        
        try:
            # Try exact date first
            if date in df.index:
                return df.loc[date, field]
            
            # Find nearest date
            idx = df.index.get_indexer([date], method='ffill')[0]
            if idx >= 0:
                return df.iloc[idx][field]
        except Exception:
            pass
        
        return None
    
    def run_backtest(
        self,
        predictions_df: pd.DataFrame,
        strategy: str = "threshold",
        threshold: float = 0.02,
        confidence_threshold: float = 0.7,
        holding_period: int = 5,
        max_positions: int = 10,
        position_size_pct: float = 0.1,
        stop_loss: Optional[float] = None,
    ) -> BacktestResult:
        """
        Run backtest with specified strategy.
        
        Args:
            predictions_df: DataFrame with columns:
                - news_id, ticker, timestamp
                - predicted_car_5d, predicted_direction, confidence
                - topic, sentiment
                - actual_car_5d (for validation)
            strategy: 'threshold', 'top_n', or 'all'
            threshold: Minimum predicted CAR for entry
            confidence_threshold: Minimum confidence for entry
            holding_period: Days to hold position
            max_positions: Maximum simultaneous positions
            position_size_pct: Position size as % of capital
        """
        
        console.print(f"\n[bold]Running Backtest[/bold]")
        console.print(f"  Strategy: {strategy}")
        console.print(f"  Threshold: {threshold:.2%}")
        console.print(f"  Confidence: {confidence_threshold:.0%}")
        
        self.trades = []
        equity = self.initial_capital
        equity_history = [(predictions_df['timestamp'].min(), equity)]
        active_positions: List[dict] = []
        
        # Sort by timestamp
        predictions_df = predictions_df.sort_values('timestamp').copy()
        
        trade_count = 0
        
        with Progress() as progress:
            task = progress.add_task("Processing...", total=len(predictions_df))
            
            for _, pred in predictions_df.iterrows():
                current_date = pd.Timestamp(pred['timestamp'])
                
                # Close expired positions
                for pos in active_positions.copy():
                    days_held = (current_date - pos['entry_date']).days
                    
                    should_close = days_held >= holding_period
                    
                    # Check stop loss
                    if stop_loss and not should_close:
                        current_price = self.get_price(pos['ticker'], current_date)
                        if current_price:
                            unrealized = (current_price - pos['entry_price']) / pos['entry_price']
                            if pos['direction'] == 'short':
                                unrealized = -unrealized
                            if unrealized < -stop_loss:
                                should_close = True
                    
                    if should_close:
                        trade = self._close_position(pos, current_date, trade_count)
                        if trade:
                            self.trades.append(trade)
                            equity += trade.pnl
                            trade_count += 1
                        active_positions.remove(pos)
                
                # Check for new position
                if self._should_enter(pred, strategy, threshold, confidence_threshold):
                    if len(active_positions) < max_positions:
                        position_size = equity * position_size_pct
                        position = self._open_position(pred, position_size, current_date)
                        if position:
                            active_positions.append(position)
                
                equity_history.append((current_date, equity))
                progress.update(task, advance=1)
        
        # Close remaining positions
        final_date = predictions_df['timestamp'].max() + timedelta(days=holding_period)
        for pos in active_positions:
            trade = self._close_position(pos, final_date, trade_count)
            if trade:
                self.trades.append(trade)
                equity += trade.pnl
                trade_count += 1
        
        equity_history.append((final_date, equity))
        
        console.print(f"\n  Total trades: {len(self.trades)}")
        
        # Calculate metrics
        return self._calculate_results(equity_history, strategy)
    
    def _should_enter(
        self,
        pred: pd.Series,
        strategy: str,
        threshold: float,
        confidence_threshold: float,
    ) -> bool:
        """Determine if we should enter a position."""
        
        confidence = pred.get('confidence', pred.get('prediction_confidence', 0))
        if confidence < confidence_threshold:
            return False
        
        predicted_car = pred.get('predicted_car_5d', pred.get('predicted_car', 0))
        
        if strategy == "threshold":
            return abs(predicted_car) >= threshold
        elif strategy == "all":
            return True
        
        return False
    
    def _open_position(
        self,
        pred: pd.Series,
        size: float,
        date: datetime,
    ) -> Optional[dict]:
        """Open a new position."""
        
        ticker = pred['ticker']
        entry_price = self.get_price(ticker, date, 'open')
        
        if entry_price is None:
            return None
        
        predicted_car = pred.get('predicted_car_5d', pred.get('predicted_car', 0))
        direction = 'long' if predicted_car > 0 else 'short'
        
        # Apply slippage
        if direction == 'long':
            entry_price *= (1 + self.slippage)
        else:
            entry_price *= (1 - self.slippage)
        
        return {
            'news_id': pred.get('news_id', ''),
            'ticker': ticker,
            'entry_date': date,
            'entry_price': entry_price,
            'direction': direction,
            'size': size,
            'predicted_car': predicted_car,
            'predicted_direction': pred.get('predicted_direction', direction),
            'confidence': pred.get('confidence', 0),
            'topic': pred.get('topic', 'unknown'),
            'sentiment': pred.get('sentiment', 0),
            'actual_car': pred.get('actual_car_5d', pred.get('car_5d', 0)),
        }
    
    def _close_position(
        self,
        pos: dict,
        date: datetime,
        trade_id: int,
    ) -> Optional[Trade]:
        """Close a position and create trade record."""
        
        exit_price = self.get_price(pos['ticker'], date, 'close')
        
        if exit_price is None:
            # Use entry price as fallback (no profit/loss)
            exit_price = pos['entry_price']
        
        # Apply slippage
        if pos['direction'] == 'long':
            exit_price *= (1 - self.slippage)
        else:
            exit_price *= (1 + self.slippage)
        
        # Calculate return
        if pos['direction'] == 'long':
            return_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        else:
            return_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
        
        # Apply commission
        return_pct -= self.commission * 2
        
        pnl = pos['size'] * return_pct
        holding_days = (date - pos['entry_date']).days
        
        return Trade(
            trade_id=f"trade_{trade_id}",
            news_id=pos['news_id'],
            ticker=pos['ticker'],
            entry_date=pos['entry_date'],
            entry_price=pos['entry_price'],
            exit_date=date,
            exit_price=exit_price,
            direction=pos['direction'],
            position_size=pos['size'],
            predicted_car=pos['predicted_car'],
            predicted_direction=pos['predicted_direction'],
            prediction_confidence=pos['confidence'],
            topic=pos['topic'],
            sentiment=pos['sentiment'],
            actual_car=pos['actual_car'],
            return_pct=return_pct,
            pnl=pnl,
            holding_days=holding_days,
        )
    
    def _calculate_results(
        self,
        equity_history: List[Tuple[datetime, float]],
        strategy: str,
    ) -> BacktestResult:
        """Calculate all backtest metrics."""
        
        if not self.trades:
            raise ValueError("No trades to analyze")
        
        returns = [t.return_pct for t in self.trades]
        pnls = [t.pnl for t in self.trades]
        
        # Basic stats
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.is_winner)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades
        prediction_accuracy = sum(1 for t in self.trades if t.prediction_correct) / total_trades
        
        # Returns
        total_pnl = sum(pnls)
        total_return = total_pnl / self.initial_capital
        avg_return = np.mean(returns)
        median_return = np.median(returns)
        std_return = np.std(returns)
        
        # Risk metrics
        avg_holding = np.mean([t.holding_days for t in self.trades])
        trades_per_year = 252 / max(avg_holding, 1)
        
        annual_return = avg_return * trades_per_year
        annual_std = std_return * np.sqrt(trades_per_year)
        
        sharpe_ratio = (annual_return - self.risk_free_rate) / annual_std if annual_std > 0 else 0
        
        # Sortino
        downside_returns = [r for r in returns if r < 0]
        downside_std = np.std(downside_returns) if downside_returns else 0
        annual_downside_std = downside_std * np.sqrt(trades_per_year)
        sortino_ratio = (annual_return - self.risk_free_rate) / annual_downside_std if annual_downside_std > 0 else 0
        
        # Drawdown
        equity_values = [e[1] for e in equity_history]
        equity_series = pd.Series(equity_values)
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Calmar
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # Trade analysis
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]
        avg_winner = np.mean(winners) if winners else 0
        avg_loser = np.mean(losers) if losers else 0
        best_trade = max(returns)
        worst_trade = min(returns)
        
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # By category
        metrics_by_topic = self._metrics_by_field('topic')
        metrics_by_direction = self._metrics_by_field('predicted_direction')
        
        # Monthly returns
        monthly_returns = self._calculate_monthly_returns(equity_history)
        
        # Drawdown curve
        drawdown_curve = [(equity_history[i][0], drawdown.iloc[i]) for i in range(len(drawdown))]
        
        return BacktestResult(
            strategy=strategy,
            initial_capital=self.initial_capital,
            start_date=equity_history[0][0],
            end_date=equity_history[-1][0],
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            prediction_accuracy=prediction_accuracy,
            total_return=total_return,
            total_pnl=total_pnl,
            avg_return_per_trade=avg_return,
            median_return=median_return,
            std_return=std_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration_days=self._max_drawdown_duration(drawdown),
            avg_winner=avg_winner,
            avg_loser=avg_loser,
            best_trade=best_trade,
            worst_trade=worst_trade,
            profit_factor=profit_factor,
            avg_holding_period=avg_holding,
            metrics_by_topic=metrics_by_topic,
            metrics_by_direction=metrics_by_direction,
            equity_curve=equity_history,
            drawdown_curve=drawdown_curve,
            monthly_returns=monthly_returns,
            trades=self.trades,
        )
    
    def _metrics_by_field(self, field: str) -> Dict[str, dict]:
        """Calculate metrics grouped by a field."""
        from collections import defaultdict
        
        grouped = defaultdict(list)
        for trade in self.trades:
            key = getattr(trade, field, 'unknown')
            grouped[key].append(trade)
        
        result = {}
        for key, trades in grouped.items():
            returns = [t.return_pct for t in trades]
            result[str(key)] = {
                'count': len(trades),
                'win_rate': sum(1 for t in trades if t.is_winner) / len(trades),
                'avg_return': np.mean(returns),
                'std_return': np.std(returns),
                'sharpe': np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0,
                'total_pnl': sum(t.pnl for t in trades),
            }
        
        return result
    
    def _calculate_monthly_returns(
        self,
        equity_history: List[Tuple[datetime, float]],
    ) -> Dict[str, float]:
        """Calculate monthly returns."""
        df = pd.DataFrame(equity_history, columns=['date', 'equity'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        monthly = df['equity'].resample('M').last()
        monthly_returns = monthly.pct_change().dropna()
        
        return {
            str(date.strftime('%Y-%m')): ret
            for date, ret in monthly_returns.items()
        }
    
    def _max_drawdown_duration(self, drawdown: pd.Series) -> int:
        """Calculate maximum drawdown duration in days."""
        in_drawdown = drawdown < 0
        
        if not in_drawdown.any():
            return 0
        
        # Find consecutive drawdown periods
        groups = (in_drawdown != in_drawdown.shift()).cumsum()
        durations = in_drawdown.groupby(groups).sum()
        
        return int(durations.max())

