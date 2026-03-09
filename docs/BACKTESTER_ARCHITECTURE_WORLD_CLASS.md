# Arquitectura: backtester escalable, robusto y de nivel mundial

Documento de arquitectura desde la perspectiva de ingeniería: cómo estructurarlo para que sea **escalable**, **robusto** y el **mejor backtester del mundo** sin reescribir todo de golpe.

---

## 1. Qué significa “el mejor backtester del mundo”

En términos de arquitectura:

| Objetivo | Traducción técnica |
|----------|---------------------|
| **Rigor** | Cero look-ahead garantizado por diseño; fills reproducibles; métricas estándar y avanzadas (DSR, PSR, walk-forward, Monte Carlo). |
| **Escalable** | Soporta desde 1 ticker/1 año hasta miles de tickers/años sin reventar; ejecución paralelizable donde tenga sentido; datos por streaming o chunks si hace falta. |
| **Robusto** | Mismo config + mismos datos → mismo resultado (reproducibilidad); validación temprana; fallos acotados y mensajes claros; sin estado global oculto. |
| **Extensible** | Nuevos datos, universos, modelos de fill, métricas o tipos de salida se añaden por **contratos** (interfaces), no tocando el core. |
| **Inspección** | Cada trade trazable a barra y regla; resultados exportables y consultables; auditoría de “por qué entré/salí”. |

La arquitectura que sigue está pensada para cumplir eso.

---

## 2. Principios de diseño

1. **Un solo flujo, capas desacopladas**  
   Datos → Universo (opcional) → Señales → Simulación → Métricas → Inspección. Cada capa tiene una **entrada y una salida** bien definidas; no se saltan capas.

2. **Contratos, no implementaciones**  
   El “motor” depende de abstracciones (DataProvider, UniverseProvider, FillEstimator, etc.). Las implementaciones concretas (FLATS, Polygon REST, pipeline por día, fixed_bps, etc.) se inyectan.

3. **Inmutabilidad y reproducibilidad**  
   Config y datos de entrada no se mutan durante el run. Un run queda identificado por (config_hash, data_version, engine_version) para poder reproducir.

4. **Fail fast, mensajes útiles**  
   Validar config y datos al inicio; si algo falta o es incoherente, fallar con un error que indique qué corregir (tickers, fechas, columnas).

5. **Sin estado global en el engine**  
   El engine es stateless: recibe (config, datos o referencia a datos) y devuelve resultado. El estado vive en el run (positions, equity) dentro de la simulación, no en singletons.

---

## 3. Arquitectura en capas (visión objetivo)

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    ORCHESTRATOR                          │
                    │  run(config) → valida → coordina capas → BacktestResult  │
                    └─────────────────────────────────────────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         │                                │                                │
         ▼                                ▼                                ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│   DATA LAYER    │            │  UNIVERSE LAYER  │            │  SIGNAL LAYER   │
│                 │            │   (opcional)     │            │                 │
│ IDataProvider   │───────────▶│ IUniverseProvider│───────────▶│ ISignalGenerator │
│ • load_bars()   │  bars      │ • get_tickers(d) │  tickers   │ • entries(df)   │
│ • schema        │            │ • pipeline      │  per day   │ • exits(df)     │
└─────────────────┘            └─────────────────┘            └─────────────────┘
         │                                │                                │
         │                                │                                │
         └────────────────────────────────┼────────────────────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │                 SIMULATION CORE                          │
                    │  • Recibe: bars + entry/exit masks + SessionClock (opcional) │
                    │  • Usa: IFillEstimator, IPositionSizer                    │
                    │  • Produce: List[TradeRecord], equity curve, warnings      │
                    └─────────────────────────────────────────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         ▼                                ▼                                ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│  METRICS LAYER  │            │ INSPECTION LAYER│            │  EXPORT LAYER   │
