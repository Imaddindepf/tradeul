# 📚 Jerarquía de Z-Index - Sistema Centralizado

## 🎯 Objetivo

Este documento define la jerarquía completa de z-index en la aplicación para **evitar conflictos** y mantener un orden visual predecible.

## ⚠️ REGLA FUNDAMENTAL

**SIEMPRE** importar y usar las constantes de `@/lib/z-index.ts`. **NUNCA** usar valores hardcodeados como `z-50`, `z-[9999]`, etc.

```tsx
// ❌ MAL - No usar valores hardcodeados
<div className="z-50">...</div>

// ✅ BIEN - Usar constantes del sistema
import { Z_INDEX } from '@/lib/z-index';
<div style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}>...</div>
```

---

## 📊 Jerarquía Completa (De Menor a Mayor)

### 1️⃣ **BASE LAYER (0-9)**
Elementos sin posicionamiento especial.

| Constante | Valor | Uso |
|-----------|-------|-----|
| `Z_INDEX.BASE` | 0 | Contenido base |

### 2️⃣ **STICKY ELEMENTS (10-19)**
Headers y footers sticky dentro de contenedores.

| Constante | Valor | Uso | Componentes |
|-----------|-------|-----|-------------|
| `Z_INDEX.TABLE_HEADER` | 10 | Headers sticky de tablas | `VirtualizedDataTable`, `ResizableTable` |
| `Z_INDEX.PAGE_HEADER` | 15 | Headers sticky de páginas | Scanner, Dilution Tracker |

### 3️⃣ **NAVIGATION (20-39)**
Elementos de navegación principal.

| Constante | Valor | Uso | Componentes |
|-----------|-------|-----|-------------|
| `Z_INDEX.SIDEBAR_MOBILE_OVERLAY` | 20 | Overlay del mobile menu | `Sidebar.tsx` |
| `Z_INDEX.SIDEBAR` | 30 | Sidebar principal | `Sidebar.tsx` |
| `Z_INDEX.SIDEBAR_MOBILE_BUTTON` | 35 | Botón del mobile menu | `Sidebar.tsx` |

### 4️⃣ **DROPDOWNS & TOOLTIPS (40-49)**
Elementos flotantes sobre contenido.

| Constante | Valor | Uso |
|-----------|-------|-----|
| `Z_INDEX.DROPDOWN` | 40 | Select menus, dropdowns |
| `Z_INDEX.TOOLTIP` | 45 | Tooltips y popovers |

### 5️⃣ **SECONDARY PANELS & OVERLAYS (50-59)**
Paneles secundarios y sus overlays.

| Constante | Valor | Uso | Componentes |
|-----------|-------|-----|-------------|
| `Z_INDEX.PANEL_OVERLAY` | 50 | Overlay de paneles secundarios | Mini sidebar del Scanner |
| `Z_INDEX.SLIDING_PANEL` | 55 | Paneles deslizantes | Mini sidebar del Scanner |

### 6️⃣ **MODALS (60-79)**
Diálogos y modales.

| Constante | Valor | Uso | Componentes |
|-----------|-------|-----|-------------|
| `Z_INDEX.MODAL_OVERLAY` | 60 | Backdrop de modales | `TickerMetadataModal` |
| `Z_INDEX.MODAL_CONTENT` | 65 | Contenido del modal | `TickerMetadataModal` |
| `Z_INDEX.ALERT_MODAL` | 70 | Modales de confirmación/alertas | - |

### 7️⃣ **FLOATING WINDOWS (1000-8999)**
Ventanas flotantes con z-index dinámico.

| Constante | Valor | Uso | Componentes |
|-----------|-------|-----|-------------|
| `Z_INDEX.FLOATING_WINDOW_BASE` | 1000 | Base para ventanas flotantes (incrementa dinámicamente) | `FloatingWindowContext` |
| `Z_INDEX.FLOATING_WINDOW_MANAGER` | 8999 | Manager de ventanas flotantes | `FloatingWindowManager` |

### 8️⃣ **NOTIFICATIONS (9000-9999)**
Toasts y notificaciones de sistema.

| Constante | Valor | Uso |
|-----------|-------|-----|
| `Z_INDEX.TOAST` | 9000 | Toasts y notificaciones |
| `Z_INDEX.NOTIFICATION` | 9500 | Notificaciones críticas |
| `Z_INDEX.MAX` | 9999 | Máximo z-index reservado |

