'use client';

import { useState, useRef, ReactNode, MouseEvent, useCallback, memo } from 'react';
import { floatingZIndexManager } from '@/lib/z-index';

export interface FloatingWindowBaseProps {
  children: ReactNode;
  dragHandleClassName?: string;
  initialSize?: { width: number; height: number };
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  enableResizing?: boolean;
  className?: string;
  focusedBorderColor?: string;
  initialZIndex?: number;
  stackOffset?: number; // Offset para posicionar múltiples ventanas escalonadas
  onZIndexChange?: (zIndex: number) => void;
  onSizeChange?: (size: { width: number; height: number }) => void;
  onPositionChange?: (position: { x: number; y: number }) => void;
}

/**
 * Ventana flotante optimizada con drag & resize nativos
 * - Position fixed sin transform
 * - Callbacks memoizados para evitar re-renders
 * - Performance optimizada para drag fluido
 */
function FloatingWindowBaseComponent({
  children,
  dragHandleClassName = 'window-drag-handle',
  initialSize = { width: 800, height: 600 },
  minWidth = 400,
  minHeight = 300,
  maxWidth = 1600,
  maxHeight = 1000,
  enableResizing = true,
  className = '',
  focusedBorderColor = 'border-blue-500',
  initialZIndex,
  stackOffset = 0,
  onZIndexChange,
  onSizeChange,
  onPositionChange,
}: FloatingWindowBaseProps) {
  // Posición inicial segura que respeta los límites del navbar y sidebar
  const getInitialPosition = () => {
    const navbarHeight = 64; // h-16
    const sidebarWidth = 256;
    const minY = navbarHeight + 20; // 84px - LÍMITE: debajo del navbar
    const minX = sidebarWidth + 20; // 276px - después del sidebar
    
    return {
      x: minX + stackOffset,
      y: minY + stackOffset,
    };
  };

  const [position, setPosition] = useState(getInitialPosition);
  const [size, setSize] = useState(initialSize);
  const [zIndex, setZIndex] = useState(() =>
    initialZIndex !== undefined ? initialZIndex : floatingZIndexManager.getNext()
  );
  const [isFocused, setIsFocused] = useState(false);

  const isDraggingRef = useRef(false);
  const isResizingRef = useRef(false);

  // Traer al frente - memoizado
  const bringToFront = useCallback(() => {
    if (initialZIndex === undefined) {
      const newZ = floatingZIndexManager.getNext();
      setZIndex(newZ);
      onZIndexChange?.(newZ);
    }
    setIsFocused(true);
  }, [initialZIndex, onZIndexChange]);

  // Drag handler optimizado con bounds checking
  const handleDragStart = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (!target.closest(`.${dragHandleClassName}`)) return;

    e.preventDefault();
    e.stopPropagation();

    bringToFront();
    isDraggingRef.current = true;

    const startX = e.clientX;
    const startY = e.clientY;
    const startPosX = position.x;
    const startPosY = position.y;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      if (!isDraggingRef.current) return;

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      // Calcular nueva posición
      let newX = startPosX + deltaX;
      let newY = startPosY + deltaY;

      // Límites de la pantalla
      const navbarHeight = 64; // h-16 = 64px
      const sidebarWidth = 256; // Ancho del sidebar expandido
      const minX = sidebarWidth + 10; // Margen después del sidebar
      const minY = navbarHeight + 10; // LÍMITE: Navbar + margen
      const maxX = window.innerWidth - size.width - 10;
      const maxY = window.innerHeight - 100; // Dejar espacio para ver el header

      // Aplicar restricciones
      newX = Math.max(minX, Math.min(maxX, newX));
      newY = Math.max(minY, Math.min(maxY, newY));

      const newPos = { x: newX, y: newY };

      setPosition(newPos);
      onPositionChange?.(newPos);
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      setIsFocused(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [dragHandleClassName, position.x, position.y, size.width, bringToFront, onPositionChange]);

  // Resize handler optimizado
  const handleResizeStart = useCallback((e: MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    bringToFront();
    isResizingRef.current = true;

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = size.width;
    const startHeight = size.height;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      if (!isResizingRef.current) return;

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      const newSize = {
        width: Math.max(minWidth, Math.min(maxWidth, startWidth + deltaX)),
        height: Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY)),
      };

      setSize(newSize);
      onSizeChange?.(newSize);
    };

    const handleMouseUp = () => {
      isResizingRef.current = false;
      setIsFocused(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [size.width, size.height, minWidth, minHeight, maxWidth, maxHeight, bringToFront, onSizeChange]);

  return (
    <div
      style={{
        position: 'fixed',
        top: `${position.y}px`,
        left: `${position.x}px`,
        width: `${size.width}px`,
        height: `${size.height}px`,
        zIndex: zIndex,
      }}
      className={`rounded-lg shadow-2xl border-4 transition-shadow flex flex-col ${isFocused ? focusedBorderColor + ' shadow-blue-500/50' : 'border-slate-200'
        } ${className}`}
      onMouseDown={handleDragStart}
      onClick={bringToFront}
    >
      {/* Contenido */}
      <div className="h-full w-full overflow-hidden flex flex-col">
        {children}
      </div>

      {/* Resize handle */}
      {enableResizing && (
        <div
          onMouseDown={handleResizeStart}
          className="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize hover:bg-blue-500/20 transition-colors"
          style={{
            borderRight: '5px solid transparent',
            borderBottom: '5px solid transparent',
            borderTop: '5px solid #cbd5e1',
            borderLeft: '5px solid #cbd5e1',
          }}
        />
      )}
    </div>
  );
}

export const FloatingWindowBase = memo(FloatingWindowBaseComponent);
