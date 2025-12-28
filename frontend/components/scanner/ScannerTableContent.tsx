'use client';

import CategoryTableV2 from './CategoryTableV2';
import { useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';

interface ScannerTableContentProps {
    categoryId: string;
    categoryName: string;
}

/**
 * Contenido de una tabla del scanner para usar dentro de FloatingWindow.
 * Usa useCloseCurrentWindow() para cerrar su propia ventana automáticamente.
 */
export function ScannerTableContent({ categoryId, categoryName }: ScannerTableContentProps) {
    const closeCurrentWindow = useCloseCurrentWindow();

    return (
        <div className="h-full w-full overflow-hidden flex flex-col bg-white">
            <CategoryTableV2
                title={categoryName}
                listName={categoryId}
                onClose={closeCurrentWindow}
            />
        </div>
    );
}