---

## 🔧 Cómo Usar

### Ejemplo 1: Componente con z-index fijo

```tsx
import { Z_INDEX } from '@/lib/z-index';

export function MyModal() {
  return (
    <div 
      className="fixed inset-0 bg-black/60"
      style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}
    >
      <div 
        className="bg-white rounded-lg"
        style={{ zIndex: Z_INDEX.MODAL_CONTENT }}
      >
        Contenido del modal
      </div>
    </div>
  );
}
```

### Ejemplo 2: Componente con z-index condicional

```tsx
import { Z_INDEX } from '@/lib/z-index';

export function MyTable({ stickyHeader }: { stickyHeader: boolean }) {
  return (
    <thead
      className={stickyHeader ? 'sticky top-0' : ''}
      style={stickyHeader ? { zIndex: Z_INDEX.TABLE_HEADER } : undefined}
    >
      {/* ... */}
    </thead>
  );
}
```

---

## 🐛 Debugging

### Función de Debug

Puedes ver todos los z-indexes en consola:

```tsx
import { debugZIndex } from '@/lib/z-index';

// En el componente o useEffect
debugZIndex();
```

### Validar z-index

```tsx
import { isValidZIndex, Z_INDEX } from '@/lib/z-index';

const myZIndex = 65;
if (isValidZIndex(myZIndex, 'MODAL_CONTENT')) {
  console.log('✅ Z-index válido');
} else {
  console.error('❌ Z-index fuera del rango esperado');
}
```

---

## 📝 Checklist para Nuevos Componentes

Cuando agregues un nuevo componente con z-index:

- [ ] ¿Importaste `Z_INDEX` desde `@/lib/z-index`?
- [ ] ¿Usaste una constante en lugar de valor hardcodeado?
- [ ] ¿La constante está en la capa correcta según su propósito?
- [ ] ¿Actualizaste esta documentación si agregaste nuevas constantes?

---

## 🔄 Migración de Código Legacy

Si encuentras código con z-index hardcodeado:

1. Identifica el propósito del elemento
2. Encuentra la constante apropiada en `Z_INDEX`
3. Reemplaza el valor hardcodeado
4. Prueba que funcione correctamente

**Ejemplo:**

```tsx
// Antes (legacy)
<div className="z-50">Modal</div>

// Después (correcto)
import { Z_INDEX } from '@/lib/z-index';
<div style={{ zIndex: Z_INDEX.MODAL_OVERLAY }}>Modal</div>
```

---

## 📌 Componentes Actualizados

✅ Componentes que ya usan el sistema centralizado:

- `frontend/lib/z-index.ts` - Sistema centralizado
- `frontend/components/layout/Sidebar.tsx`
- `frontend/app/(dashboard)/scanner/page.tsx`
- `frontend/components/scanner/TickerMetadataModal.tsx`
- `frontend/app/(dashboard)/dilution-tracker/page.tsx`
- `frontend/components/table/VirtualizedDataTable.tsx`
- `frontend/components/ui/ResizableTable.tsx`
- `frontend/contexts/FloatingWindowContext.tsx`
- `frontend/components/floating-window/FloatingWindowManager.tsx`

---

## 🚨 Problemas Resueltos

### Problema Original

El mini sidebar del scanner (z-50) estaba al mismo nivel que:
- Modal de metadata (z-50)
- Header de Dilution Tracker (z-50)
- Botón mobile del sidebar principal (z-50)

Esto causaba que los elementos se superpusieran incorrectamente.

### Solución

Se implementó un sistema centralizado con jerarquía clara:
- **Mini sidebar**: `Z_INDEX.SLIDING_PANEL` (55)
- **Modal**: `Z_INDEX.MODAL_OVERLAY` (60) y `Z_INDEX.MODAL_CONTENT` (65)
- **Headers**: `Z_INDEX.PAGE_HEADER` (15)
- **Sidebar principal**: `Z_INDEX.SIDEBAR` (30)

Ahora los modales siempre aparecen sobre los paneles secundarios, y los headers sticky quedan debajo de la navegación.

---

## 📞 Contacto

Si tienes dudas sobre qué z-index usar para un nuevo componente, consulta esta documentación o pregunta al equipo.

**Última actualización**: 19 de Noviembre, 2025

