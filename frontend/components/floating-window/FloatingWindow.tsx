'use client';

import React, { useState, useEffect } from 'react';
import { X, Minus, Maximize2, Square, ExternalLink } from 'lucide-react';
import { FloatingWindow as FloatingWindowType, useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FloatingWindowBase } from '@/components/ui/FloatingWindowBase';

interface FloatingWindowProps {
  window: FloatingWindowType;
}

export function FloatingWindow({ window }: FloatingWindowProps) {
  const { closeWindow, updateWindow } = useFloatingWindow();

  const handleClose = () => {
    closeWindow(window.id);
  };

  const handlePositionChange = (position: { x: number; y: number }) => {
    updateWindow(window.id, position);
  };

  const handleSizeChange = (size: { width: number; height: number }) => {
    updateWindow(window.id, size);
  };

  const handleOpenNewWindow = () => {
    if (window.title === 'Dilution Tracker') {
      // Extraer ticker actual del input de búsqueda
      let currentTicker = '';

      const windowElement = document.getElementById(`floating-window-${window.id}`);
      if (windowElement) {
        const searchInput = windowElement.querySelector('input[type="text"]') as HTMLInputElement;
        if (searchInput && searchInput.value) {
          currentTicker = searchInput.value.trim().toUpperCase();
        }
      }

      // Usar window-injector para about:blank (como scanner)
      const { openDilutionTrackerWindow } = require('@/lib/window-injector');
      openDilutionTrackerWindow(
        {
          ticker: currentTicker || undefined,
          apiBaseUrl: window.location.origin
        },
        {
          title: `Dilution Tracker${currentTicker ? ` - ${currentTicker}` : ''}`,
          width: 1400,
          height: 900,
          centered: true
        }
      );
    }
  };

  // Si está minimizado, no usar FloatingWindowBase
  if (window.isMinimized) {
    return (
      <div
        className="fixed bottom-0 left-0 bg-white border-t border-l border-r border-slate-300 rounded-t-lg shadow-lg cursor-pointer hover:bg-slate-50 transition-colors"
        style={{
          zIndex: window.zIndex,
          minWidth: '200px',
          padding: '8px 16px',
        }}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-sm font-medium text-slate-700">{window.title}</span>
        </div>
      </div>
    );
  }

  const handleZIndexChange = (zIndex: number) => {
    updateWindow(window.id, { zIndex });
  };

  return (
    <FloatingWindowBase
      dragHandleClassName="window-title-bar"
      initialSize={{ width: window.width, height: window.height }}
      minWidth={window.minWidth || 400}
      minHeight={window.minHeight || 300}
      maxWidth={window.maxWidth || 1600}
      maxHeight={window.maxHeight || 1000}
      enableResizing={true}
      onPositionChange={handlePositionChange}
      onSizeChange={handleSizeChange}
      onZIndexChange={handleZIndexChange}
      className="bg-white"
    >
      <div id={`floating-window-${window.id}`} className="flex flex-col h-full overflow-hidden">
        {/* Title Bar - El foco se maneja automáticamente en FloatingWindowBase */}
        <div className="window-title-bar flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-200 cursor-move select-none">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-2 h-2 rounded-full bg-blue-500" />
            <h3 className="text-sm font-semibold text-slate-800 truncate">{window.title}</h3>
          </div>

          <div className="flex items-center gap-1 ml-4">
            {/* Open in New Window Button */}
            <button
              onMouseDown={(e) => {
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.stopPropagation();
                handleOpenNewWindow();
              }}
              className="p-1.5 rounded hover:bg-blue-100 transition-colors group"
              aria-label="Abrir en nueva ventana"
              title="Abrir en nueva ventana"
            >
              <ExternalLink className="w-3.5 h-3.5 text-slate-600 group-hover:text-blue-600" />
            </button>

            {/* Close Button */}
            <button
              onMouseDown={(e) => {
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.stopPropagation();
                handleClose();
              }}
              className="p-1.5 rounded hover:bg-red-100 transition-colors group"
              aria-label="Cerrar"
            >
              <X className="w-4 h-4 text-slate-600 group-hover:text-red-600" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto bg-white">
          {window.content}
        </div>
      </div>
    </FloatingWindowBase>
  );
}

