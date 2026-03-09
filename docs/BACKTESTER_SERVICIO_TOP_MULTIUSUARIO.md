# Backtester como servicio top y multi-usuario

Análisis completo: arquitectura limpia, soporte para muchos usuarios, cola de trabajos, y ventana flotante en la UI. Incluye opción de **nuevo servicio** o refactor del actual.

---

## 1. Objetivos

- **Muchos usuarios:** Autenticación por usuario; cola de jobs; límites por usuario (concurrentes, diarios); resultados guardados por usuario.
- **Experiencia top:** Ventana flotante usable desde cualquier pantalla; progreso en tiempo real; resultados ricos (tabs, gráficos, export); no bloquear la UI.
- **Arquitectura limpia:** Capas bien definidas (API → Application → Domain → Infrastructure); contratos; testable; desacoplado de framework y de almacenamiento.
- **Escalable:** Workers independientes para ejecutar backtests; API stateless; horizontal scaling de workers.

---

## 2. ¿Nuevo servicio o refactor del actual?

**Recomendación: un solo servicio backtester**, reestructurado por capas y con nuevos componentes (cola, almacenamiento de jobs/resultados, API de jobs). No hace falta un segundo microservicio; el mismo contenedor expone la API actual y la nueva API de jobs.

- Ventaja: un solo despliegue, un solo puerto, datos (FLATS) y configuración ya compartidos.
- Si en el futuro crece mucho (miles de jobs/día), se podría separar "API + cola" y "workers" en dos servicios; por ahora workers en el mismo servicio (o réplicas consumiendo la cola) es suficiente.

---

## 3. Arquitectura limpia (capas)

Estructura tipo hexagonal: el **dominio** (motor de backtest) no depende de HTTP ni de Redis; la **infraestructura** implementa los puertos.

**ADAPTERS (Entrada/Salida)**  
REST API (FastAPI): `/api/v1/backtest`, `/api/v1/backtest/code`, `/api/v1/jobs` (POST, GET :id, GET :id/result, DELETE :id). Opcional: WebSocket o SSE para progreso. Request → DTO → Use Case; Response ← DTO ← Use Case.

**APPLICATION (Use Cases)**  
- RunBacktestSyncUseCase: validar → ejecutar motor → devolver resultado.  
- SubmitBacktestJobUseCase: validar → crear job en cola → devolver job_id.  
- GetJobStatusUseCase / GetJobResultUseCase: leer de JobRepository.  
- ListUserJobsUseCase: listar jobs del usuario (filtros, paginación).  
Dependen de puertos: IBacktestEngine, IJobQueue, IJobRepository.

**DOMAIN**  
Engine (orchestrator + simulation), contratos (IDataProvider, IUniverseProvider, IFillEstimator), modelos (StrategyConfig, BacktestResult, TradeRecord). Sin dependencias de FastAPI, Redis, DB.

**INFRASTRUCTURE**  
JobQueue (Redis RQ o Celery), JobRepository (Redis + opcional Postgres para metadata, S3 o Redis para resultado), Worker (consume cola, llama use case, guarda resultado), DataLayer, FillModel.

---

## 4. Multi-usuario: qué hace falta

- **Identidad:** Cada request lleva `user_id` (JWT, API key, o header `X-User-Id`). Los use cases asocian job ↔ user_id.
- **Límites por usuario:** Jobs **concurrentes** (ej. 2) y opcionalmente **diarios** (ej. 50). Se comprueban en SubmitBacktestJobUseCase; si se excede, 429.
- **Almacenamiento de jobs:** job_id, user_id, status (queued / running / completed / failed), created_at, started_at, finished_at, request_payload, result o error_message. TTL para borrar resultados viejos (ej. 7 días).
- **Listado y borrado:** GET /api/v1/jobs (filtrado por user_id), DELETE /api/v1/jobs/:id (solo si pertenece al usuario).

El motor no conoce usuarios; solo el use case y el repositorio.

---

## 5. API pública (diseño)

- **POST /api/v1/backtest** — Síncrono (como hoy). StrategyConfig → BacktestResponse. Timeout corto (ej. 2 min).
- **POST /api/v1/backtest/code** — Síncrono (como hoy). code + tickers + fechas → BacktestResponse.
- **POST /api/v1/backtest/natural** — Asíncrono. Body: prompt, tickers. Respuesta: job_id. Cliente hace polling a GET /jobs/:id o SSE.
- **POST /api/v1/jobs** — Genérico asíncrono. Mismo body que backtest o backtest/code. Respuesta: job_id.
- **GET /api/v1/jobs/:id** — Estado: job_id, status, progress_pct, message, result (si completed), error (si failed).
- **GET /api/v1/jobs/:id/result** — Solo resultado (BacktestResult) si completed.
- **GET /api/v1/jobs** — Lista jobs del usuario (query: user_id, status, limit, offset).
- **DELETE /api/v1/jobs/:id** — Cancelar (queued) o borrar (completed/failed).
- **GET /api/v1/backtest/indicators** — Lista indicadores (como hoy).

Progreso: worker actualiza progress_pct y message en JobRepository; GET /jobs/:id los devuelve. Opcional: SSE.

---

## 6. Cola y workers

