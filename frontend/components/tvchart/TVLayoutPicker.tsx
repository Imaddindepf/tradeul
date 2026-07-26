'use client';

/**
 * TVLayoutPicker — selector de layout calcado de tradingview.com: filas
 * agrupadas por nº de charts (1, 2, 3… 16), miniaturas oficiales y la sección
 * "SINCRONIZAR EN EL DISEÑO" con los 5 toggles. Portaleado bajo su botón del
 * header (como el picker de TV).
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getOverlayRoot } from '@/lib/overlayRoot';
import { Z_INDEX } from '@/lib/z-index';
import type { SyncFlags } from '@/components/chart/multichart/types';
import { TV_LAYOUT_GROUPS } from './tvLayouts';
import { TVLayoutIcon } from './TVLayoutIcon';

interface TVLayoutPickerProps {
    anchorEl: HTMLElement | null;
    isOpen: boolean;
    onClose: () => void;
    activeLayoutId: string;
    onPick: (id: string) => void;
    sync: SyncFlags;
    onToggleSync: (flag: keyof SyncFlags) => void;
    syncEnabled: boolean;
}

const SYNC_ROWS: Array<{ key: keyof SyncFlags; label: string }> = [
    { key: 'symbol', label: 'Símbolo' },
    { key: 'interval', label: 'Intervalo' },
    { key: 'crosshair', label: 'Retícula' },
    { key: 'time', label: 'Hora' },
    { key: 'dateRange', label: 'Rango de fechas' },
];

function Toggle({ on, disabled }: { on: boolean; disabled: boolean }) {
    return (
        <span
            className="relative inline-block h-4 w-7 rounded-full transition-colors"
            style={{
                background: on ? 'var(--color-accent, #2962ff)' : 'rgba(128,128,128,0.4)',
                opacity: disabled ? 0.4 : 1,
            }}
        >
            <span
                className="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all"
                style={{ left: on ? 14 : 2 }}
            />
        </span>
    );
}

export function TVLayoutPicker({
    anchorEl,
    isOpen,
    onClose,
    activeLayoutId,
    onPick,
    sync,
    onToggleSync,
    syncEnabled,
}: TVLayoutPickerProps) {
    const ref = useRef<HTMLDivElement>(null);
    const [mounted, setMounted] = useState(false);
    const [pos, setPos] = useState({ top: 0, left: 0 });

    useEffect(() => setMounted(true), []);

    useEffect(() => {
        if (!isOpen || !anchorEl) return;
        const update = () => {
            const r = anchorEl.getBoundingClientRect();
            const width = 420;
            let left = r.left;
            if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
            setPos({ top: r.bottom + 6, left: Math.max(8, left) });
        };
        update();
        const close = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node) && !anchorEl.contains(e.target as Node)) onClose();
        };
        const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
        window.addEventListener('resize', update);
        window.addEventListener('scroll', update, true);
        window.addEventListener('mousedown', close);
        window.addEventListener('keydown', esc);
        return () => {
            window.removeEventListener('resize', update);
            window.removeEventListener('scroll', update, true);
            window.removeEventListener('mousedown', close);
            window.removeEventListener('keydown', esc);
        };
    }, [isOpen, anchorEl, onClose]);

    if (!mounted || !isOpen) return null;

    return createPortal(
        <div
            ref={ref}
            className="overflow-y-auto rounded-lg border shadow-xl"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                width: 420,
                maxHeight: Math.min(700, window.innerHeight - pos.top - 12),
                zIndex: Z_INDEX.DASHBOARD_OVERLAY,
                background: 'var(--color-bg, #fff)',
                borderColor: 'var(--color-border, rgba(128,128,128,0.3))',
            }}
        >
            {/* Filas de layouts agrupadas por nº de charts */}
            <div className="p-1.5">
                {TV_LAYOUT_GROUPS.map(({ count, ids }) => (
                    <div
                        key={count}
                        className="flex items-center gap-1 border-b py-1 last:border-b-0"
                        style={{ borderColor: 'var(--color-border, rgba(128,128,128,0.15))' }}
                    >
                        <span className="w-6 shrink-0 text-center text-xs opacity-50">{count}</span>
                        <div className="flex flex-wrap gap-1">
                            {ids.map((id) => {
                                const active = id === activeLayoutId;
                                return (
                                    <button
                                        key={id}
                                        title={`${count} ${count === 1 ? 'gráfico' : 'gráficos'}`}
                                        onMouseDown={(e) => e.stopPropagation()}
                                        onClick={() => onPick(id)}
                                        className="grid h-8 w-8 place-items-center rounded"
                                        style={{
                                            background: active
                                                ? 'var(--color-accent, #2962ff)'
                                                : 'transparent',
                                            color: active ? '#fff' : 'inherit',
                                        }}
                                    >
                                        <TVLayoutIcon layoutId={id} active={active} />
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* Sincronizar en el diseño */}
            <div
                className="border-t px-3 py-2"
                style={{ borderColor: 'var(--color-border, rgba(128,128,128,0.25))' }}
            >
                <div className="pb-1 text-[11px] font-medium tracking-wide opacity-50">
                    SINCRONIZAR EN EL DISEÑO
                </div>
                {SYNC_ROWS.map(({ key, label }) => (
                    <button
                        key={key}
                        disabled={!syncEnabled}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={() => syncEnabled && onToggleSync(key)}
                        className="flex w-full items-center justify-between py-1.5 text-sm disabled:cursor-default"
                    >
                        <span style={{ opacity: syncEnabled ? 1 : 0.4 }}>{label}</span>
                        <Toggle on={!!sync[key]} disabled={!syncEnabled} />
                    </button>
                ))}
            </div>
        </div>,
        getOverlayRoot(),
    );
}
