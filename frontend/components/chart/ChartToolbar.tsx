'use client';

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import type { DrawingTool } from './primitives/types';

// ============================================================================
// SVG Icon Base
// ============================================================================

const I = ({ children, className = '', size = 18 }: { children: React.ReactNode; className?: string; size?: number }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);

// ============================================================================
// Icons — TradingView full set (28x28 viewBox for precision)
// ============================================================================

// --- Cursors ---
export const CrosshairIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M14 4v20M4 14h20" strokeWidth="1.2" /><circle cx="14" cy="14" r="3.5" strokeWidth="1.3" /></I>
);
export const CursorIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M7 5l4 16 3-7 7-3L7 5z" strokeWidth="1.4" /><path d="M14 14l6 6" strokeWidth="1.4" /></I>
);
export const DotIcon = ({ className }: { className?: string }) => (
  <I className={className}><circle cx="14" cy="14" r="2.5" fill="currentColor" stroke="none" /><circle cx="14" cy="14" r="6" strokeWidth="1.2" /></I>
);

// --- Lines ---
export const TrendlineIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M6 22L22 6" /><circle cx="6" cy="22" r="1.8" fill="currentColor" stroke="none" /><circle cx="22" cy="6" r="1.8" fill="currentColor" stroke="none" /></I>
);
export const HLineIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M4 14h20" strokeWidth="1.8" /><circle cx="7" cy="14" r="1.8" fill="currentColor" stroke="none" /></I>
);
const VLineIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M14 4v20" strokeWidth="1.8" /><circle cx="14" cy="7" r="1.8" fill="currentColor" stroke="none" /></I>
);
const RayIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M6 20L22 8" /><circle cx="6" cy="20" r="1.8" fill="currentColor" stroke="none" /><path d="M20 8.5l2.5-.5-.5 2.5" fill="currentColor" stroke="none" /></I>
);
const ExtendedLineIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M3 21L25 7" strokeDasharray="2 1.5" /><circle cx="10" cy="16" r="1.8" fill="currentColor" stroke="none" /><circle cx="18" cy="11" r="1.8" fill="currentColor" stroke="none" /></I>
);
const ParallelChannelIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M4 19l18-8" /><path d="M4 11l18-8" opacity="0.5" /><circle cx="4" cy="19" r="1.5" fill="currentColor" stroke="none" /><circle cx="22" cy="11" r="1.5" fill="currentColor" stroke="none" /></I>
);

// --- Pitchfork / Gann ---
const PitchforkIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M14 4v20" strokeWidth="1" /><path d="M6 22L14 4L22 22" strokeWidth="1.2" /><path d="M10 13L18 13" strokeWidth="1" opacity="0.5" /></I>
);
const GannIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M4 24L24 4" strokeWidth="1.2" /><path d="M4 24L24 14" strokeWidth="0.8" opacity="0.5" /><path d="M4 24L14 4" strokeWidth="0.8" opacity="0.5" /></I>
);

// --- Fibonacci ---
export const FibIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M5 5h18" strokeWidth="1.5" /><path d="M5 10.5h18" strokeWidth="0.8" strokeDasharray="3 2" /><path d="M5 14h18" strokeWidth="0.8" strokeDasharray="3 2" /><path d="M5 17.5h18" strokeWidth="0.8" strokeDasharray="3 2" /><path d="M5 23h18" strokeWidth="1.5" /></I>
);
const FibExtIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M5 23h18" strokeWidth="1.2" /><path d="M5 17h18" strokeWidth="0.8" strokeDasharray="3 2" /><path d="M5 11h18" strokeWidth="0.8" strokeDasharray="3 2" /><path d="M5 5h18" strokeWidth="1.2" /><path d="M7 23L21 5" strokeWidth="0.8" /></I>
);
const FibFanIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M5 23L23 5" strokeWidth="1.2" /><path d="M5 23L23 11" strokeWidth="0.8" opacity="0.6" /><path d="M5 23L23 17" strokeWidth="0.8" opacity="0.4" /></I>
);

// --- Shapes ---
export const RectIcon = ({ className }: { className?: string }) => (
  <I className={className}><rect x="5" y="7" width="18" height="14" rx="0.8" /></I>
);
const CircleIcon = ({ className }: { className?: string }) => (
  <I className={className}><circle cx="14" cy="14" r="9" /></I>
);
const TriangleIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M14 5L24 23H4z" /></I>
);

