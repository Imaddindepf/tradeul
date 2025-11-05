# Diseño Premium Moderno - Trading Scanner

## Nuevo Diseño Implementado

Un diseño completamente renovado, ultra-compacto y adaptable inspirado en las mejores plataformas de trading modernas como TradingView Pro, Robinhood, y terminales financieros premium.

## Sistema de Escalado Inteligente

La tabla ahora se adapta automáticamente según su tamaño:

**Escala XS (< 600px de ancho)**

- Padding: px-2 py-1.5
- Font size: 10px headers, 11px celdas
- Máxima densidad de información

**Escala SM (600-900px)**

- Padding: px-2.5 py-2
- Font size: 11px headers, 12px celdas
- Balance entre densidad y legibilidad

**Escala MD (900-1200px)**

- Padding: px-3 py-2.5
- Font size: 12px headers, 14px celdas
- Configuración estándar

**Escala LG (> 1200px)**

- Padding: px-4 py-3
- Font size: 12px headers, 14px celdas
- Máximo confort visual

## Columnas Ultra-Compactas

Tamaños optimizados para máxima densidad:

```
# (Rank):     40px  (min: 35px)
Symbol:      75px  (min: 55px)
Price:       80px  (min: 60px)
Gap %:       85px  (min: 70px)
Volume:      90px  (min: 70px)
RVOL:        70px  (min: 55px)
Market Cap: 100px  (min: 80px)

TOTAL: ~540px para 7 columnas completas
```

Antes necesitabas ~750px. Ahora caben más columnas en menos espacio.

## Características Clave

### 1. Estética Limpia y Moderna

**Fondo Blanco Limpio**

- Base blanca profesional
- Bordes sutiles (slate-200)
- Sombras suaves (shadow-lg)
- Bordes redondeados (4px)

**Espaciado Generoso**

- Padding: 16px-24px (px-4 a px-6)
- Line height mejorado (py-3 a py-4)
- Gaps consistentes (gap-3 a gap-6)
- Mejor breathing room

### 2. Header Premium

**Diseño Horizontal Limpio**

```
┌─────────────────────────────────────────────────────┐
│ ║ Gappers Up  ● Live  20 tickers  seq 12345 Updated │
└─────────────────────────────────────────────────────┘
```

**Elementos (Compactos)**

- Barra azul vertical más delgada (h-6)
- Título reducido: text-base
- Estado "Live" con punto más pequeño (1.5px)
- Badges compactos: px-2 py-0.5
- Gaps reducidos: gap-2 y gap-1.5
- Header height: py-2.5 (antes py-4)

**Colores del Header**

```css
Background: white
Border: blue-500 (2px bottom)
Título: slate-900, font-bold, text-base
Estado Live: emerald-600, text-xs
Badges: blue-50 con border-blue-200, más compactos
```

### 3. Tabla Ultra-Limpia

**Headers**

```
Background: slate-50 (muy sutil)
Text: slate-600, semibold, uppercase
Border: slate-100 (delgados)
Hover: text-blue-600
```

**Filas**

```
Background: white (sin rayas)
Hover: slate-50 (sutil)
Border: slate-100 (1px)
Spacing: py-3
```

**Celdas**

- Padding generoso (px-4 py-3)
- Texto slate-900 para máxima legibilidad
- Sin bordes verticales innecesarios
- Overflow elegante

### 4. Columnas con Diseño Premium

**# (Rank)**

```
Color: slate-400
Font: semibold
Size: xs
Align: center
```

**Symbol**

```
Color: blue-600 (corporativo)
Font: bold
Size: sm
```

**Price**

```
Color: slate-900
Font: mono, semibold
Flash: bg-blue-50 con rounded
Transition: 200ms
```

**Gap % (Innovación: Badges con Color)**

```
Positivo:
  bg-emerald-50
  text-emerald-700
  px-2 py-1 rounded-md
  border cuando cambia (ring-2 ring-blue-200)

Negativo:
  bg-rose-50
  text-rose-700
  px-2 py-1 rounded-md
  border cuando cambia (ring-2 ring-blue-200)
```

