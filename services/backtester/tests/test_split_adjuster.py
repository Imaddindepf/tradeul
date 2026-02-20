"""Tests for core.split_adjuster – parse, compute factors, and adjust bars."""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd
import pytest
from core.split_adjuster import parse_splits, compute_adjustment_factors, adjust_bars_with_factors


class TestParseSplits:
    def test_parse_splits_empty(self):
        result = parse_splits([])
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["ticker", "execution_date", "split_from", "split_to"]
        assert len(result) == 0

    def test_parse_splits_basic(self):
        raw = [{"ticker": "AAPL", "execution_date": "2020-08-31", "split_from": 1, "split_to": 4}]
        df = parse_splits(raw)
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "AAPL"
        assert df.iloc[0]["split_from"] == 1.0
        assert df.iloc[0]["split_to"] == 4.0
        assert df.iloc[0]["execution_date"] == date(2020, 8, 31)


class TestComputeAdjustmentFactors:
    def test_compute_adjustment_single_split(self):
        splits = pd.DataFrame([{"ticker": "AAPL", "execution_date": date(2020, 8, 31), "split_from": 1.0, "split_to": 4.0}])
        factors = compute_adjustment_factors(splits)
        assert len(factors) == 1
        row = factors.iloc[0]
        assert row["price_factor"] == pytest.approx(0.25)
        assert row["volume_factor"] == pytest.approx(4.0)

    def test_compute_adjustment_multiple_splits(self):
        splits = pd.DataFrame([
            {"ticker": "AAPL", "execution_date": date(2014, 6, 9), "split_from": 1.0, "split_to": 7.0},
            {"ticker": "AAPL", "execution_date": date(2020, 8, 31), "split_from": 1.0, "split_to": 4.0},
        ])
        factors = compute_adjustment_factors(splits)
        assert len(factors) == 2
        factors = factors.sort_values("effective_before_date").reset_index(drop=True)
        assert factors.iloc[0]["price_factor"] == pytest.approx(1.0 / 28.0, rel=1e-6)
        assert factors.iloc[1]["price_factor"] == pytest.approx(1.0 / 4.0, rel=1e-6)


class TestAdjustBars:
    def test_adjust_bars_no_splits(self):
        bars = pd.DataFrame({"ticker": ["AAPL", "AAPL"], "date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "open": [150.0, 151.0], "high": [155.0, 156.0], "low": [149.0, 150.0], "close": [154.0, 155.0], "volume": [1000000, 1100000], "vwap": [152.0, 153.0], "transactions": [5000, 5500]})
        empty_factors = pd.DataFrame(columns=["ticker", "effective_before_date", "price_factor", "volume_factor"])
        result = adjust_bars_with_factors(bars, empty_factors)
        pd.testing.assert_frame_equal(result, bars)

    def test_adjust_bars_with_split(self):
        split_date = date(2024, 3, 1)
        bars = pd.DataFrame({"ticker": ["AAPL"] * 4, "date": pd.to_datetime(["2024-02-01", "2024-02-15", "2024-03-01", "2024-03-15"]), "open": [200.0, 210.0, 105.0, 108.0], "high": [205.0, 215.0, 110.0, 112.0], "low": [198.0, 208.0, 103.0, 106.0], "close": [204.0, 212.0, 107.0, 110.0], "volume": [500000, 600000, 1000000, 1100000], "vwap": [201.0, 211.0, 106.0, 109.0], "transactions": [3000, 3500, 4000, 4200]})
        factors = pd.DataFrame([{"ticker": "AAPL", "effective_before_date": pd.Timestamp(split_date), "price_factor": 0.5, "volume_factor": 2.0}])
        result = adjust_bars_with_factors(bars, factors)
        pre = result[result["date"] < pd.Timestamp(split_date)]
        assert pre.iloc[0]["close"] == pytest.approx(204.0 * 0.5, rel=1e-4)
        assert pre.iloc[0]["open"] == pytest.approx(200.0 * 0.5, rel=1e-4)
        assert pre.iloc[0]["volume"] == pytest.approx(500000 * 2, rel=1)
        post = result[result["date"] >= pd.Timestamp(split_date)]
        assert post.iloc[0]["close"] == pytest.approx(107.0, rel=1e-4)
        assert post.iloc[0]["volume"] == pytest.approx(1000000, rel=1)
