#!/usr/bin/env python3
"""
Rebuild Pattern Index v2 (90-dim: price + volume)

Strategy to avoid OOM:
  1. Process files in small batches to extract vectors
  2. Train FAISS index on a random sample (no need to load everything)
  3. Add vectors batch by batch — never loading more than BATCH_MEM_GB at once
  4. Save to patterns_v2_* files (separate from the live index)
  5. Swap atomically at the end

Run:  python3 rebuild_v2.py [--data-dir /app/data/minute_aggs] [--batch-size 50]
"""

import argparse
import os
import sys
import sqlite3
import random
import time
from glob import glob
from datetime import datetime

import numpy as np
import faiss
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()


def process_batch(filepaths, processor):
    """Process a batch of CSV files, return (vectors, metadata)."""
    all_v, all_m = [], []
    for fp in filepaths:
        v, m = processor.process_daily_file(fp)
        if len(v):
            all_v.append(v)
            all_m.extend(m)
    if not all_v:
        return np.empty((0, 90), dtype=np.float32), []
    return np.vstack(all_v).astype(np.float32), all_m


def main():
    parser = argparse.ArgumentParser(description="Rebuild pattern index v2 (90-dim)")
    parser.add_argument("--data-dir", default="/app/data/minute_aggs")
    parser.add_argument("--index-dir", default="/app/indexes")
    parser.add_argument("--name", default="patterns_v2")
    parser.add_argument("--batch-size", type=int, default=40,
                        help="Files per batch (lower = less RAM, slower)")
    parser.add_argument("--sample-files", type=int, default=100,
                        help="Files to sample for FAISS training")
    parser.add_argument("--nlist", type=int, default=4096)
    parser.add_argument("--pq-m", type=int, default=30,
                        help="PQ subquantizers (must divide 90 evenly: 30, 18, 45, 9...)")
    args = parser.parse_args()

    os.makedirs(args.index_dir, exist_ok=True)

    files = sorted(glob(f"{args.data_dir}/*.csv.gz"))
    if not files:
        log.error("No CSV files found", data_dir=args.data_dir)
        sys.exit(1)

    log.info("Rebuild v2 started", files=len(files), batch_size=args.batch_size,
             index_dir=args.index_dir, name=args.name)

    from data_processor import DataProcessor
    processor = DataProcessor()

    DIM = 90  # 45 price + 45 volume
    index_path = os.path.join(args.index_dir, f"{args.name}_ivfpq.index")
    db_path = os.path.join(args.index_dir, f"{args.name}_metadata.db")
    traj_path = os.path.join(args.index_dir, f"{args.name}_trajectories.npy")

    # ── Step 1: Train on a random sample ──────────────────────────────────────
    log.info("Step 1/3: Training FAISS on sample", sample_files=args.sample_files)
    sample_files = random.sample(files, min(args.sample_files, len(files)))
    sample_v, _ = process_batch(sample_files, processor)

    if len(sample_v) < args.nlist * 40:
        log.warning("Sample too small, reducing nlist",
                    have=len(sample_v), need=args.nlist * 40)
        args.nlist = max(64, len(sample_v) // 40)

    quantizer = faiss.IndexFlatL2(DIM)
    index = faiss.IndexIVFPQ(quantizer, DIM, args.nlist, args.pq_m, 8)

    log.info("Training IVFPQ index", nlist=args.nlist, pq_m=args.pq_m,
             sample_vectors=len(sample_v))
    index.train(sample_v)
    log.info("Training complete")
    del sample_v

    # ── Step 2: Init SQLite + trajectories ────────────────────────────────────
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE patterns (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            date TEXT,
            start_time TEXT,
            final_return REAL
        )
    """)
    conn.execute("CREATE INDEX idx_date ON patterns(date)")
    conn.commit()

    traj_file = open(traj_path, "wb")  # We'll write raw float32 rows

    # ── Step 3: Add vectors in batches ────────────────────────────────────────
    total_added = 0
    n_batches = (len(files) + args.batch_size - 1) // args.batch_size

    log.info("Step 2/3: Adding vectors in batches",
             total_files=len(files), batches=n_batches, batch_size=args.batch_size)

    for batch_i, start in enumerate(range(0, len(files), args.batch_size)):
        batch_files = files[start:start + args.batch_size]
        t0 = time.time()

        vectors, metadata = process_batch(batch_files, processor)

        if len(vectors) == 0:
            continue

        index.add(vectors)

        rows = [
            (total_added + i, m["symbol"], m["date"], m["start_time"],
             m["future_returns"][-1] if m.get("future_returns") else 0.0)
            for i, m in enumerate(metadata)
        ]
        conn.executemany("INSERT INTO patterns VALUES (?,?,?,?,?)", rows)
        conn.commit()

        for m in metadata:
            fut = m.get("future_returns", [])
            if len(fut) >= 15:
                arr = np.array(fut[:15], dtype=np.float32)
            elif fut:
                arr = np.zeros(15, dtype=np.float32)
                arr[:len(fut)] = fut
            else:
                arr = np.zeros(15, dtype=np.float32)
            traj_file.write(arr.tobytes())

        total_added += len(vectors)
        elapsed = time.time() - t0

        log.info("Batch done",
                 batch=f"{batch_i + 1}/{n_batches}",
                 files=len(batch_files),
                 vectors=len(vectors),
                 total=total_added,
                 elapsed_s=round(elapsed, 1))

        del vectors, metadata

    traj_file.close()
    conn.close()

    # ── Step 4: Save FAISS index ───────────────────────────────────────────────
    log.info("Step 3/3: Saving index", path=index_path, total_vectors=total_added)
    faiss.write_index(index, index_path)

    # Convert raw traj file to proper numpy format
    raw = np.fromfile(traj_path, dtype=np.float32).reshape(-1, 15)
    np.save(traj_path.replace(".npy", "_tmp.npy"), raw)
    os.replace(traj_path.replace(".npy", "_tmp.npy"), traj_path)

    log.info("Rebuild v2 complete",
             total_vectors=total_added,
             index=index_path,
             db=db_path,
             trajectories=traj_path)

    print(f"\n{'='*60}")
    print(f"  REBUILD V2 COMPLETE")
    print(f"  Vectors:  {total_added:,}")
    print(f"  Dim:      {DIM}")
    print(f"  Index:    {index_path}")
    print(f"{'='*60}")
    print("\nTo swap to production:")
    print(f"  cd {args.index_dir}")
    print(f"  mv patterns_ivfpq.index patterns_ivfpq_v1.index")
    print(f"  mv {args.name}_ivfpq.index patterns_ivfpq.index")
    print(f"  mv patterns_metadata.db patterns_metadata_v1.db")
    print(f"  mv {args.name}_metadata.db patterns_metadata.db")
    print(f"  mv patterns_trajectories.npy patterns_trajectories_v1.npy")
    print(f"  mv {args.name}_trajectories.npy patterns_trajectories.npy")
    print(f"  docker restart pattern_matching")


if __name__ == "__main__":
    main()
