# 📚 Guía Completa de SEC Filing Types para Dilución

> Referencia para entender cada tipo de filing SEC y su impacto en el análisis de dilución.

## 📋 Tabla de Referencia Rápida

| Filing | Propósito | Cuándo | Impacto | Procesar |
|--------|-----------|--------|---------|----------|
| **S-1/F-1** | IPO, Follow-on, Resale | Meses (IPO) / <1 mes (FO) | None-Medium | Clasificar |
| **S-1/A** | Enmienda | Post-inicial | None | Skip si hay 424B4 |
| **EFFECT** | SEC aprobó | Post-review | Low-Medium | Señal |
| **424B4** | Prospecto FINAL | Post-pricing | None | **DEFINITIVO** |
| **S-3/F-3** | Shelf registration | Anytime | None-Low | Capacidad |
| **424B5** | ATM o oferta bajo shelf | Post-EFFECT | None-Medium | **CADA UNO** |
| **424B3** | Resale confirmation | Post-EFFECT | None-Low | Confirmación |
| **8-K/6-K** | Material event | 4 días | None-High | **TODOS** |
| **10-Q/10-K** | Financials | 45/90 días | None-Low | **TODOS** |

---

## 🔴 Dilution/Prospectus Filings

### S-1/F-1 (Registration Statement)

| Propósito | Cuándo se presenta | Cómo identificar | Impacto |
|-----------|-------------------|------------------|---------|
| **IPO** | Meses antes del pricing | Primera página dice "initial public offering" | None |
| **Follow-on/Secondary** | <1 mes antes del pricing | Especifica $ máximo, placeholders para # shares y price | Medium |
| **Resale** | Anytime (según registration rights) | Especifica qué shares, quién vende, cuántas | None-Low |

**Por qué se presenta:**
- **IPO**: Registro inicial para venta pública de acciones
- **Follow-on**: Empresa usa S-1 en lugar de S-3 para oferta secundaria
- **Resale**: Acciones restringidas necesitan registro antes de venderse sin restricciones Rule 144

### S-1/A (Amendment)

- **Cuándo**: Después del filing inicial
- **Propósito**: Enmiendas para disclosures adicionales, finalizar exhibits (underwriting agreements, warrant terms)
- **Impacto**: None (iteración hacia el documento final)

### EFFECT

- **Cuándo**: Cuando SEC termina review (usualmente <1 mes después de S-1/F-1)
- **Publicación**: Todos los EFFECTs se publican a las 6:00 AM diariamente
- **Impacto**: Low-Medium - Señala que pricing es **inminente**
- **Clave**: Small cap S-1/F-1 offerings casi siempre se precian el mismo día del EFFECT

### 424B4 (Final Prospectus)

- **Cuándo**: Después del pricing de IPO o S-1 related offering
- **Contenido**: Detalles finales del pricing y shares emitidas
- **Impacto**: None (pricing PR ya salió antes)
- **IMPORTANTE**: Este es el documento **DEFINITIVO** con precio final

### S-3/F-3 (Shelf Registration)

| Propósito | Cuándo | Identificación | Impacto |
|-----------|--------|----------------|---------|
| **Shelf** | Anytime que planea raise | Indica $ máximo y tipos de securities | None-Low |
| **Resale** | Según registration rights | Especifica qué shares y quién vende | None-Low |

**Detalles importantes:**
- Shelf efectivo permite ofrecer en cualquier momento en los próximos **3 años**
- Sujeto a límites de **Baby Shelf Rule** si float < $75M
- A veces viene con ATM adjunto

### S-3/F-3ASR (Automatic Shelf)

- **Disponible para**: WKSI (Well-Known Seasoned Issuer) - $700M+ float value
- **Diferencia clave**: Recibe EFFECT automáticamente al presentarse
- **Impacto**: None-Low (pero puede usarse inmediatamente)

### 424B5 (Prospectus Supplement)

