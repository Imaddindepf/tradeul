'use client';

import { useState } from 'react';
import { Rnd } from 'react-rnd';
import CategoryTableV2 from './CategoryTableV2';

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

export function DraggableTable({ category, index, zIndex, onBringToFront }: DraggableTableProps) {
  const [position, setPosition] = useState({
    x: 24 + (index * 40), // Offset inicial escalonado
    y: 24 + (index * 40),
  });
  
  const [size, setSize] = useState({
    width: 800,
    height: 480,
  });

  const [isFocused, setIsFocused] = useState(false);

  const handleFocus = () => {
    onBringToFront(); // Traer al frente cuando se hace click
    setIsFocused(true);
  };

  return (
    <Rnd
      default={{
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
      }}
      minWidth={400}
      minHeight={200}
      maxWidth={2000}
      maxHeight={1200}
      bounds="parent"
      dragHandleClassName="table-drag-handle"
      enableResizing={{
        top: false,
        right: true,
        bottom: true,
        left: false,
        topRight: false,
        bottomRight: true,
        bottomLeft: false,
        topLeft: false,
      }}
      onDragStart={handleFocus}
      onDragStop={(e, d) => {
        setPosition({ x: d.x, y: d.y });
      }}
      onResizeStart={handleFocus}
      onResize={(e, direction, ref) => {
        // Actualizar tamaño en tiempo real mientras se redimensiona
        setSize({
          width: ref.offsetWidth,
          height: ref.offsetHeight,
        });
      }}
      onResizeStop={(e, direction, ref, delta, position) => {
        setSize({
          width: ref.offsetWidth,
          height: ref.offsetHeight,
        });
        setPosition(position);
      }}
      onMouseDown={handleFocus} // También traer al frente al hacer click
      style={{
        zIndex: zIndex,
      }}
    >
      <div 
        className={`h-full w-full shadow-lg rounded-lg overflow-hidden border-2 transition-all ${
          isFocused ? 'border-blue-500 shadow-2xl' : 'border-slate-200'
        }`}
        onBlur={() => setIsFocused(false)}
      >
        <CategoryTableV2 
          title={category.name} 
          listName={category.id}
          tableWidth={size.width}
          tableHeight={size.height}
        />
      </div>
    </Rnd>
  );
}

