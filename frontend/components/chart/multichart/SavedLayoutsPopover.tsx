/**
 * Saved layouts library popover.
 *
 *   - Lists all named saved layouts (newest first).
 *   - Inline rename, delete and "Save current as...".
 */

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Save, Trash2, Pencil, Check, X } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { LayoutIcon } from './LayoutIcon';
import type { SavedLayout } from './types';

interface SavedLayoutsPopoverProps {
    anchorEl: HTMLElement | null;
    isOpen: boolean;
    onClose: () => void;
    savedLayouts: SavedLayout[];
    onSaveAs: (name: string) => void;
    onLoad: (id: string) => void;
    onRename: (id: string, name: string) => void;
    onDelete: (id: string) => void;
}

export function SavedLayoutsPopover({
    anchorEl,
    isOpen,
    onClose,
    savedLayouts,
    onSaveAs,
    onLoad,
    onRename,
    onDelete,
}: SavedLayoutsPopoverProps) {
    const popoverRef = useRef<HTMLDivElement>(null);
    const [pos, setPos] = useState({ top: 0, left: 0 });
    const [mounted, setMounted] = useState(false);
    const [draftName, setDraftName] = useState('');
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameDraft, setRenameDraft] = useState('');

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

    const sorted = useMemo(
        () => [...savedLayouts].sort((a, b) => b.updatedAt - a.updatedAt),
        [savedLayouts],
    );

    if (!isOpen || !mounted) return null;

    const handleSave = () => {
        const name = draftName.trim();
        if (!name) return;
        onSaveAs(name);
        setDraftName('');
    };

    const startRename = (l: SavedLayout) => {
        setRenamingId(l.id);
        setRenameDraft(l.name);
    };
    const commitRename = () => {
        if (renamingId) onRename(renamingId, renameDraft.trim() || 'Untitled');
        setRenamingId(null);
    };
    const cancelRename = () => setRenamingId(null);

    return createPortal(
        <div
            ref={popoverRef}
            role="dialog"
            aria-label="Saved layouts"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                fontFamily: 'var(--font-mono-selected)',
            }}
            className="rounded-lg border border-border bg-surface shadow-2xl p-3 select-none w-[320px]"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <div className="text-[10px] uppercase tracking-wider text-muted-fg mb-2">
                Saved layouts
            </div>

            <div className="flex items-center gap-1 mb-3">
                <input
                    type="text"
                    placeholder="Name your current layout..."
                    value={draftName}
                    onChange={(e) => setDraftName(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSave();
                    }}
                    className="flex-1 text-xs bg-background border border-border rounded px-2 py-1 outline-none focus:border-primary text-foreground placeholder-muted-fg/60"
                />
                <button
                    type="button"
                    onClick={handleSave}
                    disabled={!draftName.trim()}
                    title="Save current layout"
                    className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded bg-primary text-on-primary hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    <Save className="w-3 h-3" /> Save
                </button>
            </div>

            {sorted.length === 0 ? (
                <div className="text-[11px] text-muted-fg/80 italic py-6 text-center">
                    No saved layouts yet. Build your favourite combo and hit Save.
                </div>
            ) : (
                <ul className="flex flex-col gap-1 max-h-[260px] overflow-y-auto">
                    {sorted.map((l) => {
                        const isRenaming = renamingId === l.id;
                        return (
                            <li key={l.id}>
                                <div className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-foreground/5 transition-colors group">
                                    <span className="text-muted-fg/70 shrink-0">
                                        <LayoutIcon layoutId={l.layoutId} />
                                    </span>
                                    {isRenaming ? (
                                        <>
                                            <input
                                                autoFocus
                                                value={renameDraft}
                                                onChange={(e) => setRenameDraft(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') commitRename();
                                                    if (e.key === 'Escape') cancelRename();
                                                }}
                                                className="flex-1 text-xs bg-background border border-border rounded px-1.5 py-0.5 outline-none focus:border-primary text-foreground"
                                            />
                                            <button
                                                type="button"
                                                title="Confirm"
                                                onClick={commitRename}
                                                className="p-1 rounded text-emerald-500 hover:bg-foreground/10"
                                            >
                                                <Check className="w-3 h-3" />
                                            </button>
                                            <button
                                                type="button"
                                                title="Cancel"
                                                onClick={cancelRename}
                                                className="p-1 rounded text-muted-fg hover:bg-foreground/10"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    onLoad(l.id);
                                                    onClose();
                                                }}
                                                className="flex-1 text-left flex flex-col"
                                            >
                                                <span className="text-xs text-foreground truncate">
                                                    {l.name}
                                                </span>
                                                <span className="text-[10px] text-muted-fg/70 truncate">
                                                    {l.cells.length}{' '}
                                                    {l.cells.length === 1 ? 'chart' : 'charts'} ·{' '}
                                                    {l.cells.map((c) => c.ticker).join(' / ')}
                                                </span>
                                            </button>
                                            <button
                                                type="button"
                                                title="Rename"
                                                onClick={() => startRename(l)}
                                                className="p-1 rounded text-muted-fg hover:text-foreground hover:bg-foreground/10 opacity-0 group-hover:opacity-100"
                                            >
                                                <Pencil className="w-3 h-3" />
                                            </button>
                                            <button
                                                type="button"
                                                title="Delete"
                                                onClick={() => onDelete(l.id)}
                                                className="p-1 rounded text-muted-fg hover:text-rose-400 hover:bg-foreground/10 opacity-0 group-hover:opacity-100"
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        </>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>,
        document.body,
    );
}
