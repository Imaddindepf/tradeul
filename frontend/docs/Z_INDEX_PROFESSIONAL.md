# 🏗️ ARQUITECTURA PROFESIONAL DE Z-INDEX

**Fecha**: 20 de Noviembre, 2025  
**Estado**: ✅ **IMPLEMENTADO Y FUNCIONAL**

---

## 🎯 FILOSOFÍA

**Sistema simple de 4 capas con un solo manager global para contenido flotante.**

---

## 📊 JERARQUÍA COMPLETA

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 1: NAVEGACIÓN GLOBAL (z-50)
 - Navbar y Sidebar siempre visibles
 - A la misma altura, siempre accesibles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  52 - NAVBAR_POPOVER (Market Status)
  51 - SIDEBAR_MOBILE_BUTTON
  50 - NAVBAR y SIDEBAR (mismo nivel)
  49 - SIDEBAR_MOBILE_OVERLAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                         ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 2: CONTROLES DEL SCANNER (z-40)
 - Panel de configuración de categorías
 - Botón para abrir/cerrar el panel
 - Sobre navegación pero bajo contenido flotante
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  40 - SCANNER_BUTTON + SCANNER_PANEL + TABLE_SETTINGS_POPOVER
  39 - SCANNER_PANEL_OVERLAY
  35 - TOOLTIP + DROPDOWN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                         ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 3: CONTENIDO FLOTANTE (z-10 a z-9999)
 - TODAS las ventanas flotantes compiten aquí
 - Tablas del scanner, Modal de metadata, Dilution Tracker
 - Sistema de foco: La que se hace click sube al tope
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  9999 - FLOATING_CONTENT_MAX (límite)
  10-9999 - Contenido flotante (dinámico, compartido)
  10 - FLOATING_CONTENT_BASE (inicio)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                         ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 0: BASE (z-0 a z-5)
 - Dashboard background
 - Table headers sticky (dentro de contenedores)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  5 - TABLE_HEADER (sticky)
  0 - BASE
```

---

## 🔑 MANAGER GLOBAL

### `floatingZIndexManager`

Un solo manager para TODO el contenido flotante:

```typescript
import { floatingZIndexManager } from '@/lib/z-index';

// Obtener siguiente z-index
const myZ = floatingZIndexManager.getNext();  // 10, 11, 12...

// Obtener z-index actual más alto
const currentZ = floatingZIndexManager.getCurrent();

// Resetear (solo para testing)
floatingZIndexManager.reset();
```

**Ventajas:**
- ✅ Un solo contador compartido
- ✅ Todas las ventanas compiten en el mismo espacio
- ✅ Sistema de foco automático
- ✅ Simple y predecible

---

## 🎨 COMPONENTES Y SU USO

### 1. Navbar & Sidebar (z-50)
```typescript
// Ambos usan Z_INDEX.NAVBAR y Z_INDEX.SIDEBAR
// Mismo nivel, siempre visibles
style={{ zIndex: Z_INDEX.NAVBAR }}  // 50
style={{ zIndex: Z_INDEX.SIDEBAR }}  // 50
```

### 2. Controles del Scanner (z-40)
```typescript
// Botón de configuración
style={{ zIndex: Z_INDEX.SCANNER_BUTTON }}  // 40

// Panel de categorías
style={{ zIndex: Z_INDEX.SCANNER_PANEL }}  // 40

// Overlay oscuro
style={{ zIndex: Z_INDEX.SCANNER_PANEL_OVERLAY }}  // 39
```

### 3. Tablas del Scanner
```typescript
import { floatingZIndexManager } from '@/lib/z-index';

// Al crear una tabla
const zIndex = floatingZIndexManager.getNext();  // 10, 11, 12...

// Al traer al frente (click)
const newZ = floatingZIndexManager.getNext();
setZIndex(newZ);
```

### 4. Modal de Metadata
```typescript
import { floatingZIndexManager } from '@/lib/z-index';

// Al abrir el modal
const [modalZIndex, setModalZIndex] = useState(() => 
  floatingZIndexManager.getNext()
);

// Al hacer click (traer al frente)
const bringToFront = () => {
  setModalZIndex(floatingZIndexManager.getNext());
};
```

### 5. Dilution Tracker
```typescript
// Usa FloatingWindowContext que internamente usa el manager
const { openWindow } = useFloatingWindow();

