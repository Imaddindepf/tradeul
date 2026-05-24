'use client';

import React from 'react';
import { useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { FloatingWindow } from './FloatingWindow';
import { Z_INDEX } from '@/lib/z-index';

export function FloatingWindowManager() {
  const windows = useFloatingWindowsList();

  return (
    <>
      {windows.map((window) => (
        <FloatingWindow key={window.id} window={window} />
      ))}
    </>
  );
}

