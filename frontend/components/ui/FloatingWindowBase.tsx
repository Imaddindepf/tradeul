'use client';

import { useState, useRef, ReactNode, MouseEvent, useCallback, memo, useEffect } from 'react';
import { floatingZIndexManager, floatingFocusManager, Z_INDEX } from '@/lib/z-index';

export interface FloatingWindowBaseProps {
  children: ReactNode;
  /** Id de la ventana en el contexto, usado para el foco global */
  windowId?: string;
  dragHandleClassName?: string;
  initialSize?: { width: number; height: number };
  initialPosition?: { x: number; y: number };
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  enableResizing?: boolean;
  className?: string;
  focusedBorderColor?: string;
  initialZIndex?: number;
  stackOffset?: number; // Offset para posicionar múltiples ventanas escalonadas
  /**
   * When true the window cannot be dragged nor resized (resize handle hidden).
   * Used by the dashboard "Lock Movement" toggle in the bottom toolbar.
   */
  lockMovement?: boolean;
  onZIndexChange?: (zIndex: number) => void;
  onSizeChange?: (size: { width: number; height: number }) => void;
  onPositionChange?: (position: { x: number; y: number }) => void;
}

/**
 * Ventana flotante optimizada con drag & resize nativos
 * - Position fixed sin transform
 * - Durante drag/resize solo se actualiza estado LOCAL; el contexto padre
 *   (updateWindow) se notifica al soltar. Así evitamos un storm de
 *   re-renders que en ERN y otras ventanas pesadas llegaba a React #185
 *   (maximum update depth) al agrandar/achicar varias veces.
 */
