'use client';

import { ReactNode } from 'react';
import { Navbar } from './Navbar';
import { AnnouncementBanner } from './AnnouncementBanner';
import { FloatingWindowProvider } from '@/contexts/FloatingWindowContext';
import { FloatingWindowManager } from '@/components/floating-window/FloatingWindowManager';
import { CatalystAlertsPopup, CatalystDetectorProvider } from '@/components/catalyst-alerts';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <FloatingWindowProvider>
      {/* CatalystDetectorProvider: siempre escucha noticias en background cuando las alertas están habilitadas */}
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
    </FloatingWindowProvider>
  );
}


