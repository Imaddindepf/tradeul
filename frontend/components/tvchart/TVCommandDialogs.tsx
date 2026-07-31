'use client';

/**
 * TVCommandDialogs — diálogos ÚNICOS por ventana del multichart TVC, réplica
 * del flujo de tradingview.com: la búsqueda de símbolo y el cambio de
 * intervalo salen UNA sola vez, centrados en la ventana (no en la celda), y
 * aplican su acción a la celda ENFOCADA.
 *
 * ¿Por qué no los diálogos nativos de la CL? Cada celda es un iframe y sus
 * diálogos no pueden salirse de él: salían centrados y clipados en la celda.
 * En tradingview.com hay un solo motor por documento; aquí lo replicamos con
 * UI propia (mismo look) sobre la API imperativa de la celda activa.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { API_URL } from './TVChartCell';
import {
    EXTRA_STUDY_ALIASES,
    normalizeSearchText,
    STUDY_NAME_ES,
} from './tvStudyTranslations';

// ---------------------------------------------------------------------------
// Texto bilingüe: los diálogos siguen el idioma de la app (react-i18next).
// ---------------------------------------------------------------------------

interface Bi {
    en: string;
    es: string;
}
const bi = (en: string, es: string): Bi => ({ en, es });

function useTVLang(): keyof Bi {
    const { i18n } = useTranslation();
    return i18n.language?.toLowerCase().startsWith('es') ? 'es' : 'en';
}

// ---------------------------------------------------------------------------
// Búsqueda de símbolos
// ---------------------------------------------------------------------------

interface SymbolRow {
    symbol: string;
    name?: string;
    exchange?: string;
    asset_type?: string;
}

export function TVSymbolSearchDialog({
    seed,
    onClose,
    onPick,
}: {
    seed: string;
    onClose: () => void;
    onPick: (symbol: string) => void;
}) {
    const [q, setQ] = useState(seed);
    const [results, setResults] = useState<SymbolRow[]>([]);
    const [sel, setSel] = useState(0);
    const abortRef = useRef<AbortController | null>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const lang = useTVLang();
    const L = (b: Bi) => b[lang];

    // Debounce + abort: una petición viva como mucho.
    useEffect(() => {
        const query = q.trim();
        if (!query) {
            setResults([]);
            return;
        }
        const t = setTimeout(() => {
            abortRef.current?.abort();
            const ac = new AbortController();
            abortRef.current = ac;
            fetch(`${API_URL}/api/v1/metadata/search?q=${encodeURIComponent(query)}&limit=30`, {
                signal: ac.signal,
            })
                .then((r) => (r.ok ? r.json() : null))
                .then((json) => {
                    if (ac.signal.aborted) return;
                    const rows = Array.isArray(json?.results) ? (json.results as SymbolRow[]) : [];
                    setResults(rows);
                    setSel(0);
                })
                .catch(() => { /* abortada u offline */ });
        }, 250);
        return () => clearTimeout(t);
    }, [q]);

    // Mantener la fila seleccionada a la vista al navegar con flechas.
    useEffect(() => {
        listRef.current
            ?.querySelector(`[data-row="${sel}"]`)
            ?.scrollIntoView({ block: 'nearest' });
    }, [sel]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSel((s) => Math.min(s + 1, results.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSel((s) => Math.max(s - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const row = results[sel] ?? results[0];
            if (row) onPick(row.symbol);
            else if (q.trim()) onPick(q.trim().toUpperCase());
        }
        e.stopPropagation();
    };

    return (
        <div
            className="absolute inset-0 z-50 flex items-start justify-center bg-black/30"
            style={{ paddingTop: '9%' }}
            onMouseDown={onClose}
        >
            <div
                className="flex max-h-[70%] w-[520px] max-w-[92%] flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
                onMouseDown={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-4 pb-1 pt-3">
                    <span className="text-[15px] font-semibold text-foreground">
                        {L(bi('Symbol Search', 'Búsqueda de símbolos'))}
                    </span>
                    <button
                        className="rounded p-1 text-foreground/60 hover:bg-surface-hover hover:text-foreground"
                        onClick={onClose}
                        aria-label={L(bi('Close', 'Cerrar'))}
                    >
                        ✕
                    </button>
                </div>
                <div className="px-4 py-2">
                    <input
                        autoFocus
                        value={q}
                        onChange={(e) => setQ(e.target.value.toUpperCase())}
                        onKeyDown={handleKeyDown}
                        placeholder={L(bi('Symbol or name', 'Símbolo o nombre'))}
                        spellCheck={false}
                        className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-[14px] text-foreground outline-none focus:border-primary"
                    />
                </div>
                <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto pb-2">
                    {results.map((row, i) => (
                        <button
                            key={`${row.symbol}-${i}`}
                            data-row={i}
                            className={`flex w-full items-center gap-3 px-4 py-1.5 text-left ${
                                i === sel ? 'bg-surface-hover' : ''
                            }`}
                            onMouseEnter={() => setSel(i)}
                            onClick={() => onPick(row.symbol)}
                        >
                            <span className="w-24 shrink-0 text-[13px] font-semibold text-foreground">
                                {row.symbol}
                            </span>
                            <span className="min-w-0 flex-1 truncate text-[12px] text-foreground/60">
                                {row.name ?? ''}
                            </span>
                            <span className="shrink-0 text-[11px] uppercase text-foreground/40">
                                {row.asset_type === 'etf' ? 'fund' : 'stock'}
                                {row.exchange ? ` · ${row.exchange}` : ''}
                            </span>
                        </button>
                    ))}
                    {q.trim() && results.length === 0 && (
                        <div className="px-4 py-3 text-[12px] text-foreground/50">
                            {L(bi('No results', 'Sin resultados'))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Indicadores
// ---------------------------------------------------------------------------

/**
 * Diálogo ÚNICO de indicadores de la ventana (flujo TV): lista los estudios
 * disponibles de la celda enfocada (nativos + custom de Tradeul vía
 * custom_indicators_getter), filtro por texto, Enter/click añade al chart
 * enfocado y el diálogo QUEDA ABIERTO (como en tradingview.com, para añadir
 * varios seguidos). ESC / X / fondo lo cierran.
 */
export function TVIndicatorsDialog({
    studies,
    onClose,
    onAdd,
}: {
    studies: string[];
    onClose: () => void;
    onAdd: (name: string) => void;
}) {
    const [q, setQ] = useState('');
    const [sel, setSel] = useState(0);
    const [lastAdded, setLastAdded] = useState<string | null>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const lang = useTVLang();
    const L = (b: Bi) => b[lang];
    const isSpanish = lang === 'es';

    // Búsqueda BILINGÜE y sin acentos: cada estudio matchea por su nombre EN
    // (getStudiesList), su traducción oficial ES (bundles de la CL) y los
    // alias extra ("media movil" y "moving average" encuentran ambos lo
    // mismo, esté la app en el idioma que esté). El nombre que se muestra
    // sigue el idioma de la app; a createStudy siempre viaja el nombre EN.
    const searchTextOf = (s: string): string =>
        normalizeSearchText(
            [s, STUDY_NAME_ES[s], ...(EXTRA_STUDY_ALIASES[s] ?? [])]
                .filter(Boolean)
                .join('\n'),
        );
    const displayNameOf = (s: string): string =>
        (isSpanish ? STUDY_NAME_ES[s] : undefined) ?? s;

    const query = normalizeSearchText(q.trim());
    const filtered = !query
        ? [...studies].sort((a, b) => displayNameOf(a).localeCompare(displayNameOf(b)))
        : studies
              .filter((s) => searchTextOf(s).includes(query))
              .sort((a, b) => {
                  const pa = searchTextOf(a)
                      .split('\n')
                      .some((t) => t.startsWith(query)) ? 0 : 1;
                  const pb = searchTextOf(b)
                      .split('\n')
                      .some((t) => t.startsWith(query)) ? 0 : 1;
                  return pa - pb || displayNameOf(a).localeCompare(displayNameOf(b));
              });

    useEffect(() => {
        setSel(0);
    }, [query]);
    useEffect(() => {
        listRef.current
            ?.querySelector(`[data-row="${sel}"]`)
            ?.scrollIntoView({ block: 'nearest' });
    }, [sel]);

    const add = (name: string) => {
        onAdd(name); // SIEMPRE el nombre EN: es la clave de createStudy.
        setLastAdded(displayNameOf(name));
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSel((s) => Math.min(s + 1, filtered.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSel((s) => Math.max(s - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const row = filtered[sel] ?? filtered[0];
            if (row) add(row);
        }
        e.stopPropagation();
    };

    return (
        <div
            className="absolute inset-0 z-50 flex items-start justify-center bg-black/30"
            style={{ paddingTop: '7%' }}
            onMouseDown={onClose}
        >
            <div
                className="flex max-h-[76%] w-[480px] max-w-[92%] flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
                onMouseDown={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-4 pb-1 pt-3">
                    <span className="text-[15px] font-semibold text-foreground">{L(bi('Indicators', 'Indicadores'))}</span>
                    <div className="flex items-center gap-3">
                        {lastAdded && (
                            <span className="max-w-[220px] truncate text-[11px] text-foreground/50">
                                ✓ {lastAdded}
                            </span>
                        )}
                        <button
                            className="rounded p-1 text-foreground/60 hover:bg-surface-hover hover:text-foreground"
                            onClick={onClose}
                            aria-label={L(bi('Close', 'Cerrar'))}
                        >
                            ✕
                        </button>
                    </div>
                </div>
                <div className="px-4 py-2">
                    <input
                        autoFocus
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={L(bi('Search indicator', 'Buscar indicador'))}
                        spellCheck={false}
                        className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-[14px] text-foreground outline-none focus:border-primary"
                    />
                </div>
                <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto pb-2">
                    {filtered.map((name, i) => (
                        <button
                            key={name}
                            data-row={i}
                            className={`flex w-full items-center px-4 py-1.5 text-left text-[13px] text-foreground ${
                                i === sel ? 'bg-surface-hover' : ''
                            }`}
                            onMouseEnter={() => setSel(i)}
                            onClick={() => add(name)}
                        >
                            {displayNameOf(name)}
                        </button>
                    ))}
                    {filtered.length === 0 && (
                        <div className="px-4 py-3 text-[12px] text-foreground/50">{L(bi('No results', 'Sin resultados'))}</div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Cambiar intervalo
// ---------------------------------------------------------------------------

/**
 * Sintaxis TV: número solo = minutos; sufijo H/D/W/M = horas/días/semanas/
 * meses. La CL compone resoluciones arbitrarias a partir de los multipliers
 * declarados por el datafeed, así que "4" (4 min) o "2D" funcionan aunque el
 * backend solo sirva 1/2/5/15/30 min y 1D.
 */
const INTERVAL_UNITS: Record<string, { one: Bi; many: Bi }> = {
    min: { one: bi('1 minute', '1 minuto'), many: bi('minutes', 'minutos') },
    h: { one: bi('1 hour', '1 hora'), many: bi('hours', 'horas') },
    d: { one: bi('1 day', '1 día'), many: bi('days', 'días') },
    w: { one: bi('1 week', '1 semana'), many: bi('weeks', 'semanas') },
    m: { one: bi('1 month', '1 mes'), many: bi('months', 'meses') },
};

export function parseIntervalInput(
    raw: string,
    lang: keyof Bi = 'es',
): { resolution: string; label: string } | null {
    const m = /^(\d{1,4})\s*([hdwm]?)$/i.exec(raw.trim());
    if (!m) return null;
    const n = parseInt(m[1], 10);
    if (!n) return null;
    const unit = m[2].toLowerCase();
    const labelFor = (key: string) => {
        const u = INTERVAL_UNITS[key];
        return n === 1 ? u.one[lang] : `${n} ${u.many[lang]}`;
    };
    if (!unit) {
        return n <= 1440 ? { resolution: `${n}`, label: labelFor('min') } : null;
    }
    if (unit === 'h') {
        return n <= 24 ? { resolution: `${n * 60}`, label: labelFor('h') } : null;
    }
    if (unit === 'd') {
        return n <= 31 ? { resolution: `${n}D`, label: labelFor('d') } : null;
    }
    if (unit === 'w') {
        return n <= 52 ? { resolution: `${n}W`, label: labelFor('w') } : null;
    }
    return n <= 12 ? { resolution: `${n}M`, label: labelFor('m') } : null;
}

export function TVIntervalDialog({
    seed,
    onClose,
    onApply,
}: {
    seed: string;
    onClose: () => void;
    onApply: (resolution: string) => void;
}) {
    const [buf, setBuf] = useState(seed);
    const lang = useTVLang();
    const L = (b: Bi) => b[lang];
    const parsed = parseIntervalInput(buf, lang);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (parsed) onApply(parsed.resolution);
        }
        e.stopPropagation();
    };

    return (
        <div
            className="absolute inset-0 z-50 flex items-start justify-center"
            style={{ paddingTop: '14%' }}
            onMouseDown={onClose}
        >
            <div
                className="w-[290px] rounded-lg border border-border bg-surface px-5 pb-5 pt-4 text-center shadow-2xl"
                onMouseDown={(e) => e.stopPropagation()}
            >
                <div className="mb-3 text-[15px] font-semibold text-foreground">
                    {L(bi('Change Interval', 'Cambiar intervalo'))}
                </div>
                <input
                    autoFocus
                    value={buf.toUpperCase()}
                    onChange={(e) =>
                        setBuf(e.target.value.replace(/[^0-9a-zA-Z]/g, '').slice(0, 6))
                    }
                    onKeyDown={handleKeyDown}
                    spellCheck={false}
                    className={`w-full rounded-md border bg-transparent px-3 py-2 text-center text-[18px] font-medium text-foreground outline-none ${
                        buf && !parsed ? 'border-red-500/70' : 'border-primary'
                    }`}
                />
                <div className="mt-2 text-[12px] text-foreground/50">
                    {parsed
                        ? parsed.label
                        : buf
                          ? L(bi('Not a valid interval', 'Intervalo no válido'))
                          : L(bi('Type an interval', 'Escribe un intervalo'))}
                </div>
            </div>
        </div>
    );
}