| Propósito | Cuándo | Identificación | Impacto |
|-----------|--------|----------------|---------|
| **ATM** | Anytime post-EFFECT | "at the market offering", "equity distribution agreement" | None-Medium |
| **Final prospectus** | Post-pricing PR | Shares y price inline con PR | None |
| **Register warrants/convertibles** | Según registration rights | Especifica qué warrants/convertibles | None |

**IMPORTANTE**: Un S-3 puede tener **MÚLTIPLES** 424B5, cada uno es oferta diferente.

### 424B3 (Resale Prospectus)

- **Cuándo**: Después de que resale registration recibe EFFECT
- **Propósito**: Confirma que shares están oficialmente registradas
- **Impacto**: None-Low (puede tener impacto si unlocked shares >> float)

### RW (Withdrawal)

- **Cuándo**: Cuando empresa decide retirar registration
- **Impacto**: Low-Medium - Si mercado esperaba oferta, RW puede causar **pop**

---

##  Financials

| Filing | Propósito | Deadline | Impacto |
|--------|-----------|----------|---------|
| **10-Q** | Quarterly | 45 días (<$75M) / 40 días (otros) | None-Low |
| **10-K** | Annual | 90/75/60 días según tamaño | None-Low |
| **20-F** | Annual (foreign) | 4 meses post-year end | None-Low |
| **40-F** | Annual (Canadian) | Mismo día que en Canadá | None |

**Nota**: 99% de las veces se presenta **después** del earnings PR.

---

## 📢 Material Disclosures

### 8-K

- **Cuándo**: Dentro de 4 días del evento
- **Contenido**: Earnings, M&A, cambios en management, securities issuances, etc.
- **Impacto**: None-High (dependiendo de severidad)
- **IMPORTANTE**: 99% de las veces PR sale antes que 8-K

### 6-K (Foreign)

- **Cuándo**: "Promptly" después del evento
- **Contenido**: Mismo que 8-K pero para foreign issuers
- **Impacto**: None-High

---

## 👥 Ownership

| Filing | Propósito | Deadline | Impacto |
|--------|-----------|----------|---------|
| **SC 13D** | Activist stake >5% | 10 días | None-Medium |
| **SC 13G** | Passive stake >5% | 45 días (>5%), 10 días (>10%) | None-Medium |
| **Form 4** | Insider transaction | 2 días | None-Medium |

---

## 📝 Proxies

| Filing | Propósito | Cuándo | Impacto |
|--------|-----------|--------|---------|
| **PRE 14A** | Preliminary proxy | 10+ días antes de definitivo | None |
| **DEF 14A** | Definitive proxy | Post-preliminary o 120 días post-year | None |
| **DEFM14A** | Merger proxy | Post-merger announcement | None |

---

## 🎯 Reglas de Procesamiento para Dilución

### 1. NUNCA Deduplicar
- 8-K, 6-K (cada uno es evento único)
- 10-Q, 10-K (cada uno es período diferente)
- DEF 14A (cada uno es meeting diferente)
- Form 4 (cada transacción es única)

### 2. Deduplicar por File Number (IPO/Follow-on)
```
S-1 → S-1/A → EFFECT → 424B4
         └─── Skip ───┘   └── PROCESAR
```

### 3. Mantener Todos bajo Shelf
```
S-3 (capacidad) + 424B5 (ATM) + 424B5 (oferta 1) + 424B5 (oferta 2)
    └── TODOS SE PROCESAN (cada 424B5 es oferta diferente) ──┘
```

### 4. Clasificar S-1 por Contenido
- "initial public offering" → IPO
- "resale", "selling stockholder" → Resale
- Otro → Follow-on (más común en small caps)

---

## 📚 Referencias

- [SEC EDGAR](https://www.sec.gov/edgar)
- [Baby Shelf Rule (I.B.6)](https://www.sec.gov/rules/final/33-8878.htm)
- [Form Types Manual](https://www.sec.gov/info/edgar/forms/edgarforms.htm)