- **Cola:** Redis con RQ (Redis Queue) o Celery. Mensaje: payload del backtest (template o code) + user_id + job_id.
- **Worker:** Proceso que (1) saca job de la cola, (2) actualiza estado a running, (3) invoca RunBacktestSyncUseCase, (4) actualiza progreso si el motor soporta callback, (5) guarda resultado y estado completed/failed.
- **Escalado:** Varios workers consumiendo la misma cola. Límite por usuario: solo contar jobs en estado running de ese user_id.

---

## 7. Almacenamiento de jobs y resultados

- **Metadata del job:** Redis (hash por job_id) o Postgres (tabla backtest_jobs): job_id, user_id, status, progress_pct, message, created_at, started_at, finished_at.
- **Resultado (BacktestResult):** Redis (JSON, TTL 7 días) o S3 con clave jobs/{job_id}/result.json.
- **Listado por usuario:** Postgres (user_id, created_at) o Redis (listas por user_id).

Recomendación mínima: Redis para metadata + resultado con TTL. Si hay Postgres, tabla backtest_jobs para listado y auditoría.

---

## 8. Floating window (UI)

Objetivo: ventana flotante abierta desde cualquier parte (toolbar, /backtest, botón "Backtest"), no bloqueante.

**Apertura y posición:** Panel lateral (drawer) o modal flotante redimensionable; arrastrable por barra de título; tamaño por defecto ej. 480px × 80vh. Estado en contexto (y opcional sessionStorage para job en curso).

**Estados de la ventana:**

1. **Idle / Input:** Título "Backtest". Textarea o selector "Lenguaje natural" vs "Configuración avanzada". Botón "Ejecutar". Al ejecutar (async): POST a /jobs o /backtest/natural → job_id → estado "En cola / Ejecutando".
2. **En cola:** Mensaje "Tu backtest está en cola".
3. **Ejecutando:** Barra de progreso (progress_pct) y mensaje. Polling GET /jobs/:id cada 1–2 s o SSE. Botón "Cancelar".
4. **Completado:** Tabs Resumen, Equity, Trades, Calendario, Avanzado (reutilizar BacktestResultsPanel). Botones "Nuevo backtest", "Exportar CSV", "Guardar estrategia". Minimizable a barra.
5. **Error:** Mensaje claro, "Reintentar" o "Cerrar".

**Integración:** BacktestFloatingProvider (React context): open, mode, jobId, result, progress. Acciones: openPanel, closePanel, submitPrompt, pollJob, minimize, expand. BacktestFloatingWindow en portal (document.body), fixed, z-index alto. Una sola instancia global.

**Wireframe conceptual:** Barra superior con título y controles [_] [□] [×]. Zona de input (textarea + tickers + Ejecutar). Zona de progreso (barra + % + mensaje). Zona de resultado (tabs + métricas + acciones).

---

## 9. Estructura de carpetas (servicio backtester)

Propuesta de layout (refactor en el mismo repo):

```
services/backtester/
  api/
    deps.py           # Auth, user_id, rate limit
    routes/
      backtest.py     # POST /backtest, /backtest/code
      jobs.py         # POST/GET/DELETE /jobs
      natural.py      # POST /backtest/natural → job_id
    schemas.py        # Request/Response DTOs
  application/
    run_backtest_sync.py
    submit_backtest_job.py
    get_job_status.py
    list_jobs.py
    ports.py          # IBacktestEngine, IJobQueue, IJobRepository
  domain/
    contracts.py
    engine.py
    models.py
  infrastructure/
    data/
    queue/
    job_repository.py
    fill_model.py
  workers/
    backtest_worker.py
  config.py
  main.py
  Dockerfile
```

main.py: crea DataLayer, Engine, JobQueue, JobRepository; registra routers. Worker: python -m workers.backtest_worker (o rq worker), misma Redis, escribe en JobRepository.

---

## 10. Orden de implementación

1. **Fase 1 – Cola y jobs sin auth:** Redis en backtester; IJobQueue, IJobRepository (Redis). Endpoints POST/GET /jobs, GET /jobs/:id/result. Worker que consume y guarda resultado. Sin user_id.
2. **Fase 2 – Multi-usuario:** user_id en request; guardar en job; límite concurrentes (y opcional diario); GET/DELETE filtrado por usuario.
3. **Fase 3 – Natural vía jobs:** POST /backtest/natural devuelve job_id; cliente hace polling. LLM en backtester o en API Gateway/Agent que llame a POST /jobs.
4. **Fase 4 – Floating window:** BacktestFloatingProvider + BacktestFloatingWindow; estados idle → running (polling) → completed/error; integrar panel de resultados actual.
5. **Fase 5 – Progreso y pulido:** Worker actualiza progress en repo; GET /jobs/:id lo devuelve; opcional SSE; TTL y limpieza; docs y límites.

---

## 11. Resumen

- **Arquitectura limpia:** Adapters → Application (use cases) → Domain (motor, contratos) → Infrastructure (cola, repo, datos). Un solo servicio refactorizado.
- **Multi-usuario:** user_id por job; límites concurrencia/diarios; listado y borrado por usuario.
- **Escalable:** Cola Redis + workers; API stateless; resultados con TTL.
- **Floating window:** Ventana global (panel/modal), input → cola → progreso → resultado en tabs; minimizable y no bloqueante.
- **Fases:** Cola y jobs → user_id y límites → natural → UI flotante → progreso y pulido.

Con esto el backtester queda listo para muchos usuarios, experiencia top y base de código ordenada.
