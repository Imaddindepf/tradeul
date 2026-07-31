"""
Bootstrap del sandbox: define los helpers prometidos por el prompt de
code_exec y ejecuta el código del usuario. Corre DENTRO del subproceso
aislado (python -I, rlimits, sin red por diseño del contenedor).

Contrato (idéntico al prompt del agente):
  historical_query(ticker, start, end, interval="1d") -> DataFrame OHLCV
  live_quote(ticker) -> dict (pre-inyectado por el agente; sin red aquí)
  run_sql(query) / register_df(name, df) -> DuckDB sobre DataFrames
  save_output(data, label) / save_chart(fig, label)
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from datetime import date, datetime, timedelta

RUN_DIR = os.environ["RUN_DIR"]
DATA_DIR = os.environ.get("POLYGON_DIR", "/data/polygon")

os.environ.setdefault("MPLCONFIGDIR", RUN_DIR)
import matplotlib
matplotlib.use("Agg")

import duckdb
import pandas as pd

with open(os.path.join(RUN_DIR, "payload.json")) as fh:
    _PAYLOAD = json.load(fh)

_QUOTES: dict = _PAYLOAD.get("quotes") or {}
_USER_CODE: str = _PAYLOAD["code"]

_con = duckdb.connect()
_OUTPUTS: list = []
_CHARTS: list = []


def _day_files(start: str, end: str) -> list[str]:
    d0 = datetime.strptime(str(start)[:10], "%Y-%m-%d").date()
    d1 = datetime.strptime(str(end)[:10], "%Y-%m-%d").date()
    files = []
    d = d0
    while d <= d1:
        p = os.path.join(DATA_DIR, "day_aggs", f"{d.isoformat()}.parquet")
        if os.path.exists(p):
            files.append(p)
        d += timedelta(days=1)
    return files


def historical_query(ticker: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """OHLCV diario desde los parquet locales (interval '1d' soportado)."""
    files = _day_files(start, end)
    if not files:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = _con.execute(
        """
        SELECT to_timestamp(window_start / 1000000000)::date AS date,
               open, high, low, close, volume
        FROM read_parquet(?)
        WHERE ticker = ?
        ORDER BY date
        """,
        [files, str(ticker).upper()],
    ).df()
    return df


def live_quote(ticker: str) -> dict:
    q = _QUOTES.get(str(ticker).upper())
    if q:
        return q
    return {"error": f"no live quote pre-fetched for {ticker}",
            "hint": "live data is injected by the agent for tickers in the query"}


def register_df(name: str, df) -> None:
    _con.register(str(name), df)


def run_sql(query: str):
    return _con.execute(str(query)).df()


def _jsonable(data, max_rows: int = 300):
    if isinstance(data, pd.DataFrame):
        d = data.head(max_rows)
        return {"type": "dataframe", "rows": len(data),
                "shown": len(d), "records": json.loads(d.to_json(orient="records", date_format="iso"))}
    if isinstance(data, pd.Series):
        return _jsonable(data.to_frame())
    try:
        json.dumps(data)
        return data
    except (TypeError, ValueError):
        return {"repr": repr(data)[:2000]}


def save_output(data, label: str = "result") -> None:
    _OUTPUTS.append({"label": str(label)[:80], "data": _jsonable(data)})


def save_chart(fig, label: str = "chart") -> None:
    try:
        buf = io.BytesIO()
        if hasattr(fig, "savefig"):            # matplotlib
            fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        elif hasattr(fig, "to_image"):         # plotly (requiere kaleido; puede fallar)
            buf.write(fig.to_image(format="png"))
        else:
            _OUTPUTS.append({"label": f"{label} (unsupported figure type)",
                             "data": {"repr": repr(type(fig))}})
            return
        _CHARTS.append({"label": str(label)[:80],
                        "png_base64": base64.b64encode(buf.getvalue()).decode()})
    except Exception as exc:  # noqa: BLE001
        _OUTPUTS.append({"label": f"{label} (chart failed)", "data": {"error": str(exc)[:300]}})


def _finish(error: str | None = None) -> None:
    with open(os.path.join(RUN_DIR, "result.json"), "w") as fh:
        json.dump({"outputs": _OUTPUTS, "charts": _CHARTS, "error": error}, fh)


_scope = {
    "historical_query": historical_query,
    "live_quote": live_quote,
    "run_sql": run_sql,
    "register_df": register_df,
    "save_output": save_output,
    "save_chart": save_chart,
    "pd": pd, "duckdb": duckdb,
    "__name__": "__main__",
}

try:
    exec(compile(_USER_CODE, "<user_code>", "exec"), _scope)  # noqa: S102
    _finish()
except SystemExit:
    _finish()
except BaseException as exc:  # noqa: BLE001
    import traceback
    tb = traceback.format_exc(limit=6)
    _finish(f"{type(exc).__name__}: {exc}\n{tb[-1500:]}")
    sys.exit(1)
