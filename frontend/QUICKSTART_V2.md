# ⚡ Quick Start - Architecture V2

Guía rápida de 5 minutos para empezar con la nueva arquitectura.

---

## 📦 Paso 1: Verificar Instalación

Las dependencias ya están instaladas. Verifica con:

```bash
cd frontend
npm list @tanstack/react-virtual rxjs zustand
```

Deberías ver:
```
├── @tanstack/react-virtual@3.13.12
├── rxjs@7.8.2
└── zustand@4.5.0
```

---

## 🚀 Paso 2: Usar el Nuevo Componente

### Opción A: Reemplazar tabla existente

```typescript
// app/(dashboard)/scanner/page.tsx

// ANTES (V1):
import CategoryTable from '@/components/scanner/CategoryTable';

// DESPUÉS (V2):
import CategoryTableV2 from '@/components/scanner/CategoryTableV2';

export default function ScannerPage() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-grid-root>
      {/* ✅ Nueva versión con virtualización */}
      <CategoryTableV2 
        title="Gappers Up" 
        listName="gappers_up" 
      />
      
      <CategoryTableV2 
        title="Momentum Up" 
        listName="momentum_up" 
      />
    </div>
  );
}
```

### Opción B: Crear nueva página de prueba

```typescript
// app/(dashboard)/scanner-v2/page.tsx

import CategoryTableV2 from '@/components/scanner/CategoryTableV2';

export default function ScannerV2Page() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Scanner V2 (con Virtualización)</h1>
      
      <div className="grid grid-cols-1 gap-4" data-grid-root>
        <CategoryTableV2 
          title="Gappers Up" 
          listName="gappers_up" 
        />
      </div>
    </div>
  );
}
```

---

## 🔍 Paso 3: Verificar Funcionamiento

### 1. Iniciar el servidor

```bash
npm run dev
```

### 2. Abrir consola de navegador (F12)

Deberías ver logs (en desarrollo):

```
🟢 [RxWS] Connection opened
📸 [RxWS] Snapshot: gappers_up
✅ [gappers_up] Snapshot initialized: 50 tickers
🔄 [gappers_up] Delta applied: 3 changes
📊 [gappers_up] Aggregates batch: 15 symbols
```

### 3. Verificar virtualización

Si tienes +20 filas, verás en la esquina inferior izquierda (solo en dev):

```
15 / 50 rows
```

Esto significa que solo 15 filas están renderizadas de 50 totales. ✅

---

## 🧪 Paso 4: Probar Features

### Feature 1: Scroll suave (virtualizado)

1. Carga una lista con +100 tickers
2. Scroll rápido arriba/abajo
3. **Resultado esperado**: 60 FPS constante, sin lag

### Feature 2: Múltiples tabs compartiendo estado

```typescript
// TabA.tsx
import { useTickersStore } from '@/stores/useTickersStore';

function TabA() {
  const tickers = useTickersStore(state => state.getOrderedTickers('gappers_up'));
  return <div>Count from TabA: {tickers.length}</div>;
}

// TabB.tsx (diferente componente)
import { useTickersStore } from '@/stores/useTickersStore';

function TabB() {
  const tickers = useTickersStore(state => state.getOrderedTickers('gappers_up'));
  return <div>Count from TabB: {tickers.length}</div>;
}
```

**Resultado esperado**: Ambos tabs muestran el mismo count, actualizándose sincronizados.

### Feature 3: DevTools (Zustand)

