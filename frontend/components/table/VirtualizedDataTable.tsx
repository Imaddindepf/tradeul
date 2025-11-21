/**
 * Virtualized Data Table - TanStack Table + TanStack Virtual
 * 
 * Ventajas:
 * - Renderiza solo las filas visibles (~10-20 en viewport)
 * - Escala a 10,000+ filas sin lag
 * - Mantiene todas las features (sort, resize, reorder)
 * - Smooth scrolling con overscan
 */

'use client';

import { ReactNode, useRef, useState, useEffect, CSSProperties } from 'react';
import type { Table as TanStackTable, Row } from '@tanstack/react-table';
import { flexRender } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  GripHorizontal,
  GripVertical,
  Maximize2,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from 'lucide-react';

// ============================================================================
// TYPES
// ============================================================================

interface VirtualizedDataTableProps<T> {
  table: TanStackTable<T>;
  children?: ReactNode; // Header (MarketTableLayout)
  className?: string;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  initialWidth?: number;
  initialHeight?: number;
  showResizeHandles?: boolean;
  stickyHeader?: boolean;
  emptyState?: ReactNode;
  isLoading?: boolean;
  loadingState?: ReactNode;
  onResize?: (dimensions: { width: number; height: number }) => void;
  getRowClassName?: (row: Row<T>) => string;
  
  // Virtualization config
  estimateSize?: number; // Altura estimada de cada fila
  overscan?: number; // Número de filas fuera del viewport a pre-renderizar
  enableVirtualization?: boolean; // Toggle virtualización (útil para debugging)
}

// ============================================================================
// COMPONENT
// ============================================================================

