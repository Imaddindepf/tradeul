'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { useUserPreferencesStore, FontFamily, TimezoneOption } from '@/stores/useUserPreferencesStore';
import { TIMEZONE_LABELS } from '@/lib/date-utils';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { useWorkspaceSync } from '@/hooks/useWorkspaceSync';
import { Pin, RotateCcw, Save, Layout, Trash2, Check, Cloud, CloudOff, Globe, Clock, Sun, Moon, Monitor } from 'lucide-react';
import { MAIN_COMMANDS } from '@/lib/commands';
import { AVAILABLE_LANGUAGES, changeLanguage, getCurrentLanguage, type LanguageCode } from '@/lib/i18n';

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

function ColorRow({ label, value, onChange, presets }: { label: string; value: string; onChange: (c: string) => void; presets: string[] }) {
  return (
    <div className="flex items-center gap-1.5 py-0.5">
      <span className="text-[9px] text-muted-fg w-12">{label}</span>
      <div className="flex gap-0.5">
        {presets.map((c) => (
          <button
            key={c}
            onClick={() => onChange(c)}
            className={`w-3.5 h-3.5 rounded-sm border ${value === c ? 'ring-1 ring-primary ring-offset-1 ring-offset-background' : 'border-border'}`}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-4 h-4 rounded cursor-pointer border-0 p-0 ml-auto"
      />
    </div>
  );
}

export function SettingsContent() {
  const { t, i18n } = useTranslation();
  const { togglePin, isPinned } = usePinnedCommands();
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
  const [syncing, setSyncing] = useState(false);
  const [currentLang, setCurrentLang] = useState<LanguageCode>(getCurrentLanguage());

  const [tab, setTab] = useState<'colors' | 'layout' | 'cmds'>('colors');

  const handleLanguageChange = async (lang: LanguageCode) => {
    await changeLanguage(lang);
    setCurrentLang(lang);
  };

  const handleSaveLayout = async () => {
    saveLayout();
    setSaved(true);

    if (isSignedIn) {
      setSyncing(true);
      await forceSync();
      setSyncing(false);
    }

    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="h-full flex flex-col bg-surface text-foreground text-[10px]">
      {/* Tabs */}
      <div className="flex border-b border-border bg-surface-inset">
        <button
          onClick={() => setTab('colors')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'colors' ? 'text-primary border-b border-primary' : 'text-muted-fg'}`}
        >
          {t('settings.tabs.colors')}
        </button>
        <button
          onClick={() => setTab('layout')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'layout' ? 'text-primary border-b border-primary' : 'text-muted-fg'}`}
        >
          {t('settings.tabs.layout')}
        </button>
        <button
          onClick={() => setTab('cmds')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'cmds' ? 'text-primary border-b border-primary' : 'text-muted-fg'}`}
        >
          {t('settings.tabs.commands')}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-1.5">
        {tab === 'colors' && (
          <div className="space-y-1.5">
            {/* Language Selector */}
            <div className="flex items-center gap-1.5 py-1 border-b border-border-subtle pb-2 mb-2">
              <Globe className="w-3 h-3 text-muted-fg" />
              <span className="text-[9px] text-muted-fg w-12">{t('settings.language')}</span>
              <div className="flex gap-1">
                {AVAILABLE_LANGUAGES.map((lang) => (
                  <button
                    key={lang.code}
                    onClick={() => handleLanguageChange(lang.code)}
                    className={`px-2 py-0.5 text-[9px] rounded transition-colors flex items-center gap-1 ${currentLang === lang.code
                        ? 'bg-primary/15 text-primary font-medium'
                        : 'bg-surface-inset text-muted-fg hover:bg-surface-hover'
                      }`}
                  >
                    <span>{lang.flag}</span>
                    <span>{lang.code.toUpperCase()}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Theme Selector */}
            <div className="flex items-center gap-1.5 py-1 border-b border-border-subtle pb-2 mb-2">
              <Sun className="w-3 h-3 text-muted-fg" />
              <span className="text-[9px] text-muted-fg w-12">{t('settings.theme', 'Theme')}</span>
              <div className="flex gap-0.5 bg-surface-inset rounded p-0.5">
                {([
                  { id: 'light' as const, icon: Sun, label: 'Light' },
                  { id: 'dark' as const, icon: Moon, label: 'Dark' },
                  { id: 'system' as const, icon: Monitor, label: 'Auto' },
                ] as const).map(({ id, icon: Icon, label }) => (
                  <button
                    key={id}
                    onClick={() => setColorScheme(id)}
                    className={`flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] rounded transition-colors ${
                      theme.colorScheme === id
                        ? 'bg-primary text-white font-medium shadow-sm'
                        : 'text-muted-fg hover:text-foreground'
                    }`}
                  >
                    <Icon className="w-2.5 h-2.5" />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Timezone Selector */}
            <div className="flex items-center gap-1.5 py-1 border-b border-border-subtle pb-2 mb-2">
              <Clock className="w-3 h-3 text-muted-fg" />
              <span className="text-[9px] text-muted-fg w-12">{t('settings.timezone')}</span>
              <select
                value={theme.timezone || 'America/New_York'}
                onChange={(e) => {
                  const newTz = e.target.value as TimezoneOption;
                  if (newTz !== theme.timezone) {
                    setTimezone(newTz);
                    setTimeout(() => window.location.reload(), 100);
                  }
                }}
                className="flex-1 text-[9px] px-1.5 py-0.5 border border-border rounded bg-[var(--color-input-bg)] text-foreground"
              >
                {(Object.keys(TIMEZONE_LABELS) as TimezoneOption[]).map((tz) => (
                  <option key={tz} value={tz}>
                    {TIMEZONE_LABELS[tz].region} ({TIMEZONE_LABELS[tz].abbrev})
                  </option>
                ))}
              </select>
            </div>

            <ColorRow label={t('settings.colors.tickUp')} value={colors.tickUp} onChange={setTickUpColor} presets={PRESET_COLORS.tickUp} />
            <ColorRow label={t('settings.colors.tickDown')} value={colors.tickDown} onChange={setTickDownColor} presets={PRESET_COLORS.tickDown} />
            <ColorRow label={t('settings.colors.background')} value={colors.background} onChange={setBackgroundColor} presets={PRESET_COLORS.background} />

            {/* Font */}
            <div className="flex items-center gap-1.5 py-0.5 border-t border-border-subtle pt-1.5">
              <span className="text-[9px] text-muted-fg w-12">{t('settings.font')}</span>
              <select
                value={theme.font}
                onChange={(e) => setFont(e.target.value as FontFamily)}
                className="flex-1 text-[9px] px-1 py-0.5 border border-border rounded bg-[var(--color-input-bg)] text-foreground"
                style={{ fontFamily: `var(--font-${theme.font})` }}
              >
                {FONT_OPTIONS.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>

            {/* Preview */}
            <div className="bg-surface-inset rounded px-1.5 py-1 mt-1 border border-border" style={{ fontFamily: `var(--font-${theme.font})` }}>
              <div className="flex justify-between text-[9px] text-foreground">
                <span style={{ color: colors.tickUp }}>+4.2%</span>
                <span>NVDA $142</span>
                <span style={{ color: colors.tickDown }}>-1.8%</span>
              </div>
            </div>

            <button onClick={resetColors} className="flex items-center gap-1 text-[9px] text-muted-fg hover:text-foreground mt-1">
              <RotateCcw className="w-2.5 h-2.5" /> {t('settings.reset')}
            </button>
          </div>
        )}

        {tab === 'layout' && (
          <div className="space-y-2">
            <p className="text-[9px] text-muted-fg">
              {t('settings.saveLayoutDescription')}
            </p>

            <button
              onClick={handleSaveLayout}
              className={`w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded text-[9px] font-medium transition-colors ${saved
                  ? 'bg-success/15 text-success'
                  : 'bg-primary text-white hover:bg-primary-hover'
                }`}
            >
              {saved ? (
                <>
                  <Check className="w-3 h-3" />
                  {t('settings.saved')}
                </>
              ) : (
                <>
                  <Save className="w-3 h-3" />
                  {t('settings.saveLayout')}
                </>
              )}
            </button>

            {hasLayout && (
              <div className="flex items-center justify-between py-1 px-1.5 bg-surface-inset rounded">
                <div className="flex items-center gap-1.5">
                  <Layout className="w-3 h-3 text-muted-fg" />
                  <span className="text-[9px] text-muted-fg">
                    {t('settings.windowsSaved', { count: savedCount })}
                  </span>
                </div>
                <button
                  onClick={clearLayout}
                  className="p-0.5 rounded hover:bg-danger/15 text-muted-fg hover:text-danger transition-colors"
                  title={t('settings.clearLayout')}
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            )}

            <div className="flex items-center gap-1 text-[8px] text-muted-fg mt-2">
              {isSignedIn ? (
                <>
                  <Cloud className="w-2.5 h-2.5 text-success" />
                  <span>{t('settings.synced')}</span>
                </>
              ) : (
                <>
                  <CloudOff className="w-2.5 h-2.5" />
                  <span>{t('settings.localOnly')}</span>
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'cmds' && (
          <div className="flex flex-wrap gap-1">
            {MAIN_COMMANDS.map((cmd) => (
              <button
                key={cmd.id}
                onClick={() => togglePin(cmd.id)}
                className={`px-1.5 py-0.5 rounded text-[9px] font-mono flex items-center gap-1 ${isPinned(cmd.id) ? 'bg-primary/15 text-primary' : 'bg-surface-inset text-muted-fg'}`}
              >
                <Pin className={`w-2.5 h-2.5 ${isPinned(cmd.id) ? 'fill-current' : ''}`} />
                {cmd.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
