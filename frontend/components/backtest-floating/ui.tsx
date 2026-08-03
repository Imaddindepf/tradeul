'use client';

/**
 * Primitivas del Backtester en el lenguaje visual de ERN
 * (components/floating-window/EarningsCalendarContent.tsx).
 *
 * Reglas que hereda esta ventana y que conviene no romper:
 *  - Sin iconos. La navegación y los cierres son caracteres tipográficos.
 *  - Sin color salvo subida/bajada. Todo lo demás es alfa sobre `foreground`:
 *      fondo   /[0.03] /[0.04] /[0.05] /[0.06] /[0.08] /[0.10]
 *      borde   /10 /20 /30 /45
 *      texto   /25 /35 /45 /55 /65 /70
 *  - Campos sin borde hasta el foco.
 *  - Escala: 10px versalitas · 11px control · 12px dato · 13px título.
 *
 * Lo que añade respecto a ERN: el cableado de accesibilidad (label/htmlFor,
 * aria-pressed, aria-invalid, aria-describedby), que en el Backtester viejo
 * era literalmente cero.
 */

import {
  memo, useId, useState, useCallback, useRef, useEffect,
  type ReactNode, type InputHTMLAttributes,
} from 'react';
import { cn } from '@/lib/utils';
import { parseHumanNumber } from '@/lib/utils/numberFormat';

/* ── Bordes: ERN los pone inline con fallback, para que la ventana siga
      legible aunque el tema no defina la variable. ─────────────────────── */
export const RULE = 'var(--color-border, rgba(127,127,127,0.14))';
export const RULE_SOFT = 'var(--color-border, rgba(127,127,127,0.10))';

/* ══════════════════════════════════════════════════════════════════════
   CHIP — contador que filtra. El objeto de BMO · DUR · AMC de ERN.
   Un chip a cero se apaga y se deshabilita: filtrar a vacío es una trampa.
   ══════════════════════════════════════════════════════════════════════ */

export const Chip = memo(function Chip({
  label, value, active = false, disabled = false, title, onClick,
}: {
  label: string;
  value?: ReactNode;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  onClick?: () => void;
}) {
  const empty = value === 0 || value === '0';
  const dead = disabled || (empty && !active);

  return (
    <button
      type="button"
      title={title}
      disabled={dead}
      aria-pressed={onClick ? active : undefined}
      onClick={onClick}
      className={cn(
        'shrink-0 inline-flex items-center gap-1.5 px-2 h-6 rounded border transition-colors',
        active
          ? 'border-foreground/45 bg-foreground/[0.10]'
          : dead
            ? 'border-foreground/10 cursor-default'
            : 'border-foreground/20 bg-foreground/[0.04]',
        !dead && !active && onClick && 'hover:bg-foreground/[0.08] hover:border-foreground/30',
      )}
    >
      <span className={cn(
        'text-[10px] uppercase tracking-wider',
        active ? 'text-foreground/70' : dead ? 'text-foreground/25' : 'text-foreground/45',
      )}>
        {label}
      </span>
      {value !== undefined && (
        <span className={cn(
          'text-[11px] font-semibold tabular-nums',
          dead ? 'text-foreground/25' : 'text-foreground',
        )}>
          {value}
        </span>
      )}
    </button>
  );
});

/* ══════════════════════════════════════════════════════════════════════
   BADGE — estado. El patrón de LiveBadge: redondeado completo, punto y
   versalitas. `pulse` solo cuando algo está de verdad en marcha.
   ══════════════════════════════════════════════════════════════════════ */

export const Badge = memo(function Badge({
  children, pulse = false, title,
}: { children: ReactNode; pulse?: boolean; title?: string }) {
  return (
    <span
      title={title}
      className="shrink-0 inline-flex items-center gap-1.5 px-2 h-[22px] rounded-full border border-foreground/20 bg-foreground/[0.06]"
    >
      <span className="relative flex w-1.5 h-1.5">
        {pulse && (
          <span className="absolute inline-flex w-full h-full rounded-full bg-foreground/60 motion-safe:animate-ping" />
        )}
        <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-foreground/80" />
      </span>
      <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/70">
        {children}
      </span>
    </span>
  );
});

