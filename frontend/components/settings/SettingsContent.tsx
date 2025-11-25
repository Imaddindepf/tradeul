'use client';

import { useState } from 'react';
import { usePinnedCommands } from '@/hooks/usePinnedCommands';
import { useUserPreferencesStore, FontFamily } from '@/stores/useUserPreferencesStore';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { Pin, RotateCcw, Save, Layout, Trash2, Check } from 'lucide-react';

const AVAILABLE_COMMANDS = [
  { id: 'sc', label: 'SC' },
  { id: 'dt', label: 'DT' },
  { id: 'sec', label: 'SEC' },
  { id: 'settings', label: 'SET' },
];

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
      <span className="text-[9px] text-slate-500 w-12">{label}</span>
      <div className="flex gap-0.5">
        {presets.map((c) => (
          <button
            key={c}
            onClick={() => onChange(c)}
            className={`w-3.5 h-3.5 rounded-sm border ${value === c ? 'ring-1 ring-blue-500 ring-offset-1' : 'border-slate-200'}`}
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
  const { togglePin, isPinned } = usePinnedCommands();
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);
  const setTickUpColor = useUserPreferencesStore((state) => state.setTickUpColor);
  const setTickDownColor = useUserPreferencesStore((state) => state.setTickDownColor);
  const setBackgroundColor = useUserPreferencesStore((state) => state.setBackgroundColor);
  const setFont = useUserPreferencesStore((state) => state.setFont);
  const resetColors = useUserPreferencesStore((state) => state.resetColors);
  
  const { saveLayout, hasLayout, clearLayout, savedCount } = useLayoutPersistence();
  const [saved, setSaved] = useState(false);

  const [tab, setTab] = useState<'colors' | 'layout' | 'cmds'>('colors');

  const handleSaveLayout = () => {
    const count = saveLayout();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="h-full flex flex-col bg-white text-slate-900 text-[10px]">
      {/* Tabs */}
      <div className="flex border-b border-slate-200 bg-slate-50">
        <button
          onClick={() => setTab('colors')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'colors' ? 'text-blue-600 border-b border-blue-600' : 'text-slate-400'}`}
        >
          Colors
        </button>
        <button
          onClick={() => setTab('layout')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'layout' ? 'text-blue-600 border-b border-blue-600' : 'text-slate-400'}`}
        >
          Layout
        </button>
        <button
          onClick={() => setTab('cmds')}
          className={`flex-1 py-1 text-[9px] font-medium uppercase tracking-wide ${tab === 'cmds' ? 'text-blue-600 border-b border-blue-600' : 'text-slate-400'}`}
        >
          Cmds
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-1.5">
        {tab === 'colors' && (
          <div className="space-y-1.5">
            <ColorRow label="Up" value={colors.tickUp} onChange={setTickUpColor} presets={PRESET_COLORS.tickUp} />
            <ColorRow label="Down" value={colors.tickDown} onChange={setTickDownColor} presets={PRESET_COLORS.tickDown} />
            <ColorRow label="BG" value={colors.background} onChange={setBackgroundColor} presets={PRESET_COLORS.background} />

            {/* Font */}
            <div className="flex items-center gap-1.5 py-0.5 border-t border-slate-100 pt-1.5">
              <span className="text-[9px] text-slate-500 w-12">Font</span>
              <select
                value={theme.font}
                onChange={(e) => setFont(e.target.value as FontFamily)}
                className="flex-1 text-[9px] px-1 py-0.5 border border-slate-200 rounded bg-white"
                style={{ fontFamily: `var(--font-${theme.font})` }}
              >
                {FONT_OPTIONS.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>

            {/* Preview */}
            <div className="bg-slate-900 rounded px-1.5 py-1 mt-1" style={{ fontFamily: `var(--font-${theme.font})` }}>
              <div className="flex justify-between text-[9px] text-white">
                <span style={{ color: colors.tickUp }}>+4.2%</span>
                <span>NVDA $142</span>
                <span style={{ color: colors.tickDown }}>-1.8%</span>
              </div>
            </div>

            <button onClick={resetColors} className="flex items-center gap-1 text-[9px] text-slate-400 hover:text-slate-600 mt-1">
              <RotateCcw className="w-2.5 h-2.5" /> Reset
            </button>
          </div>
        )}

        {tab === 'layout' && (
          <div className="space-y-2">
            <p className="text-[9px] text-slate-500">
              Guarda la posición de tus ventanas para restaurarlas después.
            </p>
            
            {/* Save Layout */}
            <button
              onClick={handleSaveLayout}
              className={`w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded text-[9px] font-medium transition-colors ${
                saved 
                  ? 'bg-green-100 text-green-700' 
                  : 'bg-blue-500 text-white hover:bg-blue-600'
              }`}
            >
              {saved ? (
                <>
                  <Check className="w-3 h-3" />
                  Guardado
                </>
              ) : (
                <>
                  <Save className="w-3 h-3" />
                  Guardar Layout
                </>
              )}
            </button>

            {/* Status */}
            {hasLayout && (
              <div className="flex items-center justify-between py-1 px-1.5 bg-slate-50 rounded">
                <div className="flex items-center gap-1.5">
                  <Layout className="w-3 h-3 text-slate-400" />
                  <span className="text-[9px] text-slate-600">
                    {savedCount} ventana{savedCount !== 1 ? 's' : ''} guardada{savedCount !== 1 ? 's' : ''}
                  </span>
                </div>
                <button
                  onClick={clearLayout}
                  className="p-0.5 rounded hover:bg-red-100 text-slate-400 hover:text-red-600 transition-colors"
                  title="Borrar layout guardado"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            )}

            <p className="text-[8px] text-slate-400 mt-2">
              El layout se restaurará automáticamente al abrir el workspace.
            </p>
          </div>
        )}

        {tab === 'cmds' && (
          <div className="flex flex-wrap gap-1">
            {AVAILABLE_COMMANDS.map((cmd) => (
              <button
                key={cmd.id}
                onClick={() => togglePin(cmd.id)}
                className={`px-1.5 py-0.5 rounded text-[9px] font-mono flex items-center gap-1 ${isPinned(cmd.id) ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-500'}`}
              >
                <Pin className={`w-2.5 h-2.5 ${isPinned(cmd.id) ? 'fill-blue-500' : ''}`} />
                {cmd.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
