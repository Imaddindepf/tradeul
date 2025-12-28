'use client';

import TickersWithNewsTable from './TickersWithNewsTable';
import { useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';

interface TickersWithNewsContentProps {
    title: string;
}

/**
 * Wrapper para TickersWithNewsTable que maneja el cierre de ventana flotante.
 * Usa useCloseCurrentWindow() para cerrar su propia ventana automáticamente.
 */
export function TickersWithNewsContent({ title }: TickersWithNewsContentProps) {
    const closeCurrentWindow = useCloseCurrentWindow();
    
    return (
        <div className="h-full w-full overflow-hidden flex flex-col bg-white">
            <TickersWithNewsTable
                title={title}
                onClose={closeCurrentWindow}
            />
        </div>
    );
}