│                 │            │                 │            │                 │
│ IMetricsCompute │            │ trades_by_date  │            │ CSV / Parquet   │
│ • core          │            │ trades_by_ticker│            │ • config        │
│ • advanced      │            │ daily_summary   │            │ • trades        │
│ • walk_forward  │            │ filter, sort    │            │ • equity        │
│ • monte_carlo   │            │                 │            │                 │
└─────────────────┘            └─────────────────┘            └─────────────────┘
```

- **Orchestrator**: un único punto de entrada `run(config)`; valida, resuelve universo (si aplica), pide datos, pide señales, llama al simulation core, luego métricas e inspección. No contiene lógica de negocio; solo coordina.
- **Data / Universe / Signal**: cada uno con interfaz; el core solo ve “barras + máscaras de entrada/salida (+ opcionalmente reloj de sesión)”.
- **Simulation core**: loop por ticker/barra; no sabe de dónde vienen los datos ni cómo se generaron las señales; solo aplica reglas de entrada/salida, fill y position sizing.
- **Métricas / Inspección / Export**: consumen `BacktestResult` (trades + equity + config); no dependen del engine.

---

## 4. Contratos (interfaces) que haría

Definirías estos protocolos o ABCs en un módulo `core/contracts.py` (o `core/abstractions.py`). El engine y el orchestrator dependen de ellos; las implementaciones viven en módulos concretos.

### 4.1 Datos

```python
class IDataProvider(Protocol):
    async def load_bars(
        self,
        start: date,
        end: date,
        tickers: list[str],
        timeframe: Timeframe,
    ) -> pd.DataFrame:
        """Barras OHLCV; columnas mínimas: ticker, date|timestamp, open, high, low, close, volume."""
        ...

    def get_schema(self) -> list[str]:
        """Columnas garantizadas después de load_bars (incl. timestamp si intraday)."""
        ...
```

- Implementaciones: `FLATSDataProvider` (actual DataLayer), `PolygonRESTDataProvider`, o un `CompositeDataProvider` que usa FLATS y rellena huecos con REST. El resto del sistema no sabe qué backend es.

### 4.2 Universo

```python
class IUniverseProvider(Protocol):
    def get_tickers_for_date(self, d: date) -> set[str]:
        """Tickers candidatos para esa fecha (screening diario)."""
        ...

    # O bien, para no llamar día a día durante la simulación:
    def get_tickers_by_date(self, start: date, end: date) -> dict[date, set[str]]:
        """Precomputado: mapa fecha → set(tickers)."""
        ...
```

- Implementación “lista fija”: devuelve siempre los mismos tickers para cualquier fecha.
- Implementación “pipeline”: usa datos diarios (o precomputados) y reglas (liquidez, precio, MA) para devolver el set por día. El simulation core solo necesita “¿este ticker está permitido este día?”.

### 4.3 Señales

```python
class ISignalGenerator(Protocol):
    def compute_entries(self, bars: pd.DataFrame, config: StrategyConfig) -> pd.Series:
        """Máscara booleana por fila: True = señal de entrada."""
        ...

    def compute_exits(self, bars: pd.DataFrame, config: StrategyConfig) -> pd.Series | None:
        """Máscara opcional para exit por señal."""
        ...
```

- Implementaciones: `TemplateSignalGenerator` (señales + operadores actuales), `CodeSignalGenerator` (strategy(bars) en Python). El simulation core solo recibe las máscaras.

### 4.4 Fill y position sizing

```python
class IFillEstimator(Protocol):
    def estimate_fill(
        self,
        side: Literal["buy", "sell"],
        bar: BarView,
        order_value: float,
        config: FillConfig,
    ) -> FillResult:
        ...
```

- Implementaciones: `FixedBPSFill`, `VolumeBasedFill`, `SpreadBasedFill` (ya los tienes; se encapsulan detrás del protocolo).  
- `IPositionSizer`: dado equity y config, devuelve dólares (o shares) por operación. Implementaciones: `PctPositionSizer`, `DollarsPositionSizer`, `SharesPositionSizer`.

### 4.5 Reloj de sesión (timing intraday)

```python
class ISessionClock(Protocol):
    """Por barra, responde: minutos desde open, minutos hasta close, ¿dentro de ventana de entrada?"""
    def minutes_since_open(self, bar_index: int, bar_date: date, ticker_bars: pd.DataFrame) -> int:
        ...
    def minutes_until_close(self, bar_index: int, bar_date: date, ticker_bars: pd.DataFrame) -> int:
        ...
    def is_within_entry_window(self, ...) -> bool:
        ...
