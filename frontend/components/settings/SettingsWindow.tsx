/**
 * Settings Window - Panel de Configuración Flotante
 * 
 * Estilo Godel Terminal:
 * - Colors: Tick Up, Tick Down, Background, Primary
 * - Theme: Font selection (4 opciones)
 * - Layout: Save/Restore window positions
 */

'use client';

import { useState } from 'react';
import { X, RotateCcw, Download, Upload, Save } from 'lucide-react';
import { 
  useUserPreferencesStore, 
  type FontFamily,
  type ColorPreferences 
} from '@/stores/useUserPreferencesStore';

interface SettingsWindowProps {
  onClose: () => void;
  onSaveLayout?: () => void;
}

// ============================================================================
// COLOR PICKER COMPONENT
// ============================================================================

interface ColorPickerProps {
  label: string;
  value: string;
  onChange: (color: string) => void;
}

function ColorPicker({ label, value, onChange }: ColorPickerProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-12 h-8 rounded cursor-pointer border-0 bg-transparent"
          style={{ 
            WebkitAppearance: 'none',
            padding: 0,
          }}
        />
        <div 
          className="absolute inset-0 rounded pointer-events-none border border-slate-300"
          style={{ backgroundColor: value }}
        />
      </div>
      <span className="text-sm text-slate-700 font-medium">{label}</span>
    </div>
  );
}

// ============================================================================
// FONT SELECTOR COMPONENT
// ============================================================================

interface FontSelectorProps {
  value: FontFamily;
  onChange: (font: FontFamily) => void;
}

const FONTS: { value: FontFamily; label: string; preview: string }[] = [
  { value: 'oxygen-mono', label: 'Oxygen Mono', preview: 'var(--font-oxygen-mono)' },
  { value: 'ibm-plex-mono', label: 'IBM Plex Mono', preview: 'var(--font-ibm-plex-mono)' },
  { value: 'jetbrains-mono', label: 'JetBrains Mono', preview: 'var(--font-jetbrains-mono)' },
  { value: 'fira-code', label: 'Fira Code', preview: 'var(--font-fira-code)' },
];

function FontSelector({ value, onChange }: FontSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedFont = FONTS.find(f => f.value === value);

  return (
    <div className="relative">
      <label className="block text-xs text-slate-500 mb-1">Font</label>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-left text-sm font-medium text-slate-700 hover:border-slate-400 transition-colors flex items-center justify-between"
      >
        <span style={{ fontFamily: selectedFont?.preview }}>{selectedFont?.label}</span>
        <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 py-1">
            {FONTS.map((font) => (
              <button
                key={font.value}
                onClick={() => {
                  onChange(font.value);
                  setIsOpen(false);
                }}
                className={`w-full px-3 py-2 text-left text-sm hover:bg-slate-50 flex items-center gap-2 ${
                  value === font.value ? 'text-blue-600 bg-blue-50' : 'text-slate-700'
                }`}
                style={{ fontFamily: font.preview }}
              >
                {value === font.value && (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
                {!value && <span className="w-4" />}
                {font.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function SettingsWindow({ onClose, onSaveLayout }: SettingsWindowProps) {
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);
  
  const setTickUpColor = useUserPreferencesStore((state) => state.setTickUpColor);
  const setTickDownColor = useUserPreferencesStore((state) => state.setTickDownColor);
  const setBackgroundColor = useUserPreferencesStore((state) => state.setBackgroundColor);
  const setPrimaryColor = useUserPreferencesStore((state) => state.setPrimaryColor);
  const resetColors = useUserPreferencesStore((state) => state.resetColors);
  const setFont = useUserPreferencesStore((state) => state.setFont);
  const exportPreferences = useUserPreferencesStore((state) => state.exportPreferences);
  const importPreferences = useUserPreferencesStore((state) => state.importPreferences);
  const resetAll = useUserPreferencesStore((state) => state.resetAll);

  const handleExport = () => {
    const data = exportPreferences();
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'tradeul-preferences.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const content = e.target?.result as string;
          if (importPreferences(content)) {
            alert('Preferences imported successfully!');
          } else {
            alert('Failed to import preferences. Invalid file format.');
          }
        };
        reader.readAsText(file);
      }
    };
    input.click();
  };

  return (
    <div className="bg-white rounded-xl shadow-2xl border border-slate-200 w-[380px] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
        <h2 className="text-base font-semibold text-slate-800">Settings</h2>
        <button
          onClick={onClose}
          className="p-1 hover:bg-slate-200 rounded transition-colors"
        >
          <X className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-6 max-h-[500px] overflow-y-auto">
        {/* Colors Section */}
        <section>
          <h3 className="text-sm font-semibold text-slate-800 mb-3 pb-2 border-b border-slate-100">
            Colors
          </h3>
          <div className="space-y-3">
            <ColorPicker
              label="Positive Color (Tick Up)"
              value={colors.tickUp}
              onChange={setTickUpColor}
            />
            <ColorPicker
              label="Negative Color (Tick Down)"
              value={colors.tickDown}
              onChange={setTickDownColor}
            />
            <ColorPicker
              label="Primary Color"
              value={colors.primary}
              onChange={setPrimaryColor}
            />
            <ColorPicker
              label="Background Color"
              value={colors.background}
              onChange={setBackgroundColor}
            />
            <button
              onClick={resetColors}
              className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700 transition-colors mt-2"
            >
              <RotateCcw className="w-3 h-3" />
              Reset to Default
            </button>
          </div>
        </section>

        {/* Theme Section */}
        <section>
          <h3 className="text-sm font-semibold text-slate-800 mb-3 pb-2 border-b border-slate-100">
            Theme
          </h3>
          <div className="space-y-3">
            <FontSelector value={theme.font} onChange={setFont} />
          </div>
        </section>

        {/* Layout Section */}
        {onSaveLayout && (
          <section>
            <h3 className="text-sm font-semibold text-slate-800 mb-3 pb-2 border-b border-slate-100">
              Layout
            </h3>
            <button
              onClick={onSaveLayout}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
            >
              <Save className="w-4 h-4" />
              Save Current Layout
            </button>
            <p className="text-xs text-slate-500 mt-2">
              Saves the position and size of all open windows.
            </p>
          </section>
        )}

        {/* Import/Export Section */}
        <section>
          <h3 className="text-sm font-semibold text-slate-800 mb-3 pb-2 border-b border-slate-100">
            Backup & Restore
          </h3>
          <div className="flex gap-2">
            <button
              onClick={handleExport}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 border border-slate-300 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <Download className="w-4 h-4" />
              Export
            </button>
            <button
              onClick={handleImport}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 border border-slate-300 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <Upload className="w-4 h-4" />
              Import
            </button>
          </div>
        </section>

        {/* Reset All */}
        <section className="pt-2 border-t border-slate-100">
          <button
            onClick={() => {
              if (confirm('Reset all preferences to default? This cannot be undone.')) {
                resetAll();
              }
            }}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            Reset All to Default
          </button>
        </section>
      </div>
    </div>
  );
}

export default SettingsWindow;

