'use client';

import { memo } from 'react';
import CategoryTableV2 from './CategoryTableV2';

interface ScannerTableContentProps {
  categoryId: string;
  categoryName: string;
  onClose?: () => void;
}

/**
 * Contenido de una tabla del scanner para usar dentro de FloatingWindow
 * Este componente NO incluye el wrapper FloatingWindowBase
 */
function ScannerTableContentComponent({ categoryId, categoryName, onClose }: ScannerTableContentProps) {
  return (
    <div className="h-full w-full overflow-hidden flex flex-col bg-white">
      <CategoryTableV2 
        title={categoryName} 
        listName={categoryId}
        onClose={onClose}
      />
    </div>
  );
}

export const ScannerTableContent = memo(ScannerTableContentComponent);

