/**
 * Window Injector - Modular standalone windows system
 * 
 * This module manages standalone browser windows (about:blank) that run
 * independently from the main React app. Each window type has its own
 * HTML/JS/CSS injected at creation time.
 * 
 * Architecture:
 * - Each window type is in its own file for maintainability
 * - base.ts has shared utilities (getUserTimezoneForWindow, WindowConfig)
 * - This index.ts re-exports everything for clean imports
 * 
 * Usage:
 *   import { openNewsWindow, openScannerWindow } from '@/lib/window-injector';
 */

// Base utilities
export { getUserTimezoneForWindow, type WindowConfig } from './base';

// Scanner Window
export { 
  openScannerWindow, 
  type ScannerWindowData 
} from './scanner-window';

// Dilution Tracker Window
export { 
  openDilutionTrackerWindow, 
  type DilutionTrackerWindowData 
} from './dilution-tracker-window';

// News Window
export { 
  openNewsWindow, 
  type NewsWindowData 
} from './news-window';

// SEC Filings Window
export { 
  openSECFilingsWindow, 
  type SECFilingsWindowData 
} from './sec-filings-window';

// Financial Chart Window
export { 
  openFinancialChartWindow, 
  type FinancialChartData 
} from './financial-chart-window';

// IPO Window
export { 
  openIPOWindow, 
  type IPOWindowData 
} from './ipo-window';

// Chat Window
export { 
  openChatWindow, 
  type ChatWindowData 
} from './chat-window';

// Notes Window
export { 
  openNotesWindow, 
  type NotesWindowData,
  type NotesNote 
} from './notes-window';

// Multiple Security Window (MP)
export { 
  openMultipleSecurityWindow, 
  type MultipleSecurityWindowData 
} from './multiple-security-window';
