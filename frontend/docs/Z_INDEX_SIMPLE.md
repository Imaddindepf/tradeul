# 🎯 ARQUITECTURA SIMPLE DE Z-INDEX

**Fecha**: 20 de Noviembre, 2025  
**Estado**: ✅ **SISTEMA PROFESIONAL Y UNIFICADO**

---

## 💡 FILOSOFÍA

**Todas las ventanas flotantes (tablas, modales, dilution tracker) se comportan igual:**
- Arrastrables
- Sin overlay oscuro
- Compiten por el foco
- Mismo sistema de z-index dinámico

---

## 📊 JERARQUÍA (4 Capas Simples)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 1: NAVEGACIÓN GLOBAL (z-50)
 ├─ Navbar (50) - Siempre visible
 └─ Sidebar (50) - Siempre visible
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 2: CONTROLES (z-40)
 ├─ Botón de collapse de tablas (40)
 └─ Panel de configuración (40)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CAPA 3: CONTENIDO FLOTANTE (z-10 a z-9999)
 
 TODAS estas ventanas funcionan igual:
 ├─ Tablas del scanner (10+) - Arrastrable
 ├─ Modal de metadata (10+) - Arrastrable ✓
 ├─ Dilution Tracker (10+) - Arrastrable
 └─ Cualquier ventana futura
 
 Sistema de foco: La que se arrastra sube al tope
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🎨 VENTANAS FLOTANTES UNIFICADAS

### Características Comunes

Todas las ventanas flotantes comparten:

1. **Arrastrables** - Se pueden mover haciendo clic y arrastrando
2. **Sin overlay** - No oscurecen el fondo
3. **Sistema de foco** - Al arrastrar, suben al tope
4. **Mismo z-index dinámico** - Usan `floatingZIndexManager`
5. **Botón de cerrar** - X en la esquina

### Ventanas Actuales

#### 1. Tablas del Scanner
```typescript
// Se crean con DraggableTable
<DraggableTable 
  category={category}
  zIndex={floatingZIndexManager.getNext()}
  onBringToFront={() => setZIndex(floatingZIndexManager.getNext())}
/>
```

#### 2. Modal de Metadata (ahora ventana flotante)
```typescript
// Usa Rnd igual que las tablas
<Rnd
  dragHandleClassName="modal-drag-handle"
  onDragStart={() => setZIndex(floatingZIndexManager.getNext())}
  style={{ zIndex }}
>
  <div className="modal-drag-handle cursor-move">
    {/* Header arrastrable */}
  </div>
  {/* Contenido */}
</Rnd>
```

#### 3. Dilution Tracker
```typescript
// Usa FloatingWindowContext
openWindow({
  title: 'Dilution Tracker',
  content: <DilutionTrackerContent />,
  // z-index automático via manager
});
```

---

## 🔄 FLUJO DE INTERACCIÓN

### Abrir Modal de Metadata

```
Usuario hace clic en ticker de una tabla
  ↓
[Modal aparece como ventana flotante] (z-11)
  ↓
[Tabla original] (z-10) - Queda debajo
[Navbar] (z-50) - Visible sobre todo ✓
```

### Arrastrar Modal

```
Usuario arrastra el modal por el header
  ↓
[Modal sube] (z-12) - Nuevo z-index más alto
[Otras ventanas] (z-10, z-11) - Quedan debajo
[Navbar] (z-50) - Siempre visible ✓
```

### Multiples Ventanas

```
Tabla 1: z-10
Tabla 2: z-11
Modal: z-12
Dilution Tracker: z-13
  ↓
Usuario arrastra Tabla 1
  ↓
Tabla 1: z-14 ← Sube al tope
Modal: z-12 ← Queda debajo
Navbar: z-50 ← Siempre visible ✓
```

---

## ✅ VENTAJAS DE ESTA ARQUITECTURA

### 1. Consistencia
- Todas las ventanas se comportan igual
- No hay "ventanas especiales" con overlay
- Experiencia de usuario predecible

### 2. Flexibilidad
- Puedes tener múltiples modales abiertos
- Puedes ver el modal junto a la tabla
- Puedes comparar información fácilmente

### 3. Simplicidad
- Un solo sistema para todas las ventanas
- Un solo manager de z-index
- Fácil de mantener y extender

### 4. Profesionalidad
- Parecido a aplicaciones como VS Code, Figma
- Ventanas flotantes independientes
- Sin bloqueo de UI

---

## 🎯 COMPORTAMIENTO ESPERADO

### ✅ Navbar y Sidebar (z-50)
- Siempre visibles sobre todo el contenido
- No se ven afectados por ventanas flotantes

### ✅ Botón de Collapse (z-40)
- Visible sobre las ventanas flotantes
- Accesible en todo momento

### ✅ Todas las Ventanas Flotantes (z-10+)
- Se pueden arrastrar libremente
- No tienen overlay oscuro
- Compiten por el foco
- Al arrastrar, suben al tope

---

## 🚀 AGREGAR NUEVA VENTANA FLOTANTE

```typescript
'use client';

import { useState } from 'react';
import { Rnd } from 'react-rnd';
import { floatingZIndexManager } from '@/lib/z-index';

export function MyFloatingWindow({ onClose }) {
  const [zIndex, setZIndex] = useState(() => 
    floatingZIndexManager.getNext()
  );
  
  const handleDragStart = () => {
    setZIndex(floatingZIndexManager.getNext());
  };
  
  return (
    <Rnd
      dragHandleClassName="my-drag-handle"
      onDragStart={handleDragStart}
      style={{ zIndex }}
      bounds="window"
    >
      <div className="bg-white rounded-lg shadow-2xl border-2">
        <div className="my-drag-handle cursor-move p-4">
          {/* Header arrastrable */}
        </div>
        <div className="p-6">
          {/* Contenido */}
        </div>
      </div>
    </Rnd>
  );
}
```

---

## 📁 ARCHIVOS CLAVE

1. **`/frontend/lib/z-index.ts`** - Sistema de constantes + manager
2. **`/frontend/components/scanner/DraggableTable.tsx`** - Tabla arrastrable
3. **`/frontend/components/scanner/TickerMetadataModal.tsx`** - Modal como ventana flotante
4. **`/frontend/contexts/FloatingWindowContext.tsx`** - Context para Dilution Tracker

---

## 🎓 RESUMEN

**Sistema unificado:**
- ✅ 4 capas simples
- ✅ 1 manager global de z-index
- ✅ Todas las ventanas flotantes funcionan igual
- ✅ Sin overlay oscuro
- ✅ Arrastrables y con foco dinámico

**Resultado:** Sistema profesional, simple y escalable 🚀

---

**Última actualización**: 20 de Noviembre, 2025  
**Estado**: IMPLEMENTADO Y FUNCIONAL

