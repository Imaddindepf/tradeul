'use client';

/**
 * WidgetPalette
 *
 * Drawer compacto para añadir widgets al canvas. Agrupa por categoría, muestra
 * descripciones, y filtra widgets ya añadidos si son `singleton` (futuro).
 *
 * UX:
 *  - Botón "+" en la toolbar abre el drawer
 *  - Clic en un widget → se añade al canvas
 *  - Esc o clic fuera cierra
 *  - Search input arriba para filtrar
 */

import { useMemo, useState, useEffect, useRef } from 'react';
import { X, Plus, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
    CanvasConfig,
    WidgetCategory,
    WidgetContext,
    WidgetDefinition,
} from './types';

const CATEGORY_LABEL: Record<WidgetCategory, string> = {
    overview: 'Overview',
    fundamentals: 'Fundamentals',
    market: 'Market',
    intel: 'Intel',
    technical: 'Technical',
    risk: 'Risk',
};

const CATEGORY_ORDER: WidgetCategory[] = [
    'overview',
    'market',
    'fundamentals',
    'technical',
    'intel',
    'risk',
];

export interface WidgetPaletteProps<P extends WidgetContext = WidgetContext> {
    open: boolean;
    onClose: () => void;
    config: CanvasConfig<P>;
    onAdd: (type: string) => void;
}

export function WidgetPalette<P extends WidgetContext = WidgetContext>({
    open,
    onClose,
    config,
    onAdd,
}: WidgetPaletteProps<P>) {
    const [query, setQuery] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setQuery('');
            // Foco al abrir
            setTimeout(() => inputRef.current?.focus(), 30);
        }
    }, [open]);

    // Cerrar con ESC
    useEffect(() => {
        if (!open) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [open, onClose]);

    const grouped = useMemo(() => {
        const map = new Map<WidgetCategory, WidgetDefinition<P>[]>();
        const q = query.trim().toLowerCase();
        for (const w of config.manifest.widgets) {
            if (w.hiddenFromPalette) continue;
            if (q && !w.title.toLowerCase().includes(q) && !w.description?.toLowerCase().includes(q)) {
                continue;
            }
            const list = map.get(w.category) ?? [];
            list.push(w);
            map.set(w.category, list);
        }
        return map;
    }, [config.manifest.widgets, query]);

    if (!open) return null;

    return (
        <>
            {/* Backdrop transparente para capturar clicks fuera */}
            <div
                className="absolute inset-0 z-30"
                onClick={onClose}
                aria-hidden="true"
            />
            {/* Drawer anclado a la derecha del canvas */}
            <div
                className="absolute top-0 right-0 bottom-0 z-40 flex flex-col bg-surface border-l border-border shadow-2xl"
                style={{ width: 240, animation: 'slideInLeft 0.18s ease-out' }}
            >
                {/* Header */}
                <div className="flex items-center justify-between h-[22px] px-2 bg-surface-hover border-b border-border">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/85">
                        Add Widget
                    </span>
                    <button
                        type="button"
                        className="flex items-center justify-center w-4 h-4 rounded-sm text-muted-fg hover:text-foreground hover:bg-muted"
                        onClick={onClose}
                        aria-label="Close palette"
                    >
                        <X size={10} strokeWidth={2.25} />
                    </button>
                </div>

                {/* Search */}
                <div className="px-2 py-1.5 border-b border-border">
                    <div className="flex items-center gap-1.5 px-1.5 h-5 bg-surface-inset border border-border rounded-sm">
                        <Search size={9} className="text-muted-fg" strokeWidth={2.25} />
                        <input
                            ref={inputRef}
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search widgets..."
                            className="flex-1 bg-transparent border-0 outline-none text-[10px] text-foreground placeholder:text-muted-fg/60 font-mono"
                        />
                    </div>
                </div>

                {/* List */}
                <div className="flex-1 overflow-auto py-1">
                    {CATEGORY_ORDER.map((cat) => {
                        const items = grouped.get(cat);
                        if (!items || items.length === 0) return null;
                        return (
                            <div key={cat} className="mb-2">
                                <div className="px-2 py-1 text-[9px] font-semibold uppercase tracking-wider text-muted-fg">
                                    {CATEGORY_LABEL[cat]}
                                </div>
                                <div>
                                    {items.map((w) => (
                                        <PaletteItem
                                            key={w.type}
                                            widget={w}
                                            onAdd={() => {
                                                onAdd(w.type);
                                            }}
                                        />
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                    {grouped.size === 0 && (
                        <div className="px-3 py-4 text-[10px] text-muted-fg/70 text-center">
                            No widgets match &quot;{query}&quot;
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

function PaletteItem<P extends WidgetContext>({
    widget,
    onAdd,
}: {
    widget: WidgetDefinition<P>;
    onAdd: () => void;
}) {
    const Icon = widget.icon;
    return (
        <button
            type="button"
            onClick={onAdd}
            className={cn(
                'group flex items-start gap-2 w-full px-2 py-1 text-left',
                'hover:bg-foreground/[0.04] transition-colors cursor-pointer',
            )}
        >
            {Icon ? (
                <Icon size={11} className="text-muted-fg group-hover:text-foreground mt-[1px]" strokeWidth={2} />
            ) : (
                <Plus size={11} className="text-muted-fg group-hover:text-foreground mt-[1px]" strokeWidth={2} />
            )}
            <div className="flex-1 min-w-0">
                <div className="text-[10px] font-medium text-foreground leading-[14px] truncate">
                    {widget.title}
                </div>
                {widget.description && (
                    <div className="text-[9px] text-muted-fg leading-[12px] truncate">
                        {widget.description}
                    </div>
                )}
            </div>
        </button>
    );
}
