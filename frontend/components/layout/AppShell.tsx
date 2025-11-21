'use client';

import { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { Navbar } from './Navbar';
import { FloatingWindowProvider } from '@/contexts/FloatingWindowContext';
import { SidebarProvider } from '@/contexts/SidebarContext';
import { FloatingWindowManager } from '@/components/floating-window/FloatingWindowManager';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <SidebarProvider>
      <FloatingWindowProvider>
        <div className="min-h-screen bg-slate-50 flex">
          <Sidebar />
          <Navbar />
          <main className="flex-1 min-w-0">
            {/* Contenido principal con padding-top para dejar espacio al navbar fijo */}
            <div className="min-h-screen bg-white w-full pt-16">
              {children}
            </div>
          </main>
          <FloatingWindowManager />
        </div>
      </FloatingWindowProvider>
    </SidebarProvider>
  );
}


