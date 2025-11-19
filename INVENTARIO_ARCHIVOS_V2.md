# Inventario de Archivos - Arquitectura V2

## ✅ ARCHIVOS NUEVOS V2 (Creados para la nueva arquitectura de tablas)

### Core V2 (creados hace unas horas)
1. **`frontend/stores/useTickersStore.ts`** ← Zustand store global
2. **`frontend/hooks/useRxWebSocket.ts`** ← RxJS WebSocket Singleton
3. **`frontend/components/table/VirtualizedDataTable.tsx`** ← TanStack Virtual wrapper
4. **`frontend/components/scanner/CategoryTableV2.tsx`** ← Nueva tabla con V2

### Archivos de soporte V2 (creados para soportar lo anterior)
5. **`frontend/lib/types.ts`** ← Tipos TypeScript (Ticker, MarketSession, etc.)
6. **`frontend/lib/formatters.ts`** ← Utilidades de formato (formatPrice, formatNumber, etc.)
7. **`frontend/lib/api.ts`** ← Cliente API básico
8. **`frontend/lib/dilution-api.ts`** ← Cliente API para dilution (parcial)

### Documentación V2
9. **`frontend/ARCHITECTURE_V2.md`** ← Documentación de arquitectura
10. **`frontend/QUICKSTART_V2.md`** ← Guía rápida
11. **`RESUMEN_ARQUITECTURA_V2.md`** ← Resumen ejecutivo

---

## 📦 ARCHIVOS DE GITHUB (feature/dilution-tracker)

### Componentes existentes (del dilution tracker)
- `frontend/components/floating-window/*` (FloatingWindow, DilutionTrackerContent, etc.)
- `frontend/components/layout/*` (AppShell, Sidebar, PageContainer)
- `frontend/components/scanner/CategoryTable.tsx` ← VIEJA (V1)
- `frontend/components/scanner/TickerMetadataModal.tsx`
- `frontend/components/table/BaseDataTable.tsx` ← VIEJA (V1)
- `frontend/components/table/MarketTableLayout.tsx`
- `frontend/components/table/TableSettings.tsx`

### Páginas y contextos
- `frontend/app/(dashboard)/dilution-tracker/**`
- `frontend/contexts/FloatingWindowContext.tsx`
- `frontend/hooks/useWebSocket.ts` ← VIEJA (V1, reemplazada por useRxWebSocket)

---

## ⚠️ PROBLEMA ACTUAL

GitHub NO tiene los archivos de soporte V2 (#5-8) porque son NUEVOS.

El dilution-tracker en GitHub importa funciones que NO existen aún en `lib/dilution-api.ts`.

## 🎯 SOLUCIÓN

**Opción A (Recomendada):** Completar los archivos de soporte V2 para que el dilution-tracker compile

**Opción B:** Deshabilitar temporalmente el dilution-tracker hasta que esté listo

¿Cuál prefieres?

