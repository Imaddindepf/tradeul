# Sandbox de ejecución de código generado por LLM (Fase 4b).
#
# La frontera de seguridad es el CONTENEDOR, endurecido desde compose:
#   - red interna dedicada solo agente<->sandbox (sin ruta a redis/postgres/
#     gateway ni salida a internet)
#   - rootfs read-only + /tmp tmpfs
#   - cap_drop ALL, no-new-privileges, mem/cpu/pids limitados
# Dentro, cada ejecución corre en un subproceso `python -I` con rlimits
# propios (CPU, memoria, ficheros) y entorno vacío.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    fastapi==0.115.* uvicorn==0.30.* orjson \
    pandas numpy matplotlib plotly scipy scikit-learn ta duckdb pyarrow

RUN useradd -m -u 10001 sandbox
WORKDIR /app
COPY main.py bootstrap.py /app/
USER 10001
ENV MPLBACKEND=Agg
CMD ["python", "main.py"]
