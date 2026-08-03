'use client';

import { useCallback, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import {
  deriveDisplayUnit,
  displayToRaw,
  formatCompact,
  formatLocaleNumber,
  formatPlaceholder,
  parseLocaleNumber,
  resolveInputLocale,
} from '@/lib/utils/numberFormat';

/** Locale de ENTRADA de la app (i18n del usuario): decide coma/punto. */
export function useInputLocale(): string {
  const { i18n } = useTranslation();
  return resolveInputLocale(i18n.language);
}

const INVALID_CLS = 'border-rose-500/60';

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
  const locale = useInputLocale();
  const [displayStr, setDisplayStr] = useState('');
  const [unit, setUnit] = useState(defaultUnit || opts[0] || '');
  const [focused, setFocused] = useState(false);
  const [invalid, setInvalid] = useState(false);

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
        setInvalid(false);
        onChange(undefined);
        return;
      }
      const parsed = parseLocaleNumber(trimmed, locale);
      if (parsed.invalid || parsed.value === null) {
        // entrada no reconocida: se conserva el último valor válido, NUNCA 0
        setInvalid(true);
        return;
      }
      setInvalid(false);
      onChange(displayToRaw(parsed.value, u));
    },
    [onChange, locale],
  );

  return (
    <div className={cn(scaledGroupBase, invalid && INVALID_CLS, className)}>
      <input
        type="text"
        inputMode="decimal"
        aria-invalid={invalid || undefined}
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
  const locale = useInputLocale();
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');
  const [invalid, setInvalid] = useState(false);

  const display =
    value !== undefined && Number.isFinite(value)
      ? formatLocaleNumber(value, locale)
      : '';

  return (
    <input
      type="text"
      inputMode="decimal"
      aria-invalid={invalid || undefined}
      value={editing ? editStr : display}
      placeholder={placeholder}
      className={cn(fieldBase, FIELD_W, invalid && INVALID_CLS, className)}
      onFocus={() => {
        setEditing(true);
        setEditStr(value !== undefined ? String(value) : '');
      }}
      onBlur={() => {
        setEditing(false);
        const parsed = parseLocaleNumber(editStr, locale);
        if (parsed.invalid) {
          setInvalid(true); // conserva el último valor válido
          return;
        }
        setInvalid(false);
        onChange(parsed.value === null ? undefined : parsed.value);
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
  const locale = useInputLocale();
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
            const parsed = parseLocaleNumber(v, locale);
            if (!parsed.invalid && parsed.value !== null) onChange(parsed.value);
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

/* ════════════════════════════════════════════════════════════════════
   NumericField — EL campo numérico de la app (BUILD, Screener, Backtester).

   La semántica del campo (unidad fija, escalas K/M/B, compacto) NO se
   escribe en los consumidores: viene de un FieldSpec derivado del catálogo
   (specFromFilterDef) o del esquema del screener (specFromScreenerField).
   Una lógica, un módulo, cero espagueti.
   ════════════════════════════════════════════════════════════════════ */

export interface FieldSpec {
  /** Sufijo fijo dentro del campo: '$', '%', 'x', 'bps', 'min'… */
  suffix?: string;
  /** Escalas seleccionables (['','K','M'] o ['K','M','B']): activa el selector. */
  units?: readonly string[];
  defaultUnit?: string;
  /** Mostrar compacto (5M) al perder el foco, sin selector. */
  compact?: boolean;
  min?: number;
  max?: number;
  placeholder?: string;
}

/** FilterDef del catálogo generado (filter-catalog.generated.ts) → spec. */
export function specFromFilterDef(def: {
  suf?: string;
  units?: readonly string[];
  defU?: string;
  phMin?: string;
}): FieldSpec {
  return {
    suffix: def.suf || undefined,
    units: def.units && def.units.length > 0 ? def.units : undefined,
    defaultUnit: def.defU,
    placeholder: formatPlaceholder(def.phMin, def.defU),
  };
}

/** AVAILABLE_FIELDS del screener ({type, unit, min, max}) → spec. */
export function specFromScreenerField(f: {
  type?: string;
  unit?: string;
  min?: number;
  max?: number;
}): FieldSpec {
  if (f.type === 'units') return { compact: true };
  return {
    suffix: f.unit || undefined,
    min: f.min,
    max: f.max,
  };
}

export function NumericField({
  value,
  onChange,
  spec,
  className,
  id,
  ariaLabel,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  spec: FieldSpec;
  className?: string;
  id?: string;
  ariaLabel?: string;
}) {
  const locale = useInputLocale();
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');
  const [invalid, setInvalid] = useState(false);

  if (spec.units && spec.units.length > 1) {
    return (
      <ScaledNumInput
        rawValue={value === null ? undefined : value}
        onChange={(v) => onChange(v === undefined ? null : v)}
        unitOpts={spec.units}
        defaultUnit={spec.defaultUnit}
        placeholder={spec.placeholder}
        className={className}
      />
    );
  }

  const display =
    value === null || value === undefined || !Number.isFinite(value)
      ? ''
      : spec.compact
        ? formatCompact(value)
        : formatLocaleNumber(value, locale);

  const commit = (raw: string) => {
    setEditing(false);
    const parsed = parseLocaleNumber(raw, locale);
    if (parsed.invalid) {
      setInvalid(true); // conserva el último valor válido, NUNCA 0
      return;
    }
    setInvalid(false);
    if (parsed.value === null) {
      onChange(null);
      return;
    }
    let v = parsed.value;
    if (spec.min !== undefined && v < spec.min) v = spec.min;
    if (spec.max !== undefined && v > spec.max) v = spec.max;
    onChange(v);
  };

  return (
    <div className={cn(scaledGroupBase, invalid && INVALID_CLS, className)}>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        value={editing ? editStr : display}
        placeholder={spec.placeholder ?? '–'}
        className={scaledInputInner}
        onFocus={() => {
          setEditing(true);
          setEditStr(value === null || value === undefined ? '' : String(value));
        }}
        onBlur={(e) => commit(e.target.value)}
        onChange={(e) => setEditStr(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { commit((e.target as HTMLInputElement).value); (e.target as HTMLInputElement).blur(); }
          if (e.key === 'Escape') { setEditing(false); setInvalid(false); (e.target as HTMLInputElement).blur(); }
        }}
      />
      {spec.suffix ? <span className={cn(scaledUnitInner, 'cursor-default select-none')}>{spec.suffix}</span> : null}
    </div>
  );
}
