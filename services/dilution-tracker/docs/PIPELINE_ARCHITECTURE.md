# 🔬 PIPELINE DE DILUCIÓN - ARQUITECTURA COMPLETA

## 📋 FLUJO ACTUAL

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PIPELINE DE EXTRACCIÓN v2                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. FETCH FILINGS                                                          │
│     └─► SEC-API.io → 248 filings (pero SIN file_number!)                   │
│                                                                             │
│  2. ENRICH FILE NUMBERS                                                     │
│     └─► SEC EDGAR → Añadir file_number a cada filing                       │
│     └─► Resultado: 222 de 248 enriquecidos                                 │
│                                                                             │
│  3. FILE NUMBER GROUPING (FilingGrouper)                                   │
│     ├─► Agrupar por file_number (ej: 333-291955)                           │
│     ├─► Clasificar cadena:                                                 │
│     │   ├─► IPO/Follow-on: S-1 → S-1/A → EFFECT → 424B4                   │
│     │   │   └─► SOLO quedarse con 424B4 (precio final)                     │
│     │   ├─► Shelf + ATM: S-3 + 424B5s                                      │
│     │   │   └─► Mantener S-3 + TODOS 424B5                                 │
│     │   └─► 8-K/6-K: NUNCA deduplicar (cada uno es evento)                │
│     └─► Resultado: 155 → 135 filings (20 removidos)                        │
│                                                                             │
│  4. DOWNLOAD EXHIBITS                                                       │
│     └─► Descargar contenido + exhibits de 20 filings prioritarios          │
│                                                                             │
│  5. GEMINI EXTRACTION                                                       │
│     ├─► Prompt con schema JSON estricto                                    │
│     ├─► Extraer: notes, warrants, s1_offerings, shelfs, atm, etc.          │
│     └─► Resultado: Raw data con duplicados                                 │
│                                                                             │
│  6. PRE-MERGE                                                              │
│     └─► Combinar duplicados parciales del mismo instrumento                │
│                                                                             │
│  7. CONSOLIDATION PASS (Gemini)                                            │
│     ├─► Segunda pasada para limpiar y deduplicar                           │
│     └─► Resultado: Datos consolidados                                      │
│                                                                             │
│  8. SPLIT ADJUSTMENT                                                        │
│     └─► Ajustar precios por stock splits históricos                        │
│                                                                             │
│  9. BUILD PROFILE                                                          │
│     └─► Crear SECDilutionProfileModel final                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔍 DIFERENCIAS CON DILUTIONTRACKER

### Lo que TENEMOS ✅:
| Campo | Estado |
|-------|--------|
| S-1 Offerings | ✅ Funcionando |
| Convertible Preferred | ✅ Funcionando |
| Shelfs | ✅ Funcionando |
| ATM | ✅ Parcial (falta capacity) |
| Warrants | ⚠️ Parcial (faltan algunos) |
| Convertible Notes | ⚠️ Parcial |

### Lo que FALTA ❌:

#### 1. **ATM Total Capacity**
DilutionTracker: `$11,750,000`
Nosotros: `null`

**Por qué falta**: El capacity del ATM está en el 424B5 que registra el ATM, no en el S-3 shelf. Gemini lo extrae pero el consolidation pass lo pierde.

#### 2. **Warrants Faltantes**
DilutionTracker tiene ~7 warrants, nosotros 4.

**Por qué faltan**: 
- Algunos warrants históricos (pre-2024) no se extraen
- El `warrant_type` no se clasifica correctamente (shares vs convertible_notes)

#### 3. **Baby Shelf Calculations**
DilutionTracker calcula:
- `atm_limited_by_baby_shelf: Yes`
- `remaining_capacity_without_restriction`
- `float_value * 1/3`

**Por qué falta**: No calculamos Baby Shelf dinámicamente.

#### 4. **Historical Tracking**
DilutionTracker trackea cambios históricos (Last Update Date).

