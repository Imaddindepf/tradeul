'use client';

import React from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FloatingWindow } from './FloatingWindow';

export function FloatingWindowManager() {
  const { windows } = useFloatingWindow();

  return (
    <div className="fixed inset-0 pointer-events-none z-[9999]">
      {windows.map((window) => (
        <div key={window.id} className="pointer-events-auto">
          <FloatingWindow window={window} />
        </div>
      ))}
    </div>
  );
}

