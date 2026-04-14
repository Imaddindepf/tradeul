# 📰 News Alpha Engine - Breaking News Impact Predictor

## 🔌 CONEXIÓN A LA INSTANCIA GPU

```bash
ssh -i ~/.ssh/tradeul-gpu-key.pem ubuntu@35.180.173.149
```

**Detalles de la instancia:**
- **Tipo**: g4dn.xlarge (4 vCPU, 16GB RAM, Tesla T4 GPU)
- **Región**: eu-west-3 (Paris)
- **AMI**: Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.9 (Ubuntu 24.04)
- **Almacenamiento**: 200GB SSD

⚠️ **NOTA**: La IP cambia cada vez que se reinicia la instancia. Verificar en EC2 Console.

---

## 📋 ESTADO ACTUAL DEL PROYECTO (30 Dic 2025)

### ¿Qué estamos construyendo?
Un sistema que predice **en tiempo real** si una noticia financiera tendrá impacto significativo en el precio de una acción, analizando el movimiento **intradiario** (5min, 15min, 30min, 1h) desde el momento exacto de la noticia.

### Pipeline en progreso:

| Paso | Estado | Descripción |
|------|--------|-------------|
| 1. Filtrar noticias | ✅ Completado | 1,257,875 noticias con timestamp exacto |
| 2. Descargar minute bars | ✅ Completado | 599 días de datos (todos los tickers) |
| 3. Calcular impacto intradiario | 🔄 EN PROGRESO | Calculando para 1.1M noticias |
| 4. Normalizar por ATR | ⏳ Pendiente | |
| 5. Generar embeddings FinBERT | ⏳ Pendiente | |
| 6. Entrenar modelo multi-task | ⏳ Pendiente | |
| 7. Backtest realista | ⏳ Pendiente | |

### Script actualmente ejecutándose:
```bash
# Pipeline v3 (optimizado) corriendo en background
ps aux | grep pipeline_v3_fast  # Verificar si sigue activo
tail -f /home/ubuntu/news-alpha-engine/logs/pipeline_v3.log  # Ver progreso

# Tiempo estimado: ~34 minutos
# Velocidad: ~3.5s por día (583 días total)
```

---

## 📁 ESTRUCTURA DE ARCHIVOS EN LA INSTANCIA

```
/home/ubuntu/news-alpha-engine/
├── data/
│   ├── professional/
│   │   ├── news_all_sessions.parquet     # 1.26M noticias con timestamp exacto
│   │   └── impact_intraday_v2.parquet    # (SE GENERARÁ) Impacto calculado
│   │
│   ├── price_data/
│   │   ├── flatfiles_minute/             # 599 días de minute bars (YYYY-MM-DD.parquet)
│   │   ├── grouped/                       # 577 días de datos agrupados
│   │   └── daily/                        # Precios diarios para ATR
│   │
│   ├── news_unified.parquet              # Noticias combinadas (versión anterior)
│   ├── news_benzinga_full.parquet        # 1M noticias Polygon
│   └── news_brianferrell.parquet         # 500K noticias Brianferrell
│
├── scripts/
│   └── professional/
│       ├── pipeline_optimized_v2.py      # Pipeline v2 (lento, ~6h)
│       └── pipeline_v3_fast.py           # Pipeline v3 (optimizado, ~34min) ✅ ACTUAL
│
├── models/
│   └── production/
│       └── xgboost_full.json             # Modelo anterior (versión 2.0)
│
├── venv/                                  # Virtual environment Python
└── logs/
    └── pipeline_v2.log                   # Log del pipeline actual
```

---

## 🔧 COMANDOS ÚTILES

### Conectar y verificar estado:
```bash
# Conectar
ssh -i ~/.ssh/tradeul-gpu-key.pem ubuntu@35.180.173.149

# Activar entorno
cd /home/ubuntu/news-alpha-engine
source venv/bin/activate

# Ver RAM/CPU
htop

# Ver espacio disco
df -h

# Ver procesos Python
ps aux | grep python
```

### Ver progreso del pipeline:
```bash
tail -f logs/pipeline_v2.log
```

### Matar proceso si es necesario:
```bash
pkill -f pipeline_optimized_v2
```

### Verificar archivos generados:
```bash
ls -lh data/professional/*.parquet
```

---

##  DATOS DISPONIBLES

