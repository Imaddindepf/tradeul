/**
 * Chart icons — single source of truth for SVG iconography inside the chart UI.
 *
 * All icons use a 24x24 viewBox and `currentColor` so they inherit text color.
 * Pass `className` to size or recolor.
 */

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { className?: string };

function Base({ children, className, ...rest }: IconProps & { children: React.ReactNode }) {
    return (
        <svg
            className={className}
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            {...rest}
        >
            {children}
        </svg>
    );
}

// ── Cursors ─────────────────────────────────────────────────────────────────
export const CursorIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M6 4l3.5 14 2.5-6 6-2.5L6 4z" strokeWidth="1.4" />
        <path d="M12 12l5 5" strokeWidth="1.4" />
    </Base>
);
export const CrosshairIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M12 3v18M3 12h18" strokeWidth="1.2" />
        <circle cx="12" cy="12" r="3" strokeWidth="1.3" />
    </Base>
);
export const DotIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
        <circle cx="12" cy="12" r="5" strokeWidth="1.2" />
    </Base>
);

// ── Lines ────────────────────────────────────────────────────────────────────
export const TrendlineIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M5 19L19 5" />
        <circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none" />
        <circle cx="19" cy="5" r="1.6" fill="currentColor" stroke="none" />
    </Base>
);
export const HLineIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 12h18" strokeWidth="1.8" />
        <circle cx="6" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </Base>
);
export const VLineIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M12 3v18" strokeWidth="1.8" />
        <circle cx="12" cy="6" r="1.6" fill="currentColor" stroke="none" />
    </Base>
);
export const RayIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M5 17L19 7" />
        <circle cx="5" cy="17" r="1.6" fill="currentColor" stroke="none" />
        <path d="M17 7.4l2.1-.4-.4 2.1" fill="currentColor" stroke="none" />
    </Base>
);
export const ExtendedLineIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 18L21 6" strokeDasharray="2 1.5" />
        <circle cx="9" cy="14" r="1.6" fill="currentColor" stroke="none" />
        <circle cx="15" cy="10" r="1.6" fill="currentColor" stroke="none" />
    </Base>
);
export const ParallelChannelIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 16l18-8" />
        <path d="M3 10l18-8" opacity="0.5" />
        <circle cx="3" cy="16" r="1.4" fill="currentColor" stroke="none" />
        <circle cx="21" cy="8" r="1.4" fill="currentColor" stroke="none" />
    </Base>
);

// ── Pitchfork / Gann ────────────────────────────────────────────────────────
export const PitchforkIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M12 4v16" strokeWidth="1" />
        <path d="M5 18L12 4l7 14" strokeWidth="1.2" />
        <path d="M9 12h6" strokeWidth="1" opacity="0.5" />
    </Base>
);
export const GannIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 20L20 4" strokeWidth="1.2" />
        <path d="M4 20L20 12" strokeWidth="0.8" opacity="0.5" />
        <path d="M4 20L12 4" strokeWidth="0.8" opacity="0.5" />
    </Base>
);

// ── Fibonacci ───────────────────────────────────────────────────────────────
export const FibIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 4h16" strokeWidth="1.5" />
        <path d="M4 9h16" strokeWidth="0.8" strokeDasharray="3 2" />
        <path d="M4 12h16" strokeWidth="0.8" strokeDasharray="3 2" />
        <path d="M4 15h16" strokeWidth="0.8" strokeDasharray="3 2" />
        <path d="M4 20h16" strokeWidth="1.5" />
    </Base>
);
export const FibExtIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 20h16" strokeWidth="1.2" />
        <path d="M4 15h16" strokeWidth="0.8" strokeDasharray="3 2" />
        <path d="M4 9h16" strokeWidth="0.8" strokeDasharray="3 2" />
        <path d="M4 4h16" strokeWidth="1.2" />
        <path d="M6 20L18 4" strokeWidth="0.8" />
    </Base>
);
export const FibFanIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 20L20 4" strokeWidth="1.2" />
        <path d="M4 20L20 10" strokeWidth="0.8" opacity="0.6" />
        <path d="M4 20L20 15" strokeWidth="0.8" opacity="0.4" />
    </Base>
);

// ── Shapes ──────────────────────────────────────────────────────────────────
export const RectIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="4" y="6" width="16" height="12" rx="0.8" />
    </Base>
);
export const CircleIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="8" />
    </Base>
);
export const TriangleIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M12 4L21 20H3z" />
    </Base>
);

// ── Text / Annotations ──────────────────────────────────────────────────────
export const TextIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M6 6h12M12 6v14" strokeWidth="2" />
        <path d="M9 20h6" strokeWidth="1.5" />
    </Base>
);
export const NoteIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M8 9h8M8 13h6" strokeWidth="1.2" />
    </Base>
);
export const PriceLabelIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 12h14l4-3.5v7L17 12" fill="currentColor" fillOpacity="0.15" strokeWidth="1.2" />
        <path d="M7 12h8" strokeWidth="1" />
    </Base>
);