// --- Text / Annotations ---
const TextIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M7 7h14M14 7v16" strokeWidth="2" /><path d="M10 23h8" strokeWidth="1.5" /></I>
);
const NoteIcon = ({ className }: { className?: string }) => (
  <I className={className}><rect x="5" y="5" width="18" height="18" rx="2" /><path d="M9 10h10M9 14h7" strokeWidth="1.2" /></I>
);
const PriceLabelIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M4 14h16l4-4v8l-4-4" fill="currentColor" opacity="0.15" stroke="currentColor" strokeWidth="1.2" /><path d="M8 14h8" strokeWidth="1" /></I>
);

// --- Brush / Freehand ---
const BrushIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M20 4l-8 8-2 6 6-2 8-8-4-4z" /><path d="M15 9l4 4" /><path d="M10 18c-3 3-6 3-6 3s0-3 3-6" strokeWidth="1.2" /></I>
);

// --- Measurement ---
const MeasureIcon = ({ className }: { className?: string }) => (
  <I className={className}><rect x="5" y="5" width="18" height="18" rx="1" strokeDasharray="3 2" /><path d="M5 14h18" strokeWidth="1" /><path d="M14 5v18" strokeWidth="1" /><path d="M9 12l5-5 5 5" strokeWidth="1" fill="none" /></I>
);
const RulerIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M6 22L22 6" strokeWidth="1.5" /><path d="M9 19l2-2M12 16l2-2M15 13l2-2M18 10l2-2" strokeWidth="1.2" /></I>
);

// --- Zoom ---
const ZoomInIcon = ({ className }: { className?: string }) => (
  <I className={className}><circle cx="12" cy="12" r="7" /><path d="M17.5 17.5L24 24" strokeWidth="2" /><path d="M9 12h6M12 9v6" /></I>
);
const ZoomOutIcon = ({ className }: { className?: string }) => (
  <I className={className}><circle cx="12" cy="12" r="7" /><path d="M17.5 17.5L24 24" strokeWidth="2" /><path d="M9 12h6" /></I>
);

// --- Magnet ---
const MagnetIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M8 4v10a6 6 0 0012 0V4" strokeWidth="1.5" /><path d="M8 4h3v4H8zM17 4h3v4h-3z" fill="currentColor" opacity="0.3" stroke="currentColor" strokeWidth="1" /></I>
);

// --- Utility ---
const LockIcon = ({ className }: { className?: string }) => (
  <I className={className}><rect x="8" y="13" width="12" height="10" rx="1.5" /><path d="M10 13V9a4 4 0 018 0v4" /></I>
);
const UnlockIcon = ({ className }: { className?: string }) => (
  <I className={className}><rect x="8" y="13" width="12" height="10" rx="1.5" /><path d="M18 13V9a4 4 0 00-8 0" /></I>
);
const EyeIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M2 14s4-8 12-8 12 8 12 8-4 8-12 8-12-8-12-8z" /><circle cx="14" cy="14" r="3.5" /></I>
);
const EyeOffIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M4 4l20 20" strokeWidth="1.8" /><path d="M11.5 11.5a3.5 3.5 0 004.9 4.9" /><path d="M7 8c-2.5 2-5 6-5 6s4 8 12 8c1.5 0 3-.3 4.2-.9" /><path d="M21 20c2.5-2 5-6 5-6s-4-8-12-8c-.8 0-1.5.1-2.2.2" /></I>
);
const TrashIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M6 7h16M10 7V5.5a1.5 1.5 0 011.5-1.5h5a1.5 1.5 0 011.5 1.5V7" /><path d="M8 7v14a2 2 0 002 2h8a2 2 0 002-2V7" /><path d="M12 11v7M16 11v7" strokeWidth="1.2" /></I>
);
const StarIcon = ({ className }: { className?: string }) => (
  <I className={className}><path d="M14 4l3.1 6.3 7 1-5 4.9 1.2 6.9L14 19.8l-6.3 3.3 1.2-6.9-5-4.9 7-1L14 4z" /></I>
);
const SettingsIcon = ({ className }: { className?: string }) => (
  <I className={className}><circle cx="14" cy="14" r="3" /><path d="M14 3v3M14 22v3M3 14h3M22 14h3M6.1 6.1l2.1 2.1M19.8 19.8l2.1 2.1M6.1 21.9l2.1-2.1M19.8 8.2l2.1-2.1" strokeWidth="1.3" /></I>
);

