/**
 * Hook para sincronizar preferencias de Catalyst Alerts con el servidor
 * Se activa cuando el usuario está autenticado y cambian las preferencias
 */

import { useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useCatalystAlertsStore } from '@/stores/useCatalystAlertsStore';

export function useCatalystAlertsSync() {
  const { isSignedIn, getToken } = useAuth();
  
  const enabled = useCatalystAlertsStore((s) => s.enabled);
  const criteria = useCatalystAlertsStore((s) => s.criteria);
  const syncToServer = useCatalystAlertsStore((s) => s.syncToServer);
  const loadFromServer = useCatalystAlertsStore((s) => s.loadFromServer);
  
  // Flag para evitar sync en el primer render
  const isFirstRender = useRef(true);
  const hasLoadedFromServer = useRef(false);
  
  // Cargar preferencias del servidor cuando el usuario se autentica
  useEffect(() => {
    if (!isSignedIn || hasLoadedFromServer.current) return;
    
    const loadPrefs = async () => {
      try {
        const token = await getToken();
        if (token) {
          await loadFromServer(token);
          hasLoadedFromServer.current = true;
        }
      } catch (error) {
        console.error('[CatalystAlertsSync] Failed to load:', error);
      }
    };
    
    loadPrefs();
  }, [isSignedIn, getToken, loadFromServer]);
  
  // Sincronizar al servidor cuando cambian las preferencias
  useEffect(() => {
    // Ignorar el primer render para no hacer sync innecesario
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    
    if (!isSignedIn) return;
    
    // Debounce para evitar múltiples syncs
    const timeoutId = setTimeout(async () => {
      try {
        const token = await getToken();
        if (token) {
          await syncToServer(token);
        }
      } catch (error) {
        console.error('[CatalystAlertsSync] Failed to sync:', error);
      }
    }, 1000); // Esperar 1 segundo después del último cambio
    
    return () => clearTimeout(timeoutId);
  }, [isSignedIn, enabled, criteria, getToken, syncToServer]);
}


