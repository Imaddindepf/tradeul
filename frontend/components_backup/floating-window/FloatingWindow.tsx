'use client';

import React, { useState, useEffect } from 'react';
import { Rnd } from 'react-rnd';
import { X, Minus, Maximize2, Square, ExternalLink } from 'lucide-react';
import { FloatingWindow as FloatingWindowType, useFloatingWindow } from '@/contexts/FloatingWindowContext';

interface FloatingWindowProps {
  window: FloatingWindowType;
}

export function FloatingWindow({ window }: FloatingWindowProps) {
  const { closeWindow, bringToFront, minimizeWindow, maximizeWindow, restoreWindow, updateWindow } = useFloatingWindow();
  const [isDragging, setIsDragging] = useState(false);
  const [savedPosition, setSavedPosition] = useState({ x: window.x, y: window.y });
  const [savedSize, setSavedSize] = useState({ width: window.width, height: window.height });
  const [screenSize, setScreenSize] = useState({ width: 1920, height: 1080 });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    const updateScreenSize = () => {
      setScreenSize({ width: globalThis.window.innerWidth, height: globalThis.window.innerHeight });
    };
    updateScreenSize();
    globalThis.window.addEventListener('resize', updateScreenSize);
    return () => globalThis.window.removeEventListener('resize', updateScreenSize);
  }, []);

  useEffect(() => {
    bringToFront(window.id);
  }, [window.id, bringToFront]);

  const handleDragStart = () => {
    setIsDragging(true);
    bringToFront(window.id);
  };

  const handleDragStop = (_e: any, d: { x: number; y: number }) => {
    setIsDragging(false);
    updateWindow(window.id, { x: d.x, y: d.y });
  };

  const handleResizeStop = (_e: any, _direction: any, ref: HTMLElement, _delta: any, position: { x: number; y: number }) => {
    updateWindow(window.id, {
      width: ref.offsetWidth,
      height: ref.offsetHeight,
      x: position.x,
      y: position.y,
    });
  };

  const handleMinimize = () => {
    minimizeWindow(window.id);
  };

  const handleMaximize = () => {
    if (window.isMaximized) {
      restoreWindow(window.id);
      updateWindow(window.id, {
        x: savedPosition.x,
        y: savedPosition.y,
        width: savedSize.width,
        height: savedSize.height,
      });
    } else {
      setSavedPosition({ x: window.x, y: window.y });
      setSavedSize({ width: window.width, height: window.height });
      maximizeWindow(window.id);
      updateWindow(window.id, {
        x: 0,
        y: 0,
        width: window.maxWidth || screenSize.width,
        height: window.maxHeight || screenSize.height,
      });
    }
  };

  const handleClose = () => {
    closeWindow(window.id);
  };

  const handleOpenNewWindow = () => {
    // Determinar la URL basándose en el título de la ventana
    let url = '';
    if (window.title === 'Dilution Tracker') {
      url = '/dilution-tracker';
    }
    
    if (url) {
      const width = 1200;
      const height = 800;
      const left = typeof globalThis.window !== 'undefined' ? (globalThis.window.screen.width - width) / 2 : 100;
      const top = typeof globalThis.window !== 'undefined' ? (globalThis.window.screen.height - height) / 2 : 100;
      
      const windowFeatures = `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes,status=yes,menubar=no,toolbar=no,location=no`;
      
      globalThis.window.open(url, window.title.replace(/\s+/g, ''), windowFeatures);
    }
  };

  const handleTitleClick = () => {
    bringToFront(window.id);
  };

  if (window.isMinimized) {
    return (
      <div
        className="fixed bottom-0 left-0 bg-white border-t border-l border-r border-slate-300 rounded-t-lg shadow-lg cursor-pointer hover:bg-slate-50 transition-colors"
        style={{
          zIndex: window.zIndex,
          minWidth: '200px',
          padding: '8px 16px',
        }}
        onClick={() => restoreWindow(window.id)}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-sm font-medium text-slate-700">{window.title}</span>
        </div>
      </div>
    );
  }

  return (
    <Rnd
      size={{
        width: window.isMaximized 
          ? (window.maxWidth || screenSize.width) 
          : window.width,
        height: window.isMaximized 
          ? (window.maxHeight || screenSize.height) 
          : window.height,
      }}
      position={{
        x: window.isMaximized ? 0 : window.x,
        y: window.isMaximized ? 0 : window.y,
      }}
      minWidth={window.minWidth || 400}
      minHeight={window.minHeight || 300}
      maxWidth={window.isMaximized ? undefined : (window.maxWidth || screenSize.width)}
      maxHeight={window.isMaximized ? undefined : (window.maxHeight || screenSize.height)}
      bounds="window"
      dragHandleClassName="window-title-bar"
      onDragStart={handleDragStart}
      onDragStop={handleDragStop}
      onResizeStop={handleResizeStop}
      style={{
        zIndex: window.zIndex,
        display: 'flex',
        flexDirection: 'column',
        pointerEvents: 'auto',
      }}
      disableResizing={window.isMaximized}
      enableResizing={!window.isMaximized}
    >
      <div 
        className="flex flex-col h-full bg-white rounded-lg shadow-2xl border border-slate-200 overflow-hidden"
        onMouseDown={(e) => {
          // Solo prevenir propagación si no es en la barra de título (para que el drag funcione)
          if (!(e.target as HTMLElement).closest('.window-title-bar')) {
            e.stopPropagation();
            bringToFront(window.id);
          }
        }}
      >
        {/* Title Bar */}
        <div
          className="window-title-bar flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-200 cursor-move select-none"
          onMouseDown={(e) => {
            // Traer la ventana al frente cuando se hace click en la barra de título
            bringToFront(window.id);
            // No prevenir el evento para que react-rnd pueda manejar el drag
          }}
        >
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-2 h-2 rounded-full bg-blue-500" />
            <h3 className="text-sm font-semibold text-slate-800 truncate">{window.title}</h3>
          </div>

          <div className="flex items-center gap-1 ml-4">
            {/* Minimize Button */}
            <button
              onMouseDown={(e) => {
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.stopPropagation();
                handleMinimize();
              }}
              className="p-1.5 rounded hover:bg-slate-200 transition-colors group"
              aria-label="Minimizar"
            >
              <Minus className="w-4 h-4 text-slate-600 group-hover:text-slate-800" />
            </button>

            {/* Maximize/Restore Button */}
            <button
              onMouseDown={(e) => {
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.stopPropagation();
                handleMaximize();
              }}
              className="p-1.5 rounded hover:bg-slate-200 transition-colors group"
              aria-label={window.isMaximized ? 'Restaurar' : 'Maximizar'}
            >
              {window.isMaximized ? (
                <Square className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-800" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-800" />
              )}
            </button>

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
        <div 
          className="flex-1 overflow-auto bg-white"
          onMouseDown={(e) => {
            // Prevenir que los eventos se propaguen al fondo
            // Los elementos interactivos dentro funcionarán normalmente
            e.stopPropagation();
          }}
        >
          {window.content}
        </div>
      </div>
    </Rnd>
  );
}