// ── Brush / Freehand ────────────────────────────────────────────────────────
export const BrushIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M17 3l-7 7-1.5 5 5-1.5 7-7-3.5-3.5z" />
        <path d="M13 7l3 3" />
        <path d="M9 15c-2.4 2.4-5 2.4-5 2.4s0-2.6 2.4-5" strokeWidth="1.2" />
    </Base>
);

// ── Measurement ─────────────────────────────────────────────────────────────
export const MeasureIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="4" y="4" width="16" height="16" rx="1" strokeDasharray="3 2" />
        <path d="M4 12h16" strokeWidth="1" />
        <path d="M12 4v16" strokeWidth="1" />
        <path d="M8 10l4-4 4 4" strokeWidth="1" fill="none" />
    </Base>
);
export const RulerIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M5 19L19 5" strokeWidth="1.5" />
        <path d="M8 16l1.6-1.6M10.5 13.5l1.6-1.6M13 11l1.6-1.6M15.5 8.5l1.6-1.6" strokeWidth="1.2" />
    </Base>
);

// ── Zoom ────────────────────────────────────────────────────────────────────
export const ZoomInIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="11" cy="11" r="6" />
        <path d="M15 15l5 5" strokeWidth="2" />
        <path d="M8.5 11h5M11 8.5v5" />
    </Base>
);
export const ZoomOutIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="11" cy="11" r="6" />
        <path d="M15 15l5 5" strokeWidth="2" />
        <path d="M8.5 11h5" />
    </Base>
);

// ── Magnet ──────────────────────────────────────────────────────────────────
export const MagnetIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M7 3v9a5 5 0 0010 0V3" strokeWidth="1.5" />
        <path d="M7 3h2.5v3.5H7zM14.5 3H17v3.5h-2.5z" fill="currentColor" fillOpacity="0.3" strokeWidth="1" />
    </Base>
);

// ── Utility ─────────────────────────────────────────────────────────────────
export const LockIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="6" y="11" width="12" height="10" rx="1.5" />
        <path d="M8 11V8a4 4 0 018 0v3" />
    </Base>
);
export const UnlockIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="6" y="11" width="12" height="10" rx="1.5" />
        <path d="M16 11V8a4 4 0 00-8 0" />
    </Base>
);
export const EyeIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
        <circle cx="12" cy="12" r="3" />
    </Base>
);
export const EyeOffIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 3l18 18" strokeWidth="1.8" />
        <path d="M10 10a3 3 0 004 4" />
        <path d="M6 7c-2.2 1.7-4 5-4 5s4 7 10 7c1.3 0 2.5-.3 3.6-.8" />
        <path d="M18 17c2.2-1.7 4-5 4-5s-4-7-10-7c-.7 0-1.4.1-2 .2" />
    </Base>
);
export const TrashIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 6h16M9 6V4.5A1.5 1.5 0 0110.5 3h3A1.5 1.5 0 0115 4.5V6" />
        <path d="M6 6v13a2 2 0 002 2h8a2 2 0 002-2V6" />
        <path d="M10 10v7M14 10v7" strokeWidth="1.2" />
    </Base>
);
/** Pencil — used by the drawing-properties dialog to indicate the title is editable. */
export const PencilIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M14.7 4.3l5 5L9 20H4v-5L14.7 4.3z" />
        <path d="M13.3 5.7l5 5" strokeWidth="1.2" />
    </Base>
);
export const StarIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.9L12 16.6 6.8 19.2l1-5.9L3.5 9.2l5.9-.9L12 3z" />
    </Base>
);
export const SettingsIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2" strokeWidth="1.3" />
    </Base>
);

// ── Indicators / Layout / Alerts ────────────────────────────────────────────
export const IndicatorsIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M6 7v11M12 5v15M18 9v7" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M6 10v3M12 9v4M18 11v2" strokeWidth="3.4" strokeLinecap="round" opacity="0.3" />
    </Base>
);

export const CandleStyleIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M8 3v3M8 14v6M16 3v6M16 18v2" />
        <rect x="6" y="6" width="4" height="8" rx="0.5" fill="currentColor" stroke="none" />
        <rect x="14" y="9" width="4" height="9" rx="0.5" stroke="currentColor" fill="none" />
    </Base>
);

export const ChevronDownIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M6 9l6 6 6-6" strokeWidth="2" />
    </Base>
);

export const ChevronRightIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M9 6l6 6-6 6" strokeWidth="2" />
    </Base>
);

export const ChevronUpIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M6 15l6-6 6 6" strokeWidth="2" />
    </Base>
);

export const MaximizeIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" strokeWidth="1.6" />
    </Base>
);
export const MinimizeIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" strokeWidth="1.6" />
    </Base>
);