// --- Indicators (TradingView-style: 3 candles / oscillator bars) ---
export const IndicatorsIcon = ({ className }: { className?: string }) => (
  <I className={className}>
    <path d="M7 8v12M14 6v16M21 10v8" strokeWidth="2.2" strokeLinecap="round" />
    <path d="M7 11v4M14 9v5M21 12v3" strokeWidth="3.5" strokeLinecap="round" opacity="0.3" />
  </I>
);

// ============================================================================
// Tool Category Structure
// ============================================================================

interface ToolDef {
  id: DrawingTool | string;
  label: string;
  shortcut?: string;
  icon: React.FC<{ className?: string }>;
  enabled: boolean; // false = visually present but disabled (future)
}

interface ToolCategory {
  id: string;
  tools: ToolDef[];
}

const SIDEBAR_CATEGORIES: ToolCategory[] = [
  // Group 1: Cursors
  {
    id: 'cursor',
    tools: [
      { id: 'none', label: 'Cursor', shortcut: 'Esc', icon: CursorIcon, enabled: true },
      { id: 'crosshair_mode', label: 'Crosshair', icon: CrosshairIcon, enabled: false },
      { id: 'dot_mode', label: 'Dot', icon: DotIcon, enabled: false },
    ],
  },
  // Group 2: Lines
  {
    id: 'lines',
    tools: [
      { id: 'trendline', label: 'Trend Line', shortcut: 'T', icon: TrendlineIcon, enabled: true },
      { id: 'horizontal_line', label: 'Horizontal Line', shortcut: 'H', icon: HLineIcon, enabled: true },
      { id: 'vertical_line', label: 'Vertical Line', shortcut: 'V', icon: VLineIcon, enabled: true },
      { id: 'ray', label: 'Ray', shortcut: 'Y', icon: RayIcon, enabled: true },
      { id: 'extended_line', label: 'Extended Line', shortcut: 'E', icon: ExtendedLineIcon, enabled: true },
      { id: 'parallel_channel', label: 'Parallel Channel', icon: ParallelChannelIcon, enabled: true },
    ],
  },
  // Group 3: Pitchfork / Gann
  {
    id: 'pitchfork',
    tools: [
      { id: 'pitchfork', label: 'Pitchfork', icon: PitchforkIcon, enabled: false },
      { id: 'gann', label: 'Gann Fan', icon: GannIcon, enabled: false },
    ],
  },
  // Group 4: Fibonacci
  {
    id: 'fibonacci',
    tools: [
      { id: 'fibonacci', label: 'Fib Retracement', shortcut: 'F', icon: FibIcon, enabled: true },
      { id: 'fib_extension', label: 'Fib Extension', icon: FibExtIcon, enabled: false },
      { id: 'fib_fan', label: 'Fib Fan', icon: FibFanIcon, enabled: false },
    ],
  },
  // Group 5: Text & Annotations
  {
    id: 'text',
    tools: [
      { id: 'text', label: 'Text', icon: TextIcon, enabled: false },
      { id: 'note', label: 'Note', icon: NoteIcon, enabled: false },
      { id: 'price_label', label: 'Price Label', icon: PriceLabelIcon, enabled: false },
    ],
  },
  // Group 6: Shapes
  {
    id: 'shapes',
    tools: [
      { id: 'rectangle', label: 'Rectangle', shortcut: 'R', icon: RectIcon, enabled: true },
      { id: 'circle', label: 'Circle', shortcut: 'C', icon: CircleIcon, enabled: true },
      { id: 'triangle', label: 'Triangle', icon: TriangleIcon, enabled: true },
    ],
  },
  // Group 7: Brush
  {
    id: 'brush',
    tools: [
      { id: 'brush', label: 'Brush', icon: BrushIcon, enabled: false },
    ],
  },
  // Group 8: Measurement
  {
    id: 'measure',
    tools: [
      { id: 'measure', label: 'Measure', shortcut: 'M', icon: MeasureIcon, enabled: true },
      { id: 'ruler', label: 'Ruler', icon: RulerIcon, enabled: false },
    ],
  },
  // Group 9: Zoom
  {
    id: 'zoom',
    tools: [
      { id: '_zoomin', label: 'Zoom In', icon: ZoomInIcon, enabled: true },
      { id: '_zoomout', label: 'Zoom Out', icon: ZoomOutIcon, enabled: true },
    ],
  },
  // Group 10: Magnet
  {
    id: 'magnet',
    tools: [
      { id: 'magnet', label: 'Magnet Mode', icon: MagnetIcon, enabled: false },
    ],
  },
];