### Noticias (news_all_sessions.parquet):
```python
import pandas as pd
df = pd.read_parquet('data/professional/news_all_sessions.parquet')
# Columnas: id, ticker, title, published_ts, session, year
# Filas: 1,257,875
```

### Minute bars (flatfiles_minute/):
```python
# Cada archivo es un día, contiene TODOS los tickers
df = pd.read_parquet('data/price_data/flatfiles_minute/2023-01-03.parquet')
# Columnas: ticker, volume, open, close, high, low, window_start (nanosegundos), transactions
# Filas: ~1.5M por día
```

### Convertir window_start a timestamp:
```python
# window_start está en nanosegundos epoch
df['timestamp'] = pd.to_datetime(df['window_start'], unit='ns')
# O en DuckDB:
# to_timestamp(window_start / 1000000000) as timestamp
```

---

## 🎯 OBJETIVO FINAL

Crear un sistema que:
1. Recibe una noticia en tiempo real
2. Analiza su texto con FinBERT (embeddings)
3. Predice si tendrá impacto HIGH/MEDIUM/LOW
4. Predice dirección UP/DOWN
5. Da confianza (probabilidad)
6. Todo en <200ms

### Uso esperado:
```python
result = predict_news("FDA approves Pfizer cancer drug", ticker="PFE")
# {
#   "impact": "HIGH",
#   "direction": "UP", 
#   "confidence": 0.92,
#   "expected_move": "+2.3 ATRs"
# }
```

---

## 🐛 PROBLEMAS CONOCIDOS

### 1. OOM (Out of Memory)
- La instancia tiene 16GB RAM
- DuckDB con índices consume >12GB
- **Solución**: No crear índices, procesar día por día

### 2. Pipeline lento (~6 horas)
- El script actual hace 1 query por noticia
- **Solución**: Optimizar con batch queries (pipeline_v3.py)

### 3. IP cambia al reiniciar
- EBS persiste pero la IP pública cambia
- **Solución**: Verificar nueva IP en EC2 Console

---

## 📈 PRÓXIMOS PASOS (para el siguiente chat)

1. **Verificar que pipeline_v3 terminó** (~34 min desde 00:20 UTC):
   ```bash
   ls -lh data/professional/impact_intraday_v3.parquet
   ```

2. **Generar embeddings FinBERT** para 1.1M noticias:
   - Usar GPU Tesla T4
   - Batch size 32-64
   - Estimado: ~2-3 horas

3. **Entrenar modelo multi-task**:
   - Input: embeddings (768) + features (ATR, price)
   - Output: impact_class (HIGH/MED/LOW) + direction (UP/DOWN)
   - XGBoost o LightGBM

4. **Backtest con datos 2024+**:
   - Temporal split: train 2009-2023, test 2024+
   - Métricas: Sharpe, Win Rate, Max Drawdown

5. **Integrar con Tradeul**:
   - API REST para predicción en tiempo real
   - Webhook para noticias entrantes

---

## 🔑 CREDENCIALES

### Polygon API:
```bash
# En la instancia:
cat /home/ubuntu/news-alpha-engine/data/polygon_key.txt
# O en el .env local (Cursor):
grep POLYGON /opt/tradeul/.env
```

### SSH Key:
```
~/.ssh/tradeul-gpu-key.pem
```

---

## 📞 CONTEXTO PARA CONTINUACIÓN

**Resumen ejecutivo**: Estamos construyendo un predictor de impacto de noticias para trading de "breaking news". El dataset tiene 1.26M noticias con timestamps exactos y 599 días de minute bars. El pipeline v3 está calculando el impacto intradiario (5min, 15min, 30min, 1h) desde el momento exacto de cada noticia, normalizado por ATR.

**Última acción**: Se lanzó `pipeline_v3_fast.py` en background a las 00:20 UTC. 
- Velocidad: ~3.5s por día (10x más rápido que v2)
- Estimado: ~34 minutos para 583 días
- Output: `data/professional/impact_intraday_v3.parquet`

**Comando para verificar:**
```bash
ssh -i ~/.ssh/tradeul-gpu-key.pem ubuntu@35.180.173.149
tail -f /home/ubuntu/news-alpha-engine/logs/pipeline_v3.log
```

---

*Última actualización: 30 Dic 2025 00:25 UTC*
*Versión: 3.0-alpha (en desarrollo)*
