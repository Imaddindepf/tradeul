'use client';

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  deriveDisplayUnit,
  displayToRaw,
  formatPlaceholder,
  parseHumanNumber,
} from '@/lib/utils/numberFormat';

/**
 * Tokens de densidad alineados con el panel original (Trade Ideas–style):
 * ~26px alto, 11px texto, inputs ~76px. Un poco más anchos que w-[72px] para
 * caber "500" / "1.5" sin agrandar filas ni tipografía.
 */
const H = 'h-[26px]';
const TXT = 'text-[11px]';
const PAD = 'px-1.5';
const ROUND = 'rounded';
const RING = 'focus:outline-none focus:ring-1 focus:ring-primary';
const BG = 'bg-[var(--color-input-bg)]';

const fieldBase = cn(
  H, TXT, PAD, 'font-mono tabular-nums text-right leading-none',
  BG, 'text-foreground placeholder:text-muted-fg/40',
  'border border-border', ROUND, RING,
);

/** Ancho cómodo para min/max (original 72px → 76px) */
const FIELD_W = 'w-[76px] shrink-0';

const scaledGroupBase = cn(
  'flex items-stretch overflow-hidden', FIELD_W,
  'border border-border', BG, ROUND,
  'focus-within:ring-1 focus-within:ring-primary',
);

const scaledInputInner = cn(
  H, TXT, PAD, 'flex-1 min-w-0 font-mono tabular-nums text-right leading-none',
  'bg-transparent text-foreground placeholder:text-muted-fg/40',
  'border-0 focus:outline-none focus:ring-0',
);

const scaledUnitInner = cn(
  H, 'w-8 shrink-0 border-0 border-l border-border bg-surface/80',
  'px-0.5 text-[10px] font-medium text-muted-fg appearance-none text-center',
  'focus:outline-none focus:ring-0 cursor-pointer',
);

/* ── ScaledNumInput ──────────────────────────────────────────────── */

