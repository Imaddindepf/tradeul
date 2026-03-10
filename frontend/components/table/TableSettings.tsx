'use client';

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { Table as TanStackTable } from '@tanstack/react-table';
import { Z_INDEX } from '@/lib/z-index';

interface TableSettingsProps<T> {
  table: TanStackTable<T>;
  fontFamily?: string;
  onResetToDefaults?: () => void;
}

export function TableSettings<T>({ table, fontFamily, onResetToDefaults }: TableSettingsProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'columns' | 'order'>('columns');
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const [panelPosition, setPanelPosition] = useState({ top: 0, right: 0 });
  const [mounted, setMounted] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPanelPosition({
        top: rect.bottom + 4,
        right: window.innerWidth - rect.right,
      });
    }
  }, [isOpen]);

  const allColumns = table.getAllLeafColumns();
  const columnOrder = table.getState().columnOrder;
  const currentOrder = columnOrder.length > 0
    ? columnOrder
    : allColumns.map(c => c.id);

  const visibleCount = allColumns.filter(c => c.getIsVisible()).length;
  const totalCount = allColumns.filter(c => c.getCanHide()).length;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        isOpen &&
        panelRef.current &&
        buttonRef.current &&
        !panelRef.current.contains(event.target as Node) &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleDrop = (targetColumnId: string) => {
    if (!draggedColumn || draggedColumn === targetColumnId) return;
    const newOrder = [...currentOrder];
    const draggedIndex = newOrder.indexOf(draggedColumn);
    const targetIndex = newOrder.indexOf(targetColumnId);
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, draggedColumn);
    table.setColumnOrder(newOrder);
    setDraggedColumn(null);
  };

  const getColumnLabel = (column: typeof allColumns[0]) =>
    typeof column.columnDef.header === 'string' ? column.columnDef.header : column.id;

  const panelContent = isOpen && mounted && (
    <div
      ref={panelRef}
      className="fixed w-64 bg-surface shadow-lg rounded border border-border"
      style={{
        top: `${panelPosition.top}px`,
        right: `${panelPosition.right}px`,
        zIndex: Z_INDEX.TABLE_SETTINGS_POPOVER,
        fontFamily,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <span className="text-foreground font-medium" style={{ fontSize: '12px' }}>
          Columns
        </span>
        <span className="text-muted-fg" style={{ fontSize: '10px' }}>
          {visibleCount}/{totalCount}
        </span>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border-subtle">
        <button
          onClick={() => setActiveTab('columns')}
          className={`flex-1 py-1.5 transition-colors ${
            activeTab === 'columns'
              ? 'text-primary border-b-2 border-primary'
              : 'text-muted-fg hover:text-foreground'
          }`}
          style={{ fontSize: '11px' }}
        >
          Visibility
        </button>
        <button
          onClick={() => setActiveTab('order')}
          className={`flex-1 py-1.5 transition-colors ${
            activeTab === 'order'
              ? 'text-primary border-b-2 border-primary'
              : 'text-muted-fg hover:text-foreground'
          }`}
          style={{ fontSize: '11px' }}
        >
          Order
        </button>
      </div>

      {/* Content */}
      <div className="max-h-72 overflow-y-auto py-1">
        {activeTab === 'columns' && (
          <div>
            {allColumns.map((column) => {
              if (!column.getCanHide()) return null;
              const isVisible = column.getIsVisible();
              return (
                <label
                  key={column.id}
                  className="flex items-center gap-2 px-3 py-1 cursor-pointer hover:bg-surface-hover transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={isVisible}
                    onChange={column.getToggleVisibilityHandler()}
                    className="w-3 h-3 rounded border-border text-primary focus:ring-0 focus:ring-offset-0"
                  />
                  <span
                    className={`flex-1 ${isVisible ? 'text-foreground' : 'text-muted-fg'}`}
                    style={{ fontSize: '11px' }}
                  >
                    {getColumnLabel(column)}
                  </span>
                </label>
              );
            })}
          </div>
        )}

        {activeTab === 'order' && (
          <div>
            {currentOrder.map((columnId, index) => {
              const column = allColumns.find(c => c.id === columnId);
              if (!column) return null;
              return (
                <div
                  key={columnId}
                  draggable
                  onDragStart={() => setDraggedColumn(columnId)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => handleDrop(columnId)}
                  className={`flex items-center gap-2 px-3 py-1.5 cursor-grab transition-all ${
                    draggedColumn === columnId
                      ? 'opacity-40'
                      : 'hover:bg-[var(--color-table-row-hover)]'
                  }`}
                >
                  <span className="text-muted-fg/50 select-none" style={{ fontSize: '10px' }}>
                    ⠿
                  </span>
                  <span className="flex-1 text-foreground" style={{ fontSize: '11px' }}>
                    {getColumnLabel(column)}
                  </span>
                  <span className="text-muted-fg tabular-nums" style={{ fontSize: '10px' }}>
                    {index + 1}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-border-subtle">
        <button
          onClick={() => {
            if (onResetToDefaults) {
              onResetToDefaults();
            } else {
              table.resetColumnVisibility();
            }
            table.setColumnOrder([]);
          }}
          className="w-full py-1 rounded border border-border text-foreground hover:bg-[var(--color-table-row-hover)] transition-colors"
          style={{ fontSize: '11px' }}
        >
          Reset defaults
        </button>
      </div>
    </div>
  );

  return (
    <>
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className={`px-2 py-0.5 rounded border transition-colors ${
          isOpen
            ? 'border-primary text-primary'
            : 'border-border text-foreground/80 hover:text-foreground hover:border-border-subtle'
        }`}
        style={{ fontSize: '11px', fontFamily }}
        title="Configure columns"
      >
        Columns
      </button>

      {mounted && typeof document !== 'undefined' && panelContent &&
        createPortal(panelContent, document.getElementById('portal-root')!)}
    </>
  );
}