// Top header tools — compact quick-access
const HEADER_TOOLS: ToolDef[] = [
  { id: 'none', label: 'Cursor', shortcut: 'Esc', icon: CursorIcon, enabled: true },
  { id: 'crosshair_mode', label: 'Crosshair', icon: CrosshairIcon, enabled: false },
  { id: 'trendline', label: 'Trend Line', shortcut: 'T', icon: TrendlineIcon, enabled: true },
  { id: 'horizontal_line', label: 'Horizontal Line', shortcut: 'H', icon: HLineIcon, enabled: true },
  { id: 'vertical_line', label: 'Vertical Line', shortcut: 'V', icon: VLineIcon, enabled: true },
  { id: 'ray', label: 'Ray', shortcut: 'Y', icon: RayIcon, enabled: true },
  { id: 'fibonacci', label: 'Fib Retracement', shortcut: 'F', icon: FibIcon, enabled: true },
  { id: 'rectangle', label: 'Rectangle', shortcut: 'R', icon: RectIcon, enabled: true },
  { id: 'circle', label: 'Circle', shortcut: 'C', icon: CircleIcon, enabled: true },
  { id: 'measure', label: 'Measure', shortcut: 'M', icon: MeasureIcon, enabled: true },
  { id: 'brush', label: 'Brush', icon: BrushIcon, enabled: false },
  { id: 'magnet', label: 'Magnet', icon: MagnetIcon, enabled: false },
];

// ============================================================================
// Helpers
// ============================================================================

function findCategoryForTool(toolId: string): string | null {
  for (const cat of SIDEBAR_CATEGORIES) {
    if (cat.tools.some(t => t.id === toolId)) return cat.id;
  }
  return null;
}

const ENABLED_TOOLS = new Set<string>([
  'none', 'trendline', 'horizontal_line', 'vertical_line', 'ray', 'extended_line',
  'parallel_channel', 'fibonacci', 'rectangle', 'circle', 'triangle', 'measure',
]);

// ============================================================================
// ChartToolbar — Left Sidebar
// ============================================================================

type MagnetMode = 'off' | 'weak' | 'strong';

interface ChartToolbarProps {
  activeTool: DrawingTool;
  setActiveTool: (tool: DrawingTool) => void;
  drawingCount: number;
  clearAllDrawings: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  drawingsVisible: boolean;
  toggleDrawingsVisibility: () => void;
  magnetMode: MagnetMode;
  onCycleMagnet: () => void;
}

