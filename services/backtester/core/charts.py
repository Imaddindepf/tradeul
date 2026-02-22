"""Plotly chart generation module for backtest visualisation."""

import base64
import io

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import BacktestResult, MonteCarloResult, WalkForwardResult


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fig_to_dict(fig: go.Figure, label: str) -> dict:
    """Convert a Plotly figure to a dict with JSON and optional PNG base64."""
    plotly_json = fig.to_json()
    png_base64: str | None = None
    try:
        img_bytes = fig.to_image(format="png")
        png_base64 = base64.b64encode(img_bytes).decode("utf-8")
    except Exception:
        pass
    return {"label": label, "plotly_json": plotly_json, "png_base64": png_base64}


# ---------------------------------------------------------------------------
# Individual charts
# ---------------------------------------------------------------------------

def generate_equity_chart(result: BacktestResult) -> dict:
    """Equity curve + drawdown dual-panel chart."""
    dates = [pt[0] for pt in result.equity_curve]
    equity = np.array([pt[1] for pt in result.equity_curve], dtype=float)

    running_max = np.maximum.accumulate(equity)
    drawdown = np.where(running_max > 0, (equity - running_max) / running_max * 100, 0.0)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Equity Curve", "Drawdown (%)"),
        row_heights=[0.7, 0.3],
    )

    fig.add_trace(
        go.Scatter(x=dates, y=equity, mode="lines", name="Equity",
                   line=dict(color="#00cc96", width=2)),
        row=1, col=1,
    )

    fig.add_trace(
        go.Scatter(x=dates, y=drawdown, mode="lines", name="Drawdown",
                   fill="tozeroy", line=dict(color="#ef553b", width=1)),
        row=2, col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=500,
        width=900,
        title_text="Equity & Drawdown",
        showlegend=True,
    )
    return _fig_to_dict(fig, "equity_chart")


def generate_monthly_heatmap(result: BacktestResult) -> dict:
    """Monthly returns calendar heatmap."""
    dates = pd.to_datetime([pt[0] for pt in result.equity_curve])
    equity = np.array([pt[1] for pt in result.equity_curve], dtype=float)
    eq_series = pd.Series(equity, index=dates)

    monthly = eq_series.resample("ME").last().pct_change().dropna() * 100
    pivot = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "ret": monthly.values,
    }).pivot(index="year", columns="month", values="ret")

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(m) for m in pivot.columns],
        y=[str(y) for y in pivot.index],
        colorscale=[[0, "red"], [0.5, "white"], [1, "green"]],
        zmid=0,
        text=np.round(pivot.values, 2),
        texttemplate="%{text:.1f}%",
        hovertemplate="Year %{y}, Month %{x}: %{z:.2f}%<extra></extra>",
    ))

    fig.update_layout(
        template="plotly_dark",
        title_text="Monthly Returns (%)",
        height=500,
        width=900,
    )
    return _fig_to_dict(fig, "monthly_heatmap")


def generate_trade_distribution(result: BacktestResult) -> dict:
    """Histogram of trade returns with mean and zero lines."""
    pnl_pcts = [t.return_pct * 100 for t in result.trades]
    avg_pnl = float(np.mean(pnl_pcts)) if pnl_pcts else 0.0

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=pnl_pcts,
        nbinsx=50,
        marker_color="#636efa",
        name="Trade Returns",
    ))

    # Vertical line at zero
    fig.add_vline(x=0, line_dash="dash", line_color="white", annotation_text="0")
    # Vertical line at average
    fig.add_vline(x=avg_pnl, line_dash="dot", line_color="#ffa15a",
                  annotation_text=f"Avg: {avg_pnl:.2f}%")

    fig.update_layout(
        template="plotly_dark",
        title_text="Trade Return Distribution",
        xaxis_title="Return (%)",
        yaxis_title="Frequency",
        height=500,
        width=900,
    )
    return _fig_to_dict(fig, "trade_distribution")


def generate_walk_forward_chart(wf: WalkForwardResult) -> dict:
    """Grouped bar chart of In-Sample vs Out-of-Sample Sharpe per fold."""
    folds = [f"Fold {s.fold}" for s in wf.splits]
    is_sharpes = [s.train_sharpe for s in wf.splits]
    oos_sharpes = [s.test_sharpe for s in wf.splits]

    fig = go.Figure(data=[
        go.Bar(name="In-Sample Sharpe", x=folds, y=is_sharpes,
               marker_color="#636efa"),
        go.Bar(name="Out-of-Sample Sharpe", x=folds, y=oos_sharpes,
               marker_color="#ef553b"),
    ])

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        title_text="Walk-Forward: IS vs OOS Sharpe",
        yaxis_title="Sharpe Ratio",
        height=500,
        width=900,
    )
    return _fig_to_dict(fig, "walk_forward_chart")


def generate_monte_carlo_chart(mc: MonteCarloResult, initial_capital: float) -> dict:
    """Fan chart showing percentile bands of simulated equity paths."""
    x_label = "Simulation End"

    fig = go.Figure()

    # Percentile bands as horizontal markers at the terminal step
    bands = [
        ("P5", mc.percentile_5, "#ef553b"),
        ("P25", mc.percentile_25, "#ffa15a"),
        ("Median", mc.median_final_equity, "#00cc96"),
        ("P75", mc.percentile_75, "#ffa15a"),
        ("P95", mc.percentile_95, "#ef553b"),
    ]

    fig.add_trace(go.Scatter(
        x=["Start", x_label],
        y=[initial_capital, mc.percentile_5],
        mode="lines", line=dict(color="#ef553b", dash="dot"), name="P5",
    ))
    fig.add_trace(go.Scatter(
        x=["Start", x_label],
        y=[initial_capital, mc.percentile_25],
        mode="lines", line=dict(color="#ffa15a", dash="dash"), name="P25",
        fill="tonexty", fillcolor="rgba(239,85,59,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=["Start", x_label],
        y=[initial_capital, mc.median_final_equity],
        mode="lines", line=dict(color="#00cc96", width=3), name="Median",
        fill="tonexty", fillcolor="rgba(255,161,90,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=["Start", x_label],
        y=[initial_capital, mc.percentile_75],
        mode="lines", line=dict(color="#ffa15a", dash="dash"), name="P75",
        fill="tonexty", fillcolor="rgba(0,204,150,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=["Start", x_label],
        y=[initial_capital, mc.percentile_95],
        mode="lines", line=dict(color="#ef553b", dash="dot"), name="P95",
        fill="tonexty", fillcolor="rgba(255,161,90,0.15)",
    ))

    fig.update_layout(
        template="plotly_dark",
        title_text=f"Monte Carlo Fan Chart ({mc.n_simulations} sims)",
        yaxis_title="Equity ($)",
        height=500,
        width=900,
    )
    return _fig_to_dict(fig, "monte_carlo_chart")


# ---------------------------------------------------------------------------
# Full dashboard
# ---------------------------------------------------------------------------

def generate_full_dashboard(result: BacktestResult) -> list[dict]:
    """Generate all available charts for the given backtest result."""
    charts = [
        generate_equity_chart(result),
        generate_monthly_heatmap(result),
        generate_trade_distribution(result),
    ]
    return charts


# Need pandas for monthly heatmap
import pandas as pd  # noqa: E402
