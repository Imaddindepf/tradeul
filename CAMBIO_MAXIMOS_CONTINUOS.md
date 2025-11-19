# 🔥 CAMBIO: Máximos Continuos (Active Breakouts)

## 📋 RESUMEN

**Problema anterior:**
- USHY aparecía en "Máximos del día" aunque llevaba 30+ minutos sin hacer nuevos máximos
- El sistema mostraba tickers que estaban "cerca" (2%) de un máximo antiguo
- No diferenciaba entre un ticker estancado vs uno con momentum alcista continuo

**Solución implementada:**
- Nuevo sistema de **tracking de máximos continuos**
- Solo muestra tickers que ACTIVAMENTE están haciendo nuevos máximos
- Identifica momentum alcista real, no solo proximidad a máximos

---

## 🎯 LÓGICA DEL NUEVO SISTEMA

### Criterios para "Nuevo Máximo Activo":

Un ticker aparece en **NEW_HIGHS** solo si cumple:

1. **Criterio temporal:**
   - Hizo un nuevo máximo en los últimos **5 minutos**
   
   O

2. **Criterio de frecuencia:**
   - Ha hecho **2 o más máximos** en los últimos **15 minutos**

### Ejemplo Real:

**Ticker AAPL:**
- 10:00 AM → $150.00 (nuevo máximo) ✅
- 10:02 AM → $150.50 (nuevo máximo) ✅
- 10:05 AM → $150.30 (no es máximo, pero está dentro de 5 min del último) ✅
- 10:11 AM → $150.25 (más de 5 min sin máximo, pero tiene 2 máximos en 15 min) ✅
- 10:20 AM → $150.20 (más de 5 min sin máximo, solo 1 máximo en últimos 15 min) ❌

**Resultado:** AAPL sale de la tabla en 10:20 AM porque ya NO está activamente haciendo máximos.

---

## 🛠️ ARCHIVOS MODIFICADOS

### 1. `gap_calculator.py` (NUEVO)
- ✅ Nueva clase: `HighsLowsTracker`
- Rastrea cada vez que un ticker hace un nuevo máximo/mínimo
- Guarda timestamp del último máximo
- Cuenta frecuencia de máximos en ventana de 15 minutos

### 2. `scanner_engine.py` (ACTUALIZADO)
- ✅ Inicializa `HighsLowsTracker` con ventana de 5 minutos
- ✅ Actualiza tracker en cada scan (líneas 435-441)
- ✅ Pasa tracker al categorizador

### 3. `scanner_categories.py` (ACTUALIZADO)
- ✅ Acepta `highs_lows_tracker` en constructor
- ✅ Nueva lógica para NEW_HIGHS (líneas 133-156)
- ✅ Nueva lógica para NEW_LOWS
- ✅ Fallback a lógica antigua si no hay tracker

---

## 📊 MÉTRICAS RASTREADAS

Para cada ticker, el sistema rastrea:

```python
{
    'high': 150.50,                    # Máximo actual del día
    'high_timestamp': datetime(...),   # Cuándo se hizo el último máximo
    'high_count_15min': 3,             # Cuántos máximos en últimos 15 min
    'low': 148.20,                     # Mínimo actual del día
    'low_timestamp': datetime(...),    # Cuándo se hizo el último mínimo
    'low_count_15min': 1,              # Cuántos mínimos en últimos 15 min
    'history': [                       # Historial de máximos/mínimos
        (datetime(10, 0), 'high'),
        (datetime(10, 2), 'high'),
        (datetime(10, 5), 'high')
    ]
}
```

---

## ⚙️ CONFIGURACIÓN

### Ajustar tiempo de "máximo activo":

En `scanner_engine.py` línea 75:

```python
# Cambiar de 5 minutos a 3 minutos (más estricto)
self.highs_lows_tracker = HighsLowsTracker(max_age_seconds=180)  # 3 minutos

# O más permisivo (10 minutos)
self.highs_lows_tracker = HighsLowsTracker(max_age_seconds=600)  # 10 minutos
```

### Ajustar frecuencia mínima de máximos:

En `gap_calculator.py` línea 321:

```python
# Cambiar de 2 máximos a 3 máximos en 15 min (más estricto)
if data['high_count_15min'] >= 3:
    return True
```

---

## 🧪 CÓMO PROBARLO

### 1. Reiniciar el servicio Scanner:

```bash
docker-compose restart scanner
```

### 2. Monitorear logs del Scanner:

```bash
docker-compose logs -f scanner | grep "NEW HIGH"
```

