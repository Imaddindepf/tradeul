'use client';

import TickersWithNewsTable from './TickersWithNewsTable';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

interface TickersWithNewsContentProps {
    title: string;
}

/**
 * Wrapper para TickersWithNewsTable que maneja el cierre de ventana flotante.
 * Similar a ScannerTableContent, busca la ventana por título en el momento del click.
 */
export function TickersWithNewsContent({ title }: TickersWithNewsContentProps) {
    const { windows, closeWindow } = useFloatingWindow();
    
    // Buscar y cerrar la ventana por título en el momento del click
    const handleClose = () => {
        const windowTitle = `Scanner: ${title}`;
        const win = windows.find(w => w.title === windowTitle);
        
        if (win) {
            closeWindow(win.id);
        } else {
            // Fallback: buscar por nombre parcial
            const fallbackWin = windows.find(w => 
                w.title.includes(title) || w.title.includes('With News') || w.title.includes('with_news')
            );
            if (fallbackWin) {
                closeWindow(fallbackWin.id);
            }
        }
    };
    
    return (
        <div className="h-full w-full overflow-hidden flex flex-col bg-white">
            <TickersWithNewsTable
                title={title}
                onClose={handleClose}
            />
        </div>
    );
}