1. Instala [Redux DevTools](https://chrome.google.com/webstore/detail/redux-devtools/) (funciona con Zustand)
2. Abre DevTools > Redux tab
3. Verás: `tickers-store`
4. Click en acciones: `initializeList`, `applyDeltas`, etc.
5. **Resultado esperado**: Puedes ver el estado completo e historial de acciones

---

## 📊 Paso 5: Benchmarking (Opcional)

### Comparar V1 vs V2

```typescript
// Test con V1 (sin virtualización)
<CategoryTable title="Test V1" listName="high_volume" />

// Test con V2 (con virtualización)
<CategoryTableV2 title="Test V2" listName="high_volume" />
```

**Cómo medir**:

1. Abre Chrome DevTools > Performance
2. Click "Record"
3. Scrollea la tabla rápidamente por 10 segundos
4. Stop recording
5. Buscar en el timeline: "FPS" en la parte superior

**Resultado esperado**:
- V1 con 500 filas: ~35 FPS
- V2 con 500 filas: ~60 FPS
- V2 con 5,000 filas: ~58 FPS

---

## 🐛 Troubleshooting

### Error: "Cannot find module '@/stores/useTickersStore'"

**Solución**: Asegúrate de que la ruta está configurada en `tsconfig.json`:

```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

### Error: "webSocket is not a constructor"

**Solución**: Reinstala RxJS:

```bash
npm uninstall rxjs
npm install rxjs@7.8.2
```

### Tabla no virtualiza (siempre renderiza todas las filas)

**Solución**: La virtualización solo se activa con +20 filas. Para forzarla:

```typescript
<VirtualizedDataTable
  enableVirtualization={true}  // ← Forzar siempre
  ...
/>
```

### WebSocket no conecta

**Verificar**:

```bash
# 1. Verificar que websocket_server está corriendo
docker ps | grep websocket

# 2. Verificar URL en .env.local
# NEXT_PUBLIC_WS_URL=ws://localhost:9000/ws/scanner

# 3. Probar conexión manual
wscat -c ws://localhost:9000/ws/scanner
```

---

## 🎓 Próximos Pasos

1. **Leer documentación completa**: `ARCHITECTURE_V2.md`
2. **Explorar Zustand store**: `stores/useTickersStore.ts`
3. **Explorar RxJS hook**: `hooks/useRxWebSocket.ts`
4. **Customizar columnas**: `CategoryTableV2.tsx` (línea 200+)
5. **Agregar nuevas listas**: Solo cambiar `listName` prop

---

## 💡 Tips Pro

### Tip 1: Debugging RxJS Streams

```typescript
const ws = useRxWebSocket({ url: WS_URL, debug: true });

// Ver TODOS los mensajes
useEffect(() => {
  const sub = ws.messages$.subscribe(msg => {
    console.table({
      type: msg.type,
      list: msg.list,
      symbol: msg.symbol,
      timestamp: msg.timestamp,
    });
  });
  return () => sub.unsubscribe();
}, []);
```

### Tip 2: Performance Monitoring

```typescript
import { useEffect } from 'react';

function PerformanceMonitor() {
  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();

    const measureFPS = () => {
      frameCount++;
      const now = performance.now();
      
      if (now - lastTime >= 1000) {
        const fps = (frameCount * 1000) / (now - lastTime);
        console.log(`FPS: ${fps.toFixed(1)}`);
        frameCount = 0;
        lastTime = now;
      }
      
      requestAnimationFrame(measureFPS);
    };

    measureFPS();
  }, []);

  return null;
}
```

### Tip 3: Custom RxJS Operators

```typescript
import { pipe, Observable } from 'rxjs';
import { filter, throttleTime, distinctUntilKeyChanged } from 'rxjs/operators';

// Operator custom: solo tickers con RVOL > threshold
const highRVOL = (threshold: number) => 
  pipe(
    filter((ticker: Ticker) => (ticker.rvol || 0) > threshold)
  );

// Uso
ws.aggregates$
  .pipe(
    map(batch => Array.from(batch.data.entries())),
    mergeMap(entries => entries),
    highRVOL(3),
    throttleTime(5000)  // Max 1 alerta cada 5s
  )
  .subscribe(([symbol, data]) => {
    console.log(`🔥 ${symbol} RVOL: ${data.rvol}`);
    // Notificación, alerta, etc.
  });
```

---

## ✅ Checklist de Validación

Antes de pasar a producción, verifica:

- [ ] Sin errores en consola
- [ ] FPS estable (~60) con +500 filas
- [ ] WebSocket reconecta automáticamente
- [ ] Múltiples tabs sincronizados
- [ ] Animaciones fluidas (flash azul/verde/rojo)
- [ ] Column resize/reorder funciona
- [ ] Sorting funciona con virtualización
- [ ] DevTools muestran acciones Zustand
- [ ] Memoria estable (sin memory leaks)

---

## 📚 Recursos

- [TanStack Virtual Docs](https://tanstack.com/virtual/latest/docs/introduction)
- [RxJS Operators](https://rxjs.dev/api/operators)
- [Zustand Best Practices](https://docs.pmnd.rs/zustand/guides/practice-with-no-store-actions)

---

¿Listo para producción? 🚀

