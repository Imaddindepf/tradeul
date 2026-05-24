'use client';

import { useChartContext } from './ChartContext';
import { CloseIcon } from './icons';

/**
 * Lightweight settings dialog for chart-level visual preferences (grid,
 * watermark, log scale, magnet behaviour). Persisted via Zustand store.
 * Rendered inline (not a portal) so it stays scoped to the chart window.
 */
export function ChartSettingsDialog() {
    const ctx = useChartContext();
    if (!ctx.settingsOpen) return null;

    return (
        <>
            <div className="absolute inset-0 z-40 bg-black/30" onClick={ctx.closeSettings} />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[320px] bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg shadow-xl">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--color-border-subtle)]">
                    <span className="text-[13px] font-semibold text-[color:var(--color-fg)]">
                        Configuración del gráfico
                    </span>
                    <button
                        onClick={ctx.closeSettings}
                        className="text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)]"
                        aria-label="Cerrar"
                    >
                        <CloseIcon className="w-4 h-4" />
                    </button>
                </div>

                <div className="px-4 py-3 flex flex-col gap-2.5">
                    <Section title="Apariencia">
                        <Toggle
                            label="Mostrar cuadrícula"
                            checked={ctx.gridVisible}
                            onChange={ctx.setGridVisible}
                        />
                        <Toggle
                            label="Marca de agua del ticker"
                            checked={ctx.watermarkVisible}
                            onChange={ctx.setWatermarkVisible}
                        />
                    </Section>
                    <Section title="Escala">
                        <Toggle
                            label="Escala logarítmica"
                            checked={ctx.logScale}
                            onChange={ctx.setLogScale}
                        />
                    </Section>
                    <Section title="Imán (snap a OHLC)">
                        <div className="grid grid-cols-3 gap-1">
                            {(['off', 'weak', 'strong'] as const).map(m => {
                                const isActive = ctx.magnetMode === m;
                                const labels = { off: 'Off', weak: 'Débil', strong: 'Fuerte' };
                                return (
                                    <button
                                        key={m}
                                        onClick={() => ctx.setMagnetMode(m)}
                                        className={`px-2 py-1 text-[11px] rounded ${
                                            isActive
                                                ? 'bg-[color:var(--color-primary)] text-white font-semibold'
                                                : 'bg-[color:var(--color-surface-hover)] text-[color:var(--color-fg)]/85 hover:bg-[color:var(--color-surface-inset)]'
                                        }`}
                                    >
                                        {labels[m]}
                                    </button>
                                );
                            })}
                        </div>
                    </Section>
                </div>
            </div>
        </>
    );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div>
            <div className="text-[9.5px] text-[color:var(--color-muted-fg)] font-semibold uppercase tracking-wider mb-1.5">
                {title}
            </div>
            <div className="flex flex-col gap-1.5">{children}</div>
        </div>
    );
}

function Toggle({
    label, checked, onChange,
}: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
    return (
        <label className="flex items-center justify-between gap-2 cursor-pointer text-[11.5px] text-[color:var(--color-fg)]/90 hover:text-[color:var(--color-fg)]">
            <span>{label}</span>
            <span
                role="switch"
                aria-checked={checked}
                onClick={() => onChange(!checked)}
                className={`relative inline-flex h-4 w-7 rounded-full transition-colors ${
                    checked
                        ? 'bg-[color:var(--color-primary)]'
                        : 'bg-[color:var(--color-surface-inset)]'
                }`}
            >
                <span
                    className={`absolute top-0.5 inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${
                        checked ? 'translate-x-[14px]' : 'translate-x-0.5'
                    }`}
                />
            </span>
        </label>
    );
}
