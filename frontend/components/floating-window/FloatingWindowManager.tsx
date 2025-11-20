'use client';

import React from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FloatingWindow } from './FloatingWindow';
import { Z_INDEX } from '@/lib/z-index';

export function FloatingWindowManager() {
  const { windows } = useFloatingWindow();

  return (
    <div 
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: Z_INDEX.FLOATING_WINDOW_MANAGER }}
    >
      {windows.map((window) => (
        <div key={window.id} className="pointer-events-auto">
          <FloatingWindow window={window} />
        </div>
      ))}
    </div>
  );
}

