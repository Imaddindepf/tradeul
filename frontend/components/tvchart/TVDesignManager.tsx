'use client';

/**
 * TVDesignManager — gestor de diseños con nombre, calcado del flujo de
 * tradingview.com:
 *   • Chip [nombre + estado] + caret junto al picker de layouts. El primer
 *     guardado pide nombre en un MODAL propio (nada de window.prompt); a
 *     partir de ahí Guardar/⌘S guarda TODO en silencio (dibujos incluidos).
 *   • Menú: Guardar ⌘S, toggle Autoguardado, Hacer una copia, Renombrar,
 *     Crear nuevo diseño, "USADOS CON FRECUENCIA" (favoritos ★, el activo
 *     resaltado) y "Abrir diseño…" con diálogo completo (buscar/borrar).
 * Persistido en el backend (/api/v1/tv-designs).
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '@clerk/nextjs';
import { getOverlayRoot } from '@/lib/overlayRoot';
import { Z_INDEX } from '@/lib/z-index';
import { useTVPopover } from './tvPopovers';
import { tvDesignsApi, type TVDesignMeta } from './tvDesignsApi';

export interface ActiveDesign {
    id: string;
    name: string;
}

interface TVDesignManagerProps {
    activeDesign: ActiveDesign | null;
    dirty: boolean;
    autoSave: boolean;
    onAutoSaveChange: (on: boolean) => void;
    /** Payload completo del diseño (el contenedor refresca antes las celdas). */
    getPayload: () => Promise<object>;
    /** Payload por defecto para "Crear nuevo diseño". */
    getFreshPayload: () => object;
    applyDesign: (payload: object, meta: ActiveDesign) => void;
    onActiveDesignChange: (meta: ActiveDesign | null) => void;
    onSaved: () => void;
    /** Señal externa (⌘S) — contador. */
    saveSignal: number;
}

/* ------------------------------------------------------------------ */
/* Iconos pequeños del menú (estilo TV, 18px, stroke currentColor)     */
/* ------------------------------------------------------------------ */

const ico = (path: ReactNode) => (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden>
        {path}
    </svg>
);

const ICONS = {
    pencil: ico(<path d="M3 15l.7-3.2 8.6-8.6a1.4 1.4 0 012 0l.5.5a1.4 1.4 0 010 2l-8.6 8.6L3 15z" />),
    copy: ico(<><rect x="6" y="6" width="8" height="8" rx="1" /><path d="M12 6V4.5A1.5 1.5 0 0010.5 3h-6A1.5 1.5 0 003 4.5v6A1.5 1.5 0 004.5 12H6" /></>),
    plus: ico(<path d="M9 4v10M4 9h10" />),
    open: ico(<path d="M2.5 5.5v8h11l2-5.5H5l-1.5 4.5m-1-7v-1a1 1 0 011-1h3l1.5 2h6a1 1 0 011 1v1.5" />),
    cloud: ico(<path d="M5.5 13.5a3 3 0 01-.3-6A4 4 0 0113 8.6a2.5 2.5 0 01-.6 4.9H5.5z" />),
    search: ico(<><circle cx="8" cy="8" r="4.5" /><path d="M11.5 11.5L15 15" /></>),
    trash: ico(<path d="M3.5 5h11M7 5V3.5h4V5m-6.5 0l.7 9.5h7.6l.7-9.5M7.5 7.5v4.5m3-4.5v4.5" />),
};

function Star({ on, size = 16 }: { on: boolean; size?: number }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            fill={on ? 'currentColor' : 'none'}
            stroke="currentColor"
            strokeWidth="1.1"
            aria-hidden
        >
            <path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6L8 1.8z" strokeLinejoin="round" />
        </svg>
    );
}

