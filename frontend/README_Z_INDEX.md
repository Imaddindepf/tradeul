# 🎯 Sistema Centralizado de Z-Index

## ⚠️ PROBLEMA SOLUCIONADO

Antes teníamos **conflictos masivos** de z-index:

- **z-50** se usaba para: Mini sidebar del scanner, Modal de metadata, Header de Dilution Tracker, Botón mobile del Sidebar principal
- **z-40** se usaba para: Sidebar principal, Overlay del mini panel
- **z-30** se usaba para: Header del scanner, Overlay mobile

Esto causaba que elementos se superpusieran incorrectamente.

## ✅ SOLUCIÓN

Se creó un sistema centralizado en `frontend/lib/z-index.ts` con una jerarquía clara y predecible.

## 📚 Documentación Completa

Ver: [`frontend/docs/Z_INDEX_HIERARCHY.md`](./docs/Z_INDEX_HIERARCHY.md)

## 🚀 Uso Rápido

```tsx
import { Z_INDEX } from '@/lib/z-index';

// Modal
<div style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}>...</div>

// Sidebar
<aside style={{ zIndex: Z_INDEX.SIDEBAR }}>...</aside>

// Table header sticky
<thead style={{ zIndex: Z_INDEX.TABLE_HEADER }}>...</thead>
```

## 📊 Jerarquía Rápida

```
10  - TABLE_HEADER (headers sticky de tablas)
15  - PAGE_HEADER (headers de páginas)
20  - SIDEBAR_MOBILE_OVERLAY
30  - SIDEBAR
35  - SIDEBAR_MOBILE_BUTTON
40  - DROPDOWN
45  - TOOLTIP
50  - PANEL_OVERLAY (overlay del mini sidebar)
55  - SLIDING_PANEL (mini sidebar del scanner)
60  - MODAL_OVERLAY
65  - MODAL_CONTENT
70  - ALERT_MODAL
1000 - FLOATING_WINDOW_BASE
8999 - FLOATING_WINDOW_MANAGER
9000 - TOAST
9500 - NOTIFICATION
9999 - MAX
```

## ❌ NO HACER

```tsx
// ❌ MAL - No usar valores hardcodeados
<div className="z-50">...</div>
<div style={{ zIndex: 9999 }}>...</div>
```

## ✅ HACER

```tsx
// ✅ BIEN - Usar constantes del sistema
import { Z_INDEX } from '@/lib/z-index';
<div style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}>...</div>
```

## 🔍 Debug

```tsx
import { debugZIndex } from '@/lib/z-index';
debugZIndex(); // Imprime toda la jerarquía en consola
```

---

**Última actualización**: 19 de Noviembre, 2025

