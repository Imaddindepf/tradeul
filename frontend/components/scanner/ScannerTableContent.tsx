'use client';

import { memo, useCallback } from 'react';
import CategoryTableV2 from './CategoryTableV2';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

interface ScannerTableContentProps {
    categoryId: string;
    categoryName: string;
    onClose?: () => void;
}

/**
 * Contenido de una tabla del scanner para usar dentro de FloatingWindow
 * Este componente NO incluye el wrapper FloatingWindowBase
 * 
 * Si no se proporciona onClose, el componente se auto-cierra buscando
 * su ventana por título en el contexto de ventanas flotantes.
 */
function ScannerTableContentComponent({ categoryId, categoryName, onClose }: ScannerTableContentProps) {
    const { windows, closeWindow } = useFloatingWindow();
    
    // Si no se proporciona onClose, crear uno que cierre la ventana por título
    const handleClose = useCallback(() => {
        if (onClose) {
            onClose();
        } else {
            // Buscar la ventana por título y cerrarla
            const title = `Scanner: ${categoryName}`;
            const win = windows.find(w => w.title === title);
            if (win) {
                closeWindow(win.id);
            }
        }
    }, [onClose, categoryName, windows, closeWindow]);
    
    return (
        <div className="h-full w-full overflow-hidden flex flex-col bg-white">
            <CategoryTableV2
                title={categoryName}
                listName={categoryId}
                onClose={handleClose}
            />
        </div>
    );
}

export const ScannerTableContent = memo(ScannerTableContentComponent);

