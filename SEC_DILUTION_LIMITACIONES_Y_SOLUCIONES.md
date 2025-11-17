# SEC Dilution System - Limitaciones y Soluciones

## ❌ Problema Actual: CMBM Datos Incompletos

### Lo Que Falta (Según AskedGar)

**Warrants que NO capturamos:**

- Feb 2025: 3.5M warrants @ $1.70 (Armistice, H.C. Wainwright)
- July 2024: 947k warrants @ $10.55 (Armistice, Alto, etc.)
- Jan 2024 Series A: 433k @ $20.75 (3i, LP)
- Jan 2024 Series B: 216k @ $20.75 (3i, LP)
- Dec 2023: 63k @ $14.00 (3i, LP)
- **Total: ~6.2M warrants**

**Shelfs que NO capturamos:**

- Dec 2023: $100M shelf (activo hasta 2026)
- Solo capturamos shelfs viejos de 2020-2021 (YA EXPIRADOS)

**ATM que NO capturamos:**

- ATM con H.C. Wainwright (activo en 2024-2025)

---

## 🔍 Análisis del Problema

### 1. Los Warrants Están en Múltiples Lugares

**Dónde están los warrants de CMBM:**

- ✅ 10-K 2024: Tabla de equity (menciona warrant liability)
- ✅ 424B5 Feb 2025: Detalles del offering con Armistice
- ✅ 424B5 July 2024: Detalles del offering
- ✅ 424B5 Jan 2024: Series A y B
- ✅ S-3 Dec 2023: Prospectus del shelf con warrants

**Problema:**

- Solo descargamos 10 filings
- No priorizamos 424B5 recientes
- Grok tiene límite de tokens (~200k tokens)
- Necesitaríamos descargar y analizar 20-30 filings

### 2. Shelfs Expirados vs Activos

**Problema:**

- Capturamos S-3 de 2020 y 2021 (YA EXPIRADOS)
- No filtramos por regla de 3 años
- Falta S-3 de Dec 2023 ($100M activo)

**Causa:**

- Filtro de "3 años" no se está aplicando correctamente
- Necesitamos buscar S-3 específicamente en 2023-2024

### 3. Límites de Grok API

**Problema:**

- Grok puede analizar ~200k tokens
- Cada filing tiene 50k-100k caracteres
- Solo podemos enviar 2-3 filings completos
- Los warrants pueden estar en el filing #15

---

## 💡 Soluciones Posibles

### Opción A: Multi-Pass con Grok (IMPLEMENTABLE)

**Estrategia:**

1. **Primera pasada**: 10-K reciente → Extraer tabla de warrants summary
2. **Segunda pasada**: Últimos 5 x 424B5 → Extraer cada offering individual
3. **Tercera pasada**: S-3 recientes (<3 años) → Shelfs activos
4. **Cuarta pasada**: 10-Q recientes → ATM activity

**Pros:**

- Más completo
- Captura warrants de múltiples fuentes

**Contras:**

- 4 llamadas Grok por ticker ($$$)
- Más lento (30-40s por ticker)

### Opción B: Parser Especializado + Grok (HÍBRIDO)

**Estrategia:**

1. **Parser HTML**: Extraer tablas de equity de 10-K
2. **Parser Regex**: Buscar patrones "X warrants @ $Y.YY"
3. **Grok**: Solo para datos complejos/narrativos

**Pros:**

- Más barato (menos llamadas Grok)
- Más rápido
- Más preciso para datos tabulares

**Contras:**

- Complejidad técnica mayor
- Mantenimiento de parsers

### Opción C: API Externa (ASKEDGAR)

**Estrategia:**

- Usar API de AskedGar que ya tiene estos datos parseados

**Pros:**

- Datos completos y verificados
- Instantáneo (no scraping)
- Mantenido por terceros

**Contras:**

- Costo de API ($)
- Dependencia externa

---

## 🎯 Recomendación Inmediata

Para CMBM específicamente, necesitarías:

### 1. Buscar 424B5 de 2024-2025

```bash
# Estos filings tienen los detalles exactos de cada serie de warrants
- 424B5 Feb 2025 (Armistice offering)
- 424B5 July 2024 (offering con warrants)
- 424B5 Jan 2024 (Series A y B)
```

### 2. Filtrar Shelfs por Fecha

```python
# Solo incluir S-3 de últimos 3 años
if filing_date >= (today - 3 years):
    include_shelf()
```

### 3. Aumentar Filings Analizados

```python
# Actualmente: 5-10 filings
# Necesario: 15-20 filings para cobertura completa
```

---

## 🚀 Lo Que SÍ Funciona Ahora

### Casos de Éxito

**IVVD:**

- ✅ ATM: $150M con Cantor Fitzgerald
- ✅ Shelf: $300M (S-3)
- ✅ Dilución: 161.42%

**CMBM:**

- ✅ 2 Shelfs detectados (pero expirados)
- ❌ Warrants: 0 (debería ser 6.2M)
- ❌ Shelf Dec 2023: No detectado

**TSLA:**

- ✅ Sin dilución (correcto)

---

## 🛠️ Implementación Sugerida

Si quieres capturar TODOS los warrants de CMBM, necesito:

1. **Descargar los 424B5 de 2024-2025** (tienen los detalles exactos)
2. **Hacer múltiples llamadas a Grok** (una por cada offering)
3. **Agregar lógica de fecha** para filtrar shelfs expirados
4. **Aumentar límite de filings** a 20-30

**Tiempo estimado:** 2-3 horas de desarrollo adicional

**Alternativa rápida:**

- Usar API de terceros (AskedGar, etc.) que ya tienen estos datos parseados

---

## 📊 Estado Actual del Sistema

### ✅ Lo Implementado

- Scraping SEC EDGAR (30+ tipos de filings)
- Grok AI extraction (xAI SDK)
- Caché multi-nivel
- Parser HTML de tablas (básico)
- Frontend profesional
- API REST completa

### ❌ Limitaciones Conocidas

- No captura TODOS los warrants de TODOS los offerings
- Shelfs expirados no se filtran automáticamente
- Grok solo ve 2-3 filings completos por limitación de tokens
- No analiza 424B5 exhaustivamente

### 💡 Para Producción Real

Necesitarías:

1. Multi-pass Grok (analizar 20+ filings en varias pasadas)
2. Parser especializado para cada tipo de filing
3. O API externa profesional (AskedGar, etc.)

---

**¿Quieres que implemente el multi-pass o dejamos el sistema como MVP funcional con las limitaciones documentadas?**
