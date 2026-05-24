/**
 * Layout picker — TradingView-style popover with grouped grid templates.
 *
 * Anchored to the “Select layout” toolbar button. Each row is a category
 * (1/2/3/4/5+/8 charts) showing every variant as an icon button.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Z_INDEX } from '@/lib/z-index';
import { LayoutIcon } from './LayoutIcon';
import {
    LAYOUT_TEMPLATES,
    LAYOUT_ORDER,
    LAYOUT_CATEGORIES,
} from './layoutTemplates';
import type { LayoutId } from './types';

interface LayoutPickerPopoverProps {
    anchorEl: HTMLElement | null;
    isOpen: boolean;
    onClose: () => void;
    activeLayoutId: LayoutId;
    onPick: (id: LayoutId) => void;
}

export function LayoutPickerPopover({
    anchorEl,
    isOpen,
    onClose,
    activeLayoutId,
    onPick,
}: LayoutPickerPopoverProps) {
    const popoverRef = useRef<HTMLDivElement>(null);
    const [pos, setPos] = useState({ top: 0, left: 0 });
    const [mounted, setMounted] = useState(false);

    useEffect(() => setMounted(true), []);

    useEffect(() => {
        if (!isOpen || !anchorEl) return;
        const update = () => {
            const r = anchorEl.getBoundingClientRect();
            setPos({ top: r.bottom + 6, left: r.left });
        };
        update();
        window.addEventListener('resize', update);
        window.addEventListener('scroll', update, true);
        return () => {
            window.removeEventListener('resize', update);
            window.removeEventListener('scroll', update, true);
        };
    }, [isOpen, anchorEl]);

    useEffect(() => {
        if (!isOpen) return;
        const onMouseDown = (e: MouseEvent) => {
            if (popoverRef.current?.contains(e.target as Node)) return;
            if (anchorEl?.contains(e.target as Node)) return;
            onClose();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [isOpen, anchorEl, onClose]);

    if (!isOpen || !mounted) return null;

    return createPortal(
        <div
            ref={popoverRef}
            role="dialog"
            aria-label="Choose layout"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                fontFamily: 'var(--font-mono-selected)',
            }}
            className="rounded-lg border border-border bg-surface shadow-2xl p-2 select-none w-[260px]"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <div className="text-[10px] uppercase tracking-wider text-muted-fg px-2 py-1">
                Select layout
            </div>
            <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-1">
                {LAYOUT_CATEGORIES.map((cat) => {
                    const layouts = LAYOUT_ORDER.filter(
                        (id) => LAYOUT_TEMPLATES[id].category === cat.id,
                    );
                    if (layouts.length === 0) return null;
                    return (
                        <div key={cat.id}>
                            <div className="text-[10px] text-muted-fg/70 px-2 mb-1">
                                {cat.label}
                            </div>
                            <div className="grid grid-cols-6 gap-1.5 px-1">
                                {layouts.map((id) => {
                                    const active = id === activeLayoutId;
                                    return (
                                        <button
                                            key={id}
                                            type="button"
                                            title={LAYOUT_TEMPLATES[id].label}
                                            onClick={() => {
                                                onPick(id);
                                                onClose();
                                            }}
                                            className={`flex items-center justify-center w-8 h-8 rounded transition-colors ${
                                                active
                                                    ? 'bg-primary/15 text-primary ring-1 ring-primary/40'
                                                    : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
                                            }`}
                                        >
                                            <LayoutIcon layoutId={id} active={active} />
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>,
        document.body,
    );
}