**Volume**

```
Color: slate-700
Font: mono, medium
```

**RVOL (Destacado Premium)**

```
Alto (>3):
  bg-blue-50
  text-blue-700
  border-blue-200
  px-2 py-1 rounded-md

Medio (>1.5):
  text-blue-600

Bajo:
  text-slate-500
```

**Market Cap**

```
Color: slate-600
Font: mono
```

### 5. Handles de Resize Modernos

**Columnas**

```
Normal: w-px, slate-200
Hover: w-1, blue-500
Activo: blue-600
Indicador: línea azul redondeada (w-0.5 h-4)
```

**Tabla - Esquina**

```
Size: 3x3px
Color: blue-500
Hover: blue-600
Activo: 4x4px
Icon: borde angular blanco
Rounded: rounded-tl
```

**Tabla - Bordes**

```
Visual: barra sutil (slate-300)
Hover: blue-500
Transition: 200ms
Position: center de cada borde
```

### 6. Indicador de Dimensiones Premium

```
Background: white
Border: slate-200 rounded
Text: slate-700
Numbers: blue-600 bold
Separator: slate-400
Shadow: shadow-xl
Padding: px-3 py-1.5
```

Muestra: `1200 × 600` con números en azul

### 7. Paleta de Colores Refinada

**Azules (Corporativo)**

```
blue-600: Símbolos, handles activos
blue-500: Bordes destacados, handles hover
blue-400: -
blue-200: Borders de badges
blue-50: Backgrounds sutiles, flash
```

**Grises (Profesional)**

```
slate-900: Texto principal
slate-700: Texto secundario
slate-600: Headers, texto terciario
slate-500: RVOL bajo
slate-400: Números de fila
slate-300: Handles normales
slate-200: Bordes principales
slate-100: Separadores sutiles
slate-50: Backgrounds, hover
```

**Estados**

```
emerald-600: Live status
emerald-700: Gap positivo
emerald-50: Background positivo

rose-700: Gap negativo
rose-50: Background negativo
```

### 8. Transiciones Suaves

```
Colors: 150-200ms
Backgrounds: 150-200ms
Hover: 150ms
Flash: 200ms
Resize handles: 200ms
```

### 9. Tipografía Profesional

**Familias**

```
Sans: Default para headers y labels
Mono: Números, precios, volumen
```

**Pesos**

```
bold: Títulos, símbolos
semibold: Headers, precios, numeros importantes
medium: Volumen, texto secundario
regular: -
```

**Tamaños**

```
text-lg: Título principal (18px)
text-sm: Celdas (14px)
text-xs: Headers, badges (12px)
```

### 10. Sombras y Profundidad

**Tabla**

```
shadow-lg: Tabla principal
```

**Headers Sticky**

```
shadow-sm: Cuando scroll
backdrop-blur: 10px
background: white 98% opacity
```

**Resize Indicator**

```
shadow-xl: Máxima visibilidad
```

## Comparación Visual

**ANTES (Oscuro)**

```
┌──────────────────────────────────┐
│ ████████ HEADER OSCURO ████████  │
├══════════════════════════════════┤
│ ■■ HEADERS OSCUROS ■■■■■■■■■    │
├──────────────────────────────────┤
│ símbolo  precio  gap%            │
│ AAPL     178     +2.3%           │
└──────────────────────────────────┘
```

**AHORA (Premium)**

```
┌──────────────────────────────────┐
│ ║ Gappers Up  ● Live  20 tickers │ limpio
├──────────────────────────────────┤
│ SYMBOL  PRICE  GAP %            │ headers claros
├──────────────────────────────────┤
│ AAPL    178    [+2.3%]          │ badges color
│ TSLA    245    [-1.8%]          │ diseño moderno
└──────────────────────────────────┘
```

## Ventajas del Nuevo Diseño

**1. Densidad de Información**

- 30% más compacto que antes
- Caben más columnas en pantalla
- Escalado inteligente según tamaño
- Sin sacrificar legibilidad