/* ══════════════════════════════════════════════════════════════════════
   SEG — grupo segmentado. El conmutador Calendario/Búsqueda de ERN.
   Navegable con flechas: es un radiogroup, no una fila de botones sueltos.
   ══════════════════════════════════════════════════════════════════════ */

export interface SegOption<T extends string> {
  value: T;
  label: string;
  /** Deshabilitada pero visible: se ve que existe y por qué no se puede usar. */
  disabled?: boolean;
  title?: string;
}

export function Seg<T extends string>({
  value, options, onChange, mono = false, size = 'md', ariaLabel,
}: {
  value: T;
  options: readonly SegOption<T>[];
  onChange: (v: T) => void;
  mono?: boolean;
  size?: 'sm' | 'md';
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const move = useCallback((dir: 1 | -1) => {
    const usable = options.filter(o => !o.disabled);
    if (usable.length < 2) return;
    const i = usable.findIndex(o => o.value === value);
    const next = usable[(i + dir + usable.length) % usable.length];
    onChange(next.value);
    // El foco sigue a la selección para que el teclado no se pierda.
    requestAnimationFrame(() => {
      ref.current?.querySelector<HTMLButtonElement>(`[data-v="${next.value}"]`)?.focus();
    });
  }, [options, value, onChange]);

  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label={ariaLabel}
      className="shrink-0 inline-flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.05]"
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); move(1); }
        if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
      }}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            data-v={o.value}
            aria-checked={on}
            disabled={o.disabled}
            title={o.title}
            tabIndex={on ? 0 : -1}
            onClick={() => !o.disabled && onChange(o.value)}
            className={cn(
              'rounded font-medium transition-colors whitespace-nowrap',
              size === 'sm' ? 'px-1.5 h-5 text-[10px]' : 'px-2.5 h-7 text-[11px]',
              mono && 'font-mono',
              on
                ? 'bg-foreground/[0.10] text-foreground'
                : o.disabled
                  ? 'text-foreground/25 cursor-default'
                  : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.05]',
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   CAMPOS — sin borde hasta el foco, como el buscador de ticker de ERN.
   ══════════════════════════════════════════════════════════════════════ */

const FIELD_BASE =
  'h-7 px-2 rounded-md text-[11px] bg-foreground/[0.04] text-foreground ' +
  'placeholder:text-foreground/35 border border-transparent outline-none transition-colors ' +
  'hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] focus:border-foreground/15 ' +
  'disabled:opacity-40 disabled:cursor-not-allowed';

/** Etiqueta + control cableados. Hacer clic en la etiqueta enfoca el campo. */
export function Field({
  label, children, hint, error, className,
}: {
  label: string;
  children: (props: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
  hint?: ReactNode;
  error?: string;
  className?: string;
}) {
  const id = useId();
  const hintId = hint || error ? `${id}-d` : undefined;
  return (
    <div className={cn('flex flex-col gap-1 min-w-0', className)}>
      <label htmlFor={id} className="text-[10px] uppercase tracking-wider text-foreground/45">
        {label}
      </label>
      {children({ id, describedBy: hintId, invalid: !!error })}
      {(hint || error) && (
        <span
          id={hintId}
          className={cn('text-[11px] leading-snug', error ? 'text-rose-500 dark:text-rose-400' : 'text-foreground/45')}
        >
          {error || hint}
        </span>
      )}
    </div>
  );
}

/**
 * Igual que `Field`, pero para un control compuesto (un `Seg`, por ejemplo).
 *
 * No se puede usar `<label htmlFor>` aquí: un radiogroup no es un único
 * elemento etiquetable, y apuntar a un id inexistente es peor que no etiquetar
 * — el lector de pantalla se queda sin nombre y la etiqueta deja de enfocar.
 * Se etiqueta el grupo con `aria-labelledby`.
 */
export function FieldGroup({
  label, children, hint, className,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn('flex flex-col gap-1 min-w-0', className)}>
      <span id={id} className="text-[10px] uppercase tracking-wider text-foreground/45">
        {label}
      </span>
      <div role="group" aria-labelledby={id} className="flex min-w-0">
        {children}
      </div>
      {hint && <span className="text-[11px] leading-snug text-foreground/45">{hint}</span>}
    </div>
  );
}

export const TextInput = memo(function TextInput({
  value, onChange, mono, invalid, className, ...rest
}: {
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
  invalid?: boolean;
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  return (
    <input
      {...rest}
      value={value}
      aria-invalid={invalid || undefined}
      onChange={(e) => onChange(e.target.value)}
      className={cn(FIELD_BASE, mono && 'font-mono tabular-nums',
        invalid && 'border-rose-500/50', className)}
    />
  );
});

/**
 * Número que acepta lenguaje humano: `1.5M`, `500k`, `1,250`.
 *
 * El campo del Backtester viejo hacía `parseFloat(v) || null`, así que un `0`
 * caía a null y el filtro se descartaba en silencio. `parseHumanNumber`
 * comprueba null explícitamente, así que el cero sobrevive.
 *
 * Se edita como texto libre y solo se normaliza al salir: reformatear
 * mientras se teclea mueve el cursor y es insufrible.
 */
export const NumInput = memo(function NumInput({
  value, onChange, placeholder = '–', align = 'right', mono = true, invalid, className, id, describedBy,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  placeholder?: string;
  align?: 'left' | 'right';
  mono?: boolean;
  invalid?: boolean;
  className?: string;
  id?: string;
  describedBy?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (value === null || value === undefined ? '' : String(value));

  const commit = useCallback((raw: string) => {
    setDraft(null);
    const t = raw.trim();
    if (t === '') { onChange(null); return; }
    const n = parseHumanNumber(t);
    onChange(n === null ? null : n);
  }, [onChange]);

  return (
    <input
      id={id}
      inputMode="decimal"
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      value={shown}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { commit((e.target as HTMLInputElement).value); (e.target as HTMLInputElement).blur(); }
        if (e.key === 'Escape') { setDraft(null); (e.target as HTMLInputElement).blur(); }
      }}
      className={cn(FIELD_BASE, mono && 'font-mono tabular-nums',
        align === 'right' ? 'text-right' : 'text-left',
        invalid && 'border-rose-500/50', className)}
    />
  );
});

/* ══════════════════════════════════════════════════════════════════════
   ESTRUCTURA
   ══════════════════════════════════════════════════════════════════════ */

export function SectionHead({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/55 shrink-0">
        {title}
      </span>
      <span className="flex-1 h-px" style={{ backgroundColor: RULE }} />
      {action}
    </div>
  );
}

/** Botón de texto. Sin icono: el `+` es un carácter, como el `‹` de ERN. */
export const TextButton = memo(function TextButton({
  children, onClick, hint, disabled, tone = 'normal',
}: {
  children: ReactNode; onClick?: () => void; hint?: string; disabled?: boolean;
  tone?: 'normal' | 'quiet';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'shrink-0 inline-flex items-center gap-1.5 text-[11px] rounded px-1 -mx-1 transition-colors',
        tone === 'quiet' ? 'text-foreground/45' : 'text-foreground/65',
        !disabled && 'hover:text-foreground', disabled && 'opacity-40',
      )}
    >
      {children}
      {hint && <span className="font-mono text-[10px] text-foreground/35">{hint}</span>}
    </button>
  );
});

