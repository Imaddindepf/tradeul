'use client';

import { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
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
          <main className="flex-1 min-w-0">
            <div className="min-h-screen bg-white w-full">
              {children}
            </div>
          </main>
          <FloatingWindowManager />
        </div>
      </FloatingWindowProvider>
    </SidebarProvider>
  );
}