**2. Adaptabilidad**

- 4 escalas automáticas (XS, SM, MD, LG)
- Font size dinámico
- Padding adaptativo
- Todo proporcional

**3. Legibilidad Óptima**

- Fondo blanco con alto contraste
- Texto oscuro sobre claro
- Spacing calculado por escala
- Badges de color para datos clave

**4. Modernidad**

- Badges con color para datos importantes
- Bordes redondeados sutiles
- Sombras mínimas
- Animaciones rápidas (200ms)

**5. Profesionalismo**

- Sin elementos infantiles
- Colores refinados
- Tipografía cuidada
- Spacing consistente por escala

**6. Usabilidad**

- Handles sutiles pero funcionales
- Estados claros (Live/Offline)
- Información bien organizada
- Escaneo visual rápido

**7. Escalabilidad Total**

- Completamente redimensionable
- Mínimo: 200x150px
- Máximo: ilimitado
- Contenido se adapta automáticamente

## Inspiración

Este diseño está inspirado en:

✓ **TradingView Pro** - Limpieza y claridad
✓ **Robinhood** - Badges de color para datos
✓ **Bloomberg Terminal** - Densidad de información
✓ **Figma** - Handles de resize sutiles
✓ **Linear** - Spacing y tipografía

## Archivos Modificados

```
frontend/
├── components/
│   ├── ui/
│   │   └── ResizableTable.tsx    ← Diseño blanco limpio
│   └── scanner/
│       └── GappersTable.tsx      ← Header horizontal premium
└── app/
    └── globals.css               ← Sombras y animaciones sutiles
```

## Testing

```bash
cd frontend
npm run dev
```

**Verificar:**

- Fondo blanco limpio
- Header compacto con barra azul
- Badges de color en Gap%
- RVOL resaltado con border
- Handles sutiles pero funcionales
- Animaciones suaves (200ms)

**Probar escalado:**

1. Haz la tabla grande (>1200px) - escala LG
2. Achica a medio (~900px) - escala MD
3. Achica más (~700px) - escala SM
4. Achica al mínimo (<600px) - escala XS

Observa cómo el texto y padding se adaptan automáticamente.

**Comparar densidad:**

- Tabla grande: spacing generoso, fácil lectura
- Tabla pequeña: ultra-compacto, máxima información
- Todo sin perder diseño ni funcionalidad

## Resultado Final

Un scanner profesional, moderno y ultra-compacto que:

- 30% más eficiente en uso de espacio
- Se adapta inteligentemente a cualquier tamaño
- Mantiene legibilidad en todos los tamaños
- 4 escalas automáticas de densidad
- Usa azul corporativo de forma elegante
- Completamente redimensionable
- Luce premium y profesional

**Ventajas clave:**

- Tabla pequeña = más columnas visibles
- Tabla grande = máxima comodidad
- Transiciones suaves entre escalas
- Sin sacrificar diseño

**Ideal para:**

- Traders que usan múltiples monitores
- Layouts con varias tablas
- Dashboards compactos
- Máxima densidad de información

**Diseño listo para producción.**

## Patrón reusable de tablas (2025-11)

- `components/table/MarketTableLayout.tsx`: encabezado común para todas las tablas de mercado.
  - Props clave: `title`, `isLive`, `count`, `sequence`, `lastUpdateTime`, `rightActions`.
- `components/table/BaseDataTable.tsx`: envoltorio genérico sobre `ResizableTable` que fija estados de carga/vacío y opciones comunes.
  - Props clave: `table` (instancia TanStack), `isLoading`, `header` (normalmente `MarketTableLayout`).
- `lib/table/dataAdapter.ts`: interfaz `TableDataAdapter<T>` para unificar cómo conectamos snapshot/deltas (WS/API) por tabla.

Ejemplo de uso en `GappersTable`:

1) Construir columnas y `table` (TanStack).
2) Usar `BaseDataTable` y pasar `MarketTableLayout` como `header`.

Esto permite crear nuevas tablas replicando el patrón (solo cambian columnas y el adaptador de datos).