function ChartToolbarComponent({
  activeTool,
  setActiveTool,
  drawingCount,
  clearAllDrawings,
  zoomIn,
  zoomOut,
  drawingsVisible,
  toggleDrawingsVisibility,
  magnetMode,
  onCycleMagnet,
}: ChartToolbarProps) {
  const [openFlyout, setOpenFlyout] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const flyoutRef = useRef<HTMLDivElement>(null);

  // Last-selected tool per category
  const [lastTool, setLastTool] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('chart-toolbar-last') || '{}'); } catch { return {}; }
  });

  // Close flyout on click outside / Escape
  useEffect(() => {
    if (!openFlyout) return;
    const onClickOut = (e: MouseEvent) => {
      if (flyoutRef.current && !flyoutRef.current.contains(e.target as Node)) setOpenFlyout(null);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenFlyout(null); };
    document.addEventListener('mousedown', onClickOut);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onClickOut); document.removeEventListener('keydown', onKey); };
  }, [openFlyout]);

  const selectTool = useCallback((catId: string, toolId: string) => {
    if (!ENABLED_TOOLS.has(toolId)) return; // disabled tools do nothing
    setActiveTool((toolId === activeTool ? 'none' : toolId) as DrawingTool);
    setOpenFlyout(null);
    setLastTool(prev => {
      const next = { ...prev, [catId]: toolId };
      try { localStorage.setItem('chart-toolbar-last', JSON.stringify(next)); } catch { /* */ }
      return next;
    });
  }, [activeTool, setActiveTool]);

  const handleCatClick = useCallback((cat: ToolCategory) => {
    // Zoom is special — direct action
    if (cat.id === 'zoom') return;

    const enabledTools = cat.tools.filter(t => t.enabled);
    if (enabledTools.length <= 1 && cat.tools.length <= 1) {
      // Single tool category — direct toggle
      const tool = cat.tools[0];
      if (!tool.enabled) return;
      selectTool(cat.id, tool.id);
    } else {
      // Multi-tool category — toggle flyout
      setOpenFlyout(prev => prev === cat.id ? null : cat.id);
    }
  }, [selectTool]);

  const activeCatId = findCategoryForTool(activeTool);

  // Button style helper
  const btnBase = 'w-[32px] h-[32px] flex items-center justify-center rounded-[4px] transition-all duration-100 relative';
  const btnIdle = 'text-slate-500 hover:text-slate-800 hover:bg-slate-100';
  const btnActive = 'text-blue-600 bg-blue-50/80';
  const btnDisabled = 'text-slate-300 cursor-default';

  return (
    <div className="w-[38px] flex-shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col items-center pt-1.5 pb-1 select-none z-10">

      {SIDEBAR_CATEGORIES.map((cat, idx) => {
        const isActive = activeCatId === cat.id;
        const displayToolId = lastTool[cat.id] || cat.tools[0].id;
        const displayTool = cat.tools.find(t => t.id === displayToolId) || cat.tools[0];
        const DisplayIcon = displayTool.icon;
        const hasMultiple = cat.tools.length > 1;
        const isZoom = cat.id === 'zoom';

        return (
          <div key={cat.id}>
            {/* Separator */}
            {idx > 0 && idx !== 9 && (
              <div className="w-5 h-px bg-slate-150 mx-auto my-[3px]" style={{ backgroundColor: '#cbd5e1' }} />
            )}

            {cat.id === 'magnet' ? (
              <button
                onClick={onCycleMagnet}
                className={`${btnBase} ${magnetMode !== 'off' ? 'text-blue-600 bg-blue-50/80' : btnIdle}`}
                title={`Magnet: ${magnetMode === 'off' ? 'Off' : magnetMode === 'weak' ? 'Weak' : 'Strong'} (Ctrl to toggle temporarily)`}
              >
                <MagnetIcon className="w-[18px] h-[18px]" />
                {magnetMode !== 'off' && <div className="absolute left-0 top-[6px] bottom-[6px] w-[2px] rounded-r bg-blue-600" />}
                {magnetMode === 'strong' && <div className="absolute right-[3px] top-[3px] w-[5px] h-[5px] rounded-full bg-blue-600" />}
              </button>
            ) : isZoom ? (
              <div className="flex flex-col items-center">
                <button onClick={zoomIn} className={`${btnBase} ${btnIdle}`} title="Zoom In">
                  <ZoomInIcon className="w-[18px] h-[18px]" />
                </button>
                <button onClick={zoomOut} className={`${btnBase} ${btnIdle}`} title="Zoom Out">
                  <ZoomOutIcon className="w-[18px] h-[18px]" />
                </button>
              </div>
            ) : (
              <div className="relative" ref={openFlyout === cat.id ? flyoutRef : undefined}>
                <button
                  onClick={() => handleCatClick(cat)}
                  className={`${btnBase} ${isActive ? btnActive : !displayTool.enabled ? btnDisabled : btnIdle}`}
                  title={displayTool.label + (displayTool.shortcut ? ` (${displayTool.shortcut})` : '')}
                >
                  <DisplayIcon className="w-[18px] h-[18px]" />
                  {/* Active accent bar */}
                  {isActive && <div className="absolute left-0 top-[6px] bottom-[6px] w-[2px] rounded-r bg-blue-600" />}
                  {/* Multi-tool triangle indicator */}
                  {hasMultiple && (
                    <svg className="absolute right-[2px] bottom-[2px]" width="5" height="5" viewBox="0 0 5 5">
                      <path d="M0.5 1.5L4 4.5H0.5z" fill={isActive ? '#2563eb' : '#c0c5ce'} />
                    </svg>
                  )}
                </button>

                {/* Flyout */}
                {openFlyout === cat.id && (
                  <div className="absolute left-full top-0 ml-0.5 bg-white border border-slate-200 rounded-md shadow-lg py-1 min-w-[180px] z-50">
                    {cat.tools.map(tool => {
                      const ToolIcon = tool.icon;
                      const isToolActive = activeTool === tool.id;
                      return (
                        <button
                          key={tool.id}
                          onClick={() => tool.enabled && selectTool(cat.id, tool.id)}
                          className={`w-full flex items-center gap-2.5 px-3 py-[6px] text-[12px] transition-colors ${
                            !tool.enabled
                              ? 'text-slate-300 cursor-default'
                              : isToolActive
                                ? 'text-blue-600 bg-blue-50'
                                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-800'
                          }`}
                        >
                          <ToolIcon className={`w-4 h-4 flex-shrink-0 ${!tool.enabled ? 'opacity-40' : ''}`} />
                          <span className="flex-1 text-left">{tool.label}</span>
                          {tool.shortcut && <span className="text-[10px] text-slate-400 font-mono">{tool.shortcut}</span>}
                          {!tool.enabled && <span className="text-[9px] text-slate-300 italic">soon</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Bottom utilities */}
      <div className="flex flex-col items-center">
        <div className="w-5 h-px mx-auto my-[3px]" style={{ backgroundColor: '#cbd5e1' }} />

        {/* Lock */}
        <button
          onClick={() => setLocked(!locked)}
          className={`${btnBase} ${locked ? 'text-blue-600 bg-blue-50/80' : btnIdle}`}
          title={locked ? 'Unlock drawings' : 'Lock drawings'}
        >
          {locked ? <LockIcon className="w-[18px] h-[18px]" /> : <UnlockIcon className="w-[18px] h-[18px]" />}
        </button>

        {/* Visibility */}
        <button
          onClick={toggleDrawingsVisibility}
          className={`${btnBase} ${!drawingsVisible ? 'text-slate-300' : btnIdle}`}
          title={drawingsVisible ? 'Hide drawings' : 'Show drawings'}
        >
          {drawingsVisible ? <EyeIcon className="w-[18px] h-[18px]" /> : <EyeOffIcon className="w-[18px] h-[18px]" />}
        </button>

        {/* Trash */}
        {drawingCount > 0 && (
          <button
            onClick={clearAllDrawings}
            className={`${btnBase} text-slate-400 hover:text-red-500 hover:bg-red-50`}
            title={`Clear all (${drawingCount})`}
          >
            <TrashIcon className="w-[18px] h-[18px]" />
          </button>
        )}

        <div className="w-5 h-px mx-auto my-[3px]" style={{ backgroundColor: '#cbd5e1' }} />

        {/* Favorites */}
        <button className={`${btnBase} ${btnDisabled}`} title="Favorites (coming soon)">
          <StarIcon className="w-[18px] h-[18px]" />
        </button>

        {/* Settings */}
        <button className={`${btnBase} ${btnDisabled}`} title="Chart settings (coming soon)">
          <SettingsIcon className="w-[18px] h-[18px]" />
        </button>
      </div>
    </div>
  );
}

export const ChartToolbar = memo(ChartToolbarComponent);

// ============================================================================
// HeaderDrawingTools — inline tools for the top header bar
// ============================================================================

interface HeaderDrawingToolsProps {
  activeTool: DrawingTool;
  setActiveTool: (tool: DrawingTool) => void;
}

function HeaderDrawingToolsComponent({ activeTool, setActiveTool }: HeaderDrawingToolsProps) {
  return (
    <div className="flex items-center gap-px">
      {HEADER_TOOLS.map(({ id, icon: ToolIcon, label, shortcut, enabled }) => {
        const isActive = activeTool === id;
        return (
          <button
            key={id}
            onClick={() => {
              if (!enabled) return;
              setActiveTool((id === activeTool && id !== 'none' ? 'none' : id) as DrawingTool);
            }}
            className={`w-[22px] h-[22px] flex items-center justify-center rounded-[3px] transition-colors ${
              !enabled
                ? 'text-slate-300 cursor-default'
                : isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
            }`}
            title={`${label}${shortcut ? ` (${shortcut})` : ''}${!enabled ? ' — coming soon' : ''}`}
          >
            <ToolIcon className="w-[13px] h-[13px]" />
          </button>
        );
      })}
    </div>
  );
}

export const HeaderDrawingTools = memo(HeaderDrawingToolsComponent);
