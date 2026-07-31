'use client';

/**
 * Settings — rediseño (2026-07)
 *
 * - Navegación lateral por secciones (General / Apariencia / Workspace / Comandos)
 *   en vez de tres pestañas donde "Colors" contenía idioma y zona horaria.
 * - Formulario apilado: etiqueta + descripción + control a ancho completo, una sola
 *   rejilla de alineación en todas las secciones.
 * - UI monocroma: el color queda reservado a los datos (--color-tick-up/down).
 *   Sin banderas ni emojis: idiomas y zonas horarias en texto.
 * - Preview real (mini tabla de cotizaciones) con la fuente y los colores elegidos.
 */

import { useState, useMemo, useRef, useEffect, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { useUserPreferencesStore, FontFamily, TimezoneOption } from '@/stores/useUserPreferencesStore';
import { TIMEZONE_LABELS } from '@/lib/date-utils';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { useWorkspaceSync } from '@/hooks/useWorkspaceSync';
import {
  Pin, RotateCcw, Save, Trash2, Check, Cloud, CloudOff, Globe, Clock,
  Sun, Moon, Monitor, Palette, LayoutGrid, Terminal, Search, Pipette, Type,
} from 'lucide-react';
import { MAIN_COMMANDS } from '@/lib/commands';
import { AVAILABLE_LANGUAGES, changeLanguage, getCurrentLanguage, type LanguageCode } from '@/lib/i18n';

const FG = 'var(--color-fg)';
const BG = 'var(--color-bg)';

const PRESET_COLORS = {
  tickUp: ['#10b981', '#22c55e', '#84cc16', '#14b8a6', '#06b6d4'],
  tickDown: ['#ef4444', '#f43f5e', '#f97316', '#ec4899', '#f59e0b'],
  background: ['#ffffff', '#f8fafc', '#f9fafb', '#18181b', '#0f172a'],
};

const FONT_OPTIONS: { id: FontFamily; name: string }[] = [
  { id: 'jetbrains-mono', name: 'JetBrains' },
  { id: 'fira-code', name: 'Fira Code' },
  { id: 'ibm-plex-mono', name: 'IBM Plex' },
  { id: 'oxygen-mono', name: 'Oxygen' },
];

// Zonas horarias agrupadas por región (el catálogo plano no daba jerarquía)
const TZ_GROUPS: { key: string; zones: TimezoneOption[] }[] = [
  { key: 'americas', zones: ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'] },
  { key: 'europe', zones: ['Europe/London', 'Europe/Madrid', 'Europe/Paris', 'Europe/Berlin'] },
  { key: 'asia', zones: ['Asia/Tokyo', 'Asia/Hong_Kong', 'Asia/Singapore'] },
  { key: 'utc', zones: ['UTC'] },
];

/** El catálogo de zonas trae banderas en `region`; aquí se muestran solo en texto. */
function cityOf(tz: TimezoneOption): string {
  return TIMEZONE_LABELS[tz].region.replace(/[^\x00-\x7F]+/g, '').trim();
}

function tzTime(tz: TimezoneOption): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date());
  } catch {
    return '';
  }
}

/** Texto legible sobre un fondo arbitrario (el preview usa el color del usuario). */
function readableOn(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return FG;
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45 ? '#0f172a' : '#f5f5f7';
}

// ── Primitivas de formulario ────────────────────────────────────────────────

function Section({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="mb-5 last:mb-0">
      {title && <h3 className="text-[9px] font-bold uppercase tracking-[0.11em] text-muted-fg mb-2.5">{title}</h3>}
      <div className="space-y-3.5">{children}</div>
    </section>
  );
}