/** Acción principal. Sigue siendo monocroma: el peso lo da el fondo /[0.10]. */
export const ActionButton = memo(function ActionButton({
  children, onClick, hint, disabled, busy,
}: {
  children: ReactNode; onClick?: () => void; hint?: string; disabled?: boolean; busy?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-busy={busy || undefined}
      className={cn(
        'shrink-0 inline-flex items-center gap-2 h-7 px-3 rounded-md text-[11px] font-semibold',
        'border border-foreground/20 bg-foreground/[0.10] transition-colors',
        disabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-foreground/[0.16] hover:border-foreground/30',
      )}
    >
      {children}
      {hint && <span className="font-mono text-[10px] font-normal text-foreground/55">{hint}</span>}
    </button>
  );
});

export function CenterMessage({
  children, tone = 'muted',
}: { children: ReactNode; tone?: 'muted' | 'error' }) {
  return (
    <div className={cn(
      'flex items-center justify-center h-full px-6 text-center text-[12px]',
      tone === 'error' ? 'text-rose-500 dark:text-rose-400' : 'text-foreground/45',
    )}>
      {children}
    </div>
  );
}

/** Pie de ventana de ERN: 28px, cifras tabulares a la izquierda. */
export function WindowFooter({ left, right }: { left: ReactNode; right?: ReactNode }) {
  return (
    <div
      className="shrink-0 flex items-center justify-between gap-3 px-3 h-7 border-t text-[10px] text-foreground/55"
      style={{ borderColor: RULE_SOFT }}
    >
      <span className="tabular-nums font-mono truncate">{left}</span>
      <span className="opacity-70 shrink-0">{right ?? 'tradeul.com'}</span>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   DIVISOR ARRASTRABLE
   Mismo patrón que el canvas del agente (AIAgentContent): tirador propio,
   sin librería. El ancho se persiste y el arrastre va en rAF para no
   provocar un layout por cada mousemove.
   ══════════════════════════════════════════════════════════════════════ */

export function useSplitWidth(storageKey: string, initial: number, min: number, max: number) {
  const [width, setWidth] = useState(initial);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const n = Number(raw);
        if (Number.isFinite(n)) setWidth(Math.min(max, Math.max(min, n)));
      }
    } catch { /* almacenamiento no disponible: nos quedamos con el inicial */ }
  }, [storageKey, min, max]);

  const persist = useCallback((w: number) => {
    try { window.localStorage.setItem(storageKey, String(Math.round(w))); } catch { /* idem */ }
  }, [storageKey]);

  return { width, setWidth, persist };
}