export const UndoIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 10h13a4 4 0 010 8h-5" />
        <path d="M7 6l-4 4 4 4" />
    </Base>
);
export const RedoIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M21 10H8a4 4 0 000 8h5" />
        <path d="M17 6l4 4-4 4" />
    </Base>
);

export const AlertIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v4l2 2" />
        <path d="M20 4l1.5-1.5M4 4L2.5 2.5" />
    </Base>
);

// ── Replay controls ─────────────────────────────────────────────────────────
export const ReplayIcon = (p: IconProps) => (
    <Base {...p}>
        <polygon points="11,5 3,10 11,15" />
        <polygon points="20,5 12,10 20,15" />
    </Base>
);
export const PlayIcon = (p: IconProps) => (
    <svg className={p.className} width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="6,4 20,12 6,20" />
    </svg>
);
export const PauseIcon = (p: IconProps) => (
    <svg className={p.className} width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
        <rect x="6" y="4" width="4" height="16" rx="1" />
        <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
);
export const StepBackIcon = (p: IconProps) => (
    <Base {...p}>
        <polygon points="11,5 3,12 11,19" fill="currentColor" />
        <line x1="19" y1="5" x2="19" y2="19" strokeWidth="2" />
    </Base>
);
export const StepForwardIcon = (p: IconProps) => (
    <Base {...p}>
        <polygon points="13,5 21,12 13,19" fill="currentColor" />
        <line x1="5" y1="5" x2="5" y2="19" strokeWidth="2" />
    </Base>
);

export const CloseIcon = (p: IconProps) => (
    <Base {...p}>
        <line x1="18" y1="6" x2="6" y2="18" strokeWidth="2" />
        <line x1="6" y1="6" x2="18" y2="18" strokeWidth="2" />
    </Base>
);

export const RefreshIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 12a9 9 0 0115.6-6.2L21 8" />
        <path d="M21 4v4h-4" />
        <path d="M21 12a9 9 0 01-15.6 6.2L3 16" />
        <path d="M3 20v-4h4" />
    </Base>
);

export const RadioIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
        <path d="M8.5 8.5a5 5 0 000 7" />
        <path d="M15.5 8.5a5 5 0 010 7" />
        <path d="M5 5a10 10 0 000 14" />
        <path d="M19 5a10 10 0 010 14" />
    </Base>
);

export const NewspaperIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M4 5h13a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V5z" />
        <path d="M8 9h7M8 13h7M8 17h4" strokeWidth="1.3" />
    </Base>
);

export const EarningsBadgeIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="8.5" />
        <text x="12" y="13.5" textAnchor="middle" fontSize="9" fontWeight="700" fill="currentColor" stroke="none">E</text>
    </Base>
);

export const LayoutGridIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="3" y="3" width="8" height="8" rx="1" />
        <rect x="13" y="3" width="8" height="8" rx="1" />
        <rect x="3" y="13" width="8" height="8" rx="1" />
        <rect x="13" y="13" width="8" height="8" rx="1" />
    </Base>
);

// ── Header-specific (Compare / Template / Screenshot) ───────────────────────
/**
 * Simple "+" inside a circle, mirroring TradingView's "Compare or add symbol"
 * button. Kept minimal so the header stays visually quiet.
 */
export const CompareIcon = (p: IconProps) => (
    <Base {...p}>
        <circle cx="12" cy="12" r="8.5" strokeWidth="1.4" />
        <path d="M12 8.5v7M8.5 12h7" strokeWidth="1.6" />
    </Base>
);

/**
 * Two overlapping sparklines variant, useful when a small "+ comparison" icon
 * isn't expressive enough (e.g. inside a populated dropdown). Not used in the
 * header today, exported for future menus.
 */
export const SparklineOverlayIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 16l5-6 4 4 4-7 5 5" />
        <path d="M3 12l5-4 4 6 4-3 5 4" opacity="0.55" />
    </Base>
);

export const TemplateIcon = (p: IconProps) => (
    <Base {...p}>
        <rect x="3" y="4" width="18" height="16" rx="1.5" />
        <path d="M3 9h18" strokeWidth="1.2" />
        <path d="M9 9v11" strokeWidth="1.2" />
        <path d="M6 12h2M6 15h2M6 18h2" strokeWidth="1" />
    </Base>
);

export const CameraIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M3 8a2 2 0 012-2h2.5l1.5-2h6l1.5 2H19a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
        <circle cx="12" cy="13" r="3.5" />
    </Base>
);

export const SaveIcon = (p: IconProps) => (
    <Base {...p}>
        <path d="M5 4h11l4 4v12a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1z" />
        <path d="M8 4v5h8V4" strokeWidth="1.2" />
        <rect x="8" y="13" width="8" height="6" strokeWidth="1.2" />
    </Base>
);
