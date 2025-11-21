'use client';

import { useState } from 'react';
import CategoryTableV2 from './CategoryTableV2';
import { FloatingWindowBase } from '@/components/ui/FloatingWindowBase';

interface DraggableTableProps {
  category: {
    id: string;
    name: string;
    description: string;
  };
  index: number;
  zIndex: number;
  onBringToFront: () => void;
}

/**
 * Tabla arrastrable del scanner
 * Ahora usa el componente base FloatingWindowBase
 */
export function DraggableTable({ category, index }: DraggableTableProps) {
  const [size, setSize] = useState({ width: 800, height: 480 });
  
  return (
    <FloatingWindowBase
      dragHandleClassName="table-drag-handle"
      initialSize={{ width: 800, height: 480 }}
      minWidth={400}
      minHeight={200}
      maxWidth={2000}
      maxHeight={1200}
      enableResizing={true}
      stackOffset={index * 40}
      className="bg-white"
      onSizeChange={setSize}
    >
      <CategoryTableV2 
        title={category.name} 
        listName={category.id}
      />
    </FloatingWindowBase>
  );
}