function Field({ label, hint, children, aside }: { label: string; hint?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <label className="text-[11px] font-semibold text-foreground leading-none">{label}</label>
        {aside}
      </div>
      {hint && <p className="text-[10px] text-muted-fg leading-snug -mt-0.5 mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}

function Seg<T extends string>({ options, value, onChange }: {
  options: { key: T; label: string; icon?: typeof Sun; style?: React.CSSProperties }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex bg-surface-inset border border-border rounded-md p-px gap-px">
      {options.map((o) => {
        const Icon = o.icon;
        return (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            style={o.style}
            className={`flex-1 flex items-center justify-center gap-1 px-2 h-[22px] text-[10.5px] font-semibold rounded-[5px] transition-colors whitespace-nowrap ${
              value === o.key ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground'
            }`}
          >
            {Icon && <Icon className="w-3 h-3" />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

const SELECT_CLASS =
  'w-full h-[26px] text-[10.5px] px-2 rounded-md border border-border bg-[var(--color-input-bg)] text-foreground ' +
  'hover:border-foreground/40 focus:border-foreground outline-none transition-colors cursor-pointer';

function ColorField({ label, value, onChange, presets }: {
  label: string; value: string; onChange: (c: string) => void; presets: string[];
}) {
  return (
    <Field
      label={label}
      aside={<span className="text-[10px] font-mono text-muted-fg tabular-nums uppercase">{value}</span>}
    >
      <div className="flex items-center gap-1.5">
        {presets.map((c) => (
          <button
            key={c}
            onClick={() => onChange(c)}
            title={c}
            className={`w-[22px] h-[22px] rounded-[5px] border transition-transform hover:scale-110 ${
              value.toLowerCase() === c.toLowerCase() ? 'border-transparent' : 'border-border'
            }`}
            style={{
              backgroundColor: c,
              ...(value.toLowerCase() === c.toLowerCase()
                ? { boxShadow: `0 0 0 2px var(--color-surface), 0 0 0 3.5px ${FG}` }
                : {}),
            }}
          />
        ))}
        <label
          className="relative ml-auto w-[22px] h-[22px] rounded-[5px] border border-border grid place-items-center cursor-pointer hover:border-foreground/50 transition-colors"
          style={{ backgroundColor: value }}
          title={value}
        >
          <Pipette className="w-3 h-3 pointer-events-none" style={{ color: readableOn(value) }} />
          <input
            type="color"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer"
          />
        </label>
      </div>
    </Field>
  );
}

// ── Componente ──────────────────────────────────────────────────────────────

type NavKey = 'general' | 'appearance' | 'workspace' | 'commands';

export function SettingsContent() {
  const { t } = useTranslation();
  const { togglePin, isPinned, pinnedCommands } = usePinnedCommands();
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);
  const setTickUpColor = useUserPreferencesStore((state) => state.setTickUpColor);
  const setTickDownColor = useUserPreferencesStore((state) => state.setTickDownColor);
  const setBackgroundColor = useUserPreferencesStore((state) => state.setBackgroundColor);
  const setFont = useUserPreferencesStore((state) => state.setFont);
  const setColorScheme = useUserPreferencesStore((state) => state.setColorScheme);
  const setTimezone = useUserPreferencesStore((state) => state.setTimezone);
  const resetColors = useUserPreferencesStore((state) => state.resetColors);

  const { saveLayout, hasLayout, clearLayout, savedCount } = useLayoutPersistence();
  const { isAuthenticated: isSignedIn, forceSync } = useWorkspaceSync();
  const [saved, setSaved] = useState(false);
  const [currentLang, setCurrentLang] = useState<LanguageCode>(getCurrentLanguage());
  const [nav, setNav] = useState<NavKey>('general');
  const [cmdQuery, setCmdQuery] = useState('');

  // Ventanas restauradas de layouts antiguos pueden ser muy estrechas
  const rootRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setCompact(entry.contentRect.width < 340));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const tz = (theme.timezone || 'America/New_York') as TimezoneOption;

  const handleLanguageChange = async (lang: LanguageCode) => {
    await changeLanguage(lang);
    setCurrentLang(lang);
  };

  const handleSaveLayout = async () => {
    saveLayout();
    setSaved(true);
    if (isSignedIn) await forceSync();
    setTimeout(() => setSaved(false), 2000);
  };

  const NAV: { key: NavKey; label: string; icon: typeof Sun }[] = [
    { key: 'general', label: t('settings.nav.general', 'General'), icon: Globe },
    { key: 'appearance', label: t('settings.nav.appearance', 'Appearance'), icon: Palette },
    { key: 'workspace', label: t('settings.nav.workspace', 'Workspace'), icon: LayoutGrid },
    { key: 'commands', label: t('settings.nav.commands', 'Commands'), icon: Terminal },
  ];

  const { pinnedList, restList } = useMemo(() => {
    const q = cmdQuery.trim().toLowerCase();
    const list = q
      ? MAIN_COMMANDS.filter((c) => c.label.toLowerCase().includes(q) || t(c.description, '').toLowerCase().includes(q))
      : MAIN_COMMANDS;
    return {
      // Fijados primero, en el orden en que el usuario los fijó
      pinnedList: list
        .filter((c) => pinnedCommands.includes(c.id))
        .sort((a, b) => pinnedCommands.indexOf(a.id) - pinnedCommands.indexOf(b.id)),
      restList: list.filter((c) => !pinnedCommands.includes(c.id)),
    };
  }, [cmdQuery, pinnedCommands, t]);

  const previewFg = readableOn(colors.background);

  return (
    <div ref={rootRef} className="h-full flex bg-surface text-foreground">
      {/* Navegación lateral — se colapsa a iconos en ventanas estrechas */}
      <nav
        className={`${compact ? 'w-[34px] px-1' : 'w-[118px] px-1.5'} shrink-0 border-r border-border bg-surface-inset/60 py-2 flex flex-col gap-px`}
      >
        {NAV.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setNav(key)}
            title={compact ? label : undefined}
            className={`flex items-center gap-2 h-[26px] rounded-md text-[10.5px] font-semibold transition-colors ${
              compact ? 'justify-center px-0' : 'px-2 text-left'
            } ${nav === key ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground hover:bg-surface/60'}`}
          >
            <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={nav === key ? 2.25 : 1.75} />
            {!compact && <span className="truncate">{label}</span>}
          </button>
        ))}
      </nav>

      {/* Contenido */}
      <div className={`flex-1 min-w-0 overflow-y-auto py-3.5 ${compact ? 'px-2.5' : 'px-4'}`}>
        {nav === 'general' && (
          <Section>
            <Field label={t('settings.language')} hint={t('settings.languageDescription')}>
              <Seg
                value={currentLang}
                onChange={handleLanguageChange}
                options={AVAILABLE_LANGUAGES.map((l) => ({ key: l.code, label: l.name }))}
              />
            </Field>

            <Field
              label={t('settings.timezone')}
              hint={t('settings.timezoneDescription')}
              aside={
                <span className="flex items-center gap-1 text-[10px] font-mono text-muted-fg tabular-nums">
                  <Clock className="w-2.5 h-2.5" />
                  {tzTime(tz)}
                </span>
              }
            >
              <select
                value={tz}
                onChange={(e) => {
                  const newTz = e.target.value as TimezoneOption;
                  if (newTz !== theme.timezone) {
                    setTimezone(newTz);
                    setTimeout(() => window.location.reload(), 100);
                  }
                }}
                className={SELECT_CLASS}
              >
                {TZ_GROUPS.map((g) => (
                  <optgroup key={g.key} label={t(`settings.tzGroups.${g.key}`, g.key.toUpperCase())}>
                    {g.zones.map((z) => (
                      <option key={z} value={z}>
                        {cityOf(z)} · {TIMEZONE_LABELS[z].abbrev}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <p className="text-[9.5px] text-muted-fg/80 mt-1.5">
                {t('settings.timezoneReloadHint', 'Changing the timezone reloads the terminal.')}
              </p>
            </Field>
          </Section>
        )}

        {nav === 'appearance' && (
          <>
            <Section title={t('settings.sections.interface', 'Interface')}>
              <Field label={t('settings.theme', 'Theme')}>
                <Seg
                  value={theme.colorScheme}
                  onChange={setColorScheme}
                  options={[
                    { key: 'light' as const, label: t('common.themeLight'), icon: Sun },
                    { key: 'dark' as const, label: t('common.themeDark'), icon: Moon },
                    { key: 'system' as const, label: t('common.themeAuto'), icon: Monitor },
                  ]}
                />
              </Field>

              <Field label={t('settings.font')} hint={t('settings.fontHint', 'Applied to tables, quotes and charts.')}>
                <div className="grid grid-cols-2 gap-1 bg-surface-inset border border-border rounded-md p-px">
                  {FONT_OPTIONS.map((f) => (
                    <button
                      key={f.id}
                      onClick={() => setFont(f.id)}
                      style={{ fontFamily: `var(--font-${f.id})` }}
                      className={`h-[24px] text-[10.5px] font-semibold rounded-[5px] transition-colors ${
                        theme.font === f.id ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground'
                      }`}
                    >
                      {f.name}
                    </button>
                  ))}
                </div>
              </Field>
            </Section>

            <Section title={t('settings.dataColors', 'Data colors')}>
              <ColorField label={t('settings.colors.tickUp')} value={colors.tickUp} onChange={setTickUpColor} presets={PRESET_COLORS.tickUp} />
              <ColorField label={t('settings.colors.tickDown')} value={colors.tickDown} onChange={setTickDownColor} presets={PRESET_COLORS.tickDown} />
              <ColorField label={t('settings.colors.background')} value={colors.background} onChange={setBackgroundColor} presets={PRESET_COLORS.background} />

              {/* Preview */}
              <div>
                <div className="text-[9px] font-bold uppercase tracking-[0.11em] text-muted-fg mb-1.5">
                  {t('settings.preview', 'Preview')}
                </div>
                <div
                  className="rounded-md border border-border overflow-hidden"
                  style={{ fontFamily: `var(--font-${theme.font})`, backgroundColor: colors.background, color: previewFg }}
                >
                  <div className="flex items-center px-2 h-[18px] text-[8.5px] font-bold uppercase tracking-wider opacity-45">
                    <span className="flex-1">{t('settings.previewSymbol', 'Symbol')}</span>
                    <span className="w-14 text-right">{t('settings.previewLast', 'Last')}</span>
                    <span className="w-14 text-right">{t('settings.previewChange', 'Chg')}</span>
                  </div>
                  {[
                    { s: 'NVDA', p: '142.38', c: '+4.21%', up: true },
                    { s: 'AAPL', p: '228.11', c: '-1.84%', up: false },
                    { s: 'MSFT', p: '431.07', c: '+0.63%', up: true },
                  ].map((r) => (
                    <div key={r.s} className="flex items-center px-2 h-[19px] text-[10px] tabular-nums">
                      <span className="flex-1 font-semibold">{r.s}</span>
                      <span className="w-14 text-right">{r.p}</span>
                      <span className="w-14 text-right font-semibold" style={{ color: r.up ? colors.tickUp : colors.tickDown }}>
                        {r.c}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <button
                onClick={resetColors}
                className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-fg hover:text-foreground transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                {t('settings.reset')}
              </button>
            </Section>
          </>
        )}

        {nav === 'workspace' && (
          <Section title={t('settings.layout')}>
            <Field label={t('settings.saveLayout')} hint={t('settings.saveLayoutDescription')}>
              <button
                onClick={handleSaveLayout}
                className="w-full flex items-center justify-center gap-1.5 h-[28px] rounded-md text-[10.5px] font-bold transition-opacity hover:opacity-85"
                style={saved ? { border: `1px solid ${FG}`, color: FG } : { background: FG, color: BG }}
              >
                {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                {saved ? t('settings.saved') : t('settings.saveLayout')}
              </button>
            </Field>

            {hasLayout && (
              <div className="flex items-center justify-between gap-2 h-[30px] px-2 rounded-md border border-border bg-surface-inset">
                <span className="text-[10.5px] font-semibold text-foreground">
                  {t('settings.windowsSaved', { count: savedCount })}
                </span>
                <button
                  onClick={clearLayout}
                  className="flex items-center gap-1 text-[10px] font-semibold text-muted-fg hover:text-foreground transition-colors px-1"
                  title={t('settings.clearLayout')}
                >
                  <Trash2 className="w-3 h-3" />
                  {t('settings.clearLayout')}
                </button>
              </div>
            )}

            <div className="flex items-center gap-1.5 text-[10px] text-muted-fg pt-0.5">
              {isSignedIn ? <Cloud className="w-3 h-3" /> : <CloudOff className="w-3 h-3" />}
              <span>{isSignedIn ? t('settings.synced') : t('settings.localOnly')}</span>
            </div>
          </Section>
        )}

        {nav === 'commands' && (
          <div>
            <div className="relative mb-2">
              <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-muted-fg pointer-events-none" />
              <input
                value={cmdQuery}
                onChange={(e) => setCmdQuery(e.target.value)}
                placeholder={t('settings.searchCommands', 'Search commands…')}
                className="w-full h-[26px] pl-7 pr-2 text-[10.5px] rounded-md border border-border bg-[var(--color-input-bg)] text-foreground placeholder:text-muted-fg/60 focus:border-foreground outline-none transition-colors"
              />
            </div>

            <p className="text-[10px] text-muted-fg mb-3">
              {t('settings.pinHint', 'Pinned commands appear in the top bar.')}
            </p>

            {[
              { key: 'pinned', title: t('settings.pinned', 'Pinned'), items: pinnedList, count: `${pinnedCommands.length}` },
              { key: 'all', title: t('settings.allCommands', 'All commands'), items: restList, count: `${MAIN_COMMANDS.length}` },
            ].map((group) =>
              group.items.length === 0 ? null : (
                <div key={group.key} className="mb-4 last:mb-0">
                  <div className="flex items-baseline justify-between gap-2 mb-1.5">
                    <h3 className="text-[9px] font-bold uppercase tracking-[0.11em] text-muted-fg">{group.title}</h3>
                    <span className="text-[9.5px] font-mono text-muted-fg/70 tabular-nums">{group.count}</span>
                  </div>
                  <div className="-mx-1">
                    {group.items.map((cmd) => {
                      const pinned = isPinned(cmd.id);
                      return (
                        <button
                          key={cmd.id}
                          onClick={() => togglePin(cmd.id)}
                          className="w-full flex items-center gap-2 px-1 h-[26px] rounded-md hover:bg-surface-inset transition-colors text-left group"
                        >
                          <Pin
                            className={`w-3 h-3 shrink-0 transition-opacity ${
                              pinned ? 'fill-current text-foreground' : 'text-muted-fg opacity-30 group-hover:opacity-80'
                            }`}
                          />
                          <span className={`w-[52px] shrink-0 text-[10px] font-mono font-bold ${pinned ? 'text-foreground' : 'text-muted-fg'}`}>
                            {cmd.label}
                          </span>
                          <span className="flex-1 min-w-0 truncate text-[10px] text-muted-fg">{t(cmd.description, '')}</span>
                          {cmd.shortcut && (
                            <span className="shrink-0 text-[9px] font-mono text-muted-fg/70 border border-border rounded px-1 py-px">
                              {cmd.shortcut}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )
            )}

            {pinnedList.length === 0 && restList.length === 0 && (
              <p className="text-[10px] text-muted-fg px-1 py-3">{t('settings.noResults', 'No commands found.')}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
