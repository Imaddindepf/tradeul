/**
 * Base types and utilities for window injector modules
 */

import { useUserPreferencesStore, FontFamily } from '@/stores/useUserPreferencesStore';

// ============================================================================
// SHARED TYPES
// ============================================================================

export interface WindowConfig {
  title: string;
  width?: number;
  height?: number;
  centered?: boolean;
}

// Font configuration mapping
const FONT_CONFIG: Record<FontFamily, { name: string; googleFont: string; cssFamily: string }> = {
  'oxygen-mono': {
    name: 'Oxygen Mono',
    googleFont: 'Oxygen+Mono:wght@400',
    cssFamily: "'Oxygen Mono', monospace"
  },
  'ibm-plex-mono': {
    name: 'IBM Plex Mono',
    googleFont: 'IBM+Plex+Mono:wght@400;500;600;700',
    cssFamily: "'IBM Plex Mono', monospace"
  },
  'jetbrains-mono': {
    name: 'JetBrains Mono',
    googleFont: 'JetBrains+Mono:wght@400;500;600;700',
    cssFamily: "'JetBrains Mono', monospace"
  },
  'fira-code': {
    name: 'Fira Code',
    googleFont: 'Fira+Code:wght@400;500;600;700',
    cssFamily: "'Fira Code', monospace"
  }
};

// ============================================================================
// SHARED UTILITIES
// ============================================================================

/**
 * Get user's preferred timezone for injected windows
 */
export function getUserTimezoneForWindow(): string {
  try {
    return useUserPreferencesStore.getState().theme.timezone || 'America/New_York';
  } catch {
    return 'America/New_York';
  }
}

/**
 * Get user's preferred font for injected windows
 */
export function getUserFontForWindow(): FontFamily {
  try {
    return useUserPreferencesStore.getState().theme.font || 'jetbrains-mono';
  } catch {
    return 'jetbrains-mono';
  }
}

/**
 * Get font configuration for a given font family
 */
export function getFontConfig(font: FontFamily) {
  return FONT_CONFIG[font] || FONT_CONFIG['jetbrains-mono'];
}

/**
 * Open a new browser window with standard features
 */
export function openPopupWindow(config: WindowConfig): Window | null {
  const {
    width = 1000,
    height = 700,
    centered = true,
  } = config;

  const left = centered ? (window.screen.width - width) / 2 : 100;
  const top = centered ? (window.screen.height - height) / 2 : 100;

  const windowFeatures = [
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
    'resizable=yes',
    'scrollbars=yes',
    'status=yes',
  ].join(',');

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Window blocked by browser');
    return null;
  }

  return newWindow;
}

// ============================================================================
// SHARED HTML TEMPLATES
// ============================================================================

/**
 * Generate Google Fonts link for user's preferred font
 */
export function getSharedFontsLink(): string {
  const font = getUserFontForWindow();
  const config = getFontConfig(font);
  
  return `
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=${config.googleFont}&display=swap" rel="stylesheet">
`;
}

/**
 * Generate Tailwind config with user's preferred font
 */
export function getSharedTailwindConfig(): string {
  const font = getUserFontForWindow();
  const config = getFontConfig(font);
  
  return `
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: [${config.cssFamily}]
          },
          colors: {
            background: '#FFFFFF',
            foreground: '#0F172A',
            primary: { DEFAULT: '#2563EB', hover: '#1D4ED8' },
            border: '#E2E8F0',
            muted: '#F8FAFC',
            success: '#10B981',
            danger: '#EF4444'
          }
        }
      }
    }
  </script>
`;
}

/**
 * Generate base styles with user's preferred font
 */
export function getSharedBaseStyles(): string {
  const font = getUserFontForWindow();
  const config = getFontConfig(font);
  
  return `
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: Inter, sans-serif; color: #171717; background: #ffffff; margin: 0; }
    .font-mono { font-family: ${config.cssFamily} !important; }
    *::-webkit-scrollbar { width: 8px; height: 8px; }
    *::-webkit-scrollbar-track { background: #f1f5f9; }
    *::-webkit-scrollbar-thumb { background: #cbd5e1; }
    *::-webkit-scrollbar-thumb:hover { background: #3b82f6; }
  </style>
`;
}

// Legacy constants for backward compatibility (use functions above for dynamic fonts)
export const SHARED_FONTS_LINK = getSharedFontsLink();
export const SHARED_TAILWIND_CONFIG = getSharedTailwindConfig();
export const SHARED_BASE_STYLES = getSharedBaseStyles();

/**
 * Write HTML content to a window and close the document
 */
export function injectHTML(targetWindow: Window, htmlContent: string): void {
  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();
}

/**
 * Format a financial value for display
 * Used by Financial Chart and IPO windows
 */
export function formatValueJS(value: number | null, type: string): string {
  if (value === null || value === undefined) return '--';

  if (type === 'percent') return `${value.toFixed(2)}%`;
  if (type === 'ratio') return value.toFixed(2);
  if (type === 'eps') return `${value < 0 ? '-' : ''}$${Math.abs(value).toFixed(2)}`;
  if (type === 'shares') {
    const abs = Math.abs(value);
    if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
    return value.toFixed(0);
  }

  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