export function VirtualizedDataTable<T>({
  table,
  children,
  className = '',
  minWidth = 200,
  minHeight = 150,
  maxWidth = Infinity,
  maxHeight = Infinity,
  initialWidth,
  initialHeight = 600,
  showResizeHandles = true,
  stickyHeader = true,
  emptyState,
  isLoading = false,
  loadingState,
  onResize,
  getRowClassName,
  estimateSize = 40, // 40px por fila (ajustar según tu diseño)
  overscan = 10, // Renderizar 10 filas extra arriba/abajo
  enableVirtualization = true,
}: VirtualizedDataTableProps<T>) {
  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // State
  const [dimensions, setDimensions] = useState({
    width: initialWidth || 0,
    height: initialHeight,
  });
  const [isResizing, setIsResizing] = useState(false);
  const [resizeDirection, setResizeDirection] = useState<
    'width' | 'height' | 'both' | null
  >(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [hasUserResized, setHasUserResized] = useState(false);
  
  // Si showResizeHandles es false, observar el tamaño del contenedor padre
  useEffect(() => {
    if (showResizeHandles || !containerRef.current) return;
    
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
      }
    });
    
    resizeObserver.observe(containerRef.current);
    
    return () => resizeObserver.disconnect();
  }, [showResizeHandles]);

  // Get rows from table
  const rows = table.getRowModel().rows;
  
  // Si no tiene resize handles, usar calc para el espacio disponible
  const contentHeight = showResizeHandles 
    ? Math.max(0, dimensions.height - headerHeight)
    : undefined; // Usaremos CSS calc en el render

  // ============================================================
  // VIRTUALIZATION
  // ============================================================
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => estimateSize,
    overscan,
    enabled: enableVirtualization && rows.length > 20, // Solo virtualizar si hay muchas filas
  });

  const virtualRows = enableVirtualization && rows.length > 20
    ? rowVirtualizer.getVirtualItems()
    : rows.map((_, index) => ({ index, start: index * estimateSize, size: estimateSize }));

  const totalSize = enableVirtualization && rows.length > 20
    ? rowVirtualizer.getTotalSize()
    : rows.length * estimateSize;

  // ============================================================
  // RESIZE LOGIC (same as ResizableTable)
  // ============================================================
  const getScale = () => {
    const width = dimensions.width;
    if (width < 600) return 'xs';
    if (width < 900) return 'sm';
    if (width < 1200) return 'md';
    return 'lg';
  };

  const scale = getScale();

  // Auto-calculate initial width
  useEffect(() => {
    if (!initialWidth && containerRef.current) {
      const parentWidth = containerRef.current.parentElement?.clientWidth || 0;
      setDimensions((prev) => ({
        ...prev,
        width: parentWidth > 0 ? parentWidth : 1200,
      }));
    }
  }, [initialWidth]);

  // Sync width with container (only if user hasn't resized)
  useEffect(() => {
    if (hasUserResized) return;
    const update = () => {
      if (!containerRef.current || isResizing) return;
      const w = containerRef.current.clientWidth || 0;
      if (w > 0) {
        setDimensions((prev) => (prev.width === w ? prev : { ...prev, width: w }));
      }
    };
    update();
    const ro = new ResizeObserver(update);
    if (containerRef.current) ro.observe(containerRef.current);
    if (containerRef.current?.parentElement)
      ro.observe(containerRef.current.parentElement);
    return () => ro.disconnect();
  }, [isResizing, hasUserResized]);

  // Measure header height
  useEffect(() => {
    const measure = () => {
      const h = headerRef.current?.offsetHeight || 0;
      setHeaderHeight(h);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (headerRef.current) ro.observe(headerRef.current);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Handle resize start
  const handleResizeStart = (
    e: React.MouseEvent,
    direction: 'width' | 'height' | 'both'
  ) => {
    e.preventDefault();
    setIsResizing(true);
    setResizeDirection(direction);
    setHasUserResized(true);

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = dimensions.width;
    const startHeight = dimensions.height;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      setDimensions((prev) => {
        let newWidth = prev.width;
        let newHeight = prev.height;

        if (direction === 'width' || direction === 'both') {
          newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + deltaX));
        }

        if (direction === 'height' || direction === 'both') {
          newHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY));
        }

        const newDimensions = { width: newWidth, height: newHeight };
        onResize?.(newDimensions);
        return newDimensions;
      });
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      setResizeDirection(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Column resize handle component
  const ColumnResizeHandle = ({ header }: { header: any }) => {
    const [isHovered, setIsHovered] = useState(false);

    return (
      <div
        onMouseDown={header.getResizeHandler()}
        onTouchStart={header.getResizeHandler()}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`
          absolute right-0 top-0 h-full cursor-col-resize
          transition-all duration-200
          ${
            isHovered || header.column.getIsResizing()
              ? 'w-1 bg-blue-500'
              : 'w-px bg-slate-200 hover:bg-blue-400'
          }
          ${header.column.getIsResizing() ? 'bg-blue-600' : ''}
          group
        `}
        style={{
          userSelect: 'none',
          touchAction: 'none',
        }}
      >
        <div
          className={`
          absolute top-1/2 -translate-y-1/2 -right-1 w-2 h-12 
          flex items-center justify-center
          transition-opacity duration-200
          ${
            isHovered || header.column.getIsResizing()
              ? 'opacity-100'
              : 'opacity-0 group-hover:opacity-100'
          }
        `}
        >
          <div className="w-0.5 h-4 bg-blue-500 rounded-full"></div>
        </div>
      </div>
    );
  };

  // Auto-adjust grid span (same logic)
  useEffect(() => {
    const gridItemEl = containerRef.current?.parentElement;
    if (!gridItemEl) return;

    const gridRoot = gridItemEl.closest('[data-grid-root]') as HTMLElement | null;
    if (!gridRoot) return;

    const updateSpan = () => {
      const styles = window.getComputedStyle(gridRoot);
      const template = styles.gridTemplateColumns;
      let cols = 12;
      if (template && template.length > 0) {
        const tracks = template.split(' ').filter(Boolean);
        if (tracks.length > 0) cols = tracks.length;
      }

      const colGapPx = parseFloat(styles.columnGap || '0');
      const gridWidth = gridRoot.clientWidth;
      if (cols <= 0 || gridWidth <= 0) return;

      const colWidth = (gridWidth - colGapPx * (cols - 1)) / cols;
      const needed = Math.max(dimensions.width, minWidth);
      const span = Math.max(
        1,
        Math.min(cols, Math.ceil((needed + colGapPx) / (colWidth + colGapPx)))
      );

      gridItemEl.style.gridColumn = `span ${span} / span ${span}`;
    };

    updateSpan();
    const ro = new ResizeObserver(updateSpan);
    ro.observe(gridRoot);
    return () => ro.disconnect();
  }, [dimensions.width, minWidth]);

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <div
      ref={containerRef}
      className={`relative bg-white overflow-hidden ${className}`}
      style={
        showResizeHandles
          ? {
              width: '100%',
              maxWidth: '100%',
            }
          : {
              width: '100%',
              height: '100%',
              maxWidth: '100%',
              maxHeight: '100%',
            }
      }
    >
      {/* Header */}
      <div ref={headerRef}>{children}</div>

      {/* Table Container (scrollable) */}
      <div
        ref={scrollContainerRef}
        className="relative overflow-auto"
        style={
          showResizeHandles
            ? {
                height: contentHeight,
                maxHeight: '100%',
              }
            : {
                height: `calc(100% - ${headerHeight}px)`,
                maxHeight: '100%',
              }
        }
      >
        {isLoading ? (
          loadingState || (
            <div className="flex items-center justify-center h-full bg-slate-50">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
                <p className="text-slate-700 font-medium">Loading data...</p>
              </div>
            </div>
          )
        ) : rows.length === 0 ? (
          emptyState || (
            <div className="flex items-center justify-center h-full bg-slate-50">
              <p className="text-slate-700 font-medium">No data available</p>
            </div>
          )
        ) : (
          <table className="w-full border-collapse table-fixed">
            {/* Header */}
            <thead
              className={`bg-white border-b border-slate-200 ${
                stickyHeader ? 'sticky top-0 z-20 shadow-sm' : ''
              }`}
            >
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      draggable={!header.column.getIsResizing()}
                      onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = 'move';
                        e.dataTransfer.setData('text/plain', header.column.id);
                      }}
                      onDragOver={(e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = 'move';
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        const draggedColumnId = e.dataTransfer.getData('text/plain');
                        const targetColumnId = header.column.id;

                        if (draggedColumnId !== targetColumnId) {
                          const columnOrder = table.getState().columnOrder;
                          const currentOrder =
                            columnOrder.length > 0
                              ? columnOrder
                              : table.getAllLeafColumns().map((c) => c.id);

                          const draggedIndex = currentOrder.indexOf(draggedColumnId);
                          const targetIndex = currentOrder.indexOf(targetColumnId);

                          const newOrder = [...currentOrder];
                          newOrder.splice(draggedIndex, 1);
                          newOrder.splice(targetIndex, 0, draggedColumnId);

                          table.setColumnOrder(newOrder);
                        }
                      }}
                      className={`
                        relative text-left font-semibold text-slate-600 uppercase tracking-wider border-r border-slate-100 last:border-r-0 bg-slate-50
                        ${scale === 'xs' ? 'px-2 py-1.5 text-[10px]' : ''}
                        ${scale === 'sm' ? 'px-2.5 py-2 text-[11px]' : ''}
                        ${scale === 'md' ? 'px-3 py-2.5 text-xs' : ''}
                        ${scale === 'lg' ? 'px-4 py-3 text-xs' : ''}
                        cursor-move hover:bg-slate-100 transition-colors
                      `}
                      style={{
                        width: header.getSize(),
                        minWidth: header.column.columnDef.minSize || 50,
                        maxWidth: header.column.columnDef.maxSize || 600,
                        position: 'relative',
                      }}
                    >
                      {header.isPlaceholder ? null : (
                        <div className="flex items-center gap-2">
                          <div
                            className={
                              header.column.getCanSort()
                                ? 'cursor-pointer select-none flex items-center gap-1 hover:text-blue-600 transition-colors'
                                : 'flex items-center gap-1'
                            }
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                            {header.column.getCanSort() && (
                              <span className="ml-1">
                                {{
                                  asc: <ArrowUp className="w-3 h-3" />,
                                  desc: <ArrowDown className="w-3 h-3" />,
                                }[header.column.getIsSorted() as string] ?? (
                                  <ArrowUpDown className="w-3 h-3 opacity-40" />
                                )}
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Column Resize Handle */}
                      {header.column.getCanResize() && (
                        <ColumnResizeHandle header={header} />
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>

            {/* Body (VIRTUALIZED) */}
            <tbody
              className="divide-y divide-slate-100 bg-white"
              style={{
                height: `${totalSize}px`, // Total height for scrollbar
                position: 'relative',
              }}
            >
              {virtualRows.map((virtualRow) => {
                const row = rows[virtualRow.index];
                if (!row) return null;

                return (
                  <tr
                    key={row.id}
                    data-index={virtualRow.index}
                    className={`hover:bg-slate-50 transition-colors duration-150 border-b border-slate-100 ${
                      getRowClassName ? getRowClassName(row) : ''
                    }`}
                    style={{
                      position: enableVirtualization && rows.length > 20 ? 'absolute' : 'relative',
                      top: enableVirtualization && rows.length > 20 ? 0 : undefined,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: enableVirtualization && rows.length > 20
                        ? `translateY(${virtualRow.start}px)`
                        : undefined,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td
                        key={cell.id}
                        className={`
                          text-slate-900
                          ${scale === 'xs' ? 'px-2 py-1.5 text-[11px]' : ''}
                          ${scale === 'sm' ? 'px-2.5 py-2 text-xs' : ''}
                          ${scale === 'md' ? 'px-3 py-2.5 text-sm' : ''}
                          ${scale === 'lg' ? 'px-4 py-3 text-sm' : ''}
                        `}
                        style={{
                          width: cell.column.getSize(),
                          maxWidth: cell.column.getSize(),
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Resize Handles (same as ResizableTable) */}
      {showResizeHandles && (
        <>
          {/* Bottom-right corner */}
          <div
            className={`
              absolute bottom-0 right-0 w-3 h-3 cursor-nwse-resize
              bg-blue-500 hover:bg-blue-600 transition-all duration-200 rounded-tl
              ${isResizing && resizeDirection === 'both' ? 'bg-blue-600 w-4 h-4' : ''}
            `}
            onMouseDown={(e) => handleResizeStart(e, 'both')}
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-2 h-2 border-b-2 border-r-2 border-white opacity-70"></div>
            </div>
          </div>

          {/* Bottom edge */}
          <div
            className={`
              absolute bottom-0 left-0 right-3 h-1 cursor-ns-resize
              hover:bg-blue-500 transition-all duration-200
              ${isResizing && resizeDirection === 'height' ? 'bg-blue-600 h-1.5' : 'bg-transparent'}
            `}
            onMouseDown={(e) => handleResizeStart(e, 'height')}
          >
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-1 bg-slate-300 rounded-t hover:bg-blue-500 transition-colors"></div>
          </div>

          {/* Right edge */}
          <div
            className={`
              absolute top-0 right-0 bottom-3 w-1 cursor-ew-resize
              hover:bg-blue-500 transition-all duration-200
              ${isResizing && resizeDirection === 'width' ? 'bg-blue-600 w-1.5' : 'bg-transparent'}
            `}
            onMouseDown={(e) => handleResizeStart(e, 'width')}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-slate-300 rounded-l hover:bg-blue-500 transition-colors"></div>
          </div>
        </>
      )}

      {/* Resize indicator */}
      {isResizing && (
        <div className="absolute top-3 right-3 bg-white text-slate-700 text-xs font-mono px-3 py-1.5 shadow-xl border border-slate-200 rounded z-30">
          <span className="text-blue-600 font-semibold">
            {Math.round(dimensions.width)}
          </span>
          <span className="text-slate-400 mx-1">×</span>
          <span className="text-blue-600 font-semibold">
            {Math.round(dimensions.height)}
          </span>
        </div>
      )}

      {/* Virtualization info (development only) */}
      {process.env.NODE_ENV === 'development' && enableVirtualization && rows.length > 20 && (
        <div className="absolute bottom-3 left-3 bg-black/75 text-white text-xs font-mono px-2 py-1 rounded z-30">
          <span className="text-green-400">{virtualRows.length}</span>
          <span className="text-white/60 mx-1">/</span>
          <span className="text-white">{rows.length}</span>
          <span className="text-white/60 ml-1">rows</span>
        </div>
      )}

      {/* No-select overlay when resizing */}
      {isResizing && (
        <div className="absolute inset-0 z-10" style={{ cursor: 'inherit' }} />
      )}
    </div>
  );
}

