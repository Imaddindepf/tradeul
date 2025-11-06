'use client';

import { useState, useRef, useEffect } from 'react';
import { Settings, Eye, EyeOff, GripVertical, X } from 'lucide-react';
import type { Table as TanStackTable } from '@tanstack/react-table';

interface TableSettingsProps<T> {
  table: TanStackTable<T>;
}

export function TableSettings<T>({ table }: TableSettingsProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'visibility' | 'order'>('visibility');
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const allColumns = table.getAllLeafColumns();
  const columnOrder = table.getState().columnOrder;
  const currentOrder = columnOrder.length > 0 
    ? columnOrder 
    : allColumns.map(c => c.id);

  // Cerrar al hacer click fuera
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

  const handleDragStart = (columnId: string) => {
    setDraggedColumn(columnId);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

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

  return (
    <div className="relative">
      {/* Botón de configuración */}
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="p-1.5 hover:bg-blue-50 rounded transition-colors text-slate-600 hover:text-blue-600"
        title="Configurar tabla"
      >
        <Settings className="w-4 h-4" />
      </button>

      {/* Panel desplegable */}
      {isOpen && (
        <div
          ref={panelRef}
          className="absolute right-0 top-full mt-1 w-72 bg-white shadow-xl rounded-lg border border-gray-200 z-50"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
            <div className="flex items-center gap-1.5">
              <Settings className="w-3.5 h-3.5 text-blue-600" />
              <h3 className="text-xs font-bold text-gray-900">Configurar Tabla</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-0.5 hover:bg-gray-200 rounded transition-colors"
            >
              <X className="w-3.5 h-3.5 text-gray-500" />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-200 bg-white">
            <button
              onClick={() => setActiveTab('visibility')}
              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                activeTab === 'visibility'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <Eye className="w-3 h-3 inline mr-1" />
              Columnas
            </button>
            <button
              onClick={() => setActiveTab('order')}
              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                activeTab === 'order'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <GripVertical className="w-3 h-3 inline mr-1" />
              Orden
            </button>
          </div>

          {/* Content */}
          <div className="max-h-80 overflow-y-auto p-2">
            {activeTab === 'visibility' && (
              <div className="space-y-1">
                {allColumns.map((column) => {
                  const canHide = column.getCanHide();
                  if (!canHide) return null;

                  return (
                    <label
                      key={column.id}
                      className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={column.getIsVisible()}
                        onChange={column.getToggleVisibilityHandler()}
                        className="w-3.5 h-3.5 text-blue-600 rounded focus:ring-1 focus:ring-blue-500"
                      />
                      <span className="flex-1 text-xs font-medium text-gray-700">
                        {typeof column.columnDef.header === 'string'
                          ? column.columnDef.header
                          : column.id}
                      </span>
                      {column.getIsVisible() ? (
                        <Eye className="w-3 h-3 text-green-500" />
                      ) : (
                        <EyeOff className="w-3 h-3 text-gray-400" />
                      )}
                    </label>
                  );
                })}
              </div>
            )}

            {activeTab === 'order' && (
              <div className="space-y-1">
                {currentOrder.map((columnId, index) => {
                  const column = allColumns.find(c => c.id === columnId);
                  if (!column) return null;

                  return (
                    <div
                      key={columnId}
                      draggable
                      onDragStart={() => handleDragStart(columnId)}
                      onDragOver={handleDragOver}
                      onDrop={() => handleDrop(columnId)}
                      className={`flex items-center gap-2 p-2 bg-white border border-gray-200 rounded cursor-move transition-all ${
                        draggedColumn === columnId ? 'opacity-50 scale-95' : 'hover:shadow-sm hover:border-blue-300'
                      }`}
                    >
                      <GripVertical className="w-3 h-3 text-gray-400 flex-shrink-0" />
                      <span className="flex-1 text-xs font-medium text-gray-700">
                        {typeof column.columnDef.header === 'string'
                          ? column.columnDef.header
                          : column.id}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">#{index + 1}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-2 border-t border-gray-200 bg-gray-50">
            <button
              onClick={() => {
                table.resetColumnVisibility();
                table.setColumnOrder([]);
              }}
              className="w-full px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
            >
              Restaurar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
