# 🎯 GUÍA DEFINITIVA DE Z-INDEX

**Fecha**: 20 de Noviembre, 2025  
**Estado**: ✅ RESTAURADO Y FUNCIONAL

---

## 📊 JERARQUÍA COMPLETA

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9999 - MAX (reservado)
9900 - NOTIFICATION (notificaciones críticas)
9800 - TOAST (toasts)
9500 - NAVBAR_POPOVER (Market Status - sobre modales) ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9200 - ALERT_MODAL
9100 - MODAL_CONTENT ← TickerMetadataModal
9000 - MODAL_OVERLAY ← Cubre TODO ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1500 - NAVBAR ← Siempre visible (excepto con modales) ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1200 - SCANNER_CONFIG_BUTTON ← Botón azul ✓
1100 - SLIDING_PANEL ← Panel de categorías ✓
1000 - PANEL_OVERLAY ← Oscurece el scanner ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
900 - TABLE_POPOVER ← Config de columnas ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
899 - FLOATING_WINDOW_MANAGER (límite superior)
50-899 - VENTANAS FLOTANTES (TODAS) ✓
  ├─ Scanner Tables (DraggableTable)
  └─ Dilution Tracker (FloatingWindow)
50 - FLOATING_WINDOW_BASE (inicio)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
45 - TOOLTIP
40 - DROPDOWN
35 - SIDEBAR_MOBILE_BUTTON
30 - SIDEBAR
20 - SIDEBAR_MOBILE_OVERLAY
15 - PAGE_HEADER
10 - TABLE_HEADER
0  - BASE
```

---

## 🔧 PROBLEMAS CORREGIDOS

### 1. ✅ FloatingWindowContext
**Antes**: `let maxZIndex = 1000` ❌  
**Ahora**: `let maxZIndex = Z_INDEX.FLOATING_WINDOW_BASE` ✅

### 2. ✅ TableSettings
**Antes**: `zIndex: Z_INDEX.NAVBAR_POPOVER` (9500) ❌  
**Ahora**: `zIndex: Z_INDEX.TABLE_POPOVER` (900) ✅

### 3. ✅ Modales
**Antes**: z-60-79 (debajo de tablas) ❌  
**Ahora**: z-9000-9200 (sobre TODO) ✅

---

## 🎯 COMPORTAMIENTO ESPERADO

### Modal de Metadata
```
Usuario hace clic en ticker
  ↓
[Tablas flotantes: 50-899] ← Cubiertas
[Navbar: 1500] ← Cubierto
[Scanner button: 1200] ← Cubierto
  ↓
[MODAL_OVERLAY: 9000] ← Cubre TODO ✓
[MODAL_CONTENT: 9100] ← Contenido del modal
```

### Dilution Tracker
```
Usuario abre Dilution Tracker
  ↓
[FloatingWindow: 50-899] ← Ventana flotante
[Navbar: 1500] ← Visible SOBRE la ventana ✓
[Scanner button: 1200] ← Visible SOBRE la ventana ✓
```

### Panel de Configuración
```
Usuario hace clic en botón azul
  ↓
[PANEL_OVERLAY: 1000] ← Oscurece tablas (50-899) ✓
[SLIDING_PANEL: 1100] ← Panel visible
[SCANNER_CONFIG_BUTTON: 1200] ← Botón visible ✓
[Navbar: 1500] ← Siempre visible ✓
```

---

## ⚠️ REGLAS DE ORO

### NUNCA hacer esto:
```typescript
❌ style={{ zIndex: 1000 }}
❌ className="z-50"
❌ const myZ = 9999
```

### SIEMPRE hacer esto:
```typescript
✅ import { Z_INDEX } from '@/lib/z-index';
✅ style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}
✅ style={{ zIndex: Z_INDEX.FLOATING_WINDOW_BASE + index }}
```

---

## 🚀 VERIFICACIÓN RÁPIDA

1. ✅ Abrir modal de metadata → Debe cubrir TODO
2. ✅ Abrir Dilution Tracker → Navbar debe quedar visible
3. ✅ Abrir panel de configuración → Botón debe quedar visible
4. ✅ Config de columnas → Debe aparecer sobre tablas pero debajo de modales

---

**Si algo no funciona, verifica:**
1. ¿El componente importa `Z_INDEX`?
2. ¿Está usando la constante correcta?
3. ¿El archivo `/frontend/lib/z-index.ts` tiene los valores correctos?

---

**Última actualización**: 20 de Noviembre, 2025  
**Archivo**: `/frontend/lib/z-index.ts`  
**Contexto**: `/frontend/contexts/FloatingWindowContext.tsx`

