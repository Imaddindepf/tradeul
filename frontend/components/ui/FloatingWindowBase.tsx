'use client';

import { useState, ReactNode } from 'react';
import { Rnd } from 'react-rnd';
import { floatingZIndexManager } from '@/lib/z-index';

export interface FloatingWindowBaseProps {
  /** Contenido de la ventana */
  children: ReactNode;
  
  /** Clase CSS para el handle de arrastre */
  dragHandleClassName?: string;
  
  /** Posición inicial (opcional, se centra por defecto) */
  initialPosition?: { x: number; y: number };
  
  /** Tamaño inicial */
  initialSize?: { width: number; height: number };
  
  /** Tamaño mínimo */
  minWidth?: number;
  minHeight?: number;
  
  /** Tamaño máximo */
  maxWidth?: number;
  maxHeight?: number;
  
  /** Permitir redimensionar */
  enableResizing?: boolean;
  
  /** Clase adicional para el contenedor */
  className?: string;
  
  /** Estilo del borde cuando tiene foco (default: verde) */
  focusedBorderColor?: string;
  
  /** Callback cuando cambia el tamaño */
  onSizeChange?: (size: { width: number; height: number }) => void;
  
  /** Callback cuando cambia la posición */
  onPositionChange?: (position: { x: number; y: number }) => void;
  
  /** Offset para posición escalonada (para múltiples ventanas) */
  stackOffset?: number;
  
  /** Z-index inicial (opcional, si se proporciona se usa en lugar del manager) */
  initialZIndex?: number;
  
  /** Callback cuando cambia el z-index */
  onZIndexChange?: (zIndex: number) => void;
}

/**
 * Componente base para todas las ventanas flotantes
 * 
 * Características:
 * - Arrastrable por el handle designado
 * - Redimensionable (configurable)
 * - Sistema de foco automático (z-index dinámico)
 * - Borde visual cuando tiene foco
 * - Posicionamiento inteligente
 * 
 * Usado en:
 * - Tablas del scanner (DraggableTable)
 * - Modal de metadata (TickerMetadataModal)
 * - Dilution Tracker (FloatingWindow)
 */
export function FloatingWindowBase({
  children,
  dragHandleClassName = 'window-drag-handle',
  initialPosition,
  initialSize = { width: 800, height: 600 },
  minWidth = 400,
  minHeight = 300,
  maxWidth = 1600,
  maxHeight = 1000,
  enableResizing = true,
  className = '',
  focusedBorderColor = 'border-green-500',
  onSizeChange,
  onPositionChange,
  stackOffset = 0,
  initialZIndex,
  onZIndexChange,
}: FloatingWindowBaseProps) {
  // Calcular posición inicial centrada o con offset
  const getInitialPosition = () => {
    if (initialPosition) return initialPosition;
    
    if (typeof window === 'undefined') {
      return { x: 100 + stackOffset, y: 100 + stackOffset };
    }
    
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    return {
      x: Math.max((viewportWidth - initialSize.width) / 2 + stackOffset, 20),
      y: Math.max((viewportHeight - initialSize.height) / 2 + stackOffset, 100),
    };
  };
  
  const [position, setPosition] = useState(getInitialPosition);
  const [size, setSize] = useState(initialSize);
  const [zIndex, setZIndex] = useState(() => 
    initialZIndex !== undefined ? initialZIndex : floatingZIndexManager.getNext()
  );
  const [isFocused, setIsFocused] = useState(false);

  const handleDragStart = () => {
    const newZ = floatingZIndexManager.getNext();
    setZIndex(newZ);
    onZIndexChange?.(newZ);
    setIsFocused(true);
  };

  const handleDragStop = (_e: any, d: { x: number; y: number }) => {
    setPosition(d);
    onPositionChange?.(d);
    setIsFocused(false); // Quitar foco cuando termina de arrastrar
  };

  const handleResizeStart = () => {
    const newZ = floatingZIndexManager.getNext();
    setZIndex(newZ);
    onZIndexChange?.(newZ);
    setIsFocused(true);
  };

  const handleResize = (_e: any, _direction: any, ref: HTMLElement) => {
    const newSize = {
      width: ref.offsetWidth,
      height: ref.offsetHeight,
    };
    setSize(newSize);
    onSizeChange?.(newSize);
  };

  const handleResizeStop = (
    _e: any,
    _direction: any,
    ref: HTMLElement,
    _delta: any,
    position: { x: number; y: number }
  ) => {
    const newSize = {
      width: ref.offsetWidth,
      height: ref.offsetHeight,
    };
    setSize(newSize);
    setPosition(position);
    onSizeChange?.(newSize);
    onPositionChange?.(position);
    setIsFocused(false); // Quitar foco cuando termina de redimensionar
  };

  return (
    <Rnd
      position={position}
      size={size}
      minWidth={minWidth}
      minHeight={minHeight}
      maxWidth={maxWidth}
      maxHeight={maxHeight}
      dragHandleClassName={dragHandleClassName}
      enableResizing={
        enableResizing
          ? {
              top: false,
              right: true,
              bottom: true,
              left: false,
              topRight: false,
              bottomRight: true,
              bottomLeft: false,
              topLeft: false,
            }
          : false
      }
      onDragStart={handleDragStart}
      onDragStop={handleDragStop}
      onResizeStart={handleResizeStart}
      onResize={handleResize}
      onResizeStop={handleResizeStop}
      style={{
        zIndex: zIndex,
        position: 'fixed',
      }}
    >
      <div
        className={`h-full w-full rounded-lg shadow-2xl border-4 transition-all flex flex-col ${
          isFocused ? focusedBorderColor + ' shadow-2xl shadow-green-500/50' : 'border-slate-200'
        } ${className}`}
        onBlur={() => setIsFocused(false)}
      >
        {children}
      </div>
    </Rnd>
  );
}

