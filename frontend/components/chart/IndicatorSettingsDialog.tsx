'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import {
    INDICATOR_CONFIGS,
    INDICATOR_TYPE_DEFAULTS,
    VISIBILITY_TIMEFRAMES,
    getIndicatorSettings,
    saveIndicatorSettings,
    getInstanceLabel,
    type IndicatorConfig,
    type IndicatorInstance,
} from './constants';

// ============================================================================
// Types
// ============================================================================

interface IndicatorSettingsDialogProps {
    indicatorId: string;
    instanceData?: IndicatorInstance;
    onClose: () => void;
    onApply: (indicatorId: string, settings: { inputs: Record<string, number | string>; styles: Record<string, string | number>; visibility: string[] }) => void;
    position?: { x: number; y: number };
}

type Tab = 'inputs' | 'style' | 'visibility';

// ============================================================================
// Helper: Color input with hex conversion (for rgba defaults)
// ============================================================================

function rgbaToHex(rgba: string): string {
    if (rgba.startsWith('#')) return rgba.slice(0, 7);
    const match = rgba.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!match) return '#000000';
    const r = parseInt(match[1]).toString(16).padStart(2, '0');
    const g = parseInt(match[2]).toString(16).padStart(2, '0');
    const b = parseInt(match[3]).toString(16).padStart(2, '0');
    return `#${r}${g}${b}`;
}

// ============================================================================
// IndicatorSettingsDialog
// ============================================================================