**Por qué falta**: No guardamos historial de cambios.

---

## 📁 FILE NUMBER GROUPING - DETALLE

### Ejemplo VMAR:

```
FILE NUMBER: 333-291955 (December 2025 F-1 Offering)
├── F-1      │ 2025-12-04 │ Initial registration
├── F-1/A    │ 2025-12-10 │ Amendment 1
├── F-1/A    │ 2025-12-15 │ Amendment 2
├── EFFECT   │ 2025-12-18 │ SEC declares effective
└── 424B4    │ 2025-12-18 │ FINAL PROSPECTUS ← SOLO ESTE SE PROCESA
    └── Contiene: precio final $0.30, shares 32M, deal size $9.58M

FILE NUMBER: 333-267893 (F-3 Shelf Registration)
├── F-3      │ 2022-08-15 │ Initial shelf ($100M capacity)
├── F-3/A    │ 2022-09-01 │ Amendment
├── 424B5    │ 2023-01-10 │ ATM Agreement (ThinkEquity, $11.75M)
├── 424B5    │ 2024-03-15 │ Offering #1 ($5M)
├── 424B5    │ 2024-06-20 │ Offering #2 ($3M)
└── ... más 424B5s
    └── TODOS SE PROCESAN (cada uno es oferta diferente)
```

### Reglas Implementadas:

| Tipo de Cadena | Filings Incluidos | Filings Ignorados | Razón |
|----------------|-------------------|-------------------|-------|
| IPO/Follow-on | Solo 424B4 | S-1, S-1/A, EFFECT | 424B4 tiene precio final |
| Shelf + Ofertas | S-3 + TODOS 424B5 | S-3/A anteriores | Cada 424B5 es oferta única |
| Resale | S-1 + 424B3 | S-1/A intermedios | Ambos tienen info importante |
| 8-K/6-K | TODOS | Ninguno | Cada uno es evento material |

---

## 🎯 CAMPOS FALTANTES PARA IGUALAR DILUTIONTRACKER

### ATM Offerings:
```python
# DilutionTracker tiene:
{
    "series_name": "October 2024 ThinkEquity ATM",
    "total_capacity": 11750000,  # ❌ Nosotros: null
    "remaining_capacity": 0,      # ❌ Nosotros: null
    "atm_limited_by_baby_shelf": True,
    "remaining_capacity_without_restriction": 0,
    "placement_agent": "ThinkEquity",
    "agreement_start_date": "2024-10-17"
}
```

### Convertible Preferred:
```python
# DilutionTracker tiene:
{
    "series_name": "December 2023 Series B Convertible Preferred",
    "remaining_dollar_amount": 3000000,
    "conversion_price": 405,  # ❌ Nosotros: 1417.5 (incorrecto!)
    "known_owners": "Investissement Quebec",
    "price_protection": "Reset",
    "pp_clause": "Price adjustment on maturity"
}
```

### Warrants:
```python
# DilutionTracker tiene warrant_type:
{
    "warrant_type": "shares",  # vs "convertible_notes" vs "preferred_stock"
    "is_note_purchase_warrant": True  # ❌ No lo extraemos
}
```

---

## 🔧 PRÓXIMOS PASOS PARA IGUALAR

1. **Mejorar ATM Extraction**:
   - Extraer `total_capacity` del 424B5 de ATM
   - Implementar cálculo Baby Shelf

2. **Mejorar Convertible Preferred**:
   - Verificar `conversion_price` (puede ser split-adjusted incorrecto)
   - Extraer `known_owners` correctamente

3. **Mejorar Warrants**:
   - Añadir `warrant_type` al schema
   - Identificar `is_note_purchase_warrant`

4. **Baby Shelf Calculator**:
   - Calcular float value × 1/3
   - Determinar si está limitado

5. **Historical Tracking**:
   - Guardar historial de cambios
   - Track `last_update_date` por instrumento

