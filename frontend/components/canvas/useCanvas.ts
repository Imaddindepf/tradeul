'use client';

/**
 * useCanvas — hook que gestiona el estado del canvas para una ventana.
 *
 * - Carga/persiste el `CanvasLayout` desde `useWindowState`
 * - Aplica el `defaultLayout` la primera vez
 * - Migra layouts antiguos si cambia la versión del schema
 * - Expone API para: añadir/quitar widgets, mover, redimensionar, resetear
 * - Gestiona el `editMode` (siempre off al abrir la ventana)
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { useWindowState } from '@/contexts/FloatingWindowContext';
import {
    CANVAS_LAYOUT_VERSION,
    newInstanceId,
    type CanvasConfig,
    type CanvasItem,
    type CanvasLayout,
    type WidgetContext,
    type WidgetTypeId,
} from './types';

// El estado persistido tiene que ser compatible con `WindowComponentState`
// (= Record<string, unknown>), por eso usamos type intersection en vez de
// interface — así el index signature se cumple sin perder la tipificación
// concreta del campo `canvasLayout`.
type CanvasWindowState = {
    canvasLayout?: CanvasLayout;
} & Record<string, unknown>;

export interface UseCanvasReturn {
    layout: CanvasLayout;
    editMode: boolean;
    setEditMode: (v: boolean) => void;
    toggleEditMode: () => void;
    /** Aplica un layout completo (ej. al cambiar de plantilla) */
    setLayout: (next: CanvasLayout) => void;
    /** Reemplaza solo los `items`. Útil tras un drag/resize de RGL. */
    updateItems: (items: CanvasItem[]) => void;
    /** Añade un widget por tipo, opcionalmente en una posición concreta */
    addWidget: (type: WidgetTypeId, position?: { x: number; y: number }) => void;
    /** Elimina una instancia por id */
    removeWidget: (instanceId: string) => void;
    /** Resetea al layout default */
    resetLayout: () => void;
    /** Devuelve true si el item está en el layout */
    hasInstance: (instanceId: string) => boolean;
}

export function useCanvas<P extends WidgetContext = WidgetContext>(
    config: CanvasConfig<P>,
): UseCanvasReturn {
    const { state, updateState } = useWindowState<CanvasWindowState>();
    const [editMode, setEditMode] = useState(false);

    // Para evitar bucles infinitos cuando RGL reporta cambios derivados de
    // nuestro propio render, comparamos contra la última escritura.
    const lastWriteRef = useRef<string>('');

    const layout: CanvasLayout = useMemo(() => {
        const saved = state.canvasLayout;
        if (saved && saved.version === CANVAS_LAYOUT_VERSION) return saved;
        // Layouts de versión distinta → resetear al default (sin perder ticker
        // u otros campos persistidos). Una migración real se haría aquí.
        return config.defaultLayout;
    }, [state.canvasLayout, config.defaultLayout]);

    const persistLayout = useCallback(
        (next: CanvasLayout) => {
            const serialized = JSON.stringify(next);
            if (serialized === lastWriteRef.current) return;
            lastWriteRef.current = serialized;
            updateState({ canvasLayout: next });
        },
        [updateState],
    );

    const setLayout = useCallback(
        (next: CanvasLayout) => {
            persistLayout({
                ...next,
                version: CANVAS_LAYOUT_VERSION,
            });
        },
        [persistLayout],
    );

    const updateItems = useCallback(
        (items: CanvasItem[]) => {
            persistLayout({
                version: CANVAS_LAYOUT_VERSION,
                items,
            });
        },
        [persistLayout],
    );

    const widgetByType = useMemo(() => {
        const map = new Map<WidgetTypeId, (typeof config.manifest.widgets)[number]>();
        for (const w of config.manifest.widgets) {
            map.set(w.type, w);
        }
        return map;
    }, [config.manifest.widgets]);

    const findInsertPosition = useCallback(
        (items: CanvasItem[], w: number, h: number): { x: number; y: number } => {
            // Insertamos siempre al final, en la primera fila libre (sencillo y
            // predecible). RGL reordenará si hace falta.
            const maxY = items.reduce((acc, it) => Math.max(acc, it.y + it.h), 0);
            return { x: 0, y: maxY };
        },
        [],
    );

    const addWidget = useCallback(
        (type: WidgetTypeId, position?: { x: number; y: number }) => {
            const def = widgetByType.get(type);
            if (!def) {
                if (process.env.NODE_ENV !== 'production') {
                    console.warn(`[canvas] Unknown widget type "${type}"`);
                }
                return;
            }
            const pos = position ?? findInsertPosition(layout.items, def.defaultSize.w, def.defaultSize.h);
            const newItem: CanvasItem = {
                i: newInstanceId(type),
                type,
                x: pos.x,
                y: pos.y,
                w: def.defaultSize.w,
                h: def.defaultSize.h,
            };
            updateItems([...layout.items, newItem]);
        },
        [layout.items, widgetByType, findInsertPosition, updateItems],
    );

    const removeWidget = useCallback(
        (instanceId: string) => {
            updateItems(layout.items.filter((it) => it.i !== instanceId));
        },
        [layout.items, updateItems],
    );

    const resetLayout = useCallback(() => {
        setLayout(config.defaultLayout);
    }, [config.defaultLayout, setLayout]);

    const hasInstance = useCallback(
        (instanceId: string) => layout.items.some((it) => it.i === instanceId),
        [layout.items],
    );

    const toggleEditMode = useCallback(() => setEditMode((v) => !v), []);

    return {
        layout,
        editMode,
        setEditMode,
        toggleEditMode,
        setLayout,
        updateItems,
        addWidget,
        removeWidget,
        resetLayout,
        hasInstance,
    };
}