export function IndicatorSettingsDialog({ indicatorId, instanceData, onClose, onApply, position }: IndicatorSettingsDialogProps) {
    // For dynamic instances, use INDICATOR_TYPE_DEFAULTS; for legacy, use INDICATOR_CONFIGS
    const config = instanceData
        ? INDICATOR_TYPE_DEFAULTS[instanceData.type]
        : INDICATOR_CONFIGS[indicatorId];
    const dialogRef = useRef<HTMLDivElement>(null);

    // Load saved settings or defaults
    const [inputs, setInputs] = useState<Record<string, number | string>>(() => {
        if (instanceData) {
            // Use instance params directly, falling back to type defaults
            const result: Record<string, number | string> = {};
            if (config) {
                for (const inp of config.inputs) {
                    result[inp.key] = instanceData.params[inp.key] ?? inp.default;
                }
            }
            return result;
        }
        const all = getIndicatorSettings();
        const saved = all[indicatorId];
        const result: Record<string, number | string> = {};
        if (config) {
            for (const inp of config.inputs) {
                result[inp.key] = saved?.inputs?.[inp.key] ?? inp.default;
            }
        }
        return result;
    });

    const [styles, setStyles] = useState<Record<string, string | number>>(() => {
        if (instanceData) {
            const result: Record<string, string | number> = {};
            if (config) {
                for (const sty of config.styles) {
                    result[sty.key] = instanceData.styles[sty.key] ?? sty.default;
                }
            }
            return result;
        }
        const all = getIndicatorSettings();
        const saved = all[indicatorId];
        const result: Record<string, string | number> = {};
        if (config) {
            for (const sty of config.styles) {
                result[sty.key] = saved?.styles?.[sty.key] ?? sty.default;
            }
        }
        return result;
    });

    const [visibility, setVisibility] = useState<string[]>(() => {
        const all = getIndicatorSettings();
        const saved = all[indicatorId];
        return saved?.visibility ?? [...VISIBILITY_TIMEFRAMES];
    });

    const [activeTab, setActiveTab] = useState<Tab>(config?.inputs.length ? 'inputs' : 'style');

    // Close on Escape
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    // Close on click outside
    useEffect(() => {
        const onClick = (e: MouseEvent) => {
            if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
                onClose();
            }
        };
        // Delay to avoid immediate close from the double-click that opened this
        const timer = setTimeout(() => document.addEventListener('mousedown', onClick), 100);
        return () => { clearTimeout(timer); document.removeEventListener('mousedown', onClick); };
    }, [onClose]);

    if (!config) return null;

    const handleInputChange = (key: string, value: number | string) => {
        setInputs(prev => ({ ...prev, [key]: value }));
    };

    const handleStyleChange = (key: string, value: string | number) => {
        setStyles(prev => ({ ...prev, [key]: value }));
    };

    const handleVisibilityToggle = (tf: string) => {
        setVisibility(prev =>
            prev.includes(tf) ? prev.filter(v => v !== tf) : [...prev, tf]
        );
    };

    const handleAllTimeframes = () => {
        if (visibility.length === VISIBILITY_TIMEFRAMES.length) {
            setVisibility([]);
        } else {
            setVisibility([...VISIBILITY_TIMEFRAMES]);
        }
    };

    const handleReset = () => {
        if (!config) return;
        const defaults = instanceData ? INDICATOR_TYPE_DEFAULTS[instanceData.type] : config;
        const newInputs: Record<string, number | string> = {};
        for (const inp of defaults.inputs) newInputs[inp.key] = inp.default;
        setInputs(newInputs);

        const newStyles: Record<string, string | number> = {};
        for (const sty of defaults.styles) newStyles[sty.key] = sty.default;
        setStyles(newStyles);

        setVisibility([...VISIBILITY_TIMEFRAMES]);
    };

    const handleOk = () => {
        const all = getIndicatorSettings();
        all[indicatorId] = { inputs, styles, visibility };
        saveIndicatorSettings(all);
        onApply(indicatorId, { inputs, styles, visibility });
        onClose();
    };

    const tabs: { id: Tab; label: string; show: boolean }[] = [
        { id: 'inputs', label: 'Inputs', show: config.inputs.length > 0 },
        { id: 'style', label: 'Style', show: config.styles.length > 0 },
        { id: 'visibility', label: 'Visibility', show: true },
    ];

    return (
        <div
            ref={dialogRef}
            className="fixed z-[9999] bg-white border border-slate-200 rounded-lg shadow-2xl"
            style={{
                top: position?.y ?? '50%',
                left: position?.x ?? '50%',
                transform: position ? undefined : 'translate(-50%, -50%)',
                width: 320,
                maxHeight: 440,
            }}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50 rounded-t-lg">
                <span className="text-[12px] font-semibold text-slate-700">{instanceData ? getInstanceLabel(instanceData) : config.name}</span>
                <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                    <X className="w-3.5 h-3.5" />
                </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-slate-200">
                {tabs.filter(t => t.show).map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex-1 px-3 py-1.5 text-[11px] font-medium transition-colors ${
                            activeTab === tab.id
                                ? 'text-blue-600 border-b-2 border-blue-600 -mb-px'
                                : 'text-slate-500 hover:text-slate-700'
                        }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div className="p-3 overflow-y-auto" style={{ maxHeight: 300 }}>
                {/* Inputs Tab */}
                {activeTab === 'inputs' && (
                    <div className="space-y-3">
                        {config.inputs.map(inp => (
                            <div key={inp.key} className="flex items-center justify-between gap-3">
                                <label className="text-[11px] text-slate-600 font-medium min-w-[80px]">{inp.label}</label>
                                {inp.type === 'number' ? (
                                    <input
                                        type="number"
                                        value={inputs[inp.key] as number}
                                        onChange={e => handleInputChange(inp.key, parseFloat(e.target.value) || inp.default as number)}
                                        min={inp.min}
                                        max={inp.max}
                                        step={inp.step || 1}
                                        className="w-20 px-2 py-1 text-[11px] border border-slate-300 rounded text-right font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20"
                                    />
                                ) : (
                                    <select
                                        value={inputs[inp.key] as string}
                                        onChange={e => handleInputChange(inp.key, e.target.value)}
                                        className="w-24 px-2 py-1 text-[11px] border border-slate-300 rounded focus:outline-none focus:border-blue-500"
                                    >
                                        {inp.options?.map(opt => (
                                            <option key={opt} value={opt}>{opt}</option>
                                        ))}
                                    </select>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Style Tab */}
                {activeTab === 'style' && (
                    <div className="space-y-3">
                        {config.styles.map(sty => (
                            <div key={sty.key} className="flex items-center justify-between gap-3">
                                <label className="text-[11px] text-slate-600 font-medium min-w-[80px]">{sty.label}</label>
                                {sty.type === 'color' ? (
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="color"
                                            value={rgbaToHex(String(styles[sty.key]))}
                                            onChange={e => handleStyleChange(sty.key, e.target.value)}
                                            className="w-7 h-7 rounded border border-slate-300 cursor-pointer p-0"
                                            style={{ WebkitAppearance: 'none' }}
                                        />
                                        <span className="text-[10px] font-mono text-slate-400 w-16">{rgbaToHex(String(styles[sty.key]))}</span>
                                    </div>
                                ) : (
                                    <input
                                        type="number"
                                        value={styles[sty.key] as number}
                                        onChange={e => handleStyleChange(sty.key, parseInt(e.target.value) || sty.default as number)}
                                        min={sty.min}
                                        max={sty.max}
                                        className="w-16 px-2 py-1 text-[11px] border border-slate-300 rounded text-right font-mono focus:outline-none focus:border-blue-500"
                                    />
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Visibility Tab */}
                {activeTab === 'visibility' && (
                    <div className="space-y-2">
                        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                            <span className="text-[11px] text-slate-600 font-medium">All Timeframes</span>
                            <button
                                onClick={handleAllTimeframes}
                                className={`w-8 h-4 rounded-full transition-colors relative ${
                                    visibility.length === VISIBILITY_TIMEFRAMES.length ? 'bg-blue-600' : 'bg-slate-300'
                                }`}
                            >
                                <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                                    visibility.length === VISIBILITY_TIMEFRAMES.length ? 'translate-x-4' : 'translate-x-0.5'
                                }`} />
                            </button>
                        </div>
                        {VISIBILITY_TIMEFRAMES.map(tf => (
                            <label key={tf} className="flex items-center justify-between cursor-pointer py-0.5">
                                <span className="text-[11px] text-slate-600">{tf}</span>
                                <input
                                    type="checkbox"
                                    checked={visibility.includes(tf)}
                                    onChange={() => handleVisibilityToggle(tf)}
                                    className="w-3.5 h-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500/20 cursor-pointer"
                                />
                            </label>
                        ))}
                    </div>
                )}
            </div>

            {/* Footer Buttons */}
            <div className="flex items-center justify-between px-3 py-2 border-t border-slate-200 bg-slate-50/50 rounded-b-lg">
                <button
                    onClick={handleReset}
                    className="text-[10px] text-slate-500 hover:text-slate-700 transition-colors font-medium"
                >
                    Reset to Defaults
                </button>
                <div className="flex items-center gap-2">
                    <button
                        onClick={onClose}
                        className="px-3 py-1 text-[11px] text-slate-600 hover:bg-slate-100 rounded transition-colors font-medium"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleOk}
                        className="px-3 py-1 text-[11px] bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors font-medium"
                    >
                        OK
                    </button>
                </div>
            </div>
        </div>
    );
}
