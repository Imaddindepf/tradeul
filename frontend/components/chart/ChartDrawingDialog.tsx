'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
    Drawing,
    DrawingType,
    HorizontalLineDrawing,
    VerticalLineDrawing,
    TrendlineDrawing,
    RayDrawing,
    ExtendedLineDrawing,
    ParallelChannelDrawing,
    FibonacciDrawing,
    RectangleDrawing,
    CircleDrawing,
    TriangleDrawing,
    MeasureDrawing,
    ArrowDrawing,
    ArrowDirection,
    TextDrawing,
    PriceRangeDrawing,
    DateRangeDrawing,
} from './primitives/types';
import { FIB_LEVELS } from './primitives/types';
import { colorWithAlpha, alphaFromColor, type LineStyle } from './primitives/canvasStyles';
import { CloseIcon, TrashIcon, PencilIcon } from './icons';
import { useClickOutside } from './hooks/useClickOutside';

// ─── Public API ────────────────────────────────────────────────────────────

export interface ChartDrawingDialogProps {
    drawing: Drawing;
    colors: readonly string[];
    initialX: number;
    initialY: number;
    containerWidth: number;
    containerHeight: number;
    onClose: () => void;
    /** Shallow-merge update — used for every per-field edit so the chart
     *  reflects changes live while the dialog is open. */
    onUpdate: (patch: Partial<Drawing>) => void;
    /** Full-replace update — used by "Cancelar" to restore the pre-open
     *  snapshot of the drawing. */
    onReplace: (drawing: Drawing) => void;
    onDelete: () => void;
}

type TabId = 'style' | 'text' | 'coords' | 'visibility';

// ─── Type → spanish label ─────────────────────────────────────────────────


const HAS_FILL: Record<DrawingType, boolean> = {
    horizontal_line: false,
    vertical_line: false,
    trendline: false,
    ray: false,
    extended_line: false,
    parallel_channel: true,
    fibonacci: false,
    rectangle: true,
    circle: true,
    triangle: true,
    measure: false,
    arrow: false,
    text: false,
    price_range: false,
    date_range: false,
};

const DIALOG_WIDTH = 380;
const DIALOG_MAX_HEIGHT = 420;

// ─── Component ─────────────────────────────────────────────────────────────

