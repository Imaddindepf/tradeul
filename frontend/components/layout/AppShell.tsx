'use client';

import { ReactNode } from 'react';
interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-white w-full px-3 sm:px-4 lg:px-6 xl:px-8">{children}</div>
  );
}