function Toggle({ on }: { on: boolean }) {
    return (
        <span
            className="relative inline-block h-4 w-7 shrink-0 rounded-full transition-colors"
            style={{ background: on ? 'var(--color-accent, #2962ff)' : 'rgba(128,128,128,0.4)' }}
        >
            <span
                className="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all"
                style={{ left: on ? 14 : 2 }}
            />
        </span>
    );
}

const Caret = () => (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden>
        <path d="M1 2.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
);

function fmtDate(ts: number): string {
    return new Date(ts * 1000).toLocaleDateString('es-ES', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
    });
}

/* ------------------------------------------------------------------ */
/* Modal de nombre (Guardar / Copia / Renombrar / Crear nuevo)         */
/* ------------------------------------------------------------------ */

interface NameDialogSpec {
    title: string;
    label: string;
    confirmLabel: string;
    initial: string;
    onConfirm: (name: string) => Promise<void>;
}

function NameDialog({ spec, onClose }: { spec: NameDialogSpec; onClose: () => void }) {
    const [name, setName] = useState(spec.initial);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
    }, []);

    const valid = name.trim().length > 0;

    const confirm = async () => {
        if (!valid || busy) return;
        setBusy(true);
        setError(false);
        try {
            await spec.onConfirm(name.trim());
            onClose();
        } catch {
            setError(true);
            setBusy(false);
        }
    };

    return createPortal(
        <div
            className="fixed inset-0 flex items-center justify-center"
            style={{ zIndex: Z_INDEX.DASHBOARD_OVERLAY, background: 'rgba(0,0,0,0.45)' }}
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
            onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Escape') onClose();
                if (e.key === 'Enter') void confirm();
            }}
        >
            <div
                className="w-[340px] rounded-xl border p-5 shadow-2xl"
                style={{
                    background: 'var(--color-bg, #fff)',
                    borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
                }}
            >
                <div className="mb-4 flex items-center justify-between">
                    <span className="text-[15px] font-semibold">{spec.title}</span>
                    <button
                        onClick={onClose}
                        aria-label="Cerrar"
                        className="rounded p-1 opacity-60 hover:bg-black/10 hover:opacity-100 dark:hover:bg-white/10"
                    >
                        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.4" />
                        </svg>
                    </button>
                </div>

                <label className="mb-1 block text-[12px] opacity-60">{spec.label}</label>
                <input
                    ref={inputRef}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={120}
                    className="w-full rounded-md border px-3 py-2 text-[13px] outline-none focus:border-[var(--color-accent,#2962ff)]"
                    style={{
                        background: 'transparent',
                        borderColor: 'var(--color-border, rgba(128,128,128,0.35))',
                    }}
                />
                {error && (
                    <div className="mt-2 text-[12px]" style={{ color: '#f23645' }}>
                        No se pudo guardar. Inténtelo de nuevo.
                    </div>
                )}

                <div className="mt-5 flex justify-end gap-2">
                    <button
                        onClick={onClose}
                        className="rounded-md border px-4 py-1.5 text-[13px] hover:bg-black/5 dark:hover:bg-white/10"
                        style={{ borderColor: 'var(--color-border, rgba(128,128,128,0.35))' }}
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={() => void confirm()}
                        disabled={!valid || busy}
                        className="rounded-md px-4 py-1.5 text-[13px] font-medium text-white disabled:opacity-40"
                        style={{ background: 'var(--color-accent, #2962ff)' }}
                    >
                        {busy ? 'Guardando…' : spec.confirmLabel}
                    </button>
                </div>
            </div>
        </div>,
        getOverlayRoot(),
    );
}

/* ------------------------------------------------------------------ */
/* Diálogo "Abrir diseño" (lista completa: buscar, ★, borrar)          */
/* ------------------------------------------------------------------ */

