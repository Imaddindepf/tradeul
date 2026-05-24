'use client';

/**
 * CanvasToolbar
 *
 * Barra superior fina (22px) que se renderiza dentro de la ventana de FAN (u
 * otra ventana con canvas). Contiene:
 *  - Pill "EDIT" toggle
 *  - Dropdown de plantillas
 *  - Botón "+ Add" que abre el WidgetPalette
 *  - Botón "Reset" (solo visible en edit mode)
 *
 * El toolbar es opcional — la ventana decide si lo renderiza o si integra
 * estos controles en su propio header.
 */

import { useState, useRef, useEffect } from 'react';
import { SlidersHorizontal, Plus, LayoutGrid, RotateCcw, ChevronDown, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CanvasTemplate } from './types';

export interface CanvasToolbarProps {
    editMode: boolean;
    onToggleEdit: () => void;
    onOpenPalette: () => void;
    onReset: () => void;
    templates?: CanvasTemplate[];
    activeTemplateId?: string | null;
    onSelectTemplate?: (templateId: string) => void;
    /** Slot a la izquierda (ej. ticker info en FAN) */
    leftSlot?: React.ReactNode;
    /** Slot a la derecha (ej. botones extra) */
    rightSlot?: React.ReactNode;
}

export function CanvasToolbar({
    editMode,
    onToggleEdit,
    onOpenPalette,
    onReset,
    templates,
    activeTemplateId,
    onSelectTemplate,
    leftSlot,
    rightSlot,
}: CanvasToolbarProps) {
    return (
        <div
            className="flex items-center justify-between h-[22px] px-2 bg-surface-hover border-b border-border select-none"
            style={{ flexShrink: 0 }}
        >
            <div className="flex items-center gap-2 min-w-0 flex-1">
                <button
                    type="button"
                    onClick={onToggleEdit}
                    className={cn(
                        'flex items-center gap-1 h-[16px] px-1.5 rounded-sm text-[9px] font-semibold uppercase tracking-wider transition-colors',
                        editMode
                            ? 'bg-primary/15 text-primary border border-primary/40'
                            : 'text-muted-fg hover:text-foreground hover:bg-muted border border-transparent',
                    )}
                    title={editMode ? 'Exit edit mode' : 'Enter edit mode'}
                >
                    <SlidersHorizontal size={9} strokeWidth={2.25} />
                    EDIT
                </button>

                {leftSlot && (
                    <div className="flex items-center min-w-0 flex-1 text-[10px]">{leftSlot}</div>
                )}
            </div>

            <div className="flex items-center gap-1">
                {rightSlot}

                {templates && templates.length > 0 && onSelectTemplate && (
                    <TemplatesDropdown
                        templates={templates}
                        activeTemplateId={activeTemplateId ?? null}
                        onSelect={onSelectTemplate}
                    />
                )}

                <ToolbarButton onClick={onOpenPalette} disabled={!editMode} title="Add widget">
                    <Plus size={10} strokeWidth={2.25} />
                    ADD
                </ToolbarButton>

                {editMode && (
                    <ToolbarButton onClick={onReset} title="Reset to default layout">
                        <RotateCcw size={10} strokeWidth={2.25} />
                        RESET
                    </ToolbarButton>
                )}
            </div>
        </div>
    );
}

function ToolbarButton({
    children,
    onClick,
    disabled,
    title,
}: {
    children: React.ReactNode;
    onClick: () => void;
    disabled?: boolean;
    title?: string;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            title={title}
            className={cn(
                'flex items-center gap-1 h-[16px] px-1.5 rounded-sm text-[9px] font-semibold uppercase tracking-wider transition-colors',
                'text-muted-fg hover:text-foreground hover:bg-muted',
                'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-muted-fg disabled:hover:bg-transparent',
            )}
        >
            {children}
        </button>
    );
}

function TemplatesDropdown({
    templates,
    activeTemplateId,
    onSelect,
}: {
    templates: CanvasTemplate[];
    activeTemplateId: string | null;
    onSelect: (id: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
        };
        const esc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        window.addEventListener('mousedown', handler);
        window.addEventListener('keydown', esc);
        return () => {
            window.removeEventListener('mousedown', handler);
            window.removeEventListener('keydown', esc);
        };
    }, [open]);

    const active = templates.find((t) => t.id === activeTemplateId);

    return (
        <div ref={containerRef} className="relative">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1 h-[16px] px-1.5 rounded-sm text-[9px] font-semibold uppercase tracking-wider text-muted-fg hover:text-foreground hover:bg-muted transition-colors"
                title="Layout templates"
            >
                <LayoutGrid size={10} strokeWidth={2.25} />
                {active ? active.name.toUpperCase() : 'TEMPLATES'}
                <ChevronDown size={9} strokeWidth={2.25} />
            </button>

            {open && (
                <div
                    className="absolute top-full right-0 mt-0.5 min-w-[180px] bg-surface border border-border rounded-sm shadow-2xl py-1 z-50"
                    style={{ animation: 'slideDown 0.12s ease-out' }}
                >
                    {templates.map((t) => {
                        const isActive = t.id === activeTemplateId;
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => {
                                    onSelect(t.id);
                                    setOpen(false);
                                }}
                                className={cn(
                                    'flex items-start gap-2 w-full px-2 py-1 text-left hover:bg-foreground/[0.04] transition-colors',
                                    isActive && 'bg-primary/8',
                                )}
                            >
                                <div className="w-3 mt-[1px]">
                                    {isActive && <Check size={10} className="text-primary" strokeWidth={2.5} />}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-[10px] font-medium text-foreground leading-[14px]">
                                        {t.name}
                                    </div>
                                    {t.description && (
                                        <div className="text-[9px] text-muted-fg leading-[12px]">
                                            {t.description}
                                        </div>
                                    )}
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