openWindow({
  title: 'Dilution Tracker',
  content: <DilutionTrackerContent />,
  // z-index se asigna automáticamente via manager
});
```

---

## 🎯 COMPORTAMIENTO ESPERADO

### Test 1: Abrir Tabla del Scanner
```
Usuario hace clic en categoría
  ↓
[Tabla: z-10] ← Aparece
[Navbar: z-50] ← Visible SOBRE la tabla ✓
[Scanner Button: z-40] ← Visible SOBRE la tabla ✓
```

### Test 2: Abrir Modal de Metadata
```
Usuario hace clic en ticker
  ↓
[Modal: z-11] ← Aparece (siguiente z-index)
[Tabla: z-10] ← Queda debajo
[Navbar: z-50] ← Visible SOBRE el modal ✓
```

### Test 3: Hacer Click en Tabla (Traer al Frente)
```
Usuario hace clic en tabla con modal abierto
  ↓
[Tabla: z-12] ← Sube al tope (nuevo z-index)
[Modal: z-11] ← Queda debajo
[Navbar: z-50] ← Siempre visible ✓
```

### Test 4: Abrir Panel de Configuración
```
Usuario hace clic en botón azul
  ↓
[Panel Overlay: z-39] ← Oscurece
[Scanner Panel: z-40] ← Aparece
[Tablas y modales: z-10+] ← Quedan DEBAJO ✓
[Navbar: z-50] ← Visible SOBRE todo ✓
```

---

## ⚠️ REGLAS DE ORO

### ✅ HACER

```typescript
// Importar el manager
import { floatingZIndexManager } from '@/lib/z-index';

// Usar para contenido flotante
const z = floatingZIndexManager.getNext();

// Usar constantes para controles fijos
import { Z_INDEX } from '@/lib/z-index';
style={{ zIndex: Z_INDEX.NAVBAR }}
```

### ❌ NUNCA HACER

```typescript
// NO hardcodear valores
style={{ zIndex: 1000 }} ❌
className="z-50" ❌

// NO crear contadores separados
let myOwnCounter = 100; ❌
```

---

## 🚀 AGREGAR NUEVO CONTENIDO FLOTANTE

### Ejemplo: Nueva Ventana Personalizada

```typescript
'use client';

import { useState } from 'react';
import { floatingZIndexManager } from '@/lib/z-index';

export function MyFloatingWindow() {
  const [zIndex, setZIndex] = useState(() => 
    floatingZIndexManager.getNext()
  );
  
  const bringToFront = () => {
    setZIndex(floatingZIndexManager.getNext());
  };
  
  return (
    <div
      className="fixed bg-white rounded-lg shadow-xl"
      style={{ zIndex }}
      onClick={bringToFront}
    >
      {/* Tu contenido aquí */}
    </div>
  );
}
```

---

## 📁 ARCHIVOS CLAVE

1. **`/frontend/lib/z-index.ts`**
   - Sistema de constantes
   - `floatingZIndexManager` global

2. **`/frontend/contexts/FloatingWindowContext.tsx`**
   - Usa el manager para Dilution Tracker

3. **`/frontend/app/(dashboard)/scanner/page.tsx`**
   - Usa el manager para tablas del scanner

4. **`/frontend/components/scanner/TickerMetadataModal.tsx`**
   - Usa el manager para el modal

---

## ✅ VERIFICACIÓN

**Sin errores de linter**: Todo compila correctamente

**Sistema unificado**:
- ✅ Un solo manager global
- ✅ Todas las ventanas flotantes compiten
- ✅ Navbar y controles siempre visibles
- ✅ Sistema de foco automático

---

## 🎓 RESUMEN

**4 capas simples:**
1. Navegación (z-50) - Siempre visible
2. Controles (z-40) - Sobre navegación
3. Contenido flotante (z-10 a z-9999) - Compiten por foco
4. Base (z-0) - Dashboard

**1 manager global:**
- `floatingZIndexManager` para TODO el contenido flotante

**Sistema profesional, simple y escalable** ✅

---

**Última actualización**: 20 de Noviembre, 2025  
**Estado**: IMPLEMENTADO Y FUNCIONAL

