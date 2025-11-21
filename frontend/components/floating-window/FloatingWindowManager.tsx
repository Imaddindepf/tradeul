'use client';

import React from 'react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FloatingWindow } from './FloatingWindow';
import { Z_INDEX } from '@/lib/z-index';

export function FloatingWindowManager() {
  const { windows } = useFloatingWindow();

  return (
    <>
      {windows.map((window) => (
        <FloatingWindow key={window.id} window={window} />
      ))}
    </>
  );
}

