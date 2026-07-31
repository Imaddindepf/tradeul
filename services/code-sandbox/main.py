"""
Servicio sandbox de code_exec (Fase 4b).

POST /run {code, quotes?, timeout_s?} -> {ok, outputs, charts, stdout, stderr,
elapsed_ms, error}. Auth por X-Sandbox-Token (mismo secreto compartido que el
gateway). Cada ejecución: subproceso `python -I` con rlimits (CPU, memoria,
tamaño de fichero, descriptores), entorno mínimo, workdir tmpfs propio que se
borra al terminar, y kill de grupo al exceder el wall-timeout.

La frontera dura la pone el contenedor (compose): red interna solo con el
agente, rootfs read-only, cap_drop ALL, no-new-privileges, pids/mem/cpu caps.
"""
from __future__ import annotations

import asyncio
import json
import os
import resource
import shutil
import signal
import tempfile
import time
import uuid

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse

SANDBOX_TOKEN = os.getenv("SANDBOX_TOKEN", "").strip()
MAX_TIMEOUT_S = float(os.getenv("SANDBOX_MAX_TIMEOUT_S", "60"))
MAX_CODE_CHARS = int(os.getenv("SANDBOX_MAX_CODE_CHARS", "40000"))
MAX_STDOUT = 200_000
_CONCURRENCY = asyncio.Semaphore(int(os.getenv("SANDBOX_CONCURRENCY", "2")))

app = FastAPI(title="Tradeul Code Sandbox", default_response_class=ORJSONResponse)


def _limits(timeout_s: float):
    def apply() -> None:
        cpu = max(2, int(timeout_s))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 5))
        # 2.2GB de address space: OpenBLAS/numpy reservan arenas grandes por
        # thread; con un tope muy bajo el import de BLAS peta ("Memory
        # allocation still failed"). Se acota además con NUM_THREADS=1 abajo.
        resource.setrlimit(resource.RLIMIT_AS, (2_200_000_000, 2_200_000_000))
        resource.setrlimit(resource.RLIMIT_FSIZE, (25_000_000, 25_000_000))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        os.setsid()
    return apply


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
async def run(request: Request) -> dict:
    if SANDBOX_TOKEN and request.headers.get("X-Sandbox-Token", "") != SANDBOX_TOKEN:
        raise HTTPException(401, "bad token")
    try:
        body = orjson.loads(await request.body())
    except Exception:
        raise HTTPException(400, "invalid json")

    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "empty code")
    if len(code) > MAX_CODE_CHARS:
        raise HTTPException(400, f"code too large (>{MAX_CODE_CHARS} chars)")
    timeout_s = min(float(body.get("timeout_s") or 35), MAX_TIMEOUT_S)
    quotes = body.get("quotes") or {}

    run_dir = tempfile.mkdtemp(prefix=f"run-{uuid.uuid4().hex[:8]}-", dir="/tmp")
    t0 = time.time()
    try:
        with open(os.path.join(run_dir, "payload.json"), "wb") as fh:
            fh.write(orjson.dumps({"code": code, "quotes": quotes}))

        env = {
            "RUN_DIR": run_dir,
            "POLYGON_DIR": "/data/polygon",
            "HOME": run_dir,
            "MPLCONFIGDIR": run_dir,
            "MPLBACKEND": "Agg",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            # Un solo hilo de BLAS: evita que numpy/scipy/sklearn reserven una
            # arena por core (peta contra RLIMIT_AS) y hace el uso de CPU
            # determinista frente al RLIMIT_CPU.
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }

        async with _CONCURRENCY:
            proc = await asyncio.create_subprocess_exec(
                "python", "-I", "/app/bootstrap.py",
                cwd=run_dir, env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_limits(timeout_s),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s + 5)
            except asyncio.TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
                return {"ok": False, "error": f"execution exceeded {timeout_s:.0f}s wall limit",
                        "outputs": [], "charts": [], "stdout": "", "stderr": "",
                        "elapsed_ms": int((time.time() - t0) * 1000)}

        result_path = os.path.join(run_dir, "result.json")
        outputs, charts, run_error = [], [], None
        if os.path.exists(result_path):
            try:
                with open(result_path) as fh:
                    res = json.load(fh)
                outputs = res.get("outputs") or []
                charts = res.get("charts") or []
                run_error = res.get("error")
            except Exception as exc:  # noqa: BLE001
                run_error = f"result parse failed: {exc}"
        elif proc.returncode != 0:
            run_error = f"process died (rc={proc.returncode}) before writing results"

        return {
            "ok": proc.returncode == 0 and not run_error,
            "outputs": outputs,
            "charts": charts,
            "error": run_error,
            "stdout": stdout.decode(errors="replace")[-MAX_STDOUT:],
            "stderr": stderr.decode(errors="replace")[-8000:],
            "returncode": proc.returncode,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085, log_level="warning")
