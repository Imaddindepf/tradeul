"""
Backfill de embeddings para la memoria semántica (Fase 4a).

Recorre agent_conv_messages con embedding NULL, embebe en lotes y actualiza.
Idempotente y reanudable (solo procesa NULLs). Uso (dentro del contenedor,
necesita CHECKPOINT_DB_URL y GOOGLE_API_KEY):

    python -m memory.backfill_embeddings [--batch 25] [--sleep 0.3]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def run(batch: int, sleep_s: float) -> int:
    from psycopg_pool import AsyncConnectionPool
    from memory.embeddings import embed_texts, to_pgvector, EMBED_DIMS

    db_url = os.getenv("CHECKPOINT_DB_URL", "").strip()
    if not db_url:
        print("[error] CHECKPOINT_DB_URL not set", file=sys.stderr)
        return 2

    async with AsyncConnectionPool(db_url, min_size=1, max_size=2, open=False,
                                   kwargs={"autocommit": True}) as pool:
        await pool.open(wait=True, timeout=15)
        done = failed = 0
        while True:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT user_id, thread_id, ts, query, response
                    FROM agent_conv_messages
                    WHERE embedding IS NULL
                    ORDER BY ts DESC
                    LIMIT %s
                    """,
                    (batch,),
                )
                rows = await cur.fetchall()
            if not rows:
                break

            texts = [f"{q}\n{(r or '')[:1500]}" for _u, _t, _ts, q, r in rows]
            vecs = await embed_texts(texts)
            if vecs is None:
                failed += len(rows)
                print(f"[warn] embed batch failed ({len(rows)} rows) — retrying in 5s")
                await asyncio.sleep(5)
                continue

            async with pool.connection() as conn:
                for (user_id, thread_id, ts, _q, _r), vec in zip(rows, vecs):
                    await conn.execute(
                        """
                        UPDATE agent_conv_messages SET embedding = %s::vector
                        WHERE user_id = %s AND thread_id = %s AND ts = %s
                        """,
                        (to_pgvector(vec), user_id, thread_id, ts),
                    )
            done += len(rows)
            print(f"[backfill] {done} embebidos (dims={EMBED_DIMS})...")
            await asyncio.sleep(sleep_s)

        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FILTER (WHERE embedding IS NOT NULL), COUNT(*) "
                "FROM agent_conv_messages")
            with_emb, total = (await cur.fetchall())[0]
        print(f"[done] {with_emb}/{total} mensajes con embedding (fallos transitorios: {failed})")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.batch, args.sleep)))


if __name__ == "__main__":
    main()