```

- Implementación: con barras 1min y timestamp, se calcula por día; el simulation core pregunta “¿estoy en ventana?” sin saber si es 9:30–16:00 o configurable. Así el core sigue siendo agnóstico al huso horario o al mercado.

Con estos contratos, puedes añadir nuevos proveedores de datos, universos, modelos de fill o relojes sin tocar el loop de simulación.

---

## 5. Escalabilidad

| Dimensión | Estrategia |
|-----------|------------|
| **Más tickers / más años** | (1) Cargar datos por chunks (p.ej. por año o por 100 tickers) y simular por chunk, luego concatenar trades y equity de forma consistente. (2) O bien streaming: el DataProvider expone un iterator/async generator de DataFrames por ticker o por ventana de fechas; el simulation core consume barra a barra o por bloques. Hoy no lo necesitas para “miles de tickers”, pero el contrato IDataProvider puede devolver un “lazy” wrapper que cargue bajo demanda. |
| **Múltiples runs en paralelo** | El engine es stateless: cada run es un proceso o tarea independiente. En la API, cada request puede ser un asyncio.Task; si más adelante quieres grid/optimización masiva, un worker queue (Celery, RQ, o un pool de procesos) ejecuta N runs con distintos configs. No compartir estado entre runs. |
| **Datos muy grandes** | Si un día los barras no caben en memoria: (1) particionar por ticker y procesar ticker a ticker (ya lo haces); (2) o particionar por tiempo y tener un “merge” de equity/trades al final. La clave es que el simulation core procese en ventanas acotadas y que la agregación de resultados sea asociativa. |

No hace falta hoy un cluster distribuido; la arquitectura permite escalar “verticalmente” (chunks, iterators) y “horizontalmente” (varios runs en paralelo) sin cambiar las interfaces.

---

## 6. Robustez

| Aspecto | Cómo lograrlo |
|---------|----------------|
| **Reproducibilidad** | (1) Config inmutable; (2) versión de datos: checksum o (start, end, tickers, source) en el resultado; (3) versión del engine en BacktestResult; (4) semilla fija en cualquier aleatoriedad (Monte Carlo). Así “mismo config + mismos datos + misma versión” = mismo resultado. |
| **Validación** | Validar al inicio del run: fechas (start < end, dentro de rango disponible), tickers no vacíos, columnas requeridas presentes, valores numéricos (slippage_bps ≥ 0, etc.). Si falla, mensaje claro: “Missing column: vwap for volume_based fill”. |
| **Límites y timeouts** | Límite de barras o de tickers por run (configurable) para no colgar el servicio; timeout en carga de datos (REST); en simulación, si se excede un umbral de tiempo, opcionalmente abortar y devolver parcial (o no, según política). |
| **Errores acotados** | En el loop, si un ticker falla (p.ej. datos corruptos), registrar warning y seguir con el resto; o marcar el run como “partial” y listar tickers fallidos. No un solo fallo reviente todo el backtest. |
| **Auditoría** | Cada TradeRecord con bar index (o timestamp) de entrada y salida; opcionalmente guardar en resultado el “motivo de salida” (TARGET, STOP_LOSS, EOD, etc.). Así la inspección puede responder “por qué salí”. |

---

## 7. Estructura de módulos (objetivo)

```
services/backtester/
├── core/
│   ├── contracts.py          # Protocolos: IDataProvider, IUniverseProvider, IFillEstimator, ...
│   ├── orchestrator.py       # run(config) → BacktestResult; coordina capas
│   ├── simulation.py         # Loop de simulación puro (sin carga de datos ni señales)
│   ├── data/                 # Implementaciones de datos
│   │   ├── flats_provider.py # FLATS + REST (actual DataLayer refactorizado)
│   │   └── ...
│   ├── universe/             # Implementaciones de universo
│   │   ├── fixed_list.py     # Lista fija de tickers
│   │   └── pipeline.py       # Screening por día (liquidez, precio, ...)
│   ├── signals/              # Generación de señales
│   │   ├── template.py       # Señales + operadores (actual evaluate_entries)
│   │   └── code.py           # strategy(bars) Python
│   ├── fill/                 # Modelos de fill
│   │   ├── fixed_bps.py
│   │   ├── volume_based.py
│   │   └── ...
│   ├── session_clock.py      # ISessionClock para intraday
│   ├── models.py             # Pydantic: StrategyConfig, TradeRecord, BacktestResult, ...
│   ├── metrics.py            # Core + advanced (usa solo trades + equity)
│   └── inspection.py         # trades_by_date, daily_summary, to_dataframe, export
├── analysis/
│   ├── walk_forward.py
│   └── monte_carlo.py
├── api/                      # FastAPI: endpoints que usan orchestrator
│   └── routes.py
└── main.py                   # App + lifespan (inyección de DataLayer, etc.)
```

- **contracts.py**: define los Protocol; el resto importa desde ahí.
- **orchestrator.py**: tiene la lógica de “cargar datos → (opcional) universo por día → señales → simulation.run(bars, entry_mask, exit_mask, …) → métricas → BacktestResult”. No hace cálculos de fill ni de señales; solo ensambla.
- **simulation.py**: el loop actual de `_simulate` extraído a un módulo que recibe barras, máscaras, config de fill/sizing/session_clock y devuelve trades + equity + warnings. Depende de IFillEstimator, IPositionSizer, ISessionClock (opcional).

Así puedes testear el simulation core con barras sintéticas y mocks; testear el orchestrator con un DataProvider mock; y cambiar implementaciones sin tocar el core.

---

## 8. Cómo llegar desde el código actual

No reescribir todo de una vez:

1. **Fase A – Extraer simulación**  
   Mover el loop de `_simulate` a `simulation.py` como función o clase `run_simulation(bars_df, entry_mask, exit_sig, config, fill_estimator, ...)`. El `BacktestEngine` llama a esa función. Así el “core” ya está aislado.

2. **Fase B – Introducir contratos**  
   Definir en `contracts.py` los protocolos. Hacer que el actual `DataLayer` implemente `IDataProvider` (adaptador fino). Hacer que `estimate_fill` esté detrás de `IFillEstimator`. El engine/orchestrator reciben interfaces; por ahora una sola implementación cada una.

3. **Fase C – Orchestrator**  
   Crear `orchestrator.py`: `run(config)` que (1) valida config, (2) obtiene tickers (lista fija o universe.get_tickers_by_date), (3) carga datos vía IDataProvider, (4) genera señales vía ISignalGenerator, (5) llama a simulation.run(...), (6) calcula métricas, (7) devuelve BacktestResult. El `BacktestEngine` actual puede convertirse en un thin wrapper que construye los implementadores concretos y llama al orchestrator.

4. **Fase D – Universe y session clock**  
   Añadir `IUniverseProvider` con implementación “lista fija”; después implementación “pipeline”. Añadir `ISessionClock` e inyectarlo en la simulación para timing intraday (ventana de entrada, salida antes del cierre).

5. **Fase E – Inspección y export**  
   Módulo `inspection.py` y, si aplica, endpoints de export/filtrado de trades. Sin tocar el simulation core.

Cada fase mantiene el sistema estable y desplegable; la arquitectura “objetivo” se alcanza por pasos.

---

## 9. Resumen

- **Escalable**: contratos que permiten chunks/streaming y runs paralelos; simulation core stateless.
- **Robusto**: validación temprana, inmutabilidad, reproducibilidad (config + data + version), errores acotados, auditoría en trades.
- **Mejor backtester del mundo**: rigor (cero look-ahead, fills realistas), métricas profesionales, flexibilidad (universo fijo o dinámico, timing intraday), inspección total sobre el resultado.

La arquitectura se basa en **capas con contratos**, **orchestrator que coordina** y **simulation core que no sabe de datos ni de señales**, más un camino de **migración incremental** desde el código actual. Así un ingeniero puede construir el mejor backtester del mundo sin un big bang rewrite.
