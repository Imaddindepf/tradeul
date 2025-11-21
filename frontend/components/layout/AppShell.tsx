'use client';

import { ReactNode } from 'react';
import { Navbar } from './Navbar';
import { FloatingWindowProvider } from '@/contexts/FloatingWindowContext';
import { FloatingWindowManager } from '@/components/floating-window/FloatingWindowManager';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <FloatingWindowProvider>
      <div className="min-h-screen bg-slate-50">
        <Navbar />
        <main className="w-full">
          {/* Contenido principal con padding-top para dejar espacio al navbar fijo */}
          <div className="min-h-screen bg-white w-full pt-16">
            {children}
          </div>
        </main>
        <FloatingWindowManager />
      </div>
    </FloatingWindowProvider>
  );
}


