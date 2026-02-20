'use client';

import { ReactNode } from 'react';
import { Navbar } from './Navbar';
import { AnnouncementBanner } from './AnnouncementBanner';
import { FloatingWindowProvider } from '@/contexts/FloatingWindowContext';
import { AuthWebSocketProvider } from '@/contexts/AuthWebSocketContext';
import { SquawkProvider } from '@/contexts/SquawkContext';
import { FloatingWindowManager } from '@/components/floating-window/FloatingWindowManager';
import { CatalystAlertsPopup, CatalystDetectorProvider } from '@/components/catalyst-alerts';
import { NewsProvider } from '@/components/news/NewsProvider';
import { InsightsProvider } from '@/components/insights';
import { useTradingDayReset } from '@/hooks/useTradingDayReset';
import { useWorkspaceSync } from '@/hooks/useWorkspaceSync';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useEffect } from 'react';

interface AppShellProps {
  children: ReactNode;
}

/**
 * Componente interno que usa hooks globales
 */
function GlobalHooksHandler() {
  // Hydrate store from localStorage BEFORE any layout restoration runs.
  // The store uses skipHydration:true (SSR-safe) so we must manually trigger it.
  useEffect(() => {
    useUserPreferencesStore.persist.rehydrate();
  }, []);

  useTradingDayReset();
  useWorkspaceSync({ enableInitialLoad: true });
  return null;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <AuthWebSocketProvider>
      <SquawkProvider>
        <FloatingWindowProvider>
          {/* GlobalHooksHandler: hooks globales (reset dia, sync filtros) */}
          <GlobalHooksHandler />
          {/* NewsProvider: ingesta global de noticias (siempre activo, no se desmonta) */}
          <NewsProvider>
            {/* InsightsProvider: escucha notificaciones de Insights (Morning News, etc.) */}
            <InsightsProvider>
              {/* CatalystDetectorProvider: detecta movimientos explosivos en noticias */}
              <CatalystDetectorProvider>
                <div className="min-h-screen bg-slate-50 relative">
                  {/* Announcement Banner - floating toast */}
                  <AnnouncementBanner />
                  <Navbar />
                  <main className="w-full">
                    {/* Contenido principal con padding-top para dejar espacio al navbar fijo */}
                    <div className="min-h-screen bg-white w-full pt-11">
                      {children}
                    </div>
                  </main>
                  <FloatingWindowManager />
                  {/* Catalyst Alerts Popup - floating notifications */}
                  <CatalystAlertsPopup />
                </div>
              </CatalystDetectorProvider>
            </InsightsProvider>
          </NewsProvider>
        </FloatingWindowProvider>
      </SquawkProvider>
    </AuthWebSocketProvider>
  );
}


