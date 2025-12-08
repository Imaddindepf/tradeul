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
import { useTradingDayReset } from '@/hooks/useTradingDayReset';

interface AppShellProps {
  children: ReactNode;
}

/**
 * Componente interno que usa el hook de reset de día de trading
 * Se monta dentro de AuthWebSocketProvider para tener acceso al WebSocket
 */
function TradingDayResetHandler() {
  useTradingDayReset();
  return null;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <AuthWebSocketProvider>
      <SquawkProvider>
        <FloatingWindowProvider>
          {/* TradingDayResetHandler: detecta cambio de dia y limpia stores automaticamente */}
          <TradingDayResetHandler />
          {/* NewsProvider: ingesta global de noticias (siempre activo, no se desmonta) */}
          <NewsProvider>
            {/* CatalystDetectorProvider: detecta movimientos explosivos en noticias */}
            <CatalystDetectorProvider>
              <div className="min-h-screen bg-slate-50">
                {/* Announcement Banner - floating toast */}
                <AnnouncementBanner />
                <Navbar />
                <main className="w-full">
                  {/* Contenido principal con padding-top para dejar espacio al navbar fijo */}
                  <div className="min-h-screen bg-white w-full pt-16">
                    {children}
                  </div>
                </main>
                <FloatingWindowManager />
                {/* Catalyst Alerts Popup - floating notifications */}
                <CatalystAlertsPopup />
              </div>
            </CatalystDetectorProvider>
          </NewsProvider>
        </FloatingWindowProvider>
      </SquawkProvider>
    </AuthWebSocketProvider>
  );
}


