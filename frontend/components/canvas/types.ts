/**
 * Canvas / Widget Contract
 *
 * Sistema genérico de widgets para ventanas tipo "mini-dashboard" (FAN, futuro
 * Heatmap pro, etc.). Cualquier ventana que quiera usarlo declara un
 * `WidgetManifest` y un `defaultLayout`.
 *
 * El contract es deliberadamente minimalista: cada widget es un componente
 * React que recibe `WidgetContext` y renderiza su propio contenido. El layout,
 * tamaños y persistencia los gestiona el canvas.
 */

import type { ComponentType, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

/**
 * Identificador único de un widget dentro del manifest del canvas.
 * No confundir con la instancia (un mismo widget puede aparecer varias veces).
 */
export type WidgetTypeId = string;

/**
 * Instancia concreta de un widget en el canvas. El mismo `type` puede aparecer
 * más de una vez (ej. dos Charts a distintos timeframes), por eso necesitamos
 * `instanceId`.
 */
export type WidgetInstanceId = string;

/**
 * Categoría en el panel "Add widget". Solo afecta a la presentación.
 */
export type WidgetCategory =
    | 'overview'
    | 'fundamentals'
    | 'market'
    | 'intel'
    | 'technical'
    | 'risk';

/**
 * Props que recibe cada widget. El canvas se encarga de inyectarlas.
 * Los widgets concretos extenderán este tipo con su propia data via generics
 * o context.
 */
export interface WidgetContext {
    /** ID único de esta instancia */
    instanceId: WidgetInstanceId;
    /** Modo edición activo (afecta a algunos widgets internamente) */
    editMode: boolean;
}

/**
 * Definición de un tipo de widget. Lo registra cada ventana en su manifest.
 */
export interface WidgetDefinition<P extends WidgetContext = WidgetContext> {
    /** Identificador único dentro del manifest */
    type: WidgetTypeId;
    /** Categoría en el palette */
    category: WidgetCategory;
    /** Título mostrado en la cabecera del widget y en el palette */
    title: string;
    /** Subtítulo descriptivo (solo en el palette) */
    description?: string;
    /** Icono para el palette (opcional) */
    icon?: LucideIcon;
    /** Componente que renderiza el contenido del widget (sin la cabecera) */
    component: ComponentType<P>;
    /** Tamaño por defecto al insertar el widget */
    defaultSize: { w: number; h: number };
    /** Tamaños mínimos (en celdas del grid) */
    minSize: { w: number; h: number };
    /** Tamaños máximos opcionales */
    maxSize?: { w: number; h: number };
    /** Si true, el widget no se puede eliminar (ej. cabecera principal) */
    locked?: boolean;
    /** Si true, no aparece en el palette pero puede estar en el layout */
    hiddenFromPalette?: boolean;
    /**
     * Si true, el widget renderiza su propia cabecera personalizada y NO se
     * envuelve en `WidgetShell`. Útil para widgets que necesitan controles
     * propios (ej. tabs del Chart).
     */
    customHeader?: boolean;
}

/**
 * Manifest completo de una ventana. Lo declara cada ventana que use el canvas.
 */
export interface WidgetManifest<P extends WidgetContext = WidgetContext> {
    /** Identificador único del manifest (ej. 'fan', 'heatmap-pro') */
    id: string;
    /** Lista de tipos de widget disponibles */
    widgets: ReadonlyArray<WidgetDefinition<P>>;
}

/**
 * Posición y tamaño de una instancia en el grid (compatible con
 * react-grid-layout). Persistido en `useWindowState`.
 */
export interface CanvasItem {
    /** ID único de esta instancia */
    i: WidgetInstanceId;
    /** Tipo de widget (referencia al manifest) */
    type: WidgetTypeId;
    /** Posición columna (0..cols-1) */
    x: number;
    /** Posición fila (0..N) */
    y: number;
    /** Ancho en columnas */
    w: number;
    /** Alto en filas */
    h: number;
    /** Estado interno opcional del widget (ej. tab seleccionada del chart) */
    state?: Record<string, unknown>;
}

/**
 * Layout completo del canvas. Es lo que se persiste por ventana.
 */
export interface CanvasLayout {
    /** Versión del schema; se incrementa si rompemos compatibilidad */
    version: number;
    /** Lista de instancias en el grid */
    items: CanvasItem[];
}

/**
 * Plantilla predefinida ("Default", "Day Trader", "Value Investor", ...).
 */
export interface CanvasTemplate {
    id: string;
    name: string;
    description?: string;
    layout: CanvasLayout;
}

/**
 * Configuración global del canvas, pasada al componente raíz.
 */
export interface CanvasConfig<P extends WidgetContext = WidgetContext> {
    manifest: WidgetManifest<P>;
    /** Layout inicial si no hay nada persistido */
    defaultLayout: CanvasLayout;
    /** Plantillas disponibles (incluye el default) */
    templates?: CanvasTemplate[];
    /** Número de columnas del grid (default 12) */
    cols?: number;
    /** Altura de cada fila en píxeles (default 32 — extra denso) */
    rowHeight?: number;
}

/**
 * Helper para generar nuevos IDs únicos de instancia.
 */
export function newInstanceId(type: WidgetTypeId): WidgetInstanceId {
    return `${type}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Schema actual del CanvasLayout. Si cambia el formato, incrementar y añadir
 * migración en `useCanvas`.
 */
export const CANVAS_LAYOUT_VERSION = 1 as const;

/**
 * Helper render type para widgets que necesitan envoltorio personalizado.
 */
export type WidgetRenderProps = WidgetContext & {
    children?: ReactNode;
};
