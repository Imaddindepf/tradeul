#!/usr/bin/env python3
"""Paridad del matcher portado contra los fixtures del código vivo.

Corre el port de Python (services/backtester/matching) sobre cada caso de
fixtures/*/inputs.jsonl y exige el veredicto IDÉNTICO al congelado en
fixtures/*/fixtures.jsonl. Cualquier desviación es un bug del port.

    python3 services/backtester/parity/check_matcher_parity.py            # todas las tandas
    python3 services/backtester/parity/check_matcher_parity.py 2026-08-02 # una tanda

Exit 1 si hay desajustes; imprime los primeros con su contexto para depurar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/backtester"))

from matching.matcher import match_event  # noqa: E402
from matching.matcher_defs_generated import SOURCE_SHA256  # noqa: E402

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
MAX_SHOWN = 10


def run_batch(batch_dir: Path) -> tuple:
    frozen = {}
    for line in (batch_dir / "fixtures.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            frozen[r["case_id"]] = r

    meta = json.loads((batch_dir / "meta.json").read_text())
    if meta.get("source_sha256") != SOURCE_SHA256:
        print(
            f"  AVISO: {batch_dir.name} se congeló con otro index.js "
            f"({meta.get('source_sha256', '?')[:12]}… vs defs {SOURCE_SHA256[:12]}…) — "
            "los veredictos siguen siendo la spec hasta regenerar la tanda"
        )

    mismatches = []
    n = 0
    with open(batch_dir / "inputs.jsonl") as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            cache = {}
            if c.get("enriched"):
                cache[c["event_fields"]["symbol"]] = c["enriched"]
            got = match_event(c["event_fields"], c["sub_data"], cache)
            n += 1
            want = frozen[c["case_id"]]["verdict"]
            if got != want:
                mismatches.append((c, want, got))
    return n, mismatches


def main() -> int:
    batches = (
        [FIXTURES_ROOT / sys.argv[1]]
        if len(sys.argv) > 1
        else sorted(p for p in FIXTURES_ROOT.iterdir() if (p / "fixtures.jsonl").exists())
    )
    if not batches:
        print("No hay tandas de fixtures — genera una primero (ver README.md)")
        return 1

    total, bad = 0, 0
    for b in batches:
        n, mismatches = run_batch(b)
        total += n
        bad += len(mismatches)
        status = "OK" if not mismatches else f"{len(mismatches)} DESAJUSTES"
        print(f"  {b.name}: {n} casos — {status}")
        for c, want, got in mismatches[:MAX_SHOWN]:
            print(
                f"    {c['case_id']} [{c['origin']}/{c.get('mutation')}] "
                f"{c['event_fields']['event_type']}@{c['event_fields']['symbol']} "
                f"estrategia={c['strategy_id']} vivo={want} port={got}"
            )
        if len(mismatches) > MAX_SHOWN:
            print(f"    … y {len(mismatches) - MAX_SHOWN} más")

    if bad:
        print(f"Matcher parity FAILED: {bad}/{total} veredictos difieren del vivo")
        return 1
    print(f"Matcher parity OK: {total} veredictos idénticos al código vivo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
