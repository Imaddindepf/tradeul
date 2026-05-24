'use client';

/**
 * CanvasGrid
 *
 * Renderiza un grid de widgets editable, basado en react-grid-layout. Es
 * agnóstico al tipo de widgets — se le pasa un `CanvasConfig` y un
 * `UseCanvasReturn` (devuelto por `useCanvas`).
 *
 * Diseño:
 *  - Edit mode: muestra dot-grid de fondo, drag-handles, resize handles
 *  - Read mode: layout limpio, sin chrome editable
 *  - Cada widget se envuelve en `WidgetShell` salvo que declare `customHeader`
 *  - Drag handle es `.widget-drag-handle` (definido en WidgetShell)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
// Usamos la API "legacy" (v1-compat) de react-grid-layout v2. Ofrece flat props
// (cols, rowHeight, margin, isDraggable, draggableHandle, etc.) que son más
// directos que los config objects de la nueva API v2.
import GridLayout from 'react-grid-layout/legacy';
import type { Layout, LayoutItem } from 'react-grid-layout';
import { WidgetShell } from './WidgetShell';
import type {
    CanvasConfig,
    CanvasItem,
    WidgetContext,
} from './types';
import type { UseCanvasReturn } from './useCanvas';
import './canvas.css';

export interface CanvasGridProps<P extends WidgetContext = WidgetContext> {
    config: CanvasConfig<P>;
    canvas: UseCanvasReturn;
    /** Props extra a inyectar en CADA widget (ej. ticker para FAN) */
    widgetProps?: Omit<P, keyof WidgetContext>;
}

/**
 * Hook interno para medir el ancho real del contenedor (RGL requiere width
 * explícito). Más fiable que `WidthProvider` para casos con redimensionamiento
 * de ventana flotante.
 */
function useContainerWidth(): [React.RefObject<HTMLDivElement>, number] {
    const ref = useRef<HTMLDivElement>(null);
    const [width, setWidth] = useState(0);

    useEffect(() => {
        if (!ref.current) return;
        const el = ref.current;
        const measure = () => {
            const w = el.getBoundingClientRect().width;
            setWidth(w);
        };
        measure();
        const ro = new ResizeObserver(measure);
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    return [ref, width];
}

export function CanvasGrid<P extends WidgetContext = WidgetContext>({
    config,
    canvas,
    widgetProps,
}: CanvasGridProps<P>) {
    const cols = config.cols ?? 12;
    const rowHeight = config.rowHeight ?? 32;
    const [containerRef, width] = useContainerWidth();

    const widgetByType = useMemo(() => {
        const map = new Map<string, (typeof config.manifest.widgets)[number]>();
        for (const w of config.manifest.widgets) map.set(w.type, w);
        return map;
    }, [config.manifest.widgets]);

    // RGL espera un Layout (readonly LayoutItem[]). Mapeamos desde nuestros CanvasItem.
    const rglLayout: LayoutItem[] = useMemo(
        () =>
            canvas.layout.items.map((it) => {
                const def = widgetByType.get(it.type);
                return {
                    i: it.i,
                    x: it.x,
                    y: it.y,
                    w: it.w,
                    h: it.h,
                    minW: def?.minSize.w ?? 1,
                    minH: def?.minSize.h ?? 1,
                    maxW: def?.maxSize?.w,
                    maxH: def?.maxSize?.h,
                    static: !canvas.editMode,
                };
            }),
        [canvas.layout.items, canvas.editMode, widgetByType],
    );

    const handleLayoutChange = useCallback(
        (next: Layout) => {
            if (!canvas.editMode) return; // ignorar reportes espurios en read mode
            // Merge: mantener `type` y `state` originales, actualizar pos/tamaño
            const byId = new Map(canvas.layout.items.map((it) => [it.i, it]));
            const merged: CanvasItem[] = next
                .map((n) => {
                    const original = byId.get(n.i);
                    if (!original) return null;
                    return {
                        ...original,
                        x: n.x,
                        y: n.y,
                        w: n.w,
                        h: n.h,
                    };
                })
                .filter((it): it is CanvasItem => it !== null);
            canvas.updateItems(merged);
        },
        [canvas],
    );

    // No renderizar el grid hasta tener ancho real (evita parpadeos)
    if (width === 0) {
        return <div ref={containerRef} className="w-full h-full" aria-hidden="true" />;
    }

    return (
        <div ref={containerRef} className="w-full h-full">
            <GridLayout
                className={`canvas-grid ${canvas.editMode ? 'canvas-edit' : ''}`}
                layout={rglLayout}
                cols={cols}
                width={width}
                rowHeight={rowHeight}
                margin={[4, 4]}
                containerPadding={[4, 4]}
                isDraggable={canvas.editMode}
                isResizable={canvas.editMode}
                draggableHandle=".widget-drag-handle"
                compactType="vertical"
                preventCollision={false}
                onLayoutChange={handleLayoutChange}
                useCSSTransforms
            >
                {canvas.layout.items.map((item) => {
                    const def = widgetByType.get(item.type);
                    if (!def) {
                        return (
                            <div key={item.i}>
                                <UnknownWidget type={item.type} />
                            </div>
                        );
                    }

                    const ctx: WidgetContext = {
                        instanceId: item.i,
                        editMode: canvas.editMode,
                    };
                    const Component = def.component;
                    const componentProps = { ...(widgetProps as object), ...ctx } as P;

                    const content = <Component {...componentProps} />;

                    return (
                        <div key={item.i}>
                            {def.customHeader ? (
                                content
                            ) : (
                                <WidgetShell
                                    title={def.title}
                                    editMode={canvas.editMode}
                                    onRemove={
                                        !def.locked && canvas.editMode
                                            ? () => canvas.removeWidget(item.i)
                                            : undefined
                                    }
                                >
                                    {content}
                                </WidgetShell>
                            )}
                        </div>
                    );
                })}
            </GridLayout>
        </div>
    );
}

function UnknownWidget({ type }: { type: string }) {
    return (
        <div className="widget-shell h-full">
            <div className="widget-shell-header">
                <span className="widget-shell-title">Unknown widget</span>
            </div>
            <div className="widget-shell-body opacity-60">
                Widget type &quot;{type}&quot; not registered in manifest.
            </div>
        </div>
    );
}