export function ScaledNumInput({
  rawValue,
  onChange,
  unitOpts,
  defaultUnit = '',
  placeholder,
  className,
}: {
  rawValue: number | undefined;
  onChange: (raw: number | undefined) => void;
  unitOpts: readonly string[];
  defaultUnit?: string;
  placeholder?: string;
  className?: string;
}) {
  const opts = unitOpts.length > 0 ? unitOpts : [''];
  const [displayStr, setDisplayStr] = useState('');
  const [unit, setUnit] = useState(defaultUnit || opts[0] || '');
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (focused) return;
    if (rawValue === undefined || rawValue === null) {
      setDisplayStr('');
      setUnit(defaultUnit || opts[0] || '');
      return;
    }
    const { display, unit: u } = deriveDisplayUnit(rawValue, opts, defaultUnit);
    setDisplayStr(String(display));
    setUnit(u);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawValue, defaultUnit, focused]);

  const commit = useCallback(
    (disp: string, u: string) => {
      const trimmed = disp.trim();
      if (trimmed === '') {
        onChange(undefined);
        return;
      }
      const num = parseHumanNumber(trimmed);
      if (num === null) return;
      onChange(displayToRaw(num, u));
    },
    [onChange],
  );

  return (
    <div className={cn(scaledGroupBase, className)}>
      <input
        type="text"
        inputMode="decimal"
        value={displayStr}
        placeholder={placeholder}
        className={scaledInputInner}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          commit(displayStr, unit);
        }}
        onChange={(e) => setDisplayStr(e.target.value)}
      />
      <select
        value={unit}
        className={scaledUnitInner}
        aria-label="Unit"
        onChange={(e) => {
          const next = e.target.value;
          setUnit(next);
          commit(displayStr, next);
        }}
      >
        {opts.map((u) => (
          <option key={u || 'raw'} value={u}>
            {u || 'sh'}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ── PlainNumInput ───────────────────────────────────────────────── */

export function PlainNumInput({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');

  const display =
    value !== undefined && Number.isFinite(value)
      ? value.toLocaleString('en-US', { maximumFractionDigits: 6 })
      : '';

  return (
    <input
      type="text"
      inputMode="decimal"
      value={editing ? editStr : display}
      placeholder={placeholder}
      className={cn(fieldBase, FIELD_W, className)}
      onFocus={() => {
        setEditing(true);
        setEditStr(value !== undefined ? String(value) : '');
      }}
      onBlur={() => {
        setEditing(false);
        const parsed = parseHumanNumber(editStr);
        onChange(parsed === null ? undefined : parsed);
      }}
      onChange={(e) => setEditStr(e.target.value)}
    />
  );
}

/* ── AlertThresholdInput ─────────────────────────────────────────── */

export function AlertThresholdInput({
  value,
  onChange,
  placeholder,
  unit,
  title,
  onClick,
}: {
  value: number | string | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
  unit?: string;
  title?: string;
  onClick?: (e: React.MouseEvent) => void;
}) {
  return (
    <div className="flex items-center gap-0.5 shrink-0" title={title}>
      <input
        type="text"
        inputMode="decimal"
        placeholder={placeholder}
        value={value ?? ''}
        onClick={onClick}
        onChange={(e) => {
          const v = e.target.value.trim();
          if (v === '') onChange(undefined);
          else {
            const n = parseHumanNumber(v);
            onChange(n === null ? undefined : n);
          }
        }}
        className={cn(
          fieldBase,
          'w-14 text-center px-1',
        )}
      />
      {unit ? (
        <span className="w-3.5 text-[10px] text-muted-fg text-center shrink-0">{unit}</span>
      ) : null}
    </div>
  );
}

/* ── FilterRangeRow ──────────────────────────────────────────────── */

export interface FilterRangeRowProps {
  label: string;
  minValue?: number;
  maxValue?: number;
  onMinChange: (v?: number) => void;
  onMaxChange: (v?: number) => void;
  unitOpts?: readonly string[];
  defaultUnit?: string;
  phMin?: string;
  phMax?: string;
  suffix?: string;
  help?: React.ReactNode;
  warn?: React.ReactNode;
  /** Scanner panel: label column un poco más estrecha */
  compactLabel?: boolean;
  /** Strategy Builder: columna de label ancha (cabe "Distance from Inside Market")
   *  e inputs más anchos (cabe "100000" junto al selector de unidad). */
  wide?: boolean;
}

export function FilterRangeRow({
  label,
  minValue,
  maxValue,
  onMinChange,
  onMaxChange,
  unitOpts,
  defaultUnit,
  phMin,
  phMax,
  suffix,
  help,
  warn,
  compactLabel,
  wide,
}: FilterRangeRowProps) {
  const hasUnits = unitOpts && unitOpts.length > 0;
  const phMinTxt = formatPlaceholder(phMin, defaultUnit) || 'min';
  const phMaxTxt = formatPlaceholder(phMax, defaultUnit) || 'max';
  // En modo wide los campos crecen para que "100000" quepa junto al selector de unidad
  const fieldW = wide ? 'w-[96px]' : undefined;

  return (
    <div className="flex items-center gap-1.5 px-3 py-[3px]">
      <div
        className={cn(
          'flex items-center gap-0.5 shrink-0 font-medium text-foreground/70',
          compactLabel ? 'w-[5.5rem]' : wide ? 'w-56' : 'w-24',
        )}
      >
        {/* wide: sin truncate — el label más largo del catálogo mide 196px (< w-56=224px);
            si el catálogo crece, hace wrap en vez de cortarse */}
        <span className={cn(TXT, wide ? 'leading-tight' : 'truncate')} title={label}>{label}</span>
        {help}
      </div>

      {hasUnits ? (
        <>
          <ScaledNumInput
            rawValue={minValue}
            onChange={onMinChange}
            unitOpts={unitOpts}
            defaultUnit={defaultUnit}
            placeholder={phMinTxt}
            className={fieldW}
          />
          <span className="text-muted-fg/40 text-[9px] shrink-0">-</span>
          <ScaledNumInput
            rawValue={maxValue}
            onChange={onMaxChange}
            unitOpts={unitOpts}
            defaultUnit={defaultUnit}
            placeholder={phMaxTxt}
            className={fieldW}
          />
        </>
      ) : (
        <>
          <PlainNumInput value={minValue} onChange={onMinChange} placeholder={phMinTxt} className={fieldW} />
          <span className="text-muted-fg/40 text-[9px] shrink-0">-</span>
          <PlainNumInput value={maxValue} onChange={onMaxChange} placeholder={phMaxTxt} className={fieldW} />
        </>
      )}

      {suffix ? (
        <span className="text-[10px] text-muted-fg w-4 text-center shrink-0">{suffix}</span>
      ) : (
        <span className="w-4 shrink-0" />
      )}
      {warn}
    </div>
  );
}
