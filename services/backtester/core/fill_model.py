"""
Realistic Fill Simulation Models.

Provides multiple slippage models from simple (fixed BPS) to sophisticated
(volume-participation market impact based on Almgren-Chriss simplified).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .models import SlippageModel


@dataclass(frozen=True, slots=True)
class FillResult:
    fill_price: float
    slippage_cost: float
    commission_cost: float
    fill_pct: float  # 1.0 = fully filled


def estimate_fill(
    side: Literal["buy", "sell"],
    reference_price: float,
    bar_volume: int,
    bar_vwap: float | None,
    order_size_dollars: float,
    model: SlippageModel = SlippageModel.FIXED_BPS,
    slippage_bps: float = 10.0,
    commission_per_trade: float = 0.0,
    impact_coefficient: float = 0.1,
    max_participation_rate: float = 0.05,
) -> FillResult:
    """
    Estimate fill price given market conditions.

    Args:
        side:                'buy' or 'sell'
        reference_price:     Price at entry time (open, close, etc.)
        bar_volume:          Volume of the bar
        bar_vwap:            VWAP of the bar (if available)
        order_size_dollars:  Dollar amount of the order
        model:               Slippage model to use
        slippage_bps:        Basis points for FIXED_BPS model
        commission_per_trade: Fixed commission per trade
        impact_coefficient:  For VOLUME_BASED model (typically 0.05-0.2)
        max_participation_rate: Max fraction of bar volume we'll trade

    Returns:
        FillResult with fill price, costs, and fill percentage.
    """
    if reference_price <= 0:
        return FillResult(
            fill_price=reference_price,
            slippage_cost=0.0,
            commission_cost=commission_per_trade,
            fill_pct=0.0,
        )

    shares_desired = order_size_dollars / reference_price

    if model == SlippageModel.FIXED_BPS:
        slippage_frac = slippage_bps / 10_000
        if side == "buy":
            fill_price = reference_price * (1 + slippage_frac)
        else:
            fill_price = reference_price * (1 - slippage_frac)

        slippage_cost = abs(fill_price - reference_price) * shares_desired
        return FillResult(
            fill_price=fill_price,
            slippage_cost=slippage_cost,
            commission_cost=commission_per_trade,
            fill_pct=1.0,
        )

    elif model == SlippageModel.VOLUME_BASED:
        # Square-root market impact (simplified Almgren-Chriss)
        # impact = η * σ * sqrt(shares / ADV)
        if bar_volume <= 0:
            return FillResult(
                fill_price=reference_price,
                slippage_cost=0.0,
                commission_cost=commission_per_trade,
                fill_pct=0.0,
            )

        dollar_volume = reference_price * bar_volume
        participation = order_size_dollars / dollar_volume
        capped_participation = min(participation, max_participation_rate)

        impact_pct = impact_coefficient * math.sqrt(capped_participation)
        fill_pct = capped_participation / participation if participation > 0 else 1.0

        if side == "buy":
            fill_price = reference_price * (1 + impact_pct)
        else:
            fill_price = reference_price * (1 - impact_pct)

        filled_shares = shares_desired * fill_pct
        slippage_cost = abs(fill_price - reference_price) * filled_shares

        return FillResult(
            fill_price=fill_price,
            slippage_cost=slippage_cost,
            commission_cost=commission_per_trade,
            fill_pct=fill_pct,
        )

    elif model == SlippageModel.SPREAD_BASED:
        # Use VWAP as proxy for mid-price; assume half-spread slippage
        vwap = bar_vwap if bar_vwap and bar_vwap > 0 else reference_price
        estimated_spread_pct = max(slippage_bps / 10_000, abs(vwap - reference_price) / vwap)
        half_spread = estimated_spread_pct / 2

        if side == "buy":
            fill_price = reference_price * (1 + half_spread)
        else:
            fill_price = reference_price * (1 - half_spread)

        slippage_cost = abs(fill_price - reference_price) * shares_desired
        return FillResult(
            fill_price=fill_price,
            slippage_cost=slippage_cost,
            commission_cost=commission_per_trade,
            fill_pct=1.0,
        )

    raise ValueError(f"Unknown slippage model: {model}")
