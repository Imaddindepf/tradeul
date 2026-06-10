/**
 * AUTO-GENERATED — DO NOT EDIT BY HAND.
 *
 * Source of truth: shared/config/filter_catalog.json
 * Regenerate with:  python3 scripts/gen_filter_assets.py
 */

/* eslint-disable */

export interface FilterDef {
  label: string;
  minK: string;
  maxK: string;
  suf: string;
  units?: readonly string[];
  defU?: string;
  phMin?: string;
  phMax?: string;
}

export interface FilterGroup {
  id: string;
  group: string;
  filters: FilterDef[];
}

export const FILTER_GROUPS: readonly FilterGroup[] = [
  {
    "id": "price_quote",
    "group": "Price & Quote",
    "filters": [
      {
        "label": "Price",
        "minK": "min_price",
        "maxK": "max_price",
        "suf": "$",
        "phMin": "0.50",
        "phMax": "500"
      },
      {
        "label": "Spread",
        "minK": "min_spread",
        "maxK": "max_spread",
        "suf": "$",
        "phMin": "0.01",
        "phMax": "0.50"
      },
      {
        "label": "Bid Size",
        "minK": "min_bid_size",
        "maxK": "max_bid_size",
        "suf": "",
        "units": [
          "",
          "K"
        ],
        "defU": "",
        "phMin": "100",
        "phMax": "10000"
      },
      {
        "label": "Ask Size",
        "minK": "min_ask_size",
        "maxK": "max_ask_size",
        "suf": "",
        "units": [
          "",
          "K"
        ],
        "defU": "",
        "phMin": "100",
        "phMax": "10000"
      },
      {
        "label": "Bid / Ask Ratio",
        "minK": "min_bid_ask_ratio",
        "maxK": "max_bid_ask_ratio",
        "suf": "",
        "phMin": "0.5",
        "phMax": "3"
      },
      {
        "label": "Distance from Inside Market",
        "minK": "min_distance_from_nbbo",
        "maxK": "max_distance_from_nbbo",
        "suf": "%",
        "phMin": "0",
        "phMax": "1"
      },
      {
        "label": "Decimal",
        "minK": "min_decimal",
        "maxK": "max_decimal",
        "suf": "",
        "phMin": "0",
        "phMax": "0.99"
      }
    ]
  },
  {
    "id": "volume",
    "group": "Volume",
    "filters": [
      {
        "label": "Relative Volume",
        "minK": "min_rvol",
        "maxK": "max_rvol",
        "suf": "x",
        "phMin": "1",
        "phMax": "10"
      },
      {
        "label": "Volume Today",
        "minK": "min_volume",
        "maxK": "max_volume",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "10",
        "phMax": "500"
      },
      {
        "label": "Volume Today %",
        "minK": "min_volume_today_pct",
        "maxK": "max_volume_today_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "500"
      },
      {
        "label": "Volume Yesterday %",
        "minK": "min_volume_yesterday_pct",
        "maxK": "max_volume_yesterday_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "500"
      },
      {
        "label": "Dollar Volume",
        "minK": "min_dollar_volume",
        "maxK": "max_dollar_volume",
        "suf": "$",
        "units": [
          "K",
          "M",
          "B"
        ],
        "defU": "M",
        "phMin": "1",
        "phMax": "100"
      },
      {
        "label": "Float Turnover",
        "minK": "min_float_turnover",
        "maxK": "max_float_turnover",
        "suf": "x",
        "phMin": "0.01",
        "phMax": "5"
      },
      {
        "label": "Previous Day Volume",
        "minK": "min_prev_day_volume",
        "maxK": "max_prev_day_volume",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "100",
        "phMax": "10000"
      },
      {
        "label": "Post-Market Volume",
        "minK": "min_postmarket_volume",
        "maxK": "max_postmarket_volume",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "10",
        "phMax": "500"
      }
    ]
  },
  {
    "id": "volume_by_minute_window",
    "group": "Volume by Minute Window",
    "filters": [
      {
        "label": "Volume 1 Minute",
        "minK": "min_vol_1min",
        "maxK": "max_vol_1min",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "1",
        "phMax": "50"
      },
      {
        "label": "Volume 5 Minute",
        "minK": "min_vol_5min",
        "maxK": "max_vol_5min",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "1",
        "phMax": "100"
      },
      {
        "label": "Volume 10 Minute",
        "minK": "min_vol_10min",
        "maxK": "max_vol_10min",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "5",
        "phMax": "200"
      },
      {
        "label": "Volume 15 Minute",
        "minK": "min_vol_15min",
        "maxK": "max_vol_15min",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "10",
        "phMax": "500"
      },
      {
        "label": "Volume 30 Minute",
        "minK": "min_vol_30min",
        "maxK": "max_vol_30min",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "20",
        "phMax": "1000"
      },
      {
        "label": "Average Volume 1m %",
        "minK": "min_vol_1min_pct",
        "maxK": "max_vol_1min_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "500"
      },
      {
        "label": "Average Volume 5m %",
        "minK": "min_vol_5min_pct",
        "maxK": "max_vol_5min_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "500"
      },
      {
        "label": "Average Volume 10m %",
        "minK": "min_vol_10min_pct",
        "maxK": "max_vol_10min_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "500"
      },
      {
        "label": "Average Volume 15m %",
        "minK": "min_vol_15min_pct",
        "maxK": "max_vol_15min_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "500"
      },
      {
        "label": "Average Volume 30m %",
        "minK": "min_vol_30min_pct",
        "maxK": "max_vol_30min_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "500"
      },
      {
        "label": "Minute Volume",
        "minK": "min_minute_volume",
        "maxK": "max_minute_volume",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "1",
        "phMax": "100"
      }
    ]
  },
  {
    "id": "average_daily_volume",
    "group": "Average Daily Volume",
    "filters": [
      {
        "label": "Average Daily Volume (5D)",
        "minK": "min_avg_volume_5d",
        "maxK": "max_avg_volume_5d",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "100",
        "phMax": "5000"
      },
      {
        "label": "Average Daily Volume (10D)",
        "minK": "min_avg_volume_10d",
        "maxK": "max_avg_volume_10d",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "100",
        "phMax": "5000"
      },
      {
        "label": "Average Daily Volume (20D)",
        "minK": "min_avg_volume_20d",
        "maxK": "max_avg_volume_20d",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "100",
        "phMax": "5000"
      },
      {
        "label": "Average Daily Volume (3M)",
        "minK": "min_avg_volume_3m",
        "maxK": "max_avg_volume_3m",
        "suf": "",
        "units": [
          "",
          "K",
          "M"
        ],
        "defU": "K",
        "phMin": "100",
        "phMax": "5000"
      }
    ]
  },
  {
    "id": "change_from_close_open",
    "group": "Change from Close / Open",
    "filters": [
      {
        "label": "Change from the Close %",
        "minK": "min_change_percent",
        "maxK": "max_change_percent",
        "suf": "%",
        "phMin": "-10",
        "phMax": "50"
      },
      {
        "label": "Change from the Close $",
        "minK": "min_change_from_close_dollars",
        "maxK": "max_change_from_close_dollars",
        "suf": "$",
        "phMin": "-10",
        "phMax": "20"
      },
      {
        "label": "Change from the Close (ATR)",
        "minK": "min_change_from_close_ratio",
        "maxK": "max_change_from_close_ratio",
        "suf": "x",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from the Open %",
        "minK": "min_change_from_open",
        "maxK": "max_change_from_open",
        "suf": "%",
        "phMin": "-5",
        "phMax": "20"
      },
      {
        "label": "Change from the Open $",
        "minK": "min_change_from_open_dollars",
        "maxK": "max_change_from_open_dollars",
        "suf": "$",
        "phMin": "-5",
        "phMax": "10"
      },
      {
        "label": "Change from the Open (ATR)",
        "minK": "min_change_from_open_ratio",
        "maxK": "max_change_from_open_ratio",
        "suf": "x",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from the Open Weighted",
        "minK": "min_change_from_open_weighted",
        "maxK": "max_change_from_open_weighted",
        "suf": "",
        "phMin": "-3",
        "phMax": "3"
      }
    ]
  },
  {
    "id": "gap",
    "group": "Gap",
    "filters": [
      {
        "label": "Gap %",
        "minK": "min_gap_percent",
        "maxK": "max_gap_percent",
        "suf": "%",
        "phMin": "-10",
        "phMax": "30"
      },
      {
        "label": "Gap $",
        "minK": "min_gap_dollars",
        "maxK": "max_gap_dollars",
        "suf": "$",
        "phMin": "-5",
        "phMax": "10"
      },
      {
        "label": "Gap (ATR)",
        "minK": "min_gap_ratio",
        "maxK": "max_gap_ratio",
        "suf": "x",
        "phMin": "-3",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "pre_market_post_market",
    "group": "Pre-Market / Post-Market",
    "filters": [
      {
        "label": "Change Pre-Market %",
        "minK": "min_premarket_change_percent",
        "maxK": "max_premarket_change_percent",
        "suf": "%",
        "phMin": "-5",
        "phMax": "20"
      },
      {
        "label": "Change Post-Market %",
        "minK": "min_postmarket_change_percent",
        "maxK": "max_postmarket_change_percent",
        "suf": "%",
        "phMin": "-5",
        "phMax": "10"
      },
      {
        "label": "Change Post-Market $",
        "minK": "min_postmarket_change_dollars",
        "maxK": "max_postmarket_change_dollars",
        "suf": "$",
        "phMin": "-5",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "change_by_minute",
    "group": "Change by Minute",
    "filters": [
      {
        "label": "Change 1 Minute",
        "minK": "min_chg_1min",
        "maxK": "max_chg_1min",
        "suf": "%",
        "phMin": "-2",
        "phMax": "5"
      },
      {
        "label": "Change 1 Minute",
        "minK": "min_chg_1min_dollars",
        "maxK": "max_chg_1min_dollars",
        "suf": "$",
        "phMin": "-0.50",
        "phMax": "1.00"
      },
      {
        "label": "Change 2 Minute",
        "minK": "min_chg_2min",
        "maxK": "max_chg_2min",
        "suf": "%",
        "phMin": "-3",
        "phMax": "7"
      },
      {
        "label": "Change 2 Minute",
        "minK": "min_chg_2min_dollars",
        "maxK": "max_chg_2min_dollars",
        "suf": "$",
        "phMin": "-0.75",
        "phMax": "1.50"
      },
      {
        "label": "Change 5 Minute",
        "minK": "min_chg_5min",
        "maxK": "max_chg_5min",
        "suf": "%",
        "phMin": "-5",
        "phMax": "10"
      },
      {
        "label": "Change 5 Minute",
        "minK": "min_chg_5min_dollars",
        "maxK": "max_chg_5min_dollars",
        "suf": "$",
        "phMin": "-1.00",
        "phMax": "2.50"
      },
      {
        "label": "Change 10 Minute",
        "minK": "min_chg_10min",
        "maxK": "max_chg_10min",
        "suf": "%",
        "phMin": "-5",
        "phMax": "15"
      },
      {
        "label": "Change 10 Minute",
        "minK": "min_chg_10min_dollars",
        "maxK": "max_chg_10min_dollars",
        "suf": "$",
        "phMin": "-1.50",
        "phMax": "4.00"
      },
      {
        "label": "Change 15 Minute",
        "minK": "min_chg_15min",
        "maxK": "max_chg_15min",
        "suf": "%",
        "phMin": "-8",
        "phMax": "20"
      },
      {
        "label": "Change 15 Minute",
        "minK": "min_chg_15min_dollars",
        "maxK": "max_chg_15min_dollars",
        "suf": "$",
        "phMin": "-2.00",
        "phMax": "5.00"
      },
      {
        "label": "Change 30 Minute",
        "minK": "min_chg_30min",
        "maxK": "max_chg_30min",
        "suf": "%",
        "phMin": "-10",
        "phMax": "25"
      },
      {
        "label": "Change 30 Minute",
        "minK": "min_chg_30min_dollars",
        "maxK": "max_chg_30min_dollars",
        "suf": "$",
        "phMin": "-3.00",
        "phMax": "7.00"
      },
      {
        "label": "Change 60 Minute",
        "minK": "min_chg_60min",
        "maxK": "max_chg_60min",
        "suf": "%",
        "phMin": "-15",
        "phMax": "30"
      },
      {
        "label": "Change 60 Minute",
        "minK": "min_chg_60min_dollars",
        "maxK": "max_chg_60min_dollars",
        "suf": "$",
        "phMin": "-5.00",
        "phMax": "10.00"
      },
      {
        "label": "Change 120 Minute",
        "minK": "min_chg_120min",
        "maxK": "max_chg_120min",
        "suf": "%",
        "phMin": "-20",
        "phMax": "40"
      },
      {
        "label": "Change 120 Minute",
        "minK": "min_chg_120min_dollars",
        "maxK": "max_chg_120min_dollars",
        "suf": "$",
        "phMin": "-8.00",
        "phMax": "15.00"
      }
    ]
  },
  {
    "id": "change_in_days_%",
    "group": "Change in Days %",
    "filters": [
      {
        "label": "Change Previous Day",
        "minK": "min_change_1d",
        "maxK": "max_change_1d",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change in 3 Days",
        "minK": "min_change_3d",
        "maxK": "max_change_3d",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change in 5 Days",
        "minK": "min_change_5d",
        "maxK": "max_change_5d",
        "suf": "%",
        "phMin": "-20",
        "phMax": "50"
      },
      {
        "label": "Change in 10 Days",
        "minK": "min_change_10d",
        "maxK": "max_change_10d",
        "suf": "%",
        "phMin": "-30",
        "phMax": "100"
      },
      {
        "label": "Change in 20 Days",
        "minK": "min_change_20d",
        "maxK": "max_change_20d",
        "suf": "%",
        "phMin": "-50",
        "phMax": "200"
      }
    ]
  },
  {
    "id": "change_in_days_$",
    "group": "Change in Days $",
    "filters": [
      {
        "label": "Change in 5 Days $",
        "minK": "min_change_5d_dollars",
        "maxK": "max_change_5d_dollars",
        "suf": "$",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change in 10 Days $",
        "minK": "min_change_10d_dollars",
        "maxK": "max_change_10d_dollars",
        "suf": "$",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change in 20 Days $",
        "minK": "min_change_20d_dollars",
        "maxK": "max_change_20d_dollars",
        "suf": "$",
        "phMin": "-30",
        "phMax": "30"
      }
    ]
  },
  {
    "id": "long_term_change",
    "group": "Long-Term Change",
    "filters": [
      {
        "label": "Change in 1 Year %",
        "minK": "min_change_1y",
        "maxK": "max_change_1y",
        "suf": "%",
        "phMin": "-50",
        "phMax": "200"
      },
      {
        "label": "Change in 1 Year $",
        "minK": "min_change_1y_dollars",
        "maxK": "max_change_1y_dollars",
        "suf": "$",
        "phMin": "-50",
        "phMax": "100"
      },
      {
        "label": "Change Since January 1 %",
        "minK": "min_change_ytd",
        "maxK": "max_change_ytd",
        "suf": "%",
        "phMin": "-30",
        "phMax": "100"
      },
      {
        "label": "Change Since January 1 $",
        "minK": "min_change_ytd_dollars",
        "maxK": "max_change_ytd_dollars",
        "suf": "$",
        "phMin": "-20",
        "phMax": "50"
      }
    ]
  },
  {
    "id": "volatility",
    "group": "Volatility",
    "filters": [
      {
        "label": "Average True Range",
        "minK": "min_atr",
        "maxK": "max_atr",
        "suf": "$",
        "phMin": "0.1",
        "phMax": "5"
      },
      {
        "label": "Average True Range %",
        "minK": "min_atr_percent",
        "maxK": "max_atr_percent",
        "suf": "%",
        "phMin": "2",
        "phMax": "10"
      },
      {
        "label": "Yearly Standard Deviation",
        "minK": "min_yearly_std_dev",
        "maxK": "max_yearly_std_dev",
        "suf": "$",
        "phMin": "0.5",
        "phMax": "10"
      },
      {
        "label": "Standard Deviation (Bollinger)",
        "minK": "min_bb_std_dev",
        "maxK": "max_bb_std_dev",
        "suf": "$",
        "phMin": "0.01",
        "phMax": "5"
      },
      {
        "label": "Daily ATR %",
        "minK": "min_daily_atr_percent",
        "maxK": "max_daily_atr_percent",
        "suf": "%",
        "phMin": "1",
        "phMax": "15"
      }
    ]
  },
  {
    "id": "today",
    "group": "Today",
    "filters": [
      {
        "label": "Today's Range $",
        "minK": "min_todays_range",
        "maxK": "max_todays_range",
        "suf": "$",
        "phMin": "0.1",
        "phMax": "10"
      },
      {
        "label": "Today's Range %",
        "minK": "min_todays_range_pct",
        "maxK": "max_todays_range_pct",
        "suf": "%",
        "phMin": "1",
        "phMax": "20"
      }
    ]
  },
  {
    "id": "minute_range_$",
    "group": "Minute Range $",
    "filters": [
      {
        "label": "2 Minute Range $",
        "minK": "min_range_2min",
        "maxK": "max_range_2min",
        "suf": "$",
        "phMin": "0.10",
        "phMax": "2"
      },
      {
        "label": "5 Minute Range $",
        "minK": "min_range_5min",
        "maxK": "max_range_5min",
        "suf": "$",
        "phMin": "0.20",
        "phMax": "5"
      },
      {
        "label": "15 Minute Range $",
        "minK": "min_range_15min",
        "maxK": "max_range_15min",
        "suf": "$",
        "phMin": "0.50",
        "phMax": "10"
      },
      {
        "label": "30 Minute Range $",
        "minK": "min_range_30min",
        "maxK": "max_range_30min",
        "suf": "$",
        "phMin": "1",
        "phMax": "15"
      },
      {
        "label": "60 Minute Range $",
        "minK": "min_range_60min",
        "maxK": "max_range_60min",
        "suf": "$",
        "phMin": "1",
        "phMax": "20"
      },
      {
        "label": "120 Minute Range $",
        "minK": "min_range_120min",
        "maxK": "max_range_120min",
        "suf": "$",
        "phMin": "2",
        "phMax": "30"
      }
    ]
  },
  {
    "id": "minute_range_%",
    "group": "Minute Range %",
    "filters": [
      {
        "label": "2 Minute Range %",
        "minK": "min_range_2min_pct",
        "maxK": "max_range_2min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      },
      {
        "label": "5 Minute Range %",
        "minK": "min_range_5min_pct",
        "maxK": "max_range_5min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      },
      {
        "label": "15 Minute Range %",
        "minK": "min_range_15min_pct",
        "maxK": "max_range_15min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      },
      {
        "label": "30 Minute Range %",
        "minK": "min_range_30min_pct",
        "maxK": "max_range_30min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      },
      {
        "label": "60 Minute Range %",
        "minK": "min_range_60min_pct",
        "maxK": "max_range_60min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      },
      {
        "label": "120 Minute Range %",
        "minK": "min_range_120min_pct",
        "maxK": "max_range_120min_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "300"
      }
    ]
  },
  {
    "id": "multi_day_range_$",
    "group": "Multi-Day Range $",
    "filters": [
      {
        "label": "5 Day Range $",
        "minK": "min_range_5d",
        "maxK": "max_range_5d",
        "suf": "$",
        "phMin": "0.5",
        "phMax": "20"
      },
      {
        "label": "10 Day Range $",
        "minK": "min_range_10d",
        "maxK": "max_range_10d",
        "suf": "$",
        "phMin": "1",
        "phMax": "30"
      },
      {
        "label": "20 Day Range $",
        "minK": "min_range_20d",
        "maxK": "max_range_20d",
        "suf": "$",
        "phMin": "2",
        "phMax": "50"
      }
    ]
  },
  {
    "id": "multi_day_range_%",
    "group": "Multi-Day Range %",
    "filters": [
      {
        "label": "5 Day Range %",
        "minK": "min_range_5d_pct",
        "maxK": "max_range_5d_pct",
        "suf": "%",
        "phMin": "50",
        "phMax": "500"
      },
      {
        "label": "10 Day Range %",
        "minK": "min_range_10d_pct",
        "maxK": "max_range_10d_pct",
        "suf": "%",
        "phMin": "100",
        "phMax": "800"
      },
      {
        "label": "20 Day Range %",
        "minK": "min_range_20d_pct",
        "maxK": "max_range_20d_pct",
        "suf": "%",
        "phMin": "150",
        "phMax": "1200"
      }
    ]
  },
  {
    "id": "position_in_range",
    "group": "Position in Range",
    "filters": [
      {
        "label": "Position in Range (Today)",
        "minK": "min_pos_in_range",
        "maxK": "max_pos_in_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Previous Day's Range",
        "minK": "min_pos_in_prev_day_range",
        "maxK": "max_pos_in_prev_day_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 5 Day Range",
        "minK": "min_pos_in_5d_range",
        "maxK": "max_pos_in_5d_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 10 Day Range",
        "minK": "min_pos_in_10d_range",
        "maxK": "max_pos_in_10d_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 20 Day Range",
        "minK": "min_pos_in_20d_range",
        "maxK": "max_pos_in_20d_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 52 Week Range",
        "minK": "min_pos_in_52w_range",
        "maxK": "max_pos_in_52w_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 3 Month Range",
        "minK": "min_pos_in_3m_range",
        "maxK": "max_pos_in_3m_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 6 Month Range",
        "minK": "min_pos_in_6m_range",
        "maxK": "max_pos_in_6m_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 9 Month Range",
        "minK": "min_pos_in_9m_range",
        "maxK": "max_pos_in_9m_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 2 Year Range",
        "minK": "min_pos_in_2y_range",
        "maxK": "max_pos_in_2y_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Lifetime Range",
        "minK": "min_pos_in_lifetime_range",
        "maxK": "max_pos_in_lifetime_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Pre-Market Range",
        "minK": "min_pos_in_premarket_range",
        "maxK": "max_pos_in_premarket_range",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      }
    ]
  },
  {
    "id": "position_in_minute_range",
    "group": "Position in Minute Range",
    "filters": [
      {
        "label": "Position in 5 Minute Range",
        "minK": "min_pos_in_range_5m",
        "maxK": "max_pos_in_range_5m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 15 Minute Range",
        "minK": "min_pos_in_range_15m",
        "maxK": "max_pos_in_range_15m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 30 Minute Range",
        "minK": "min_pos_in_range_30m",
        "maxK": "max_pos_in_range_30m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in 60 Minute Range",
        "minK": "min_pos_in_range_60m",
        "maxK": "max_pos_in_range_60m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      }
    ]
  },
  {
    "id": "high_low",
    "group": "High / Low",
    "filters": [
      {
        "label": "Below High",
        "minK": "min_below_high",
        "maxK": "max_below_high",
        "suf": "$",
        "phMin": "0",
        "phMax": "5"
      },
      {
        "label": "Above Low",
        "minK": "min_above_low",
        "maxK": "max_above_low",
        "suf": "$",
        "phMin": "0",
        "phMax": "5"
      },
      {
        "label": "Below Pre-Market High",
        "minK": "min_below_premarket_high",
        "maxK": "max_below_premarket_high",
        "suf": "$",
        "phMin": "0",
        "phMax": "5"
      },
      {
        "label": "Above Pre-Market Low",
        "minK": "min_above_premarket_low",
        "maxK": "max_above_premarket_low",
        "suf": "$",
        "phMin": "0",
        "phMax": "5"
      },
      {
        "label": "From Intraday High %",
        "minK": "min_price_from_intraday_high",
        "maxK": "max_price_from_intraday_high",
        "suf": "%",
        "phMin": "-10",
        "phMax": "0"
      },
      {
        "label": "From Intraday Low %",
        "minK": "min_price_from_intraday_low",
        "maxK": "max_price_from_intraday_low",
        "suf": "%",
        "phMin": "0",
        "phMax": "20"
      },
      {
        "label": "From High %",
        "minK": "min_price_from_high",
        "maxK": "max_price_from_high",
        "suf": "%",
        "phMin": "-20",
        "phMax": "0"
      },
      {
        "label": "From Low %",
        "minK": "min_price_from_low",
        "maxK": "max_price_from_low",
        "suf": "%",
        "phMin": "0",
        "phMax": "50"
      },
      {
        "label": "Position of Open",
        "minK": "min_pos_of_open",
        "maxK": "max_pos_of_open",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      }
    ]
  },
  {
    "id": "consecutive_candles",
    "group": "Consecutive Candles",
    "filters": [
      {
        "label": "Consecutive Candles (1m)",
        "minK": "min_consecutive_candles",
        "maxK": "max_consecutive_candles",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (2m)",
        "minK": "min_consecutive_candles_2m",
        "maxK": "max_consecutive_candles_2m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (5m)",
        "minK": "min_consecutive_candles_5m",
        "maxK": "max_consecutive_candles_5m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (10m)",
        "minK": "min_consecutive_candles_10m",
        "maxK": "max_consecutive_candles_10m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (15m)",
        "minK": "min_consecutive_candles_15m",
        "maxK": "max_consecutive_candles_15m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (30m)",
        "minK": "min_consecutive_candles_30m",
        "maxK": "max_consecutive_candles_30m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Consecutive Candles (60m)",
        "minK": "min_consecutive_candles_60m",
        "maxK": "max_consecutive_candles_60m",
        "suf": "",
        "phMin": "-10",
        "phMax": "10"
      }
    ]
  },
  {
    "id": "consecutive_days",
    "group": "Consecutive Days",
    "filters": [
      {
        "label": "Consecutive Days Up/Down",
        "minK": "min_consecutive_days_up",
        "maxK": "max_consecutive_days_up",
        "suf": "",
        "phMin": "-5",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "pivot_points",
    "group": "Pivot Points",
    "filters": [
      {
        "label": "Distance from Pivot",
        "minK": "min_dist_pivot",
        "maxK": "max_dist_pivot",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Distance from Pivot R1",
        "minK": "min_dist_pivot_r1",
        "maxK": "max_dist_pivot_r1",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Distance from Pivot R2",
        "minK": "min_dist_pivot_r2",
        "maxK": "max_dist_pivot_r2",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Distance from Pivot S1",
        "minK": "min_dist_pivot_s1",
        "maxK": "max_dist_pivot_s1",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Distance from Pivot S2",
        "minK": "min_dist_pivot_s2",
        "maxK": "max_dist_pivot_s2",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "vwap",
    "group": "VWAP",
    "filters": [
      {
        "label": "VWAP",
        "minK": "min_vwap",
        "maxK": "max_vwap",
        "suf": "$",
        "phMin": "5",
        "phMax": "200"
      },
      {
        "label": "Distance from VWAP",
        "minK": "min_dist_from_vwap",
        "maxK": "max_dist_from_vwap",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      }
    ]
  },
  {
    "id": "intraday_technical",
    "group": "Intraday Technical",
    "filters": [
      {
        "label": "RSI (1m)",
        "minK": "min_rsi",
        "maxK": "max_rsi",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "SMA 5",
        "minK": "min_sma_5",
        "maxK": "max_sma_5",
        "suf": "$",
        "phMin": "1",
        "phMax": "500"
      },
      {
        "label": "SMA 8",
        "minK": "min_sma_8",
        "maxK": "max_sma_8",
        "suf": "$",
        "phMin": "1",
        "phMax": "500"
      },
      {
        "label": "SMA 20",
        "minK": "min_sma_20",
        "maxK": "max_sma_20",
        "suf": "$",
        "phMin": "5",
        "phMax": "500"
      },
      {
        "label": "SMA 50",
        "minK": "min_sma_50",
        "maxK": "max_sma_50",
        "suf": "$",
        "phMin": "5",
        "phMax": "500"
      },
      {
        "label": "SMA 200",
        "minK": "min_sma_200",
        "maxK": "max_sma_200",
        "suf": "$",
        "phMin": "5",
        "phMax": "500"
      },
      {
        "label": "EMA 20",
        "minK": "min_ema_20",
        "maxK": "max_ema_20",
        "suf": "$",
        "phMin": "5",
        "phMax": "500"
      },
      {
        "label": "EMA 50",
        "minK": "min_ema_50",
        "maxK": "max_ema_50",
        "suf": "$",
        "phMin": "5",
        "phMax": "500"
      },
      {
        "label": "MACD Line",
        "minK": "min_macd_line",
        "maxK": "max_macd_line",
        "suf": "",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "MACD Histogram",
        "minK": "min_macd_hist",
        "maxK": "max_macd_hist",
        "suf": "",
        "phMin": "-2",
        "phMax": "2"
      },
      {
        "label": "Stochastic %K",
        "minK": "min_stoch_k",
        "maxK": "max_stoch_k",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "Stochastic %D",
        "minK": "min_stoch_d",
        "maxK": "max_stoch_d",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "ADX (Intraday)",
        "minK": "min_adx_14",
        "maxK": "max_adx_14",
        "suf": "",
        "phMin": "20",
        "phMax": "50"
      },
      {
        "label": "Bollinger Upper",
        "minK": "min_bb_upper",
        "maxK": "max_bb_upper",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "Bollinger Lower",
        "minK": "min_bb_lower",
        "maxK": "max_bb_lower",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      }
    ]
  },
  {
    "id": "multi_timeframe_rsi",
    "group": "Multi-Timeframe RSI",
    "filters": [
      {
        "label": "2 Minute RSI",
        "minK": "min_rsi_2m",
        "maxK": "max_rsi_2m",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "5 Minute RSI",
        "minK": "min_rsi_5m",
        "maxK": "max_rsi_5m",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "15 Minute RSI",
        "minK": "min_rsi_15m",
        "maxK": "max_rsi_15m",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "60 Minute RSI",
        "minK": "min_rsi_60m",
        "maxK": "max_rsi_60m",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      }
    ]
  },
  {
    "id": "position_in_bollinger_bands",
    "group": "Position in Bollinger Bands",
    "filters": [
      {
        "label": "Position in Bollinger Bands (1m)",
        "minK": "min_bb_position_1m",
        "maxK": "max_bb_position_1m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Bollinger Bands (5m)",
        "minK": "min_bb_position_5m",
        "maxK": "max_bb_position_5m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Bollinger Bands (15m)",
        "minK": "min_bb_position_15m",
        "maxK": "max_bb_position_15m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Bollinger Bands (60m)",
        "minK": "min_bb_position_60m",
        "maxK": "max_bb_position_60m",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Position in Bollinger Bands (Daily)",
        "minK": "min_daily_bb_position",
        "maxK": "max_daily_bb_position",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      }
    ]
  },
  {
    "id": "change_from_period_sma_(intraday)",
    "group": "Change from Period SMA (Intraday)",
    "filters": [
      {
        "label": "Change from 5 Period SMA (2m)",
        "minK": "min_dist_sma_5_2m",
        "maxK": "max_dist_sma_5_2m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 5 Period SMA (5m)",
        "minK": "min_dist_sma_5_5m",
        "maxK": "max_dist_sma_5_5m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 5 Period SMA (15m)",
        "minK": "min_dist_sma_5_15m",
        "maxK": "max_dist_sma_5_15m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 5 Period SMA (60m)",
        "minK": "min_dist_sma_5_60m",
        "maxK": "max_dist_sma_5_60m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 8 Period SMA (2m)",
        "minK": "min_dist_sma_8_2m",
        "maxK": "max_dist_sma_8_2m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 8 Period SMA (5m)",
        "minK": "min_dist_sma_8_5m",
        "maxK": "max_dist_sma_8_5m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 8 Period SMA (15m)",
        "minK": "min_dist_sma_8_15m",
        "maxK": "max_dist_sma_8_15m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 8 Period SMA (60m)",
        "minK": "min_dist_sma_8_60m",
        "maxK": "max_dist_sma_8_60m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 10 Period SMA (2m)",
        "minK": "min_dist_sma_10_2m",
        "maxK": "max_dist_sma_10_2m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 10 Period SMA (5m)",
        "minK": "min_dist_sma_10_5m",
        "maxK": "max_dist_sma_10_5m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 10 Period SMA (15m)",
        "minK": "min_dist_sma_10_15m",
        "maxK": "max_dist_sma_10_15m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 10 Period SMA (60m)",
        "minK": "min_dist_sma_10_60m",
        "maxK": "max_dist_sma_10_60m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 20 Period SMA (2m)",
        "minK": "min_dist_sma_20_2m",
        "maxK": "max_dist_sma_20_2m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 20 Period SMA (5m)",
        "minK": "min_dist_sma_20_5m",
        "maxK": "max_dist_sma_20_5m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 20 Period SMA (15m)",
        "minK": "min_dist_sma_20_15m",
        "maxK": "max_dist_sma_20_15m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 20 Period SMA (60m)",
        "minK": "min_dist_sma_20_60m",
        "maxK": "max_dist_sma_20_60m",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 130 Period SMA (15m)",
        "minK": "min_dist_sma_130_15m",
        "maxK": "max_dist_sma_130_15m",
        "suf": "%",
        "phMin": "-15",
        "phMax": "15"
      },
      {
        "label": "Change from 200 Period SMA (2m)",
        "minK": "min_dist_sma_200_2m",
        "maxK": "max_dist_sma_200_2m",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from 200 Period SMA (5m)",
        "minK": "min_dist_sma_200_5m",
        "maxK": "max_dist_sma_200_5m",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from 200 Period SMA (15m)",
        "minK": "min_dist_sma_200_15m",
        "maxK": "max_dist_sma_200_15m",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from 200 Period SMA (60m)",
        "minK": "min_dist_sma_200_60m",
        "maxK": "max_dist_sma_200_60m",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from SMA 5 (Intraday)",
        "minK": "min_dist_sma_5",
        "maxK": "max_dist_sma_5",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from SMA 8 (Intraday)",
        "minK": "min_dist_sma_8",
        "maxK": "max_dist_sma_8",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from SMA 20 (Intraday)",
        "minK": "min_dist_sma_20",
        "maxK": "max_dist_sma_20",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from SMA 50 (Intraday)",
        "minK": "min_dist_sma_50",
        "maxK": "max_dist_sma_50",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from SMA 200 (Intraday)",
        "minK": "min_dist_sma_200",
        "maxK": "max_dist_sma_200",
        "suf": "%",
        "phMin": "-50",
        "phMax": "50"
      }
    ]
  },
  {
    "id": "8_vs_20_period_sma",
    "group": "8 vs. 20 Period SMA",
    "filters": [
      {
        "label": "8 vs. 20 Period SMA (2m)",
        "minK": "min_sma_8_vs_20_2m",
        "maxK": "max_sma_8_vs_20_2m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "8 vs. 20 Period SMA (5m)",
        "minK": "min_sma_8_vs_20_5m",
        "maxK": "max_sma_8_vs_20_5m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "8 vs. 20 Period SMA (15m)",
        "minK": "min_sma_8_vs_20_15m",
        "maxK": "max_sma_8_vs_20_15m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "8 vs. 20 Period SMA (60m)",
        "minK": "min_sma_8_vs_20_60m",
        "maxK": "max_sma_8_vs_20_60m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "20_vs_200_period_sma",
    "group": "20 vs. 200 Period SMA",
    "filters": [
      {
        "label": "20 vs. 200 Period SMA (2m)",
        "minK": "min_sma_20_vs_200_2m",
        "maxK": "max_sma_20_vs_200_2m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "20 vs. 200 Period SMA (5m)",
        "minK": "min_sma_20_vs_200_5m",
        "maxK": "max_sma_20_vs_200_5m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "20 vs. 200 Period SMA (15m)",
        "minK": "min_sma_20_vs_200_15m",
        "maxK": "max_sma_20_vs_200_15m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "20 vs. 200 Period SMA (60m)",
        "minK": "min_sma_20_vs_200_60m",
        "maxK": "max_sma_20_vs_200_60m",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "daily_sma",
    "group": "Daily SMA",
    "filters": [
      {
        "label": "5 Day SMA",
        "minK": "min_daily_sma_5",
        "maxK": "max_daily_sma_5",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "8 Day SMA",
        "minK": "min_daily_sma_8",
        "maxK": "max_daily_sma_8",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "10 Day SMA",
        "minK": "min_daily_sma_10",
        "maxK": "max_daily_sma_10",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "20 Day SMA",
        "minK": "min_daily_sma_20",
        "maxK": "max_daily_sma_20",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "50 Day SMA",
        "minK": "min_daily_sma_50",
        "maxK": "max_daily_sma_50",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "200 Day SMA",
        "minK": "min_daily_sma_200",
        "maxK": "max_daily_sma_200",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      }
    ]
  },
  {
    "id": "change_from_daily_sma_%",
    "group": "Change from Daily SMA %",
    "filters": [
      {
        "label": "Change from 5 Day SMA %",
        "minK": "min_dist_daily_sma_5",
        "maxK": "max_dist_daily_sma_5",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 8 Day SMA %",
        "minK": "min_dist_daily_sma_8",
        "maxK": "max_dist_daily_sma_8",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 10 Day SMA %",
        "minK": "min_dist_daily_sma_10",
        "maxK": "max_dist_daily_sma_10",
        "suf": "%",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 20 Day SMA %",
        "minK": "min_dist_daily_sma_20",
        "maxK": "max_dist_daily_sma_20",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 50 Day SMA %",
        "minK": "min_dist_daily_sma_50",
        "maxK": "max_dist_daily_sma_50",
        "suf": "%",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from 200 Day SMA %",
        "minK": "min_dist_daily_sma_200",
        "maxK": "max_dist_daily_sma_200",
        "suf": "%",
        "phMin": "-50",
        "phMax": "50"
      }
    ]
  },
  {
    "id": "change_from_daily_sma_$",
    "group": "Change from Daily SMA $",
    "filters": [
      {
        "label": "Change from 5 Day SMA $",
        "minK": "min_dist_daily_sma_5_dollars",
        "maxK": "max_dist_daily_sma_5_dollars",
        "suf": "$",
        "phMin": "-2",
        "phMax": "2"
      },
      {
        "label": "Change from 8 Day SMA $",
        "minK": "min_dist_daily_sma_8_dollars",
        "maxK": "max_dist_daily_sma_8_dollars",
        "suf": "$",
        "phMin": "-3",
        "phMax": "3"
      },
      {
        "label": "Change from 10 Day SMA $",
        "minK": "min_dist_daily_sma_10_dollars",
        "maxK": "max_dist_daily_sma_10_dollars",
        "suf": "$",
        "phMin": "-5",
        "phMax": "5"
      },
      {
        "label": "Change from 20 Day SMA $",
        "minK": "min_dist_daily_sma_20_dollars",
        "maxK": "max_dist_daily_sma_20_dollars",
        "suf": "$",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change from 50 Day SMA $",
        "minK": "min_dist_daily_sma_50_dollars",
        "maxK": "max_dist_daily_sma_50_dollars",
        "suf": "$",
        "phMin": "-20",
        "phMax": "20"
      },
      {
        "label": "Change from 200 Day SMA $",
        "minK": "min_dist_daily_sma_200_dollars",
        "maxK": "max_dist_daily_sma_200_dollars",
        "suf": "$",
        "phMin": "-50",
        "phMax": "50"
      }
    ]
  },
  {
    "id": "daily_indicators",
    "group": "Daily Indicators",
    "filters": [
      {
        "label": "Daily RSI",
        "minK": "min_daily_rsi",
        "maxK": "max_daily_rsi",
        "suf": "",
        "phMin": "20",
        "phMax": "80"
      },
      {
        "label": "Average Directional Index (Daily)",
        "minK": "min_daily_adx_14",
        "maxK": "max_daily_adx_14",
        "suf": "",
        "phMin": "20",
        "phMax": "50"
      },
      {
        "label": "Directional Indicator (+DI - -DI)",
        "minK": "min_plus_di_minus_di",
        "maxK": "max_plus_di_minus_di",
        "suf": "",
        "phMin": "-30",
        "phMax": "30"
      },
      {
        "label": "52 Week High",
        "minK": "min_high_52w",
        "maxK": "max_high_52w",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "52 Week Low",
        "minK": "min_low_52w",
        "maxK": "max_low_52w",
        "suf": "$",
        "phMin": "",
        "phMax": ""
      },
      {
        "label": "From 52 Week High %",
        "minK": "min_from_52w_high",
        "maxK": "max_from_52w_high",
        "suf": "%",
        "phMin": "-80",
        "phMax": "0"
      },
      {
        "label": "From 52 Week Low %",
        "minK": "min_from_52w_low",
        "maxK": "max_from_52w_low",
        "suf": "%",
        "phMin": "0",
        "phMax": "500"
      }
    ]
  },
  {
    "id": "consolidation_regression",
    "group": "Consolidation & Regression",
    "filters": [
      {
        "label": "Consolidation Days",
        "minK": "min_consolidation_days",
        "maxK": "max_consolidation_days",
        "suf": "",
        "phMin": "2",
        "phMax": "20"
      },
      {
        "label": "Position in Consolidation",
        "minK": "min_pos_in_consolidation",
        "maxK": "max_pos_in_consolidation",
        "suf": "%",
        "phMin": "0",
        "phMax": "100"
      },
      {
        "label": "Range Contraction",
        "minK": "min_range_contraction",
        "maxK": "max_range_contraction",
        "suf": "",
        "phMin": "0.2",
        "phMax": "1"
      },
      {
        "label": "Linear Regression Divergence",
        "minK": "min_lr_divergence_130",
        "maxK": "max_lr_divergence_130",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      },
      {
        "label": "Change Previous Day %",
        "minK": "min_change_prev_day_pct",
        "maxK": "max_change_prev_day_pct",
        "suf": "%",
        "phMin": "-10",
        "phMax": "10"
      }
    ]
  },
  {
    "id": "time_of_day",
    "group": "Time of Day",
    "filters": [
      {
        "label": "Minutes Since Open",
        "minK": "min_minutes_since_open",
        "maxK": "max_minutes_since_open",
        "suf": "min",
        "phMin": "0",
        "phMax": "390"
      }
    ]
  },
  {
    "id": "fundamentals",
    "group": "Fundamentals",
    "filters": [
      {
        "label": "Market Cap",
        "minK": "min_market_cap",
        "maxK": "max_market_cap",
        "suf": "$",
        "units": [
          "K",
          "M",
          "B"
        ],
        "defU": "M",
        "phMin": "50",
        "phMax": "10"
      },
      {
        "label": "Float",
        "minK": "min_float_shares",
        "maxK": "max_float_shares",
        "suf": "",
        "units": [
          "K",
          "M",
          "B"
        ],
        "defU": "M",
        "phMin": "1",
        "phMax": "100"
      },
      {
        "label": "Shares Outstanding",
        "minK": "min_shares_outstanding",
        "maxK": "max_shares_outstanding",
        "suf": "",
        "units": [
          "K",
          "M",
          "B"
        ],
        "defU": "M",
        "phMin": "1",
        "phMax": "500"
      }
    ]
  },
  {
    "id": "prints_trades",
    "group": "Prints / Trades",
    "filters": [
      {
        "label": "Average Number of Prints",
        "minK": "min_trades_today",
        "maxK": "max_trades_today",
        "suf": "",
        "units": [
          "",
          "K"
        ],
        "defU": "",
        "phMin": "100",
        "phMax": "10000"
      },
      {
        "label": "Trades Z-Score",
        "minK": "min_trades_z_score",
        "maxK": "max_trades_z_score",
        "suf": "",
        "phMin": "1",
        "phMax": "5"
      }
    ]
  },
  {
    "id": "index_change",
    "group": "Index Change",
    "filters": [
      {
        "label": "S&P 500 (SPY) Change 5 Minute",
        "minK": "min_spy_chg_5min",
        "maxK": "max_spy_chg_5min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "S&P 500 (SPY) Change 10 Minute",
        "minK": "min_spy_chg_10min",
        "maxK": "max_spy_chg_10min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "S&P 500 (SPY) Change 15 Minute",
        "minK": "min_spy_chg_15min",
        "maxK": "max_spy_chg_15min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "S&P 500 (SPY) Change 30 Minute",
        "minK": "min_spy_chg_30min",
        "maxK": "max_spy_chg_30min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "S&P 500 (SPY) Change Today",
        "minK": "min_spy_chg_today",
        "maxK": "max_spy_chg_today",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "NASDAQ (QQQ) Change 5 Minute",
        "minK": "min_qqq_chg_5min",
        "maxK": "max_qqq_chg_5min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "NASDAQ (QQQ) Change 10 Minute",
        "minK": "min_qqq_chg_10min",
        "maxK": "max_qqq_chg_10min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "NASDAQ (QQQ) Change 15 Minute",
        "minK": "min_qqq_chg_15min",
        "maxK": "max_qqq_chg_15min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "NASDAQ (QQQ) Change 30 Minute",
        "minK": "min_qqq_chg_30min",
        "maxK": "max_qqq_chg_30min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "NASDAQ (QQQ) Change Today",
        "minK": "min_qqq_chg_today",
        "maxK": "max_qqq_chg_today",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "Dow (DIA) Change 5 Minute",
        "minK": "min_dia_chg_5min",
        "maxK": "max_dia_chg_5min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "Dow (DIA) Change 10 Minute",
        "minK": "min_dia_chg_10min",
        "maxK": "max_dia_chg_10min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "Dow (DIA) Change 15 Minute",
        "minK": "min_dia_chg_15min",
        "maxK": "max_dia_chg_15min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "Dow (DIA) Change 30 Minute",
        "minK": "min_dia_chg_30min",
        "maxK": "max_dia_chg_30min",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      },
      {
        "label": "Dow (DIA) Change Today",
        "minK": "min_dia_chg_today",
        "maxK": "max_dia_chg_today",
        "suf": "%",
        "phMin": "-1",
        "phMax": "1"
      }
    ]
  }
] as const;

export const FILTER_LABELS: Record<string, { label: string; suf: string }> = {
  "min_price": {
    "label": "Price >",
    "suf": "$"
  },
  "max_price": {
    "label": "Price <",
    "suf": "$"
  },
  "min_rvol": {
    "label": "Relative Volume >",
    "suf": "x"
  },
  "max_rvol": {
    "label": "Relative Volume <",
    "suf": "x"
  },
  "min_change_percent": {
    "label": "Change from the Close % >",
    "suf": "%"
  },
  "max_change_percent": {
    "label": "Change from the Close % <",
    "suf": "%"
  },
  "min_volume": {
    "label": "Volume Today >",
    "suf": ""
  },
  "max_volume": {
    "label": "Volume Today <",
    "suf": ""
  },
  "min_gap_percent": {
    "label": "Gap % >",
    "suf": "%"
  },
  "max_gap_percent": {
    "label": "Gap % <",
    "suf": "%"
  },
  "min_change_from_open": {
    "label": "Change from the Open % >",
    "suf": "%"
  },
  "max_change_from_open": {
    "label": "Change from the Open % <",
    "suf": "%"
  },
  "min_atr_percent": {
    "label": "Average True Range % >",
    "suf": "%"
  },
  "max_atr_percent": {
    "label": "Average True Range % <",
    "suf": "%"
  },
  "min_rsi": {
    "label": "RSI (1m) >",
    "suf": ""
  },
  "max_rsi": {
    "label": "RSI (1m) <",
    "suf": ""
  },
  "min_market_cap": {
    "label": "Market Cap >",
    "suf": "$"
  },
  "max_market_cap": {
    "label": "Market Cap <",
    "suf": "$"
  },
  "min_float_shares": {
    "label": "Float >",
    "suf": ""
  },
  "max_float_shares": {
    "label": "Float <",
    "suf": ""
  },
  "min_shares_outstanding": {
    "label": "Shares Outstanding >",
    "suf": ""
  },
  "max_shares_outstanding": {
    "label": "Shares Outstanding <",
    "suf": ""
  },
  "min_vol_1min": {
    "label": "Volume 1 Minute >",
    "suf": ""
  },
  "max_vol_1min": {
    "label": "Volume 1 Minute <",
    "suf": ""
  },
  "min_vol_5min": {
    "label": "Volume 5 Minute >",
    "suf": ""
  },
  "max_vol_5min": {
    "label": "Volume 5 Minute <",
    "suf": ""
  },
  "min_vol_10min": {
    "label": "Volume 10 Minute >",
    "suf": ""
  },
  "max_vol_10min": {
    "label": "Volume 10 Minute <",
    "suf": ""
  },
  "min_vol_15min": {
    "label": "Volume 15 Minute >",
    "suf": ""
  },
  "max_vol_15min": {
    "label": "Volume 15 Minute <",
    "suf": ""
  },
  "min_vol_30min": {
    "label": "Volume 30 Minute >",
    "suf": ""
  },
  "max_vol_30min": {
    "label": "Volume 30 Minute <",
    "suf": ""
  },
  "min_vol_1min_pct": {
    "label": "Average Volume 1m % >",
    "suf": "%"
  },
  "max_vol_1min_pct": {
    "label": "Average Volume 1m % <",
    "suf": "%"
  },
  "min_vol_5min_pct": {
    "label": "Average Volume 5m % >",
    "suf": "%"
  },
  "max_vol_5min_pct": {
    "label": "Average Volume 5m % <",
    "suf": "%"
  },
  "min_vol_10min_pct": {
    "label": "Average Volume 10m % >",
    "suf": "%"
  },
  "max_vol_10min_pct": {
    "label": "Average Volume 10m % <",
    "suf": "%"
  },
  "min_vol_15min_pct": {
    "label": "Average Volume 15m % >",
    "suf": "%"
  },
  "max_vol_15min_pct": {
    "label": "Average Volume 15m % <",
    "suf": "%"
  },
  "min_vol_30min_pct": {
    "label": "Average Volume 30m % >",
    "suf": "%"
  },
  "max_vol_30min_pct": {
    "label": "Average Volume 30m % <",
    "suf": "%"
  },
  "min_range_2min": {
    "label": "2 Minute Range $ >",
    "suf": "$"
  },
  "max_range_2min": {
    "label": "2 Minute Range $ <",
    "suf": "$"
  },
  "min_range_5min": {
    "label": "5 Minute Range $ >",
    "suf": "$"
  },
  "max_range_5min": {
    "label": "5 Minute Range $ <",
    "suf": "$"
  },
  "min_range_15min": {
    "label": "15 Minute Range $ >",
    "suf": "$"
  },
  "max_range_15min": {
    "label": "15 Minute Range $ <",
    "suf": "$"
  },
  "min_range_30min": {
    "label": "30 Minute Range $ >",
    "suf": "$"
  },
  "max_range_30min": {
    "label": "30 Minute Range $ <",
    "suf": "$"
  },
  "min_range_60min": {
    "label": "60 Minute Range $ >",
    "suf": "$"
  },
  "max_range_60min": {
    "label": "60 Minute Range $ <",
    "suf": "$"
  },
  "min_range_120min": {
    "label": "120 Minute Range $ >",
    "suf": "$"
  },
  "max_range_120min": {
    "label": "120 Minute Range $ <",
    "suf": "$"
  },
  "min_range_2min_pct": {
    "label": "2 Minute Range % >",
    "suf": "%"
  },
  "max_range_2min_pct": {
    "label": "2 Minute Range % <",
    "suf": "%"
  },
  "min_range_5min_pct": {
    "label": "5 Minute Range % >",
    "suf": "%"
  },
  "max_range_5min_pct": {
    "label": "5 Minute Range % <",
    "suf": "%"
  },
  "min_range_15min_pct": {
    "label": "15 Minute Range % >",
    "suf": "%"
  },
  "max_range_15min_pct": {
    "label": "15 Minute Range % <",
    "suf": "%"
  },
  "min_range_30min_pct": {
    "label": "30 Minute Range % >",
    "suf": "%"
  },
  "max_range_30min_pct": {
    "label": "30 Minute Range % <",
    "suf": "%"
  },
  "min_range_60min_pct": {
    "label": "60 Minute Range % >",
    "suf": "%"
  },
  "max_range_60min_pct": {
    "label": "60 Minute Range % <",
    "suf": "%"
  },
  "min_range_120min_pct": {
    "label": "120 Minute Range % >",
    "suf": "%"
  },
  "max_range_120min_pct": {
    "label": "120 Minute Range % <",
    "suf": "%"
  },
  "min_chg_1min": {
    "label": "Change 1 Minute >",
    "suf": "%"
  },
  "max_chg_1min": {
    "label": "Change 1 Minute <",
    "suf": "%"
  },
  "min_chg_1min_dollars": {
    "label": "Change 1 Minute >",
    "suf": "$"
  },
  "max_chg_1min_dollars": {
    "label": "Change 1 Minute <",
    "suf": "$"
  },
  "min_chg_5min": {
    "label": "Change 5 Minute >",
    "suf": "%"
  },
  "max_chg_5min": {
    "label": "Change 5 Minute <",
    "suf": "%"
  },
  "min_chg_5min_dollars": {
    "label": "Change 5 Minute >",
    "suf": "$"
  },
  "max_chg_5min_dollars": {
    "label": "Change 5 Minute <",
    "suf": "$"
  },
  "min_chg_10min": {
    "label": "Change 10 Minute >",
    "suf": "%"
  },
  "max_chg_10min": {
    "label": "Change 10 Minute <",
    "suf": "%"
  },
  "min_chg_10min_dollars": {
    "label": "Change 10 Minute >",
    "suf": "$"
  },
  "max_chg_10min_dollars": {
    "label": "Change 10 Minute <",
    "suf": "$"
  },
  "min_chg_15min": {
    "label": "Change 15 Minute >",
    "suf": "%"
  },
  "max_chg_15min": {
    "label": "Change 15 Minute <",
    "suf": "%"
  },
  "min_chg_15min_dollars": {
    "label": "Change 15 Minute >",
    "suf": "$"
  },
  "max_chg_15min_dollars": {
    "label": "Change 15 Minute <",
    "suf": "$"
  },
  "min_chg_30min": {
    "label": "Change 30 Minute >",
    "suf": "%"
  },
  "max_chg_30min": {
    "label": "Change 30 Minute <",
    "suf": "%"
  },
  "min_chg_30min_dollars": {
    "label": "Change 30 Minute >",
    "suf": "$"
  },
  "max_chg_30min_dollars": {
    "label": "Change 30 Minute <",
    "suf": "$"
  },
  "min_chg_60min": {
    "label": "Change 60 Minute >",
    "suf": "%"
  },
  "max_chg_60min": {
    "label": "Change 60 Minute <",
    "suf": "%"
  },
  "min_chg_60min_dollars": {
    "label": "Change 60 Minute >",
    "suf": "$"
  },
  "max_chg_60min_dollars": {
    "label": "Change 60 Minute <",
    "suf": "$"
  },
  "min_bid_size": {
    "label": "Bid Size >",
    "suf": ""
  },
  "max_bid_size": {
    "label": "Bid Size <",
    "suf": ""
  },
  "min_ask_size": {
    "label": "Ask Size >",
    "suf": ""
  },
  "max_ask_size": {
    "label": "Ask Size <",
    "suf": ""
  },
  "min_spread": {
    "label": "Spread >",
    "suf": "$"
  },
  "max_spread": {
    "label": "Spread <",
    "suf": "$"
  },
  "min_sma_5": {
    "label": "SMA 5 >",
    "suf": "$"
  },
  "max_sma_5": {
    "label": "SMA 5 <",
    "suf": "$"
  },
  "min_sma_8": {
    "label": "SMA 8 >",
    "suf": "$"
  },
  "max_sma_8": {
    "label": "SMA 8 <",
    "suf": "$"
  },
  "min_sma_20": {
    "label": "SMA 20 >",
    "suf": "$"
  },
  "max_sma_20": {
    "label": "SMA 20 <",
    "suf": "$"
  },
  "min_sma_50": {
    "label": "SMA 50 >",
    "suf": "$"
  },
  "max_sma_50": {
    "label": "SMA 50 <",
    "suf": "$"
  },
  "min_sma_200": {
    "label": "SMA 200 >",
    "suf": "$"
  },
  "max_sma_200": {
    "label": "SMA 200 <",
    "suf": "$"
  },
  "min_ema_20": {
    "label": "EMA 20 >",
    "suf": "$"
  },
  "max_ema_20": {
    "label": "EMA 20 <",
    "suf": "$"
  },
  "min_ema_50": {
    "label": "EMA 50 >",
    "suf": "$"
  },
  "max_ema_50": {
    "label": "EMA 50 <",
    "suf": "$"
  },
  "min_macd_line": {
    "label": "MACD Line >",
    "suf": ""
  },
  "max_macd_line": {
    "label": "MACD Line <",
    "suf": ""
  },
  "min_macd_hist": {
    "label": "MACD Histogram >",
    "suf": ""
  },
  "max_macd_hist": {
    "label": "MACD Histogram <",
    "suf": ""
  },
  "min_stoch_k": {
    "label": "Stochastic %K >",
    "suf": ""
  },
  "max_stoch_k": {
    "label": "Stochastic %K <",
    "suf": ""
  },
  "min_stoch_d": {
    "label": "Stochastic %D >",
    "suf": ""
  },
  "max_stoch_d": {
    "label": "Stochastic %D <",
    "suf": ""
  },
  "min_adx_14": {
    "label": "ADX (Intraday) >",
    "suf": ""
  },
  "max_adx_14": {
    "label": "ADX (Intraday) <",
    "suf": ""
  },
  "min_bb_upper": {
    "label": "Bollinger Upper >",
    "suf": "$"
  },
  "max_bb_upper": {
    "label": "Bollinger Upper <",
    "suf": "$"
  },
  "min_bb_lower": {
    "label": "Bollinger Lower >",
    "suf": "$"
  },
  "max_bb_lower": {
    "label": "Bollinger Lower <",
    "suf": "$"
  },
  "min_daily_sma_5": {
    "label": "5 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_5": {
    "label": "5 Day SMA <",
    "suf": "$"
  },
  "min_daily_sma_8": {
    "label": "8 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_8": {
    "label": "8 Day SMA <",
    "suf": "$"
  },
  "min_daily_sma_10": {
    "label": "10 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_10": {
    "label": "10 Day SMA <",
    "suf": "$"
  },
  "min_daily_sma_20": {
    "label": "20 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_20": {
    "label": "20 Day SMA <",
    "suf": "$"
  },
  "min_daily_sma_50": {
    "label": "50 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_50": {
    "label": "50 Day SMA <",
    "suf": "$"
  },
  "min_daily_sma_200": {
    "label": "200 Day SMA >",
    "suf": "$"
  },
  "max_daily_sma_200": {
    "label": "200 Day SMA <",
    "suf": "$"
  },
  "min_daily_rsi": {
    "label": "Daily RSI >",
    "suf": ""
  },
  "max_daily_rsi": {
    "label": "Daily RSI <",
    "suf": ""
  },
  "min_high_52w": {
    "label": "52 Week High >",
    "suf": "$"
  },
  "max_high_52w": {
    "label": "52 Week High <",
    "suf": "$"
  },
  "min_low_52w": {
    "label": "52 Week Low >",
    "suf": "$"
  },
  "max_low_52w": {
    "label": "52 Week Low <",
    "suf": "$"
  },
  "min_trades_today": {
    "label": "Average Number of Prints >",
    "suf": ""
  },
  "max_trades_today": {
    "label": "Average Number of Prints <",
    "suf": ""
  },
  "min_trades_z_score": {
    "label": "Trades Z-Score >",
    "suf": ""
  },
  "max_trades_z_score": {
    "label": "Trades Z-Score <",
    "suf": ""
  },
  "min_vwap": {
    "label": "VWAP >",
    "suf": "$"
  },
  "max_vwap": {
    "label": "VWAP <",
    "suf": "$"
  },
  "min_dollar_volume": {
    "label": "Dollar Volume >",
    "suf": "$"
  },
  "max_dollar_volume": {
    "label": "Dollar Volume <",
    "suf": "$"
  },
  "min_todays_range": {
    "label": "Today's Range $ >",
    "suf": "$"
  },
  "max_todays_range": {
    "label": "Today's Range $ <",
    "suf": "$"
  },
  "min_todays_range_pct": {
    "label": "Today's Range % >",
    "suf": "%"
  },
  "max_todays_range_pct": {
    "label": "Today's Range % <",
    "suf": "%"
  },
  "min_bid_ask_ratio": {
    "label": "Bid / Ask Ratio >",
    "suf": ""
  },
  "max_bid_ask_ratio": {
    "label": "Bid / Ask Ratio <",
    "suf": ""
  },
  "min_float_turnover": {
    "label": "Float Turnover >",
    "suf": "x"
  },
  "max_float_turnover": {
    "label": "Float Turnover <",
    "suf": "x"
  },
  "min_dist_from_vwap": {
    "label": "Distance from VWAP >",
    "suf": "%"
  },
  "max_dist_from_vwap": {
    "label": "Distance from VWAP <",
    "suf": "%"
  },
  "min_dist_sma_5": {
    "label": "Change from SMA 5 (Intraday) >",
    "suf": "%"
  },
  "max_dist_sma_5": {
    "label": "Change from SMA 5 (Intraday) <",
    "suf": "%"
  },
  "min_dist_sma_8": {
    "label": "Change from SMA 8 (Intraday) >",
    "suf": "%"
  },
  "max_dist_sma_8": {
    "label": "Change from SMA 8 (Intraday) <",
    "suf": "%"
  },
  "min_dist_sma_20": {
    "label": "Change from SMA 20 (Intraday) >",
    "suf": "%"
  },
  "max_dist_sma_20": {
    "label": "Change from SMA 20 (Intraday) <",
    "suf": "%"
  },
  "min_dist_sma_50": {
    "label": "Change from SMA 50 (Intraday) >",
    "suf": "%"
  },
  "max_dist_sma_50": {
    "label": "Change from SMA 50 (Intraday) <",
    "suf": "%"
  },
  "min_dist_sma_200": {
    "label": "Change from SMA 200 (Intraday) >",
    "suf": "%"
  },
  "max_dist_sma_200": {
    "label": "Change from SMA 200 (Intraday) <",
    "suf": "%"
  },
  "min_pos_in_range": {
    "label": "Position in Range (Today) >",
    "suf": "%"
  },
  "max_pos_in_range": {
    "label": "Position in Range (Today) <",
    "suf": "%"
  },
  "min_below_high": {
    "label": "Below High >",
    "suf": "$"
  },
  "max_below_high": {
    "label": "Below High <",
    "suf": "$"
  },
  "min_above_low": {
    "label": "Above Low >",
    "suf": "$"
  },
  "max_above_low": {
    "label": "Above Low <",
    "suf": "$"
  },
  "min_pos_of_open": {
    "label": "Position of Open >",
    "suf": "%"
  },
  "max_pos_of_open": {
    "label": "Position of Open <",
    "suf": "%"
  },
  "min_prev_day_volume": {
    "label": "Previous Day Volume >",
    "suf": ""
  },
  "max_prev_day_volume": {
    "label": "Previous Day Volume <",
    "suf": ""
  },
  "min_change_1d": {
    "label": "Change Previous Day >",
    "suf": "%"
  },
  "max_change_1d": {
    "label": "Change Previous Day <",
    "suf": "%"
  },
  "min_change_3d": {
    "label": "Change in 3 Days >",
    "suf": "%"
  },
  "max_change_3d": {
    "label": "Change in 3 Days <",
    "suf": "%"
  },
  "min_change_5d": {
    "label": "Change in 5 Days >",
    "suf": "%"
  },
  "max_change_5d": {
    "label": "Change in 5 Days <",
    "suf": "%"
  },
  "min_change_10d": {
    "label": "Change in 10 Days >",
    "suf": "%"
  },
  "max_change_10d": {
    "label": "Change in 10 Days <",
    "suf": "%"
  },
  "min_change_20d": {
    "label": "Change in 20 Days >",
    "suf": "%"
  },
  "max_change_20d": {
    "label": "Change in 20 Days <",
    "suf": "%"
  },
  "min_avg_volume_5d": {
    "label": "Average Daily Volume (5D) >",
    "suf": ""
  },
  "max_avg_volume_5d": {
    "label": "Average Daily Volume (5D) <",
    "suf": ""
  },
  "min_avg_volume_10d": {
    "label": "Average Daily Volume (10D) >",
    "suf": ""
  },
  "max_avg_volume_10d": {
    "label": "Average Daily Volume (10D) <",
    "suf": ""
  },
  "min_avg_volume_20d": {
    "label": "Average Daily Volume (20D) >",
    "suf": ""
  },
  "max_avg_volume_20d": {
    "label": "Average Daily Volume (20D) <",
    "suf": ""
  },
  "min_dist_daily_sma_20": {
    "label": "Change from 20 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_20": {
    "label": "Change from 20 Day SMA % <",
    "suf": "%"
  },
  "min_dist_daily_sma_50": {
    "label": "Change from 50 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_50": {
    "label": "Change from 50 Day SMA % <",
    "suf": "%"
  },
  "min_from_52w_high": {
    "label": "From 52 Week High % >",
    "suf": "%"
  },
  "max_from_52w_high": {
    "label": "From 52 Week High % <",
    "suf": "%"
  },
  "min_from_52w_low": {
    "label": "From 52 Week Low % >",
    "suf": "%"
  },
  "max_from_52w_low": {
    "label": "From 52 Week Low % <",
    "suf": "%"
  },
  "min_daily_adx_14": {
    "label": "Average Directional Index (Daily) >",
    "suf": ""
  },
  "max_daily_adx_14": {
    "label": "Average Directional Index (Daily) <",
    "suf": ""
  },
  "min_daily_atr_percent": {
    "label": "Daily ATR % >",
    "suf": "%"
  },
  "max_daily_atr_percent": {
    "label": "Daily ATR % <",
    "suf": "%"
  },
  "min_daily_bb_position": {
    "label": "Position in Bollinger Bands (Daily) >",
    "suf": "%"
  },
  "max_daily_bb_position": {
    "label": "Position in Bollinger Bands (Daily) <",
    "suf": "%"
  },
  "min_volume_today_pct": {
    "label": "Volume Today % >",
    "suf": "%"
  },
  "max_volume_today_pct": {
    "label": "Volume Today % <",
    "suf": "%"
  },
  "min_minute_volume": {
    "label": "Minute Volume >",
    "suf": ""
  },
  "max_minute_volume": {
    "label": "Minute Volume <",
    "suf": ""
  },
  "min_price_from_high": {
    "label": "From High % >",
    "suf": "%"
  },
  "max_price_from_high": {
    "label": "From High % <",
    "suf": "%"
  },
  "min_price_from_low": {
    "label": "From Low % >",
    "suf": "%"
  },
  "max_price_from_low": {
    "label": "From Low % <",
    "suf": "%"
  },
  "min_price_from_intraday_high": {
    "label": "From Intraday High % >",
    "suf": "%"
  },
  "max_price_from_intraday_high": {
    "label": "From Intraday High % <",
    "suf": "%"
  },
  "min_price_from_intraday_low": {
    "label": "From Intraday Low % >",
    "suf": "%"
  },
  "max_price_from_intraday_low": {
    "label": "From Intraday Low % <",
    "suf": "%"
  },
  "min_volume_yesterday_pct": {
    "label": "Volume Yesterday % >",
    "suf": "%"
  },
  "max_volume_yesterday_pct": {
    "label": "Volume Yesterday % <",
    "suf": "%"
  },
  "min_change_from_open_dollars": {
    "label": "Change from the Open $ >",
    "suf": "$"
  },
  "max_change_from_open_dollars": {
    "label": "Change from the Open $ <",
    "suf": "$"
  },
  "min_distance_from_nbbo": {
    "label": "Distance from Inside Market >",
    "suf": "%"
  },
  "max_distance_from_nbbo": {
    "label": "Distance from Inside Market <",
    "suf": "%"
  },
  "min_premarket_change_percent": {
    "label": "Change Pre-Market % >",
    "suf": "%"
  },
  "max_premarket_change_percent": {
    "label": "Change Pre-Market % <",
    "suf": "%"
  },
  "min_postmarket_change_percent": {
    "label": "Change Post-Market % >",
    "suf": "%"
  },
  "max_postmarket_change_percent": {
    "label": "Change Post-Market % <",
    "suf": "%"
  },
  "min_postmarket_volume": {
    "label": "Post-Market Volume >",
    "suf": ""
  },
  "max_postmarket_volume": {
    "label": "Post-Market Volume <",
    "suf": ""
  },
  "min_avg_volume_3m": {
    "label": "Average Daily Volume (3M) >",
    "suf": ""
  },
  "max_avg_volume_3m": {
    "label": "Average Daily Volume (3M) <",
    "suf": ""
  },
  "min_atr": {
    "label": "Average True Range >",
    "suf": "$"
  },
  "max_atr": {
    "label": "Average True Range <",
    "suf": "$"
  },
  "min_dist_pivot": {
    "label": "Distance from Pivot >",
    "suf": "%"
  },
  "max_dist_pivot": {
    "label": "Distance from Pivot <",
    "suf": "%"
  },
  "min_dist_pivot_r1": {
    "label": "Distance from Pivot R1 >",
    "suf": "%"
  },
  "max_dist_pivot_r1": {
    "label": "Distance from Pivot R1 <",
    "suf": "%"
  },
  "min_dist_pivot_s1": {
    "label": "Distance from Pivot S1 >",
    "suf": "%"
  },
  "max_dist_pivot_s1": {
    "label": "Distance from Pivot S1 <",
    "suf": "%"
  },
  "min_dist_pivot_r2": {
    "label": "Distance from Pivot R2 >",
    "suf": "%"
  },
  "max_dist_pivot_r2": {
    "label": "Distance from Pivot R2 <",
    "suf": "%"
  },
  "min_dist_pivot_s2": {
    "label": "Distance from Pivot S2 >",
    "suf": "%"
  },
  "max_dist_pivot_s2": {
    "label": "Distance from Pivot S2 <",
    "suf": "%"
  },
  "min_consecutive_candles": {
    "label": "Consecutive Candles (1m) >",
    "suf": ""
  },
  "max_consecutive_candles": {
    "label": "Consecutive Candles (1m) <",
    "suf": ""
  },
  "min_consecutive_candles_2m": {
    "label": "Consecutive Candles (2m) >",
    "suf": ""
  },
  "max_consecutive_candles_2m": {
    "label": "Consecutive Candles (2m) <",
    "suf": ""
  },
  "min_consecutive_candles_5m": {
    "label": "Consecutive Candles (5m) >",
    "suf": ""
  },
  "max_consecutive_candles_5m": {
    "label": "Consecutive Candles (5m) <",
    "suf": ""
  },
  "min_consecutive_candles_10m": {
    "label": "Consecutive Candles (10m) >",
    "suf": ""
  },
  "max_consecutive_candles_10m": {
    "label": "Consecutive Candles (10m) <",
    "suf": ""
  },
  "min_consecutive_candles_15m": {
    "label": "Consecutive Candles (15m) >",
    "suf": ""
  },
  "max_consecutive_candles_15m": {
    "label": "Consecutive Candles (15m) <",
    "suf": ""
  },
  "min_consecutive_candles_30m": {
    "label": "Consecutive Candles (30m) >",
    "suf": ""
  },
  "max_consecutive_candles_30m": {
    "label": "Consecutive Candles (30m) <",
    "suf": ""
  },
  "min_consecutive_candles_60m": {
    "label": "Consecutive Candles (60m) >",
    "suf": ""
  },
  "max_consecutive_candles_60m": {
    "label": "Consecutive Candles (60m) <",
    "suf": ""
  },
  "min_pos_in_range_5m": {
    "label": "Position in 5 Minute Range >",
    "suf": "%"
  },
  "max_pos_in_range_5m": {
    "label": "Position in 5 Minute Range <",
    "suf": "%"
  },
  "min_pos_in_range_15m": {
    "label": "Position in 15 Minute Range >",
    "suf": "%"
  },
  "max_pos_in_range_15m": {
    "label": "Position in 15 Minute Range <",
    "suf": "%"
  },
  "min_pos_in_range_30m": {
    "label": "Position in 30 Minute Range >",
    "suf": "%"
  },
  "max_pos_in_range_30m": {
    "label": "Position in 30 Minute Range <",
    "suf": "%"
  },
  "min_pos_in_range_60m": {
    "label": "Position in 60 Minute Range >",
    "suf": "%"
  },
  "max_pos_in_range_60m": {
    "label": "Position in 60 Minute Range <",
    "suf": "%"
  },
  "min_rsi_2m": {
    "label": "2 Minute RSI >",
    "suf": ""
  },
  "max_rsi_2m": {
    "label": "2 Minute RSI <",
    "suf": ""
  },
  "min_rsi_5m": {
    "label": "5 Minute RSI >",
    "suf": ""
  },
  "max_rsi_5m": {
    "label": "5 Minute RSI <",
    "suf": ""
  },
  "min_rsi_15m": {
    "label": "15 Minute RSI >",
    "suf": ""
  },
  "max_rsi_15m": {
    "label": "15 Minute RSI <",
    "suf": ""
  },
  "min_rsi_60m": {
    "label": "60 Minute RSI >",
    "suf": ""
  },
  "max_rsi_60m": {
    "label": "60 Minute RSI <",
    "suf": ""
  },
  "min_bb_position_1m": {
    "label": "Position in Bollinger Bands (1m) >",
    "suf": "%"
  },
  "max_bb_position_1m": {
    "label": "Position in Bollinger Bands (1m) <",
    "suf": "%"
  },
  "min_bb_position_5m": {
    "label": "Position in Bollinger Bands (5m) >",
    "suf": "%"
  },
  "max_bb_position_5m": {
    "label": "Position in Bollinger Bands (5m) <",
    "suf": "%"
  },
  "min_bb_position_15m": {
    "label": "Position in Bollinger Bands (15m) >",
    "suf": "%"
  },
  "max_bb_position_15m": {
    "label": "Position in Bollinger Bands (15m) <",
    "suf": "%"
  },
  "min_bb_position_60m": {
    "label": "Position in Bollinger Bands (60m) >",
    "suf": "%"
  },
  "max_bb_position_60m": {
    "label": "Position in Bollinger Bands (60m) <",
    "suf": "%"
  },
  "min_chg_2min": {
    "label": "Change 2 Minute >",
    "suf": "%"
  },
  "max_chg_2min": {
    "label": "Change 2 Minute <",
    "suf": "%"
  },
  "min_chg_120min": {
    "label": "Change 120 Minute >",
    "suf": "%"
  },
  "max_chg_120min": {
    "label": "Change 120 Minute <",
    "suf": "%"
  },
  "min_chg_2min_dollars": {
    "label": "Change 2 Minute >",
    "suf": "$"
  },
  "max_chg_2min_dollars": {
    "label": "Change 2 Minute <",
    "suf": "$"
  },
  "min_chg_120min_dollars": {
    "label": "Change 120 Minute >",
    "suf": "$"
  },
  "max_chg_120min_dollars": {
    "label": "Change 120 Minute <",
    "suf": "$"
  },
  "min_gap_dollars": {
    "label": "Gap $ >",
    "suf": "$"
  },
  "max_gap_dollars": {
    "label": "Gap $ <",
    "suf": "$"
  },
  "min_gap_ratio": {
    "label": "Gap (ATR) >",
    "suf": "x"
  },
  "max_gap_ratio": {
    "label": "Gap (ATR) <",
    "suf": "x"
  },
  "min_change_from_close_dollars": {
    "label": "Change from the Close $ >",
    "suf": "$"
  },
  "max_change_from_close_dollars": {
    "label": "Change from the Close $ <",
    "suf": "$"
  },
  "min_change_from_close_ratio": {
    "label": "Change from the Close (ATR) >",
    "suf": "x"
  },
  "max_change_from_close_ratio": {
    "label": "Change from the Close (ATR) <",
    "suf": "x"
  },
  "min_change_from_open_ratio": {
    "label": "Change from the Open (ATR) >",
    "suf": "x"
  },
  "max_change_from_open_ratio": {
    "label": "Change from the Open (ATR) <",
    "suf": "x"
  },
  "min_postmarket_change_dollars": {
    "label": "Change Post-Market $ >",
    "suf": "$"
  },
  "max_postmarket_change_dollars": {
    "label": "Change Post-Market $ <",
    "suf": "$"
  },
  "min_decimal": {
    "label": "Decimal >",
    "suf": ""
  },
  "max_decimal": {
    "label": "Decimal <",
    "suf": ""
  },
  "min_pos_in_prev_day_range": {
    "label": "Position in Previous Day's Range >",
    "suf": "%"
  },
  "max_pos_in_prev_day_range": {
    "label": "Position in Previous Day's Range <",
    "suf": "%"
  },
  "min_plus_di_minus_di": {
    "label": "Directional Indicator (+DI - -DI) >",
    "suf": ""
  },
  "max_plus_di_minus_di": {
    "label": "Directional Indicator (+DI - -DI) <",
    "suf": ""
  },
  "min_bb_std_dev": {
    "label": "Standard Deviation (Bollinger) >",
    "suf": "$"
  },
  "max_bb_std_dev": {
    "label": "Standard Deviation (Bollinger) <",
    "suf": "$"
  },
  "min_dist_sma_5_2m": {
    "label": "Change from 5 Period SMA (2m) >",
    "suf": "%"
  },
  "max_dist_sma_5_2m": {
    "label": "Change from 5 Period SMA (2m) <",
    "suf": "%"
  },
  "min_dist_sma_5_5m": {
    "label": "Change from 5 Period SMA (5m) >",
    "suf": "%"
  },
  "max_dist_sma_5_5m": {
    "label": "Change from 5 Period SMA (5m) <",
    "suf": "%"
  },
  "min_dist_sma_5_15m": {
    "label": "Change from 5 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_5_15m": {
    "label": "Change from 5 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_8_2m": {
    "label": "Change from 8 Period SMA (2m) >",
    "suf": "%"
  },
  "max_dist_sma_8_2m": {
    "label": "Change from 8 Period SMA (2m) <",
    "suf": "%"
  },
  "min_dist_sma_8_5m": {
    "label": "Change from 8 Period SMA (5m) >",
    "suf": "%"
  },
  "max_dist_sma_8_5m": {
    "label": "Change from 8 Period SMA (5m) <",
    "suf": "%"
  },
  "min_dist_sma_8_15m": {
    "label": "Change from 8 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_8_15m": {
    "label": "Change from 8 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_8_60m": {
    "label": "Change from 8 Period SMA (60m) >",
    "suf": "%"
  },
  "max_dist_sma_8_60m": {
    "label": "Change from 8 Period SMA (60m) <",
    "suf": "%"
  },
  "min_dist_sma_20_2m": {
    "label": "Change from 20 Period SMA (2m) >",
    "suf": "%"
  },
  "max_dist_sma_20_2m": {
    "label": "Change from 20 Period SMA (2m) <",
    "suf": "%"
  },
  "min_dist_sma_20_5m": {
    "label": "Change from 20 Period SMA (5m) >",
    "suf": "%"
  },
  "max_dist_sma_20_5m": {
    "label": "Change from 20 Period SMA (5m) <",
    "suf": "%"
  },
  "min_dist_sma_20_15m": {
    "label": "Change from 20 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_20_15m": {
    "label": "Change from 20 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_20_60m": {
    "label": "Change from 20 Period SMA (60m) >",
    "suf": "%"
  },
  "max_dist_sma_20_60m": {
    "label": "Change from 20 Period SMA (60m) <",
    "suf": "%"
  },
  "min_sma_8_vs_20_2m": {
    "label": "8 vs. 20 Period SMA (2m) >",
    "suf": "%"
  },
  "max_sma_8_vs_20_2m": {
    "label": "8 vs. 20 Period SMA (2m) <",
    "suf": "%"
  },
  "min_sma_8_vs_20_5m": {
    "label": "8 vs. 20 Period SMA (5m) >",
    "suf": "%"
  },
  "max_sma_8_vs_20_5m": {
    "label": "8 vs. 20 Period SMA (5m) <",
    "suf": "%"
  },
  "min_sma_8_vs_20_15m": {
    "label": "8 vs. 20 Period SMA (15m) >",
    "suf": "%"
  },
  "max_sma_8_vs_20_15m": {
    "label": "8 vs. 20 Period SMA (15m) <",
    "suf": "%"
  },
  "min_sma_8_vs_20_60m": {
    "label": "8 vs. 20 Period SMA (60m) >",
    "suf": "%"
  },
  "max_sma_8_vs_20_60m": {
    "label": "8 vs. 20 Period SMA (60m) <",
    "suf": "%"
  },
  "min_dist_daily_sma_200": {
    "label": "Change from 200 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_200": {
    "label": "Change from 200 Day SMA % <",
    "suf": "%"
  },
  "min_range_5d": {
    "label": "5 Day Range $ >",
    "suf": "$"
  },
  "max_range_5d": {
    "label": "5 Day Range $ <",
    "suf": "$"
  },
  "min_range_10d": {
    "label": "10 Day Range $ >",
    "suf": "$"
  },
  "max_range_10d": {
    "label": "10 Day Range $ <",
    "suf": "$"
  },
  "min_range_20d": {
    "label": "20 Day Range $ >",
    "suf": "$"
  },
  "max_range_20d": {
    "label": "20 Day Range $ <",
    "suf": "$"
  },
  "min_pos_in_5d_range": {
    "label": "Position in 5 Day Range >",
    "suf": "%"
  },
  "max_pos_in_5d_range": {
    "label": "Position in 5 Day Range <",
    "suf": "%"
  },
  "min_pos_in_10d_range": {
    "label": "Position in 10 Day Range >",
    "suf": "%"
  },
  "max_pos_in_10d_range": {
    "label": "Position in 10 Day Range <",
    "suf": "%"
  },
  "min_pos_in_20d_range": {
    "label": "Position in 20 Day Range >",
    "suf": "%"
  },
  "max_pos_in_20d_range": {
    "label": "Position in 20 Day Range <",
    "suf": "%"
  },
  "min_pos_in_52w_range": {
    "label": "Position in 52 Week Range >",
    "suf": "%"
  },
  "max_pos_in_52w_range": {
    "label": "Position in 52 Week Range <",
    "suf": "%"
  },
  "min_range_5d_pct": {
    "label": "5 Day Range % >",
    "suf": "%"
  },
  "max_range_5d_pct": {
    "label": "5 Day Range % <",
    "suf": "%"
  },
  "min_range_10d_pct": {
    "label": "10 Day Range % >",
    "suf": "%"
  },
  "max_range_10d_pct": {
    "label": "10 Day Range % <",
    "suf": "%"
  },
  "min_range_20d_pct": {
    "label": "20 Day Range % >",
    "suf": "%"
  },
  "max_range_20d_pct": {
    "label": "20 Day Range % <",
    "suf": "%"
  },
  "min_change_5d_dollars": {
    "label": "Change in 5 Days $ >",
    "suf": "$"
  },
  "max_change_5d_dollars": {
    "label": "Change in 5 Days $ <",
    "suf": "$"
  },
  "min_change_10d_dollars": {
    "label": "Change in 10 Days $ >",
    "suf": "$"
  },
  "max_change_10d_dollars": {
    "label": "Change in 10 Days $ <",
    "suf": "$"
  },
  "min_change_20d_dollars": {
    "label": "Change in 20 Days $ >",
    "suf": "$"
  },
  "max_change_20d_dollars": {
    "label": "Change in 20 Days $ <",
    "suf": "$"
  },
  "min_change_from_open_weighted": {
    "label": "Change from the Open Weighted >",
    "suf": ""
  },
  "max_change_from_open_weighted": {
    "label": "Change from the Open Weighted <",
    "suf": ""
  },
  "min_dist_daily_sma_5_dollars": {
    "label": "Change from 5 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_5_dollars": {
    "label": "Change from 5 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_8_dollars": {
    "label": "Change from 8 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_8_dollars": {
    "label": "Change from 8 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_10_dollars": {
    "label": "Change from 10 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_10_dollars": {
    "label": "Change from 10 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_20_dollars": {
    "label": "Change from 20 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_20_dollars": {
    "label": "Change from 20 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_50_dollars": {
    "label": "Change from 50 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_50_dollars": {
    "label": "Change from 50 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_200_dollars": {
    "label": "Change from 200 Day SMA $ >",
    "suf": "$"
  },
  "max_dist_daily_sma_200_dollars": {
    "label": "Change from 200 Day SMA $ <",
    "suf": "$"
  },
  "min_dist_daily_sma_5": {
    "label": "Change from 5 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_5": {
    "label": "Change from 5 Day SMA % <",
    "suf": "%"
  },
  "min_dist_daily_sma_8": {
    "label": "Change from 8 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_8": {
    "label": "Change from 8 Day SMA % <",
    "suf": "%"
  },
  "min_dist_daily_sma_10": {
    "label": "Change from 10 Day SMA % >",
    "suf": "%"
  },
  "max_dist_daily_sma_10": {
    "label": "Change from 10 Day SMA % <",
    "suf": "%"
  },
  "min_sma_20_vs_200_2m": {
    "label": "20 vs. 200 Period SMA (2m) >",
    "suf": "%"
  },
  "max_sma_20_vs_200_2m": {
    "label": "20 vs. 200 Period SMA (2m) <",
    "suf": "%"
  },
  "min_sma_20_vs_200_5m": {
    "label": "20 vs. 200 Period SMA (5m) >",
    "suf": "%"
  },
  "max_sma_20_vs_200_5m": {
    "label": "20 vs. 200 Period SMA (5m) <",
    "suf": "%"
  },
  "min_sma_20_vs_200_15m": {
    "label": "20 vs. 200 Period SMA (15m) >",
    "suf": "%"
  },
  "max_sma_20_vs_200_15m": {
    "label": "20 vs. 200 Period SMA (15m) <",
    "suf": "%"
  },
  "min_sma_20_vs_200_60m": {
    "label": "20 vs. 200 Period SMA (60m) >",
    "suf": "%"
  },
  "max_sma_20_vs_200_60m": {
    "label": "20 vs. 200 Period SMA (60m) <",
    "suf": "%"
  },
  "min_change_1y": {
    "label": "Change in 1 Year % >",
    "suf": "%"
  },
  "max_change_1y": {
    "label": "Change in 1 Year % <",
    "suf": "%"
  },
  "min_change_1y_dollars": {
    "label": "Change in 1 Year $ >",
    "suf": "$"
  },
  "max_change_1y_dollars": {
    "label": "Change in 1 Year $ <",
    "suf": "$"
  },
  "min_change_ytd": {
    "label": "Change Since January 1 % >",
    "suf": "%"
  },
  "max_change_ytd": {
    "label": "Change Since January 1 % <",
    "suf": "%"
  },
  "min_change_ytd_dollars": {
    "label": "Change Since January 1 $ >",
    "suf": "$"
  },
  "max_change_ytd_dollars": {
    "label": "Change Since January 1 $ <",
    "suf": "$"
  },
  "min_yearly_std_dev": {
    "label": "Yearly Standard Deviation >",
    "suf": "$"
  },
  "max_yearly_std_dev": {
    "label": "Yearly Standard Deviation <",
    "suf": "$"
  },
  "min_consecutive_days_up": {
    "label": "Consecutive Days Up/Down >",
    "suf": ""
  },
  "max_consecutive_days_up": {
    "label": "Consecutive Days Up/Down <",
    "suf": ""
  },
  "min_dist_sma_10_2m": {
    "label": "Change from 10 Period SMA (2m) >",
    "suf": "%"
  },
  "max_dist_sma_10_2m": {
    "label": "Change from 10 Period SMA (2m) <",
    "suf": "%"
  },
  "min_dist_sma_10_5m": {
    "label": "Change from 10 Period SMA (5m) >",
    "suf": "%"
  },
  "max_dist_sma_10_5m": {
    "label": "Change from 10 Period SMA (5m) <",
    "suf": "%"
  },
  "min_dist_sma_10_15m": {
    "label": "Change from 10 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_10_15m": {
    "label": "Change from 10 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_10_60m": {
    "label": "Change from 10 Period SMA (60m) >",
    "suf": "%"
  },
  "max_dist_sma_10_60m": {
    "label": "Change from 10 Period SMA (60m) <",
    "suf": "%"
  },
  "min_dist_sma_130_15m": {
    "label": "Change from 130 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_130_15m": {
    "label": "Change from 130 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_200_2m": {
    "label": "Change from 200 Period SMA (2m) >",
    "suf": "%"
  },
  "max_dist_sma_200_2m": {
    "label": "Change from 200 Period SMA (2m) <",
    "suf": "%"
  },
  "min_dist_sma_200_5m": {
    "label": "Change from 200 Period SMA (5m) >",
    "suf": "%"
  },
  "max_dist_sma_200_5m": {
    "label": "Change from 200 Period SMA (5m) <",
    "suf": "%"
  },
  "min_dist_sma_200_15m": {
    "label": "Change from 200 Period SMA (15m) >",
    "suf": "%"
  },
  "max_dist_sma_200_15m": {
    "label": "Change from 200 Period SMA (15m) <",
    "suf": "%"
  },
  "min_dist_sma_200_60m": {
    "label": "Change from 200 Period SMA (60m) >",
    "suf": "%"
  },
  "max_dist_sma_200_60m": {
    "label": "Change from 200 Period SMA (60m) <",
    "suf": "%"
  },
  "min_dist_sma_5_60m": {
    "label": "Change from 5 Period SMA (60m) >",
    "suf": "%"
  },
  "max_dist_sma_5_60m": {
    "label": "Change from 5 Period SMA (60m) <",
    "suf": "%"
  },
  "min_pos_in_3m_range": {
    "label": "Position in 3 Month Range >",
    "suf": "%"
  },
  "max_pos_in_3m_range": {
    "label": "Position in 3 Month Range <",
    "suf": "%"
  },
  "min_pos_in_6m_range": {
    "label": "Position in 6 Month Range >",
    "suf": "%"
  },
  "max_pos_in_6m_range": {
    "label": "Position in 6 Month Range <",
    "suf": "%"
  },
  "min_pos_in_9m_range": {
    "label": "Position in 9 Month Range >",
    "suf": "%"
  },
  "max_pos_in_9m_range": {
    "label": "Position in 9 Month Range <",
    "suf": "%"
  },
  "min_pos_in_2y_range": {
    "label": "Position in 2 Year Range >",
    "suf": "%"
  },
  "max_pos_in_2y_range": {
    "label": "Position in 2 Year Range <",
    "suf": "%"
  },
  "min_pos_in_lifetime_range": {
    "label": "Position in Lifetime Range >",
    "suf": "%"
  },
  "max_pos_in_lifetime_range": {
    "label": "Position in Lifetime Range <",
    "suf": "%"
  },
  "min_below_premarket_high": {
    "label": "Below Pre-Market High >",
    "suf": "$"
  },
  "max_below_premarket_high": {
    "label": "Below Pre-Market High <",
    "suf": "$"
  },
  "min_above_premarket_low": {
    "label": "Above Pre-Market Low >",
    "suf": "$"
  },
  "max_above_premarket_low": {
    "label": "Above Pre-Market Low <",
    "suf": "$"
  },
  "min_pos_in_premarket_range": {
    "label": "Position in Pre-Market Range >",
    "suf": "%"
  },
  "max_pos_in_premarket_range": {
    "label": "Position in Pre-Market Range <",
    "suf": "%"
  },
  "min_consolidation_days": {
    "label": "Consolidation Days >",
    "suf": ""
  },
  "max_consolidation_days": {
    "label": "Consolidation Days <",
    "suf": ""
  },
  "min_pos_in_consolidation": {
    "label": "Position in Consolidation >",
    "suf": "%"
  },
  "max_pos_in_consolidation": {
    "label": "Position in Consolidation <",
    "suf": "%"
  },
  "min_range_contraction": {
    "label": "Range Contraction >",
    "suf": ""
  },
  "max_range_contraction": {
    "label": "Range Contraction <",
    "suf": ""
  },
  "min_lr_divergence_130": {
    "label": "Linear Regression Divergence >",
    "suf": "%"
  },
  "max_lr_divergence_130": {
    "label": "Linear Regression Divergence <",
    "suf": "%"
  },
  "min_change_prev_day_pct": {
    "label": "Change Previous Day % >",
    "suf": "%"
  },
  "max_change_prev_day_pct": {
    "label": "Change Previous Day % <",
    "suf": "%"
  },
  "min_minutes_since_open": {
    "label": "Minutes Since Open >",
    "suf": "min"
  },
  "max_minutes_since_open": {
    "label": "Minutes Since Open <",
    "suf": "min"
  },
  "min_dilution_overall_risk_score": {
    "label": "Overall Risk >",
    "suf": ""
  },
  "max_dilution_overall_risk_score": {
    "label": "Overall Risk <",
    "suf": ""
  },
  "min_dilution_offering_ability_score": {
    "label": "Offering Ability >",
    "suf": ""
  },
  "max_dilution_offering_ability_score": {
    "label": "Offering Ability <",
    "suf": ""
  },
  "min_dilution_overhead_supply_score": {
    "label": "Overhead Supply >",
    "suf": ""
  },
  "max_dilution_overhead_supply_score": {
    "label": "Overhead Supply <",
    "suf": ""
  },
  "min_dilution_historical_score": {
    "label": "Historical >",
    "suf": ""
  },
  "max_dilution_historical_score": {
    "label": "Historical <",
    "suf": ""
  },
  "min_dilution_cash_need_score": {
    "label": "Cash Need >",
    "suf": ""
  },
  "max_dilution_cash_need_score": {
    "label": "Cash Need <",
    "suf": ""
  },
  "min_spy_chg_5min": {
    "label": "S&P 500 (SPY) Change 5 Minute >",
    "suf": "%"
  },
  "max_spy_chg_5min": {
    "label": "S&P 500 (SPY) Change 5 Minute <",
    "suf": "%"
  },
  "min_spy_chg_10min": {
    "label": "S&P 500 (SPY) Change 10 Minute >",
    "suf": "%"
  },
  "max_spy_chg_10min": {
    "label": "S&P 500 (SPY) Change 10 Minute <",
    "suf": "%"
  },
  "min_spy_chg_15min": {
    "label": "S&P 500 (SPY) Change 15 Minute >",
    "suf": "%"
  },
  "max_spy_chg_15min": {
    "label": "S&P 500 (SPY) Change 15 Minute <",
    "suf": "%"
  },
  "min_spy_chg_30min": {
    "label": "S&P 500 (SPY) Change 30 Minute >",
    "suf": "%"
  },
  "max_spy_chg_30min": {
    "label": "S&P 500 (SPY) Change 30 Minute <",
    "suf": "%"
  },
  "min_spy_chg_today": {
    "label": "S&P 500 (SPY) Change Today >",
    "suf": "%"
  },
  "max_spy_chg_today": {
    "label": "S&P 500 (SPY) Change Today <",
    "suf": "%"
  },
  "min_qqq_chg_5min": {
    "label": "NASDAQ (QQQ) Change 5 Minute >",
    "suf": "%"
  },
  "max_qqq_chg_5min": {
    "label": "NASDAQ (QQQ) Change 5 Minute <",
    "suf": "%"
  },
  "min_qqq_chg_10min": {
    "label": "NASDAQ (QQQ) Change 10 Minute >",
    "suf": "%"
  },
  "max_qqq_chg_10min": {
    "label": "NASDAQ (QQQ) Change 10 Minute <",
    "suf": "%"
  },
  "min_qqq_chg_15min": {
    "label": "NASDAQ (QQQ) Change 15 Minute >",
    "suf": "%"
  },
  "max_qqq_chg_15min": {
    "label": "NASDAQ (QQQ) Change 15 Minute <",
    "suf": "%"
  },
  "min_qqq_chg_30min": {
    "label": "NASDAQ (QQQ) Change 30 Minute >",
    "suf": "%"
  },
  "max_qqq_chg_30min": {
    "label": "NASDAQ (QQQ) Change 30 Minute <",
    "suf": "%"
  },
  "min_qqq_chg_today": {
    "label": "NASDAQ (QQQ) Change Today >",
    "suf": "%"
  },
  "max_qqq_chg_today": {
    "label": "NASDAQ (QQQ) Change Today <",
    "suf": "%"
  },
  "min_dia_chg_5min": {
    "label": "Dow (DIA) Change 5 Minute >",
    "suf": "%"
  },
  "max_dia_chg_5min": {
    "label": "Dow (DIA) Change 5 Minute <",
    "suf": "%"
  },
  "min_dia_chg_10min": {
    "label": "Dow (DIA) Change 10 Minute >",
    "suf": "%"
  },
  "max_dia_chg_10min": {
    "label": "Dow (DIA) Change 10 Minute <",
    "suf": "%"
  },
  "min_dia_chg_15min": {
    "label": "Dow (DIA) Change 15 Minute >",
    "suf": "%"
  },
  "max_dia_chg_15min": {
    "label": "Dow (DIA) Change 15 Minute <",
    "suf": "%"
  },
  "min_dia_chg_30min": {
    "label": "Dow (DIA) Change 30 Minute >",
    "suf": "%"
  },
  "max_dia_chg_30min": {
    "label": "Dow (DIA) Change 30 Minute <",
    "suf": "%"
  },
  "min_dia_chg_today": {
    "label": "Dow (DIA) Change Today >",
    "suf": "%"
  },
  "max_dia_chg_today": {
    "label": "Dow (DIA) Change Today <",
    "suf": "%"
  }
};

/** [paramMin, paramMax, wireMin, wireMax] for every events-scope filter */
export const EVENT_WIRE_PAIRS: readonly (readonly [string, string, string, string])[] = [
[
"min_price",
"max_price",
"price_min",
"price_max"
],
[
"min_rvol",
"max_rvol",
"rvol_min",
"rvol_max"
],
[
"min_change_percent",
"max_change_percent",
"change_min",
"change_max"
],
[
"min_volume",
"max_volume",
"volume_min",
"volume_max"
],
[
"min_gap_percent",
"max_gap_percent",
"gap_percent_min",
"gap_percent_max"
],
[
"min_change_from_open",
"max_change_from_open",
"change_from_open_min",
"change_from_open_max"
],
[
"min_atr_percent",
"max_atr_percent",
"atr_percent_min",
"atr_percent_max"
],
[
"min_rsi",
"max_rsi",
"rsi_min",
"rsi_max"
],
[
"min_market_cap",
"max_market_cap",
"market_cap_min",
"market_cap_max"
],
[
"min_float_shares",
"max_float_shares",
"float_shares_min",
"float_shares_max"
],
[
"min_shares_outstanding",
"max_shares_outstanding",
"shares_outstanding_min",
"shares_outstanding_max"
],
[
"min_vol_1min",
"max_vol_1min",
"vol_1min_min",
"vol_1min_max"
],
[
"min_vol_5min",
"max_vol_5min",
"vol_5min_min",
"vol_5min_max"
],
[
"min_vol_10min",
"max_vol_10min",
"vol_10min_min",
"vol_10min_max"
],
[
"min_vol_15min",
"max_vol_15min",
"vol_15min_min",
"vol_15min_max"
],
[
"min_vol_30min",
"max_vol_30min",
"vol_30min_min",
"vol_30min_max"
],
[
"min_vol_1min_pct",
"max_vol_1min_pct",
"vol_1min_pct_min",
"vol_1min_pct_max"
],
[
"min_vol_5min_pct",
"max_vol_5min_pct",
"vol_5min_pct_min",
"vol_5min_pct_max"
],
[
"min_vol_10min_pct",
"max_vol_10min_pct",
"vol_10min_pct_min",
"vol_10min_pct_max"
],
[
"min_vol_15min_pct",
"max_vol_15min_pct",
"vol_15min_pct_min",
"vol_15min_pct_max"
],
[
"min_vol_30min_pct",
"max_vol_30min_pct",
"vol_30min_pct_min",
"vol_30min_pct_max"
],
[
"min_range_2min",
"max_range_2min",
"range_2min_min",
"range_2min_max"
],
[
"min_range_5min",
"max_range_5min",
"range_5min_min",
"range_5min_max"
],
[
"min_range_15min",
"max_range_15min",
"range_15min_min",
"range_15min_max"
],
[
"min_range_30min",
"max_range_30min",
"range_30min_min",
"range_30min_max"
],
[
"min_range_60min",
"max_range_60min",
"range_60min_min",
"range_60min_max"
],
[
"min_range_120min",
"max_range_120min",
"range_120min_min",
"range_120min_max"
],
[
"min_range_2min_pct",
"max_range_2min_pct",
"range_2min_pct_min",
"range_2min_pct_max"
],
[
"min_range_5min_pct",
"max_range_5min_pct",
"range_5min_pct_min",
"range_5min_pct_max"
],
[
"min_range_15min_pct",
"max_range_15min_pct",
"range_15min_pct_min",
"range_15min_pct_max"
],
[
"min_range_30min_pct",
"max_range_30min_pct",
"range_30min_pct_min",
"range_30min_pct_max"
],
[
"min_range_60min_pct",
"max_range_60min_pct",
"range_60min_pct_min",
"range_60min_pct_max"
],
[
"min_range_120min_pct",
"max_range_120min_pct",
"range_120min_pct_min",
"range_120min_pct_max"
],
[
"min_chg_1min",
"max_chg_1min",
"chg_1min_min",
"chg_1min_max"
],
[
"min_chg_1min_dollars",
"max_chg_1min_dollars",
"chg_1min_dollars_min",
"chg_1min_dollars_max"
],
[
"min_chg_5min",
"max_chg_5min",
"chg_5min_min",
"chg_5min_max"
],
[
"min_chg_5min_dollars",
"max_chg_5min_dollars",
"chg_5min_dollars_min",
"chg_5min_dollars_max"
],
[
"min_chg_10min",
"max_chg_10min",
"chg_10min_min",
"chg_10min_max"
],
[
"min_chg_10min_dollars",
"max_chg_10min_dollars",
"chg_10min_dollars_min",
"chg_10min_dollars_max"
],
[
"min_chg_15min",
"max_chg_15min",
"chg_15min_min",
"chg_15min_max"
],
[
"min_chg_15min_dollars",
"max_chg_15min_dollars",
"chg_15min_dollars_min",
"chg_15min_dollars_max"
],
[
"min_chg_30min",
"max_chg_30min",
"chg_30min_min",
"chg_30min_max"
],
[
"min_chg_30min_dollars",
"max_chg_30min_dollars",
"chg_30min_dollars_min",
"chg_30min_dollars_max"
],
[
"min_chg_60min",
"max_chg_60min",
"chg_60min_min",
"chg_60min_max"
],
[
"min_chg_60min_dollars",
"max_chg_60min_dollars",
"chg_60min_dollars_min",
"chg_60min_dollars_max"
],
[
"min_bid",
"max_bid",
"bid_min",
"bid_max"
],
[
"min_ask",
"max_ask",
"ask_min",
"ask_max"
],
[
"min_bid_size",
"max_bid_size",
"bid_size_min",
"bid_size_max"
],
[
"min_ask_size",
"max_ask_size",
"ask_size_min",
"ask_size_max"
],
[
"min_spread",
"max_spread",
"spread_min",
"spread_max"
],
[
"min_sma_5",
"max_sma_5",
"sma_5_min",
"sma_5_max"
],
[
"min_sma_8",
"max_sma_8",
"sma_8_min",
"sma_8_max"
],
[
"min_sma_20",
"max_sma_20",
"sma_20_min",
"sma_20_max"
],
[
"min_sma_50",
"max_sma_50",
"sma_50_min",
"sma_50_max"
],
[
"min_sma_200",
"max_sma_200",
"sma_200_min",
"sma_200_max"
],
[
"min_ema_20",
"max_ema_20",
"ema_20_min",
"ema_20_max"
],
[
"min_ema_50",
"max_ema_50",
"ema_50_min",
"ema_50_max"
],
[
"min_macd_line",
"max_macd_line",
"macd_line_min",
"macd_line_max"
],
[
"min_macd_hist",
"max_macd_hist",
"macd_hist_min",
"macd_hist_max"
],
[
"min_stoch_k",
"max_stoch_k",
"stoch_k_min",
"stoch_k_max"
],
[
"min_stoch_d",
"max_stoch_d",
"stoch_d_min",
"stoch_d_max"
],
[
"min_adx_14",
"max_adx_14",
"adx_14_min",
"adx_14_max"
],
[
"min_bb_upper",
"max_bb_upper",
"bb_upper_min",
"bb_upper_max"
],
[
"min_bb_lower",
"max_bb_lower",
"bb_lower_min",
"bb_lower_max"
],
[
"min_daily_sma_5",
"max_daily_sma_5",
"daily_sma_5_min",
"daily_sma_5_max"
],
[
"min_daily_sma_8",
"max_daily_sma_8",
"daily_sma_8_min",
"daily_sma_8_max"
],
[
"min_daily_sma_10",
"max_daily_sma_10",
"daily_sma_10_min",
"daily_sma_10_max"
],
[
"min_daily_sma_20",
"max_daily_sma_20",
"daily_sma_20_min",
"daily_sma_20_max"
],
[
"min_daily_sma_50",
"max_daily_sma_50",
"daily_sma_50_min",
"daily_sma_50_max"
],
[
"min_daily_sma_200",
"max_daily_sma_200",
"daily_sma_200_min",
"daily_sma_200_max"
],
[
"min_daily_rsi",
"max_daily_rsi",
"daily_rsi_min",
"daily_rsi_max"
],
[
"min_high_52w",
"max_high_52w",
"high_52w_min",
"high_52w_max"
],
[
"min_low_52w",
"max_low_52w",
"low_52w_min",
"low_52w_max"
],
[
"min_trades_today",
"max_trades_today",
"trades_today_min",
"trades_today_max"
],
[
"min_trades_z_score",
"max_trades_z_score",
"trades_z_score_min",
"trades_z_score_max"
],
[
"min_vwap",
"max_vwap",
"vwap_min",
"vwap_max"
],
[
"min_dollar_volume",
"max_dollar_volume",
"dollar_volume_min",
"dollar_volume_max"
],
[
"min_todays_range",
"max_todays_range",
"todays_range_min",
"todays_range_max"
],
[
"min_todays_range_pct",
"max_todays_range_pct",
"todays_range_pct_min",
"todays_range_pct_max"
],
[
"min_bid_ask_ratio",
"max_bid_ask_ratio",
"bid_ask_ratio_min",
"bid_ask_ratio_max"
],
[
"min_float_turnover",
"max_float_turnover",
"float_turnover_min",
"float_turnover_max"
],
[
"min_dist_from_vwap",
"max_dist_from_vwap",
"dist_from_vwap_min",
"dist_from_vwap_max"
],
[
"min_dist_sma_5",
"max_dist_sma_5",
"dist_sma_5_min",
"dist_sma_5_max"
],
[
"min_dist_sma_8",
"max_dist_sma_8",
"dist_sma_8_min",
"dist_sma_8_max"
],
[
"min_dist_sma_20",
"max_dist_sma_20",
"dist_sma_20_min",
"dist_sma_20_max"
],
[
"min_dist_sma_50",
"max_dist_sma_50",
"dist_sma_50_min",
"dist_sma_50_max"
],
[
"min_dist_sma_200",
"max_dist_sma_200",
"dist_sma_200_min",
"dist_sma_200_max"
],
[
"min_pos_in_range",
"max_pos_in_range",
"pos_in_range_min",
"pos_in_range_max"
],
[
"min_below_high",
"max_below_high",
"below_high_min",
"below_high_max"
],
[
"min_above_low",
"max_above_low",
"above_low_min",
"above_low_max"
],
[
"min_pos_of_open",
"max_pos_of_open",
"pos_of_open_min",
"pos_of_open_max"
],
[
"min_prev_day_volume",
"max_prev_day_volume",
"prev_day_volume_min",
"prev_day_volume_max"
],
[
"min_change_1d",
"max_change_1d",
"change_1d_min",
"change_1d_max"
],
[
"min_change_3d",
"max_change_3d",
"change_3d_min",
"change_3d_max"
],
[
"min_change_5d",
"max_change_5d",
"change_5d_min",
"change_5d_max"
],
[
"min_change_10d",
"max_change_10d",
"change_10d_min",
"change_10d_max"
],
[
"min_change_20d",
"max_change_20d",
"change_20d_min",
"change_20d_max"
],
[
"min_avg_volume_5d",
"max_avg_volume_5d",
"avg_volume_5d_min",
"avg_volume_5d_max"
],
[
"min_avg_volume_10d",
"max_avg_volume_10d",
"avg_volume_10d_min",
"avg_volume_10d_max"
],
[
"min_avg_volume_20d",
"max_avg_volume_20d",
"avg_volume_20d_min",
"avg_volume_20d_max"
],
[
"min_dist_daily_sma_20",
"max_dist_daily_sma_20",
"dist_daily_sma_20_min",
"dist_daily_sma_20_max"
],
[
"min_dist_daily_sma_50",
"max_dist_daily_sma_50",
"dist_daily_sma_50_min",
"dist_daily_sma_50_max"
],
[
"min_from_52w_high",
"max_from_52w_high",
"from_52w_high_min",
"from_52w_high_max"
],
[
"min_from_52w_low",
"max_from_52w_low",
"from_52w_low_min",
"from_52w_low_max"
],
[
"min_daily_adx_14",
"max_daily_adx_14",
"daily_adx_14_min",
"daily_adx_14_max"
],
[
"min_daily_atr_percent",
"max_daily_atr_percent",
"daily_atr_percent_min",
"daily_atr_percent_max"
],
[
"min_daily_bb_position",
"max_daily_bb_position",
"daily_bb_position_min",
"daily_bb_position_max"
],
[
"min_volume_today_pct",
"max_volume_today_pct",
"volume_today_pct_min",
"volume_today_pct_max"
],
[
"min_minute_volume",
"max_minute_volume",
"minute_volume_min",
"minute_volume_max"
],
[
"min_price_from_high",
"max_price_from_high",
"price_from_high_min",
"price_from_high_max"
],
[
"min_price_from_low",
"max_price_from_low",
"price_from_low_min",
"price_from_low_max"
],
[
"min_price_from_intraday_high",
"max_price_from_intraday_high",
"price_from_intraday_high_min",
"price_from_intraday_high_max"
],
[
"min_price_from_intraday_low",
"max_price_from_intraday_low",
"price_from_intraday_low_min",
"price_from_intraday_low_max"
],
[
"min_volume_yesterday_pct",
"max_volume_yesterday_pct",
"volume_yesterday_pct_min",
"volume_yesterday_pct_max"
],
[
"min_change_from_open_dollars",
"max_change_from_open_dollars",
"change_from_open_dollars_min",
"change_from_open_dollars_max"
],
[
"min_distance_from_nbbo",
"max_distance_from_nbbo",
"distance_from_nbbo_min",
"distance_from_nbbo_max"
],
[
"min_premarket_change_percent",
"max_premarket_change_percent",
"premarket_change_percent_min",
"premarket_change_percent_max"
],
[
"min_postmarket_change_percent",
"max_postmarket_change_percent",
"postmarket_change_percent_min",
"postmarket_change_percent_max"
],
[
"min_postmarket_volume",
"max_postmarket_volume",
"postmarket_volume_min",
"postmarket_volume_max"
],
[
"min_avg_volume_3m",
"max_avg_volume_3m",
"avg_volume_3m_min",
"avg_volume_3m_max"
],
[
"min_atr",
"max_atr",
"atr_min",
"atr_max"
],
[
"min_dist_pivot",
"max_dist_pivot",
"dist_pivot_min",
"dist_pivot_max"
],
[
"min_dist_pivot_r1",
"max_dist_pivot_r1",
"dist_pivot_r1_min",
"dist_pivot_r1_max"
],
[
"min_dist_pivot_s1",
"max_dist_pivot_s1",
"dist_pivot_s1_min",
"dist_pivot_s1_max"
],
[
"min_dist_pivot_r2",
"max_dist_pivot_r2",
"dist_pivot_r2_min",
"dist_pivot_r2_max"
],
[
"min_dist_pivot_s2",
"max_dist_pivot_s2",
"dist_pivot_s2_min",
"dist_pivot_s2_max"
],
[
"min_consecutive_candles",
"max_consecutive_candles",
"consecutive_candles_min",
"consecutive_candles_max"
],
[
"min_consecutive_candles_2m",
"max_consecutive_candles_2m",
"consecutive_candles_2m_min",
"consecutive_candles_2m_max"
],
[
"min_consecutive_candles_5m",
"max_consecutive_candles_5m",
"consecutive_candles_5m_min",
"consecutive_candles_5m_max"
],
[
"min_consecutive_candles_10m",
"max_consecutive_candles_10m",
"consecutive_candles_10m_min",
"consecutive_candles_10m_max"
],
[
"min_consecutive_candles_15m",
"max_consecutive_candles_15m",
"consecutive_candles_15m_min",
"consecutive_candles_15m_max"
],
[
"min_consecutive_candles_30m",
"max_consecutive_candles_30m",
"consecutive_candles_30m_min",
"consecutive_candles_30m_max"
],
[
"min_consecutive_candles_60m",
"max_consecutive_candles_60m",
"consecutive_candles_60m_min",
"consecutive_candles_60m_max"
],
[
"min_pos_in_range_5m",
"max_pos_in_range_5m",
"pos_in_range_5m_min",
"pos_in_range_5m_max"
],
[
"min_pos_in_range_15m",
"max_pos_in_range_15m",
"pos_in_range_15m_min",
"pos_in_range_15m_max"
],
[
"min_pos_in_range_30m",
"max_pos_in_range_30m",
"pos_in_range_30m_min",
"pos_in_range_30m_max"
],
[
"min_pos_in_range_60m",
"max_pos_in_range_60m",
"pos_in_range_60m_min",
"pos_in_range_60m_max"
],
[
"min_rsi_2m",
"max_rsi_2m",
"rsi_2m_min",
"rsi_2m_max"
],
[
"min_rsi_5m",
"max_rsi_5m",
"rsi_5m_min",
"rsi_5m_max"
],
[
"min_rsi_15m",
"max_rsi_15m",
"rsi_15m_min",
"rsi_15m_max"
],
[
"min_rsi_60m",
"max_rsi_60m",
"rsi_60m_min",
"rsi_60m_max"
],
[
"min_bb_position_1m",
"max_bb_position_1m",
"bb_position_1m_min",
"bb_position_1m_max"
],
[
"min_bb_position_5m",
"max_bb_position_5m",
"bb_position_5m_min",
"bb_position_5m_max"
],
[
"min_bb_position_15m",
"max_bb_position_15m",
"bb_position_15m_min",
"bb_position_15m_max"
],
[
"min_bb_position_60m",
"max_bb_position_60m",
"bb_position_60m_min",
"bb_position_60m_max"
],
[
"min_chg_2min",
"max_chg_2min",
"chg_2min_min",
"chg_2min_max"
],
[
"min_chg_120min",
"max_chg_120min",
"chg_120min_min",
"chg_120min_max"
],
[
"min_chg_2min_dollars",
"max_chg_2min_dollars",
"chg_2min_dollars_min",
"chg_2min_dollars_max"
],
[
"min_chg_120min_dollars",
"max_chg_120min_dollars",
"chg_120min_dollars_min",
"chg_120min_dollars_max"
],
[
"min_gap_dollars",
"max_gap_dollars",
"gap_dollars_min",
"gap_dollars_max"
],
[
"min_gap_ratio",
"max_gap_ratio",
"gap_ratio_min",
"gap_ratio_max"
],
[
"min_change_from_close_dollars",
"max_change_from_close_dollars",
"change_from_close_dollars_min",
"change_from_close_dollars_max"
],
[
"min_change_from_close_ratio",
"max_change_from_close_ratio",
"change_from_close_ratio_min",
"change_from_close_ratio_max"
],
[
"min_change_from_open_ratio",
"max_change_from_open_ratio",
"change_from_open_ratio_min",
"change_from_open_ratio_max"
],
[
"min_postmarket_change_dollars",
"max_postmarket_change_dollars",
"postmarket_change_dollars_min",
"postmarket_change_dollars_max"
],
[
"min_decimal",
"max_decimal",
"decimal_min",
"decimal_max"
],
[
"min_pos_in_prev_day_range",
"max_pos_in_prev_day_range",
"pos_in_prev_day_range_min",
"pos_in_prev_day_range_max"
],
[
"min_plus_di_minus_di",
"max_plus_di_minus_di",
"plus_di_minus_di_min",
"plus_di_minus_di_max"
],
[
"min_bb_std_dev",
"max_bb_std_dev",
"bb_std_dev_min",
"bb_std_dev_max"
],
[
"min_dist_sma_5_2m",
"max_dist_sma_5_2m",
"dist_sma_5_2m_min",
"dist_sma_5_2m_max"
],
[
"min_dist_sma_5_5m",
"max_dist_sma_5_5m",
"dist_sma_5_5m_min",
"dist_sma_5_5m_max"
],
[
"min_dist_sma_5_15m",
"max_dist_sma_5_15m",
"dist_sma_5_15m_min",
"dist_sma_5_15m_max"
],
[
"min_dist_sma_8_2m",
"max_dist_sma_8_2m",
"dist_sma_8_2m_min",
"dist_sma_8_2m_max"
],
[
"min_dist_sma_8_5m",
"max_dist_sma_8_5m",
"dist_sma_8_5m_min",
"dist_sma_8_5m_max"
],
[
"min_dist_sma_8_15m",
"max_dist_sma_8_15m",
"dist_sma_8_15m_min",
"dist_sma_8_15m_max"
],
[
"min_dist_sma_8_60m",
"max_dist_sma_8_60m",
"dist_sma_8_60m_min",
"dist_sma_8_60m_max"
],
[
"min_dist_sma_20_2m",
"max_dist_sma_20_2m",
"dist_sma_20_2m_min",
"dist_sma_20_2m_max"
],
[
"min_dist_sma_20_5m",
"max_dist_sma_20_5m",
"dist_sma_20_5m_min",
"dist_sma_20_5m_max"
],
[
"min_dist_sma_20_15m",
"max_dist_sma_20_15m",
"dist_sma_20_15m_min",
"dist_sma_20_15m_max"
],
[
"min_dist_sma_20_60m",
"max_dist_sma_20_60m",
"dist_sma_20_60m_min",
"dist_sma_20_60m_max"
],
[
"min_sma_8_vs_20_2m",
"max_sma_8_vs_20_2m",
"sma_8_vs_20_2m_min",
"sma_8_vs_20_2m_max"
],
[
"min_sma_8_vs_20_5m",
"max_sma_8_vs_20_5m",
"sma_8_vs_20_5m_min",
"sma_8_vs_20_5m_max"
],
[
"min_sma_8_vs_20_15m",
"max_sma_8_vs_20_15m",
"sma_8_vs_20_15m_min",
"sma_8_vs_20_15m_max"
],
[
"min_sma_8_vs_20_60m",
"max_sma_8_vs_20_60m",
"sma_8_vs_20_60m_min",
"sma_8_vs_20_60m_max"
],
[
"min_dist_daily_sma_200",
"max_dist_daily_sma_200",
"dist_daily_sma_200_min",
"dist_daily_sma_200_max"
],
[
"min_range_5d",
"max_range_5d",
"range_5d_min",
"range_5d_max"
],
[
"min_range_10d",
"max_range_10d",
"range_10d_min",
"range_10d_max"
],
[
"min_range_20d",
"max_range_20d",
"range_20d_min",
"range_20d_max"
],
[
"min_pos_in_5d_range",
"max_pos_in_5d_range",
"pos_in_5d_range_min",
"pos_in_5d_range_max"
],
[
"min_pos_in_10d_range",
"max_pos_in_10d_range",
"pos_in_10d_range_min",
"pos_in_10d_range_max"
],
[
"min_pos_in_20d_range",
"max_pos_in_20d_range",
"pos_in_20d_range_min",
"pos_in_20d_range_max"
],
[
"min_pos_in_52w_range",
"max_pos_in_52w_range",
"pos_in_52w_range_min",
"pos_in_52w_range_max"
],
[
"min_range_5d_pct",
"max_range_5d_pct",
"range_5d_pct_min",
"range_5d_pct_max"
],
[
"min_range_10d_pct",
"max_range_10d_pct",
"range_10d_pct_min",
"range_10d_pct_max"
],
[
"min_range_20d_pct",
"max_range_20d_pct",
"range_20d_pct_min",
"range_20d_pct_max"
],
[
"min_change_5d_dollars",
"max_change_5d_dollars",
"change_5d_dollars_min",
"change_5d_dollars_max"
],
[
"min_change_10d_dollars",
"max_change_10d_dollars",
"change_10d_dollars_min",
"change_10d_dollars_max"
],
[
"min_change_20d_dollars",
"max_change_20d_dollars",
"change_20d_dollars_min",
"change_20d_dollars_max"
],
[
"min_change_from_open_weighted",
"max_change_from_open_weighted",
"change_from_open_weighted_min",
"change_from_open_weighted_max"
],
[
"min_dist_daily_sma_5_dollars",
"max_dist_daily_sma_5_dollars",
"dist_daily_sma_5_dollars_min",
"dist_daily_sma_5_dollars_max"
],
[
"min_dist_daily_sma_8_dollars",
"max_dist_daily_sma_8_dollars",
"dist_daily_sma_8_dollars_min",
"dist_daily_sma_8_dollars_max"
],
[
"min_dist_daily_sma_10_dollars",
"max_dist_daily_sma_10_dollars",
"dist_daily_sma_10_dollars_min",
"dist_daily_sma_10_dollars_max"
],
[
"min_dist_daily_sma_20_dollars",
"max_dist_daily_sma_20_dollars",
"dist_daily_sma_20_dollars_min",
"dist_daily_sma_20_dollars_max"
],
[
"min_dist_daily_sma_50_dollars",
"max_dist_daily_sma_50_dollars",
"dist_daily_sma_50_dollars_min",
"dist_daily_sma_50_dollars_max"
],
[
"min_dist_daily_sma_200_dollars",
"max_dist_daily_sma_200_dollars",
"dist_daily_sma_200_dollars_min",
"dist_daily_sma_200_dollars_max"
],
[
"min_dist_daily_sma_5",
"max_dist_daily_sma_5",
"dist_daily_sma_5_min",
"dist_daily_sma_5_max"
],
[
"min_dist_daily_sma_8",
"max_dist_daily_sma_8",
"dist_daily_sma_8_min",
"dist_daily_sma_8_max"
],
[
"min_dist_daily_sma_10",
"max_dist_daily_sma_10",
"dist_daily_sma_10_min",
"dist_daily_sma_10_max"
],
[
"min_sma_20_vs_200_2m",
"max_sma_20_vs_200_2m",
"sma_20_vs_200_2m_min",
"sma_20_vs_200_2m_max"
],
[
"min_sma_20_vs_200_5m",
"max_sma_20_vs_200_5m",
"sma_20_vs_200_5m_min",
"sma_20_vs_200_5m_max"
],
[
"min_sma_20_vs_200_15m",
"max_sma_20_vs_200_15m",
"sma_20_vs_200_15m_min",
"sma_20_vs_200_15m_max"
],
[
"min_sma_20_vs_200_60m",
"max_sma_20_vs_200_60m",
"sma_20_vs_200_60m_min",
"sma_20_vs_200_60m_max"
],
[
"min_change_1y",
"max_change_1y",
"change_1y_min",
"change_1y_max"
],
[
"min_change_1y_dollars",
"max_change_1y_dollars",
"change_1y_dollars_min",
"change_1y_dollars_max"
],
[
"min_change_ytd",
"max_change_ytd",
"change_ytd_min",
"change_ytd_max"
],
[
"min_change_ytd_dollars",
"max_change_ytd_dollars",
"change_ytd_dollars_min",
"change_ytd_dollars_max"
],
[
"min_yearly_std_dev",
"max_yearly_std_dev",
"yearly_std_dev_min",
"yearly_std_dev_max"
],
[
"min_consecutive_days_up",
"max_consecutive_days_up",
"consecutive_days_up_min",
"consecutive_days_up_max"
],
[
"min_dist_sma_10_2m",
"max_dist_sma_10_2m",
"dist_sma_10_2m_min",
"dist_sma_10_2m_max"
],
[
"min_dist_sma_10_5m",
"max_dist_sma_10_5m",
"dist_sma_10_5m_min",
"dist_sma_10_5m_max"
],
[
"min_dist_sma_10_15m",
"max_dist_sma_10_15m",
"dist_sma_10_15m_min",
"dist_sma_10_15m_max"
],
[
"min_dist_sma_10_60m",
"max_dist_sma_10_60m",
"dist_sma_10_60m_min",
"dist_sma_10_60m_max"
],
[
"min_dist_sma_130_15m",
"max_dist_sma_130_15m",
"dist_sma_130_15m_min",
"dist_sma_130_15m_max"
],
[
"min_dist_sma_200_2m",
"max_dist_sma_200_2m",
"dist_sma_200_2m_min",
"dist_sma_200_2m_max"
],
[
"min_dist_sma_200_5m",
"max_dist_sma_200_5m",
"dist_sma_200_5m_min",
"dist_sma_200_5m_max"
],
[
"min_dist_sma_200_15m",
"max_dist_sma_200_15m",
"dist_sma_200_15m_min",
"dist_sma_200_15m_max"
],
[
"min_dist_sma_200_60m",
"max_dist_sma_200_60m",
"dist_sma_200_60m_min",
"dist_sma_200_60m_max"
],
[
"min_dist_sma_5_60m",
"max_dist_sma_5_60m",
"dist_sma_5_60m_min",
"dist_sma_5_60m_max"
],
[
"min_pos_in_3m_range",
"max_pos_in_3m_range",
"pos_in_3m_range_min",
"pos_in_3m_range_max"
],
[
"min_pos_in_6m_range",
"max_pos_in_6m_range",
"pos_in_6m_range_min",
"pos_in_6m_range_max"
],
[
"min_pos_in_9m_range",
"max_pos_in_9m_range",
"pos_in_9m_range_min",
"pos_in_9m_range_max"
],
[
"min_pos_in_2y_range",
"max_pos_in_2y_range",
"pos_in_2y_range_min",
"pos_in_2y_range_max"
],
[
"min_pos_in_lifetime_range",
"max_pos_in_lifetime_range",
"pos_in_lifetime_range_min",
"pos_in_lifetime_range_max"
],
[
"min_below_premarket_high",
"max_below_premarket_high",
"below_premarket_high_min",
"below_premarket_high_max"
],
[
"min_above_premarket_low",
"max_above_premarket_low",
"above_premarket_low_min",
"above_premarket_low_max"
],
[
"min_pos_in_premarket_range",
"max_pos_in_premarket_range",
"pos_in_premarket_range_min",
"pos_in_premarket_range_max"
],
[
"min_consolidation_days",
"max_consolidation_days",
"consolidation_days_min",
"consolidation_days_max"
],
[
"min_pos_in_consolidation",
"max_pos_in_consolidation",
"pos_in_consolidation_min",
"pos_in_consolidation_max"
],
[
"min_range_contraction",
"max_range_contraction",
"range_contraction_min",
"range_contraction_max"
],
[
"min_lr_divergence_130",
"max_lr_divergence_130",
"lr_divergence_130_min",
"lr_divergence_130_max"
],
[
"min_change_prev_day_pct",
"max_change_prev_day_pct",
"change_prev_day_pct_min",
"change_prev_day_pct_max"
],
[
"min_minutes_since_open",
"max_minutes_since_open",
"minutes_since_open_min",
"minutes_since_open_max"
],
[
"min_dilution_overall_risk_score",
"max_dilution_overall_risk_score",
"dilution_overall_risk_score_min",
"dilution_overall_risk_score_max"
],
[
"min_dilution_offering_ability_score",
"max_dilution_offering_ability_score",
"dilution_offering_ability_score_min",
"dilution_offering_ability_score_max"
],
[
"min_dilution_overhead_supply_score",
"max_dilution_overhead_supply_score",
"dilution_overhead_supply_score_min",
"dilution_overhead_supply_score_max"
],
[
"min_dilution_historical_score",
"max_dilution_historical_score",
"dilution_historical_score_min",
"dilution_historical_score_max"
],
[
"min_dilution_cash_need_score",
"max_dilution_cash_need_score",
"dilution_cash_need_score_min",
"dilution_cash_need_score_max"
],
[
"min_spy_chg_5min",
"max_spy_chg_5min",
"spy_chg_5min_min",
"spy_chg_5min_max"
],
[
"min_spy_chg_10min",
"max_spy_chg_10min",
"spy_chg_10min_min",
"spy_chg_10min_max"
],
[
"min_spy_chg_15min",
"max_spy_chg_15min",
"spy_chg_15min_min",
"spy_chg_15min_max"
],
[
"min_spy_chg_30min",
"max_spy_chg_30min",
"spy_chg_30min_min",
"spy_chg_30min_max"
],
[
"min_spy_chg_today",
"max_spy_chg_today",
"spy_chg_today_min",
"spy_chg_today_max"
],
[
"min_qqq_chg_5min",
"max_qqq_chg_5min",
"qqq_chg_5min_min",
"qqq_chg_5min_max"
],
[
"min_qqq_chg_10min",
"max_qqq_chg_10min",
"qqq_chg_10min_min",
"qqq_chg_10min_max"
],
[
"min_qqq_chg_15min",
"max_qqq_chg_15min",
"qqq_chg_15min_min",
"qqq_chg_15min_max"
],
[
"min_qqq_chg_30min",
"max_qqq_chg_30min",
"qqq_chg_30min_min",
"qqq_chg_30min_max"
],
[
"min_qqq_chg_today",
"max_qqq_chg_today",
"qqq_chg_today_min",
"qqq_chg_today_max"
],
[
"min_dia_chg_5min",
"max_dia_chg_5min",
"dia_chg_5min_min",
"dia_chg_5min_max"
],
[
"min_dia_chg_10min",
"max_dia_chg_10min",
"dia_chg_10min_min",
"dia_chg_10min_max"
],
[
"min_dia_chg_15min",
"max_dia_chg_15min",
"dia_chg_15min_min",
"dia_chg_15min_max"
],
[
"min_dia_chg_30min",
"max_dia_chg_30min",
"dia_chg_30min_min",
"dia_chg_30min_max"
],
[
"min_dia_chg_today",
"max_dia_chg_today",
"dia_chg_today_min",
"dia_chg_today_max"
]
] as const;

export const DILUTION_FILTERS: readonly { label: string; minK: string; maxK: string }[] = [
  {
    "label": "Overall Risk",
    "minK": "min_dilution_overall_risk_score",
    "maxK": "max_dilution_overall_risk_score"
  },
  {
    "label": "Offering Ability",
    "minK": "min_dilution_offering_ability_score",
    "maxK": "max_dilution_offering_ability_score"
  },
  {
    "label": "Overhead Supply",
    "minK": "min_dilution_overhead_supply_score",
    "maxK": "max_dilution_overhead_supply_score"
  },
  {
    "label": "Historical",
    "minK": "min_dilution_historical_score",
    "maxK": "max_dilution_historical_score"
  },
  {
    "label": "Cash Need",
    "minK": "min_dilution_cash_need_score",
    "maxK": "max_dilution_cash_need_score"
  }
] as const;