function FloatingWindowBaseComponent({
  children,
  windowId,
  dragHandleClassName = 'window-drag-handle',
  initialSize = { width: 800, height: 600 },
  initialPosition,
  minWidth = 400,
  minHeight = 300,
  maxWidth = 1600,
  maxHeight = 1000,
  enableResizing = true,
  className = '',
  initialZIndex,
  stackOffset = 0,
  lockMovement = false,
  onZIndexChange,
  onSizeChange,
  onPositionChange,
}: FloatingWindowBaseProps) {
  // Posición inicial segura que respeta los límites del navbar
  const getInitialPosition = () => {
    const navbarHeight = 44; // h-11 (navbar compacto)
    const minY = navbarHeight + 6; // 50px - LÍMITE: debajo del navbar
    const minX = 10; // Margen desde el borde izquierdo

    if (initialPosition) {
      return {
        x: Math.max(minX, initialPosition.x),
        y: Math.max(minY, initialPosition.y),
      };
    }

    return {
      x: minX + stackOffset,
      y: minY + stackOffset,
    };
  };

  const [position, setPosition] = useState(getInitialPosition);
  const [size, setSize] = useState(initialSize);
  const [zIndex, setZIndex] = useState(initialZIndex ?? Z_INDEX.FLOATING_TABLES_BASE);
  const [isFocused, setIsFocused] = useState(
    () => windowId !== undefined && floatingFocusManager.getCurrent() === windowId,
  );

  const isDraggingRef = useRef(false);
  const isResizingRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef(size);
  const positionRef = useRef(position);
  const zIndexRef = useRef(zIndex);
  sizeRef.current = size;
  positionRef.current = position;
  zIndexRef.current = zIndex;

  // Callbacks estables vía ref — evita que bringToFront cambie de identidad
  // en cada render del padre (onSizeChange/onZIndexChange no memoizados) y
  // re-enganche el listener de captura en mitad de un resize.
  const onZIndexChangeRef = useRef(onZIndexChange);
  const onSizeChangeRef = useRef(onSizeChange);
  const onPositionChangeRef = useRef(onPositionChange);
  onZIndexChangeRef.current = onZIndexChange;
  onSizeChangeRef.current = onSizeChange;
  onPositionChangeRef.current = onPositionChange;

  // Sincronizar zIndex desde el contexto (p. ej. openWindow vuelve a subir la ventana).
  // NO llamar a focus() aquí: eso re-notificaba a todas las ventanas y, combinado
  // con updateWindow en cada mousemove de resize, podía encadenar updates hasta #185.
  useEffect(() => {
    if (initialZIndex !== undefined && initialZIndex !== zIndexRef.current) {
      setZIndex(initialZIndex);
    }
  }, [initialZIndex]);

  // Suscribirse al foco global: solo una ventana puede estar enfocada a la vez
  useEffect(() => {
    if (windowId === undefined) return;
    setIsFocused(floatingFocusManager.getCurrent() === windowId);
    const unsubscribe = floatingFocusManager.subscribe((focusedId) => {
      setIsFocused(focusedId === windowId);
    });
    return unsubscribe;
  }, [windowId]);

  // Establecer z-index solo en el cliente para evitar mismatch SSR (primera vez)
  useEffect(() => {
    if (initialZIndex === undefined && zIndexRef.current === Z_INDEX.FLOATING_TABLES_BASE) {
      const newZ = floatingZIndexManager.getNext();
      setZIndex(newZ);
      onZIndexChangeRef.current?.(newZ);
    }
  }, []); // Solo ejecutar una vez al montar

  // Traer al frente — no-op si ya somos la ventana top + enfocada.
  const bringToFront = useCallback(() => {
    const alreadyFocused = windowId !== undefined && floatingFocusManager.getCurrent() === windowId;
    const alreadyTop = zIndexRef.current === floatingZIndexManager.getCurrent();
    if (alreadyFocused && alreadyTop) return;

    const newZ = floatingZIndexManager.getNext();
    setZIndex(newZ);
    onZIndexChangeRef.current?.(newZ);
    if (windowId !== undefined) {
      floatingFocusManager.focus(windowId);
    } else {
      setIsFocused(true);
    }
  }, [windowId]);

  // Drag: estado local en mousemove; persistir posición al soltar.
  const handleDragStart = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (lockMovement) return;
    const target = e.target as HTMLElement;
    if (!target.closest(`.${dragHandleClassName}`)) return;

    e.preventDefault();
    e.stopPropagation();

    bringToFront();
    isDraggingRef.current = true;

    const startX = e.clientX;
    const startY = e.clientY;
    const startPosX = positionRef.current.x;
    const startPosY = positionRef.current.y;
    const dragWidth = sizeRef.current.width;
    let latestPos = positionRef.current;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      if (!isDraggingRef.current) return;

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      let newX = startPosX + deltaX;
      let newY = startPosY + deltaY;

      const navbarHeight = 44;
      const minX = 10;
      const minY = navbarHeight + 6;
      const maxX = window.innerWidth - dragWidth - 10;
      const maxY = window.innerHeight - 100;

      newX = Math.max(minX, Math.min(maxX, newX));
      newY = Math.max(minY, Math.min(maxY, newY));

      latestPos = { x: newX, y: newY };
      setPosition(latestPos);
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      onPositionChangeRef.current?.(latestPos);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [dragHandleClassName, bringToFront, lockMovement]);

  // Resize: estado local en mousemove; persistir tamaño al soltar.
  const handleResizeStart = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (lockMovement) return;
    e.preventDefault();
    e.stopPropagation();

    // bringToFront ya lo hace el listener de captura del contenedor.
    isResizingRef.current = true;

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = sizeRef.current.width;
    const startHeight = sizeRef.current.height;
    let latestSize = sizeRef.current;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      if (!isResizingRef.current) return;

      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      latestSize = {
        width: Math.max(minWidth, Math.min(maxWidth, startWidth + deltaX)),
        height: Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY)),
      };

      setSize(latestSize);
    };

    const handleMouseUp = () => {
      isResizingRef.current = false;
      onSizeChangeRef.current?.(latestSize);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [minWidth, minHeight, maxWidth, maxHeight, lockMovement]);

  // Capturar click en fase de captura para traer al frente SIEMPRE
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleCapture = () => {
      bringToFront();
    };

    container.addEventListener('mousedown', handleCapture, { capture: true });
    return () => container.removeEventListener('mousedown', handleCapture, { capture: true });
  }, [bringToFront]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'fixed',
        top: `${position.y}px`,
        left: `${position.x}px`,
        width: `${size.width}px`,
        height: `${size.height}px`,
        zIndex: zIndex,
      }}
      className={`rounded-lg shadow-md border transition-shadow flex flex-col ${isFocused ? 'border-primary shadow-sm' : 'border-border'
        } ${className}`}
      onMouseDown={handleDragStart}
    >
      <div className="h-full w-full overflow-hidden flex flex-col">
        {children}
      </div>

      {enableResizing && !lockMovement && (
        <div
          onMouseDown={handleResizeStart}
          className="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize hover:bg-primary/20 transition-colors z-[100]"
          style={{
            borderRight: '5px solid transparent',
            borderBottom: '5px solid transparent',
            borderTop: '5px solid var(--color-border)',
            borderLeft: '5px solid var(--color-border)',
          }}
        />
      )}
    </div>
  );
}

export const FloatingWindowBase = memo(FloatingWindowBaseComponent);