function OpenDialog({
    designs,
    activeId,
    onLoad,
    onToggleFavorite,
    onDelete,
    onClose,
}: {
    designs: TVDesignMeta[];
    activeId?: string;
    onLoad: (meta: TVDesignMeta) => void;
    onToggleFavorite: (meta: TVDesignMeta) => void;
    onDelete: (meta: TVDesignMeta) => void;
    onClose: () => void;
}) {
    const [query, setQuery] = useState('');
    const [confirmingId, setConfirmingId] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => inputRef.current?.focus(), []);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        const list = [...designs].sort((a, b) => b.updatedAt - a.updatedAt);
        if (!q) return list;
        return list.filter(
            (d) => d.name.toLowerCase().includes(q) || (d.symbol ?? '').toLowerCase().includes(q),
        );
    }, [designs, query]);

    return createPortal(
        <div
            className="fixed inset-0 flex items-center justify-center"
            style={{ zIndex: Z_INDEX.DASHBOARD_OVERLAY, background: 'rgba(0,0,0,0.45)' }}
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
            onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Escape') onClose();
            }}
        >
            <div
                className="flex max-h-[70vh] w-[440px] flex-col rounded-xl border shadow-2xl"
                style={{
                    background: 'var(--color-bg, #fff)',
                    borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
                }}
            >
                <div className="flex items-center justify-between px-5 pb-3 pt-4">
                    <span className="text-[15px] font-semibold">Abrir diseño</span>
                    <button
                        onClick={onClose}
                        aria-label="Cerrar"
                        className="rounded p-1 opacity-60 hover:bg-black/10 hover:opacity-100 dark:hover:bg-white/10"
                    >
                        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
                            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.4" />
                        </svg>
                    </button>
                </div>

                <div className="px-5 pb-3">
                    <div
                        className="flex items-center gap-2 rounded-md border px-3 py-1.5"
                        style={{ borderColor: 'var(--color-border, rgba(128,128,128,0.35))' }}
                    >
                        <span className="opacity-50">{ICONS.search}</span>
                        <input
                            ref={inputRef}
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Buscar"
                            className="w-full bg-transparent text-[13px] outline-none"
                        />
                    </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto pb-2">
                    {filtered.length === 0 && (
                        <div className="px-5 py-6 text-center text-[13px] opacity-50">
                            {designs.length === 0 ? 'Aún no hay diseños guardados' : 'Sin resultados'}
                        </div>
                    )}
                    {filtered.map((d) => {
                        const active = d.id === activeId;
                        return (
                            <div
                                key={d.id}
                                onClick={() => onLoad(d)}
                                className="group flex cursor-pointer items-center gap-2 px-5 py-2 hover:bg-black/5 dark:hover:bg-white/10"
                                style={active ? { background: 'rgba(41,98,255,0.12)' } : undefined}
                            >
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onToggleFavorite(d);
                                    }}
                                    title={d.favorite ? 'Quitar de favoritos' : 'Marcar favorito'}
                                    className="shrink-0 p-0.5"
                                    style={{
                                        color: d.favorite ? '#f7a600' : 'currentColor',
                                        opacity: d.favorite ? 1 : 0.35,
                                    }}
                                >
                                    <Star on={d.favorite} />
                                </button>
                                <span className="min-w-0 flex-1">
                                    <span className={`block truncate text-[13px] ${active ? 'font-semibold' : ''}`}>
                                        {d.name}
                                    </span>
                                    <span className="block text-[11px] opacity-50">
                                        {d.symbol ?? '—'}{d.interval ? `, ${d.interval}` : ''}
                                    </span>
                                </span>
                                <span className="shrink-0 text-[11px] opacity-40">{fmtDate(d.updatedAt)}</span>
                                {confirmingId === d.id ? (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setConfirmingId(null);
                                            onDelete(d);
                                        }}
                                        className="shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
                                        style={{ background: '#f23645' }}
                                    >
                                        ¿Eliminar?
                                    </button>
                                ) : (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setConfirmingId(d.id);
                                        }}
                                        title="Eliminar diseño"
                                        className="shrink-0 rounded p-0.5 opacity-0 hover:bg-black/10 group-hover:opacity-60 dark:hover:bg-white/10"
                                    >
                                        {ICONS.trash}
                                    </button>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>,
        getOverlayRoot(),
    );
}

