'use client';

import { memo } from 'react';
import CategoryTableV2 from './CategoryTableV2';
import { FloatingWindowBase } from '@/components/ui/FloatingWindowBase';

interface DraggableTableProps {
  category: {
    id: string;
    name: string;
    description: string;
  };
  index: number;
  onClose?: () => void;
}

/**
 * Tabla arrastrable del scanner - Optimizada
 */
function DraggableTableComponent({ category, index, onClose }: DraggableTableProps) {
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
    >
      <CategoryTableV2 
        title={category.name} 
        listName={category.id}
        onClose={onClose}
      />
    </FloatingWindowBase>
  );
}

export const DraggableTable = memo(DraggableTableComponent);