export function SplitHandle({
  onDrag, onCommit, ariaLabel,
}: {
  onDrag: (deltaX: number) => void;
  onCommit: () => void;
  ariaLabel: string;
}) {
  const raf = useRef(0);
  const startX = useRef(0);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    startX.current = e.clientX;
    setDragging(true);
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);

    const move = (ev: PointerEvent) => {
      // Un solo recálculo por frame: sin esto el arrastre dispara un layout
      // completo del split en cada evento de puntero.
      if (raf.current) return;
      raf.current = requestAnimationFrame(() => {
        raf.current = 0;
        onDrag(ev.clientX - startX.current);
        startX.current = ev.clientX;
      });
    };
    const up = (ev: PointerEvent) => {
      if (raf.current) { cancelAnimationFrame(raf.current); raf.current = 0; }
      el.releasePointerCapture(ev.pointerId);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      setDragging(false);
      onCommit();
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
  }, [onDrag, onCommit]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={ariaLabel}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') { e.preventDefault(); onDrag(-24); onCommit(); }
        if (e.key === 'ArrowRight') { e.preventDefault(); onDrag(24); onCommit(); }
      }}
      className={cn(
        'shrink-0 w-[5px] cursor-col-resize grid place-items-center touch-none',
        'bg-foreground/[0.05] hover:bg-foreground/[0.09] transition-colors',
        'focus-visible:outline-none focus-visible:bg-foreground/[0.14]',
        dragging && 'bg-foreground/[0.14]',
      )}
    >
      <span className="w-px h-8 rounded-full bg-foreground/25" />
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Ancho del contenedor. Mismo umbral que el canvas del agente (680px):
   por debajo, el segundo panel estorba más de lo que aporta.
   ══════════════════════════════════════════════════════════════════════ */

export function useNarrow(threshold = 680) {
  const ref = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => {
      setNarrow(entry.contentRect.width < threshold);
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);

  return { ref, narrow };
}