export function ChartDrawingDialog({
    drawing, colors, initialX, initialY,
    containerWidth, containerHeight,
    onClose, onUpdate, onReplace, onDelete,
}: ChartDrawingDialogProps) {
    const { t } = useTranslation();
    const defaultTypeLabel = t(`chart.drawing.types.${drawing.type}`);
    // ── Cancel snapshot ────────────────────────────────────────────────
    const [initialSnapshot] = useState<Drawing>(() => structuredClone(drawing));

    // ── Position (drag) ────────────────────────────────────────────────
    const [pos, setPos] = useState(() => clampPos(initialX, initialY, containerWidth, containerHeight));
    const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origX: number; origY: number } | null>(null);
    const headerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // Re-clamp when container resizes
        setPos(prev => clampPos(prev.x, prev.y, containerWidth, containerHeight));
    }, [containerWidth, containerHeight]);

    const onHeaderPointerDown = useCallback((e: React.PointerEvent) => {
        if (e.button !== 0) return;
        const target = e.currentTarget as HTMLDivElement;
        target.setPointerCapture(e.pointerId);
        dragRef.current = { pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y };
    }, [pos]);

    const onHeaderPointerMove = useCallback((e: React.PointerEvent) => {
        const d = dragRef.current;
        if (!d || e.pointerId !== d.pointerId) return;
        const nx = d.origX + (e.clientX - d.startX);
        const ny = d.origY + (e.clientY - d.startY);
        setPos(clampPos(nx, ny, containerWidth, containerHeight));
    }, [containerWidth, containerHeight]);

    const onHeaderPointerUp = useCallback((e: React.PointerEvent) => {
        const d = dragRef.current;
        if (!d || e.pointerId !== d.pointerId) return;
        (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
        dragRef.current = null;
    }, []);

    // ── Title (editable) ───────────────────────────────────────────────
    const [editingTitle, setEditingTitle] = useState(false);
    const [title, setTitle] = useState<string>(() => (drawing as { label?: string }).label || defaultTypeLabel);
    const commitTitle = useCallback(() => {
        setEditingTitle(false);
        const next = title.trim() || defaultTypeLabel;
        setTitle(next);
        if ('label' in drawing || drawing.type === 'horizontal_line') {
            // Persist into drawing.label when the type supports it
            onUpdate({ label: next === defaultTypeLabel ? undefined : next } as Partial<Drawing>);
        }
    }, [title, drawing, onUpdate, defaultTypeLabel]);

    // ── Tabs ───────────────────────────────────────────────────────────
    const [tab, setTab] = useState<TabId>('style');

    // ── Dismissal ──────────────────────────────────────────────────────
    // Edits apply live, so every "just close" path (click-outside, Escape, the
    // X button, "Aceptar") keeps the changes — only the explicit "Cancelar"
    // button reverts to the pre-open snapshot. This makes the close behaviour
    // consistent and matches TradingView (clicking the chart closes the panel
    // without losing your edits).
    const dialogRef = useRef<HTMLDivElement>(null);
    useClickOutside(dialogRef, onClose);

    const handleCancel = useCallback(() => {
        onReplace(initialSnapshot);
        onClose();
    }, [onReplace, initialSnapshot, onClose]);

    const handleAccept = useCallback(() => {
        // Changes already applied live. Just close.
        onClose();
    }, [onClose]);

    return (
        <div
            ref={dialogRef}
            className="absolute z-50 rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-2xl flex flex-col"
            style={{
                left: pos.x, top: pos.y,
                width: DIALOG_WIDTH,
                maxHeight: DIALOG_MAX_HEIGHT,
            }}
            role="dialog"
            aria-label={defaultTypeLabel}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
        >
            {/* ─── Header (drag handle) ─────────────────────────────── */}
            <div
                ref={headerRef}
                onPointerDown={onHeaderPointerDown}
                onPointerMove={onHeaderPointerMove}
                onPointerUp={onHeaderPointerUp}
                onPointerCancel={onHeaderPointerUp}
                className="flex items-center justify-between gap-2 px-3 py-2 border-b border-[color:var(--color-border)] cursor-grab active:cursor-grabbing select-none"
            >
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    {editingTitle ? (
                        <input
                            autoFocus
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            onBlur={commitTitle}
                            onKeyDown={(e) => { if (e.key === 'Enter') commitTitle(); }}
                            onPointerDown={(e) => e.stopPropagation()}
                            className="flex-1 min-w-0 bg-transparent border-b border-[color:var(--color-primary)] text-[13px] font-semibold text-[color:var(--color-fg)] focus:outline-none"
                        />
                    ) : (
                        <button
                            onClick={() => setEditingTitle(true)}
                            onPointerDown={(e) => e.stopPropagation()}
                            className="flex items-center gap-1.5 min-w-0 text-[13px] font-semibold text-[color:var(--color-fg)] hover:text-[color:var(--color-primary)] transition-colors"
                            title={t('chart.drawing.editName')}
                        >
                            <span className="truncate">{title}</span>
                            <PencilIcon className="w-3 h-3 opacity-60 flex-shrink-0" />
                        </button>
                    )}
                </div>
                <button
                    onClick={onClose}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="p-0.5 rounded text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                    aria-label={t('common.close')}
                >
                    <CloseIcon className="w-3.5 h-3.5" />
                </button>
            </div>

            {/* ─── Tabs ──────────────────────────────────────────────── */}
            <div className="flex gap-4 px-3 pt-2 border-b border-[color:var(--color-border)] text-[12px]">
                {(['style', 'text', 'coords', 'visibility'] as TabId[]).map(tabId => (
                    <button
                        key={tabId}
                        onClick={() => setTab(tabId)}
                        className={`relative pb-2 font-medium transition-colors ${
                            tab === tabId
                                ? 'text-[color:var(--color-fg)]'
                                : 'text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)]'
                        }`}
                    >
                        {t(`chart.drawing.tabs.${tabId}`)}
                        {tab === tabId && (
                            <span className="absolute left-0 right-0 -bottom-px h-[2px] bg-[color:var(--color-fg)] rounded-t" />
                        )}
                    </button>
                ))}
            </div>

            {/* ─── Body ──────────────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto px-3 py-3">
                {tab === 'style' && <StyleTab drawing={drawing} colors={colors} onUpdate={onUpdate} />}
                {tab === 'text' && <ComingSoonTab title={t('chart.drawing.tabs.text')} hint={t('chart.drawing.textHint')} />}
                {tab === 'coords' && <CoordinatesTab drawing={drawing} onUpdate={onUpdate} />}
                {tab === 'visibility' && <ComingSoonTab title={t('chart.drawing.tabs.visibility')} hint={t('chart.drawing.visibilityHint')} />}
            </div>

            {/* ─── Footer ────────────────────────────────────────────── */}
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-[color:var(--color-border)]">
                <div className="flex items-center gap-1.5">
                    <button
                        disabled
                        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded border border-[color:var(--color-border)] text-[color:var(--color-muted-fg)]/50 cursor-not-allowed"
                        title={t('chart.drawing.comingSoon')}
                    >
                        {t('chart.drawing.template')}
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.2" /></svg>
                    </button>
                    <button
                        onClick={onDelete}
                        className="p-1 rounded text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-danger)] hover:bg-[color:var(--color-danger)]/10 transition-colors"
                        aria-label={t('chart.drawing.delete')}
                        title={t('chart.drawing.delete')}
                    >
                        <TrashIcon className="w-3.5 h-3.5" />
                    </button>
                </div>
                <div className="flex items-center gap-1.5">
                    <button
                        onClick={handleCancel}
                        className="px-3 py-1 text-[12px] rounded border border-[color:var(--color-border)] text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)] transition-colors"
                    >
                        {t('chart.drawing.cancel')}
                    </button>
                    <button
                        onClick={handleAccept}
                        className="px-3 py-1 text-[12px] font-semibold rounded bg-[color:var(--color-fg)] text-[color:var(--color-surface)] hover:opacity-90 transition-opacity"
                    >
                        {t('chart.drawing.accept')}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Tabs ───────────────────────────────────────────────────────────────────

interface StyleTabProps {
    drawing: Drawing;
    colors: readonly string[];
    onUpdate: (patch: Partial<Drawing>) => void;
}

function StyleTab({ drawing, colors, onUpdate }: StyleTabProps) {
    const { t } = useTranslation();
    const hasFill = HAS_FILL[drawing.type];

    return (
        <div className="space-y-3 text-[12px]">
            {/* Color */}
            <Row label={t('chart.drawing.color')}>
                <ColorSwatchPicker
                    value={drawing.color}
                    colors={colors}
                    onChange={(c) => {
                        const patch: Partial<Drawing> = { color: c };
                        if (hasFill && 'fillColor' in drawing) {
                            const alpha = alphaFromColor((drawing as { fillColor: string }).fillColor);
                            (patch as { fillColor: string }).fillColor = colorWithAlpha(c, alpha);
                        }
                        onUpdate(patch);
                    }}
                />
            </Row>

            {/* Line width */}
            <Row label={t('chart.drawing.thickness')}>
                <LineWidthPicker
                    value={drawing.lineWidth}
                    color={drawing.color}
                    onChange={(w) => onUpdate({ lineWidth: w })}
                />
            </Row>

            {/* Line style */}
            <Row label={t('chart.drawing.style')}>
                <LineStyleSwitcher
                    value={drawing.lineStyle}
                    color={drawing.color}
                    onChange={(s) => onUpdate({ lineStyle: s })}
                />
            </Row>

            {/* Fill: shapes & channel only */}
            {hasFill && 'fillColor' in drawing && (
                <Row label={t('chart.drawing.fill')}>
                    <FillControl
                        baseColor={drawing.color}
                        fillColor={(drawing as { fillColor: string }).fillColor}
                        onChange={(fillColor) => onUpdate({ fillColor } as Partial<Drawing>)}
                    />
                </Row>
            )}

            {/* Per-tool extras */}
            {drawing.type === 'horizontal_line' && (
                <Row label={t('chart.drawing.label')}>
                    <input
                        type="text"
                        value={(drawing as HorizontalLineDrawing).label || ''}
                        onChange={(e) => onUpdate({ label: e.target.value || undefined } as Partial<HorizontalLineDrawing>)}
                        placeholder={t('chart.drawing.optional')}
                        className="flex-1 px-2 py-1 text-[12px] rounded border border-[color:var(--color-border)] bg-[color:var(--color-surface)] focus:outline-none focus:border-[color:var(--color-primary)]"
                    />
                </Row>
            )}

            {drawing.type === 'fibonacci' && (
                <FibLevelsControl
                    levels={(drawing as FibonacciDrawing).levels}
                    onChange={(levels) => onUpdate({ levels } as Partial<FibonacciDrawing>)}
                />
            )}

            {drawing.type === 'arrow' && (
                <Row label={t('chart.drawing.direction')}>
                    <ArrowDirectionPicker
                        value={(drawing as ArrowDrawing).direction}
                        onChange={(d) => onUpdate({ direction: d } as Partial<ArrowDrawing>)}
                    />
                </Row>
            )}

            {drawing.type === 'text' && (
                <>
                    <Row label={t('chart.drawing.text')}>
                        <textarea
                            value={(drawing as TextDrawing).text}
                            onChange={(e) => onUpdate({ text: e.target.value } as Partial<TextDrawing>)}
                            rows={2}
                            className="flex-1 px-2 py-1 text-[12px] rounded border border-[color:var(--color-border)] bg-[color:var(--color-surface)] focus:outline-none focus:border-[color:var(--color-primary)] resize-none"
                        />
                    </Row>
                    <Row label={t('chart.drawing.size')}>
                        <input
                            type="range"
                            min={9}
                            max={32}
                            step={1}
                            value={(drawing as TextDrawing).fontSize}
                            onChange={(e) => onUpdate({ fontSize: Number(e.target.value) } as Partial<TextDrawing>)}
                            className="flex-1"
                        />
                        <span className="ml-2 text-[11px] tabular-nums w-8 text-right">{(drawing as TextDrawing).fontSize}px</span>
                    </Row>
                    <Row label={t('chart.drawing.background')}>
                        <label className="flex items-center gap-2 text-[12px]">
                            <input
                                type="checkbox"
                                checked={(drawing as TextDrawing).background}
                                onChange={(e) => onUpdate({ background: e.target.checked } as Partial<TextDrawing>)}
                            />
                            <span className="text-[color:var(--color-muted-fg)]">{t('chart.drawing.coloredPill')}</span>
                        </label>
                    </Row>
                </>
            )}
        </div>
    );
}

function ArrowDirectionPicker({ value, onChange }: { value: ArrowDirection; onChange: (d: ArrowDirection) => void }) {
    const dirs: Array<{ d: ArrowDirection; label: string }> = [
        { d: 'up', label: '↑' },
        { d: 'down', label: '↓' },
        { d: 'left', label: '←' },
        { d: 'right', label: '→' },
    ];
    return (
        <div className="flex gap-1.5">
            {dirs.map(({ d, label }) => (
                <button
                    key={d}
                    type="button"
                    onClick={() => onChange(d)}
                    className={`w-8 h-7 rounded border text-[14px] leading-none transition-colors ${
                        value === d
                            ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                            : 'border-[color:var(--color-border)] text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                >
                    {label}
                </button>
            ))}
        </div>
    );
}

interface CoordinatesTabProps {
    drawing: Drawing;
    onUpdate: (patch: Partial<Drawing>) => void;
}

function CoordinatesTab({ drawing, onUpdate }: CoordinatesTabProps) {
    switch (drawing.type) {
        case 'horizontal_line':
            return (
                <div className="space-y-2 text-[12px]">
                    <Row label="Nº 1 (precio)">
                        <NumberInput
                            value={drawing.price}
                            step={0.01}
                            onChange={(v) => onUpdate({ price: v } as Partial<HorizontalLineDrawing>)}
                        />
                    </Row>
                </div>
            );
        case 'vertical_line':
            return (
                <div className="space-y-2 text-[12px]">
                    <Row label="Nº 1 (fecha)">
                        <DateTimeInput
                            value={drawing.time}
                            onChange={(t) => onUpdate({ time: t } as Partial<VerticalLineDrawing>)}
                        />
                    </Row>
                </div>
            );
        case 'trendline':
        case 'ray':
        case 'extended_line':
        case 'fibonacci':
        case 'rectangle':
        case 'circle':
        case 'measure':
        case 'price_range':
        case 'date_range':
            return <TwoPointEditor drawing={drawing} onUpdate={onUpdate} />;
        case 'parallel_channel':
        case 'triangle':
            return <ThreePointEditor drawing={drawing} onUpdate={onUpdate} />;
        case 'arrow':
        case 'text':
            return (
                <div className="space-y-2 text-[12px]">
                    <PointEditor
                        index={1}
                        point={drawing.point1}
                        onChange={(p) => onUpdate({ point1: p } as Partial<Drawing>)}
                    />
                </div>
            );
    }
}

interface TwoPointEditorProps {
    drawing: TrendlineDrawing | RayDrawing | ExtendedLineDrawing | FibonacciDrawing | RectangleDrawing | CircleDrawing | MeasureDrawing | PriceRangeDrawing | DateRangeDrawing;
    onUpdate: (patch: Partial<Drawing>) => void;
}

function TwoPointEditor({ drawing, onUpdate }: TwoPointEditorProps) {
    return (
        <div className="space-y-3 text-[12px]">
            <PointEditor
                index={1}
                point={drawing.point1}
                onChange={(p) => onUpdate({ point1: p } as Partial<Drawing>)}
            />
            <PointEditor
                index={2}
                point={drawing.point2}
                onChange={(p) => onUpdate({ point2: p } as Partial<Drawing>)}
            />
        </div>
    );
}

interface ThreePointEditorProps {
    drawing: ParallelChannelDrawing | TriangleDrawing;
    onUpdate: (patch: Partial<Drawing>) => void;
}

function ThreePointEditor({ drawing, onUpdate }: ThreePointEditorProps) {
    return (
        <div className="space-y-3 text-[12px]">
            <PointEditor index={1} point={drawing.point1} onChange={(p) => onUpdate({ point1: p } as Partial<Drawing>)} />
            <PointEditor index={2} point={drawing.point2} onChange={(p) => onUpdate({ point2: p } as Partial<Drawing>)} />
            <PointEditor index={3} point={drawing.point3} onChange={(p) => onUpdate({ point3: p } as Partial<Drawing>)} />
        </div>
    );
}

interface PointEditorProps {
    index: number;
    point: { time: number; price: number; logical?: number };
    onChange: (next: { time: number; price: number; logical?: number }) => void;
}

function PointEditor({ index, point, onChange }: PointEditorProps) {
    const { t } = useTranslation();
    return (
        <div className="border border-[color:var(--color-border-subtle)] rounded p-2 space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-muted-fg)]">{t('chart.drawing.pointN', { n: index })}</div>
            <Row label={t('chart.drawing.price')}>
                <NumberInput value={point.price} step={0.01} onChange={(v) => onChange({ ...point, price: v })} />
            </Row>
            <Row label={t('chart.drawing.date')}>
                <DateTimeInput value={point.time} onChange={(time) => onChange({ ...point, time })} />
            </Row>
        </div>
    );
}

function ComingSoonTab({ title, hint }: { title: string; hint: string }) {
    const { t } = useTranslation();
    return (
        <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="text-[13px] font-semibold text-[color:var(--color-fg)]">{title}</div>
            <div className="text-[11px] text-[color:var(--color-muted-fg)] mt-1 max-w-[260px]">{hint}</div>
            <div className="text-[10px] text-[color:var(--color-muted-fg)]/70 mt-3 px-2 py-0.5 rounded border border-[color:var(--color-border)]">
                {t('chart.drawing.comingSoon')}
            </div>
        </div>
    );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function Row({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center gap-3">
            <div className="w-20 text-[11px] text-[color:var(--color-muted-fg)] flex-shrink-0">{label}</div>
            <div className="flex-1 min-w-0 flex items-center gap-2">{children}</div>
        </div>
    );
}

interface ColorSwatchPickerProps {
    value: string;
    colors: readonly string[];
    onChange: (c: string) => void;
}

function ColorSwatchPicker({ value, colors, onChange }: ColorSwatchPickerProps) {
    return (
        <div className="flex flex-wrap gap-1.5">
            {colors.map(c => (
                <button
                    key={c}
                    onClick={() => onChange(c)}
                    className={`w-5 h-5 rounded transition-transform ${
                        value === c
                            ? 'ring-2 ring-offset-1 ring-[color:var(--color-fg)] scale-110'
                            : 'hover:scale-110'
                    }`}
                    style={{ backgroundColor: c }}
                    aria-label={`Color ${c}`}
                />
            ))}
        </div>
    );
}

interface LineWidthPickerProps {
    value: number;
    color: string;
    onChange: (w: number) => void;
}

function LineWidthPicker({ value, color, onChange }: LineWidthPickerProps) {
    return (
        <div className="flex gap-1">
            {[1, 2, 3, 4].map(w => (
                <button
                    key={w}
                    onClick={() => onChange(w)}
                    className={`flex-1 h-6 flex items-center justify-center rounded border transition-colors ${
                        value === w
                            ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                            : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                    aria-label={`Grosor ${w}px`}
                >
                    <span className="rounded-full" style={{ width: 18, height: w, backgroundColor: color }} />
                </button>
            ))}
        </div>
    );
}

interface LineStyleSwitcherProps {
    value: LineStyle;
    color: string;
    onChange: (s: LineStyle) => void;
}

function LineStyleSwitcher({ value, color, onChange }: LineStyleSwitcherProps) {
    const { t } = useTranslation();
    const styles: { id: LineStyle; label: string; pattern: string }[] = [
        { id: 'solid', label: t('chart.drawing.solid'), pattern: '' },
        { id: 'dashed', label: t('chart.drawing.dashed'), pattern: '6 4' },
        { id: 'dotted', label: t('chart.drawing.dotted'), pattern: '2 3' },
    ];
    return (
        <div className="flex gap-1 flex-1">
            {styles.map(s => (
                <button
                    key={s.id}
                    onClick={() => onChange(s.id)}
                    className={`flex-1 h-6 flex items-center justify-center rounded border transition-colors ${
                        value === s.id
                            ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10'
                            : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-surface-hover)]'
                    }`}
                    aria-label={s.label}
                    title={s.label}
                >
                    <svg width="32" height="6" viewBox="0 0 32 6">
                        <line
                            x1="2" y1="3" x2="30" y2="3"
                            stroke={color}
                            strokeWidth="2"
                            strokeLinecap={s.id === 'dotted' ? 'round' : 'butt'}
                            strokeDasharray={s.pattern}
                        />
                    </svg>
                </button>
            ))}
        </div>
    );
}

interface FillControlProps {
    baseColor: string;
    fillColor: string;
    onChange: (fillColor: string) => void;
}

function FillControl({ baseColor, fillColor, onChange }: FillControlProps) {
    const { t } = useTranslation();
    const alpha = alphaFromColor(fillColor);
    return (
        <div className="flex items-center gap-2 flex-1">
            <div
                className="w-5 h-5 rounded border border-[color:var(--color-border)]"
                style={{ backgroundColor: fillColor }}
                title={t('chart.drawing.fillColor')}
            />
            <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={alpha}
                onChange={(e) => onChange(colorWithAlpha(baseColor, parseFloat(e.target.value)))}
                className="flex-1"
                aria-label="Opacidad del relleno"
            />
            <span className="text-[10px] text-[color:var(--color-muted-fg)] tabular-nums w-8 text-right">
                {Math.round(alpha * 100)}%
            </span>
        </div>
    );
}

interface FibLevelsControlProps {
    levels: number[];
    onChange: (levels: number[]) => void;
}

const FIB_EXT_LEVELS = [1.272, 1.414, 1.618, 2.0, 2.618];

function FibLevelsControl({ levels, onChange }: FibLevelsControlProps) {
    const toggle = (lvl: number) => {
        const next = levels.includes(lvl)
            ? levels.filter(l => l !== lvl)
            : [...levels, lvl].sort((a, b) => a - b);
        onChange(next);
    };
    return (
        <div className="pt-1 border-t border-[color:var(--color-border-subtle)]">
            <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-muted-fg)] mb-1.5">Niveles</div>
            <div className="grid grid-cols-3 gap-y-1.5 gap-x-2">
                {[...FIB_LEVELS, ...FIB_EXT_LEVELS].map(lvl => {
                    const checked = levels.includes(lvl);
                    return (
                        <label key={lvl} className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                            <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggle(lvl)}
                                className="w-3 h-3 accent-[color:var(--color-primary)]"
                            />
                            <span className="tabular-nums">{(lvl * 100).toFixed(lvl < 1 ? 1 : 0).replace(/\.0$/, '')}%</span>
                        </label>
                    );
                })}
            </div>
        </div>
    );
}

interface NumberInputProps {
    value: number;
    step: number;
    onChange: (v: number) => void;
}

function NumberInput({ value, step, onChange }: NumberInputProps) {
    const [local, setLocal] = useState(String(value));
    useEffect(() => { setLocal(String(value)); }, [value]);

    const commit = (raw: string) => {
        const n = parseFloat(raw);
        if (Number.isFinite(n)) onChange(n);
        else setLocal(String(value));
    };

    return (
        <div className="flex items-center flex-1 border border-[color:var(--color-primary)] rounded overflow-hidden">
            <input
                type="number"
                value={local}
                step={step}
                onChange={(e) => setLocal(e.target.value)}
                onBlur={(e) => commit(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                className="flex-1 min-w-0 px-2 py-1 text-[12px] bg-[color:var(--color-surface)] focus:outline-none tabular-nums"
            />
            <div className="flex flex-col border-l border-[color:var(--color-border)]">
                <button
                    onClick={() => onChange(value + step)}
                    className="w-5 h-3 flex items-center justify-center text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                    tabIndex={-1}
                    aria-label="Aumentar"
                >
                    <svg width="8" height="5" viewBox="0 0 8 5"><path d="M1 4l3-3 3 3" stroke="currentColor" strokeWidth="1.2" fill="none" /></svg>
                </button>
                <button
                    onClick={() => onChange(value - step)}
                    className="w-5 h-3 flex items-center justify-center text-[color:var(--color-muted-fg)] hover:text-[color:var(--color-fg)] hover:bg-[color:var(--color-surface-hover)]"
                    tabIndex={-1}
                    aria-label="Disminuir"
                >
                    <svg width="8" height="5" viewBox="0 0 8 5"><path d="M1 1l3 3 3-3" stroke="currentColor" strokeWidth="1.2" fill="none" /></svg>
                </button>
            </div>
        </div>
    );
}

interface DateTimeInputProps {
    value: number;        // Unix seconds
    onChange: (t: number) => void;
}

function DateTimeInput({ value, onChange }: DateTimeInputProps) {
    const dt = useMemo(() => unixToInputValue(value), [value]);
    return (
        <input
            type="datetime-local"
            value={dt}
            onChange={(e) => {
                const t = inputValueToUnix(e.target.value);
                if (Number.isFinite(t)) onChange(t);
            }}
            className="flex-1 min-w-0 px-2 py-1 text-[12px] rounded border border-[color:var(--color-border)] bg-[color:var(--color-surface)] focus:outline-none focus:border-[color:var(--color-primary)] tabular-nums"
        />
    );
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function clampPos(x: number, y: number, cw: number, ch: number): { x: number; y: number } {
    return {
        x: Math.min(Math.max(8, x), Math.max(8, cw - DIALOG_WIDTH - 8)),
        y: Math.min(Math.max(8, y), Math.max(8, ch - DIALOG_MAX_HEIGHT - 8)),
    };
}

function unixToInputValue(unixSec: number): string {
    const d = new Date(unixSec * 1000);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function inputValueToUnix(raw: string): number {
    const ms = Date.parse(raw);
    return Number.isFinite(ms) ? Math.floor(ms / 1000) : NaN;
}