Verás logs como:
```
🔥 NEW HIGH: AAPL price=150.50 high_count=3
```

### 3. Verificar en el Frontend:

- Ir a la tabla **"Nuevos Máximos"**
- Verificar que solo aparecen tickers con momentum activo
- Observar que tickers como USHY **desaparecen** después de 5 min sin hacer máximos

### 4. Probar manualmente en Python:

```python
from gap_calculator import HighsLowsTracker
from datetime import datetime, timedelta

tracker = HighsLowsTracker(max_age_seconds=300)

# Simular AAPL haciendo máximos
now = datetime.now()
tracker.update_ticker('AAPL', 150.0, now)
tracker.update_ticker('AAPL', 150.5, now + timedelta(minutes=2))

# Verificar si está activo
is_active = tracker.is_making_new_highs('AAPL', now + timedelta(minutes=3))
print(f"AAPL activo: {is_active}")  # True (último máximo hace 1 min)

# 10 minutos después
is_active = tracker.is_making_new_highs('AAPL', now + timedelta(minutes=12))
print(f"AAPL activo: {is_active}")  # False (último máximo hace 10 min)
```

---

## 📈 BENEFICIOS

### Para Traders:

1. **Momentum Real:** Solo ven tickers que ACTUALMENTE están subiendo
2. **Menos Ruido:** No ven tickers estancados en máximos antiguos
3. **Oportunidades Activas:** Identifican breakouts en tiempo real
4. **Timing Mejor:** Entran cuando hay momentum, no cuando ya pasó

### Ejemplo de uso:

Un trader ve que **NVDA** aparece en "Nuevos Máximos":
- Sabe que hizo un máximo hace menos de 5 minutos
- Tiene confianza de que hay buyers activos
- Puede entrar con mejor timing
- Si NVDA permanece 10+ minutos, el sistema lo quita automáticamente

---

## 🎛️ PARÁMETROS RECOMENDADOS

### Configuración Conservadora (menos tickers, mayor calidad):
```python
HighsLowsTracker(max_age_seconds=180)  # 3 minutos
high_count_15min >= 3  # 3+ máximos en 15 min
```

### Configuración Balanceada (recomendada):
```python
HighsLowsTracker(max_age_seconds=300)  # 5 minutos
high_count_15min >= 2  # 2+ máximos en 15 min
```

### Configuración Permisiva (más tickers):
```python
HighsLowsTracker(max_age_seconds=600)  # 10 minutos
high_count_15min >= 1  # 1+ máximo en 15 min
```

---

## 🔄 LIMPIEZA AUTOMÁTICA

El tracker limpia datos automáticamente:

1. **Historial antiguo:** Elimina máximos > 15 minutos (línea 292)
2. **Nuevo día:** Se limpia al inicio del día (método `clear_for_new_day()`)
3. **Memoria eficiente:** Solo guarda últimos 15 minutos por ticker

---

## 📝 NOTAS TÉCNICAS

- El tracker funciona **solo en memoria** (no persiste en Redis)
- Se reinicia cuando el servicio Scanner se reinicia
- Compatible con pre-market, market hours, y post-market
- Usa `intraday_high`/`intraday_low` (incluye pre/post market)

---

## ✅ PRÓXIMOS PASOS

1. ✅ Sistema implementado
2. ⏳ Reiniciar servicio Scanner
3. ⏳ Verificar logs y comportamiento
4. ⏳ Ajustar parámetros según feedback de traders
5. ⏳ Opcional: Agregar métricas al dashboard (cuántos máximos/15min)

---

## 🆘 TROUBLESHOOTING

### Problema: No aparecen tickers en "Nuevos Máximos"

**Solución:**
- Verificar que Scanner está corriendo: `docker-compose ps scanner`
- Verificar logs: `docker-compose logs scanner | grep "NEW HIGH"`
- Probar con configuración más permisiva (10 minutos)

### Problema: Aparecen demasiados tickers

**Solución:**
- Configuración más estricta (3 minutos)
- Aumentar frecuencia mínima a 3 máximos en 15 min

### Problema: USHY sigue apareciendo

**Solución:**
- Verificar que el servicio Scanner se reinició correctamente
- Verificar logs para confirmar que el tracker está funcionando
- Esperar 5-10 minutos para que el sistema se estabilice

---

## 📞 CONTACTO

Si tienes dudas o necesitas ajustes adicionales, házmelo saber.

**Cambio implementado:** 18 Nov 2025

