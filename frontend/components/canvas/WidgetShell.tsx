'use client';

/**
 * WidgetShell
 *
 * Envoltorio estándar de un widget del canvas. Proporciona:
 *  - Cabecera de 18px con drag-handle (solo en edit), título y acciones
 *  - Body con scroll automático y tipografía monospace
 *  - Botón de cerrar (solo en edit)
 *  - Menú "⋯" opcional con acciones del widget
 *
 * Los widgets con `customHeader: true` en su `WidgetDefinition` no usan este
 * shell — renderizan su propio chrome.
 */

import { forwardRef, type ReactNode } from 'react';
import { GripVertical, X, MoreHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface WidgetShellProps {
    title: string;
    children: ReactNode;
    editMode: boolean;
    /** Permite eliminar el widget. Si el widget es `locked`, se ignora. */
    onRemove?: () => void;
    /** Render opcional del contenido del menú "⋯" */
    menu?: ReactNode;
    /** Slot para controles extra a la derecha del título (tabs, filtros, etc.) */
    headerExtra?: ReactNode;
    /** Override del padding del body (algunos widgets necesitan padding 0) */
    bodyPadding?: string;
    className?: string;
}

export const WidgetShell = forwardRef<HTMLDivElement, WidgetShellProps>(function WidgetShell(
    { title, children, editMode, onRemove, menu, headerExtra, bodyPadding, className },
    ref,
) {
    return (
        <div ref={ref} className={cn('widget-shell', className)}>
            <div className="widget-shell-header">
                <div className="flex items-center min-w-0 flex-1">
                    {editMode && (
                        <span className="widget-shell-drag widget-drag-handle" aria-hidden="true">
                            <GripVertical size={10} strokeWidth={2} />
                        </span>
                    )}
                    <span className="widget-shell-title">{title}</span>
                </div>

                {headerExtra && (
                    <div className="flex items-center mx-2 min-w-0">{headerExtra}</div>
                )}

                <div className="widget-shell-actions">
                    {menu && (
                        <button
                            type="button"
                            className="widget-shell-action-btn"
                            onMouseDown={(e) => e.stopPropagation()}
                            aria-label="More"
                            title="More"
                        >
                            <MoreHorizontal size={10} strokeWidth={2.25} />
                        </button>
                    )}
                    {onRemove && (
                        <button
                            type="button"
                            className="widget-shell-action-btn widget-shell-close danger"
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                                e.stopPropagation();
                                onRemove();
                            }}
                            aria-label="Remove widget"
                            title="Remove widget"
                        >
                            <X size={10} strokeWidth={2.25} />
                        </button>
                    )}
                </div>
            </div>

            <div className="widget-shell-body" style={bodyPadding ? { padding: bodyPadding } : undefined}>
                {children}
            </div>
        </div>
    );
});
