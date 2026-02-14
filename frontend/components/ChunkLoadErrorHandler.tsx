'use client';

import { useEffect } from 'react';

/**
 * ChunkLoadErrorHandler
 * 
 * Maneja errores de carga de chunks de Next.js que ocurren cuando:
 * - Se hace un nuevo deploy mientras el usuario tiene la página abierta
 * - Los chunks viejos ya no existen en el servidor
 * 
 * Solución: Recargar automáticamente la página para obtener los nuevos chunks
 */
export function ChunkLoadErrorHandler() {
  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      const { message } = event;
      
      // Detectar ChunkLoadError
      const isChunkLoadError = 
        message?.includes('ChunkLoadError') ||
        message?.includes('Loading chunk') ||
        message?.includes('Failed to fetch dynamically imported module');
      
      if (isChunkLoadError) {
        console.warn('[ChunkLoadError] Detectado error de chunk, recargando página...');
        
        // Evitar loop infinito: solo recargar una vez cada 10 segundos
        const lastReload = sessionStorage.getItem('lastChunkErrorReload');
        const now = Date.now();
        
        if (!lastReload || now - parseInt(lastReload, 10) > 10000) {
          sessionStorage.setItem('lastChunkErrorReload', now.toString());
          
          // Recargar sin usar cache (force reload)
          window.location.reload();
        } else {
          console.error('[ChunkLoadError] Múltiples errores detectados, evitando loop de recarga');
        }
      }
    };

    const handleRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      
      // Detectar ChunkLoadError en promesas rechazadas
      const isChunkLoadError =
        reason?.name === 'ChunkLoadError' ||
        reason?.message?.includes('ChunkLoadError') ||
        reason?.message?.includes('Loading chunk') ||
        reason?.message?.includes('Failed to fetch dynamically imported module');
      
      if (isChunkLoadError) {
        console.warn('[ChunkLoadError] Detectado error de chunk en promise, recargando página...');
        
        const lastReload = sessionStorage.getItem('lastChunkErrorReload');
        const now = Date.now();
        
        if (!lastReload || now - parseInt(lastReload, 10) > 10000) {
          sessionStorage.setItem('lastChunkErrorReload', now.toString());
          window.location.reload();
        }
      }
    };

    // Escuchar errores globales
    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleRejection);

    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  }, []);

  return null;
}