/* ------------------------------------------------------------------ */
/* Gestor principal                                                    */
/* ------------------------------------------------------------------ */

export function TVDesignManager({
    activeDesign,
    dirty,
    autoSave,
    onAutoSaveChange,
    getPayload,
    getFreshPayload,
    applyDesign,
    onActiveDesignChange,
    onSaved,
    saveSignal,
}: TVDesignManagerProps) {
    const { getToken } = useAuth();
    const [open, setOpen] = useState(false);
    const [designs, setDesigns] = useState<TVDesignMeta[]>([]);
    const [busy, setBusy] = useState(false);
    const [saveError, setSaveError] = useState(false);
    const [dialog, setDialog] = useState<NameDialogSpec | null>(null);
    const [openDialog, setOpenDialog] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const flashError = useCallback(() => {
        setSaveError(true);
        if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
        errorTimerRef.current = setTimeout(() => setSaveError(false), 4000);
    }, []);

    useEffect(() => () => {
        if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    }, []);

    const refresh = useCallback(async () => {
        try {
            setDesigns(await tvDesignsApi.list(getToken));
        } catch { /* backend caído: la lista se queda como esté */ }
    }, [getToken]);

    useEffect(() => {
        if (open || openDialog) void refresh();
    }, [open, openDialog, refresh]);

    // Exclusividad + cierre por clic fuera (incl. iframes) + Escape.
    useTVPopover(open, () => setOpen(false), (t) => rootRef.current?.contains(t) ?? false);

    /** Crear un diseño nuevo con el payload dado y activarlo. */
    const createDesign = useCallback(async (name: string, payload: object) => {
        const meta = await tvDesignsApi.create(getToken, name, payload);
        onActiveDesignChange({ id: meta.id, name: meta.name });
        onSaved();
    }, [getToken, onActiveDesignChange, onSaved]);

    /**
     * Guardar (botón, ⌘S, autoguardado): con diseño activo guarda TODO en
     * silencio; sin diseño, primer guardado → modal de nombre (flujo TV).
     */
    const save = useCallback(async () => {
        if (busy) return;
        if (!activeDesign) {
            setDialog({
                title: 'Guardar diseño',
                label: 'Nombre del diseño',
                confirmLabel: 'Guardar',
                initial: 'Mi diseño',
                onConfirm: async (name) => createDesign(name, await getPayload()),
            });
            return;
        }
        setBusy(true);
        try {
            await tvDesignsApi.update(getToken, activeDesign.id, { payload: await getPayload() });
            onSaved();
        } catch {
            flashError();
        } finally {
            setBusy(false);
        }
    }, [activeDesign, busy, createDesign, flashError, getPayload, getToken, onSaved]);

    // ⌘S desde el contenedor (ventana o iframes).
    const prevSignal = useRef(saveSignal);
    useEffect(() => {
        if (saveSignal !== prevSignal.current) {
            prevSignal.current = saveSignal;
            void save();
        }
    }, [saveSignal, save]);

    // Autoguardado: si hay cambios y diseño activo, guardar con debounce.
    useEffect(() => {
        if (!autoSave || !dirty || !activeDesign) return;
        const t = setTimeout(() => void save(), 4000);
        return () => clearTimeout(t);
    }, [autoSave, dirty, activeDesign, save]);

    const saveAsCopy = () => {
        setOpen(false);
        setDialog({
            title: 'Hacer una copia',
            label: 'Nombre del diseño',
            confirmLabel: 'Crear',
            initial: `${activeDesign?.name ?? 'Diseño'} (copia)`,
            onConfirm: async (name) => createDesign(name, await getPayload()),
        });
    };

    const rename = () => {
        if (!activeDesign) return;
        setOpen(false);
        setDialog({
            title: 'Renombrar diseño',
            label: 'Nuevo nombre de diseño',
            confirmLabel: 'Renombrar',
            initial: activeDesign.name,
            onConfirm: async (name) => {
                if (name !== activeDesign.name) {
                    await tvDesignsApi.update(getToken, activeDesign.id, { name });
                }
                onActiveDesignChange({ id: activeDesign.id, name });
            },
        });
    };

    const createNew = () => {
        setOpen(false);
        setDialog({
            title: 'Crear diseño',
            label: 'Nuevo nombre de diseño',
            confirmLabel: 'Crear',
            initial: 'Mi diseño',
            onConfirm: async (name) => {
                const fresh = getFreshPayload();
                const meta = await tvDesignsApi.create(getToken, name, fresh);
                applyDesign(fresh, { id: meta.id, name: meta.name });
                onSaved();
            },
        });
    };

    const load = async (meta: TVDesignMeta) => {
        setOpen(false);
        setOpenDialog(false);
        try {
            const payload = await tvDesignsApi.getPayload(getToken, meta.id);
            applyDesign(payload, { id: meta.id, name: meta.name });
        } catch {
            flashError();
        }
    };

    const toggleFavorite = async (meta: TVDesignMeta) => {
        try {
            await tvDesignsApi.update(getToken, meta.id, { favorite: !meta.favorite });
        } catch { /* sin backend */ }
        void refresh();
    };

    const deleteDesign = async (meta: TVDesignMeta) => {
        try {
            await tvDesignsApi.remove(getToken, meta.id);
            if (meta.id === activeDesign?.id) onActiveDesignChange(null);
        } catch { /* sin backend */ }
        void refresh();
    };

    // "Usados con frecuencia": favoritos primero, luego los más recientes.
    const frequent = useMemo(
        () =>
            [...designs]
                .sort(
                    (a, b) =>
                        Number(b.favorite) - Number(a.favorite) || b.updatedAt - a.updatedAt,
                )
                .slice(0, 8),
        [designs],
    );

    const status = busy
        ? 'Guardando…'
        : saveError
            ? 'Error al guardar'
            : dirty || !activeDesign
                ? 'Guardar'
                : 'Guardado';

    const item = 'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[13px] hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-35 disabled:hover:bg-transparent';

    return (
        <div ref={rootRef} className="relative flex items-center">
            {/* Zona principal: guardar (o pedir nombre la primera vez) */}
            <button
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => {
                    if (dirty || !activeDesign) void save();
                    else setOpen((v) => !v);
                }}
                title={
                    dirty || !activeDesign
                        ? 'Guarde todos los gráficos de todos los símbolos e intervalos en su diseño (⌘S)'
                        : 'Todos los cambios guardados'
                }
                className="flex h-8 max-w-40 flex-col items-start justify-center rounded-l px-1.5 hover:bg-black/10 dark:hover:bg-white/10"
            >
                <span className="w-full truncate text-[13px] font-medium leading-tight">
                    {activeDesign?.name ?? 'Sin nombre'}
                </span>
                <span
                    className="text-[10px] leading-tight"
                    style={{
                        color: saveError
                            ? '#f23645'
                            : dirty || !activeDesign
                                ? 'var(--color-accent, #2962ff)'
                                : 'inherit',
                        opacity: saveError || dirty || !activeDesign ? 1 : 0.45,
                    }}
                >
                    {status}
                </span>
            </button>

            {/* Caret: abre el menú del gestor */}
            <button
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => setOpen((v) => !v)}
                title="Gestionar diseños"
                aria-label="Gestionar diseños"
                className="flex h-8 items-center rounded-r px-1 hover:bg-black/10 dark:hover:bg-white/10"
            >
                <Caret />
            </button>

            {open && (
                <div
                    className="absolute right-0 top-9 z-50 w-72 rounded-lg border py-1.5 shadow-xl"
                    style={{
                        background: 'var(--color-bg, #fff)',
                        borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
                        maxHeight: 480,
                        overflowY: 'auto',
                    }}
                >
                    <button
                        className={item}
                        disabled={Boolean(activeDesign) && !dirty}
                        onClick={() => {
                            setOpen(false);
                            void save();
                        }}
                    >
                        <span className="opacity-70">{ICONS.cloud}</span>
                        <span className="flex-1">Guardar diseño</span>
                        <span className="opacity-40">⌘S</span>
                    </button>
                    <button className={item} onClick={() => onAutoSaveChange(!autoSave)}>
                        <span className="w-[18px]" />
                        <span className="flex-1">Autoguardado</span>
                        <Toggle on={autoSave} />
                    </button>

                    <div className="my-1 h-px" style={{ background: 'var(--color-border, rgba(128,128,128,0.2))' }} />

                    <button className={item} onClick={saveAsCopy}>
                        <span className="opacity-70">{ICONS.copy}</span>
                        <span className="flex-1">Hacer una copia…</span>
                    </button>
                    <button className={item} onClick={rename} disabled={!activeDesign}>
                        <span className="opacity-70">{ICONS.pencil}</span>
                        <span className="flex-1">Renombrar…</span>
                    </button>
                    <button className={item} onClick={createNew}>
                        <span className="opacity-70">{ICONS.plus}</span>
                        <span className="flex-1">Crear nuevo diseño…</span>
                    </button>

                    {frequent.length > 0 && (
                        <>
                            <div className="px-3 pb-1 pt-3 text-[11px] font-medium tracking-wide opacity-50">
                                USADOS CON FRECUENCIA
                            </div>
                            {frequent.map((d) => {
                                const active = d.id === activeDesign?.id;
                                return (
                                    <div
                                        key={d.id}
                                        onClick={() => void load(d)}
                                        className="flex cursor-pointer items-center gap-2.5 px-3 py-1.5 hover:bg-black/5 dark:hover:bg-white/10"
                                        style={active ? { background: 'rgba(41,98,255,0.12)' } : undefined}
                                    >
                                        <span className="min-w-0 flex-1">
                                            <span className={`block truncate text-[13px] ${active ? 'font-semibold' : ''}`}>
                                                {d.name}
                                            </span>
                                            <span className="block text-[11px] opacity-50">
                                                {d.symbol ?? '—'}{d.interval ? `, ${d.interval}` : ''}
                                            </span>
                                        </span>
                                        <button
                                            onMouseDown={(e) => e.stopPropagation()}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                void toggleFavorite(d);
                                            }}
                                            title={d.favorite ? 'Quitar de favoritos' : 'Marcar favorito'}
                                            className="shrink-0 p-0.5"
                                            style={{
                                                color: d.favorite ? '#f7a600' : 'currentColor',
                                                opacity: d.favorite ? 1 : 0.35,
                                            }}
                                        >
                                            <Star on={d.favorite} />
                                        </button>
                                    </div>
                                );
                            })}
                        </>
                    )}

                    <div className="my-1 h-px" style={{ background: 'var(--color-border, rgba(128,128,128,0.2))' }} />

                    <button
                        className={item}
                        onClick={() => {
                            setOpen(false);
                            setOpenDialog(true);
                        }}
                    >
                        <span className="opacity-70">{ICONS.open}</span>
                        <span className="flex-1">Abrir diseño…</span>
                    </button>
                </div>
            )}

            {dialog && <NameDialog spec={dialog} onClose={() => setDialog(null)} />}
            {openDialog && (
                <OpenDialog
                    designs={designs}
                    activeId={activeDesign?.id}
                    onLoad={(d) => void load(d)}
                    onToggleFavorite={(d) => void toggleFavorite(d)}
                    onDelete={(d) => void deleteDesign(d)}
                    onClose={() => setOpenDialog(false)}
                />
            )}
        </div>
    );
}
