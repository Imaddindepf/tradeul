'use client';

import CategoryTableV2 from './CategoryTableV2';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

interface ScannerTableContentProps {
    categoryId: string;
    categoryName: string;
}

/**
 * Contenido de una tabla del scanner para usar dentro de FloatingWindow
 * 
 * El cierre se maneja internamente usando el contexto de FloatingWindow,
 * buscando la ventana por título en el momento del click (evita stale closures).
 */
export function ScannerTableContent({ categoryId, categoryName }: ScannerTableContentProps) {
    const { windows, closeWindow } = useFloatingWindow();
    
    // Buscar y cerrar la ventana por título en el momento del click
    const handleClose = () => {
        const title = `Scanner: ${categoryName}`;
        const win = windows.find(w => w.title === title);
        
        if (win) {
            closeWindow(win.id);
        } else {
            // Fallback: buscar por nombre parcial
            const fallbackWin = windows.find(w => 
                w.title.includes(categoryName) || w.title.includes(categoryId)
            );
            if (fallbackWin) {
                closeWindow(fallbackWin.id);
            }
        }
    };
    
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

