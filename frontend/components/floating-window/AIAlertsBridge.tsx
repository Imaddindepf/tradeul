'use client';

/**
 * AIAlertsBridge — global listener that opens the AI Alerts floating window
 * when any component (e.g. the AlertDraftCard inside the agent chat)
 * dispatches `tradeul:open-ai-alerts`. Mounted once in AppShell, inside the
 * FloatingWindowProvider.
 */
import { useEffect } from 'react';
import { useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { AIAlertsContent } from './AIAlertsContent';

export function AIAlertsBridge() {
  const { openWindow, bringToFront, restoreWindow } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();

  useEffect(() => {
    const handler = () => {
      const existing = windows.find(w => w.title === 'AI Alerts');
      if (existing) {
        if (existing.isMinimized) restoreWindow(existing.id);
        bringToFront(existing.id);
        return;
      }
      const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1400;
      openWindow({
        title: 'AI Alerts',
        content: <AIAlertsContent />,
        width: 480,
        height: 560,
        x: screenWidth - 510,
        y: 90,
        minWidth: 400,
        minHeight: 420,
      });
    };
    window.addEventListener('tradeul:open-ai-alerts', handler);
    return () => window.removeEventListener('tradeul:open-ai-alerts', handler);
  }, [openWindow, bringToFront, restoreWindow, windows]);

  return null;
}
