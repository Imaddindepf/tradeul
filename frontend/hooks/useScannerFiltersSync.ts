/**
 * Hook para sincronizar filtros del scanner con la BD
 * 
 * Conecta useFiltersStore con useUserPreferencesStore.savedFilters
 * que a su vez se sincroniza con la BD via useClerkSync
 */

import { useEffect, useRef } from 'react';
import { useFiltersStore } from '@/stores/useFiltersStore';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

const SCANNER_FILTERS_KEY = 'scanner';

export function useScannerFiltersSync() {
  const activeFilters = useFiltersStore((s) => s.activeFilters);
  const setAllFilters = useFiltersStore((s) => s.setAllFilters);
  
  const savedFilters = useUserPreferencesStore((s) => s.savedFilters);
  const saveFilters = useUserPreferencesStore((s) => s.saveFilters);
  
  const hasLoadedRef = useRef(false);
  const lastSyncedRef = useRef<string>('');
  
  // 1. Cargar filtros desde savedFilters cuando se monta (una vez)
  useEffect(() => {
    if (hasLoadedRef.current) return;
    
    const saved = savedFilters[SCANNER_FILTERS_KEY];
    if (saved && typeof saved === 'object' && Object.keys(saved).length > 0) {
      console.log('[ScannerFiltersSync] Loading filters from BD:', saved);
      setAllFilters(saved);
      hasLoadedRef.current = true;
    }
  }, [savedFilters, setAllFilters]);
  
  // 2. Guardar filtros en savedFilters cuando cambian
  useEffect(() => {
    // Evitar guardar si aún no hemos cargado
    if (!hasLoadedRef.current && Object.keys(activeFilters).length === 0) {
      return;
    }
    
    // Serializar para comparar
    const serialized = JSON.stringify(activeFilters);
    
    // Evitar loops infinitos
    if (serialized === lastSyncedRef.current) {
      return;
    }
    
    lastSyncedRef.current = serialized;
    hasLoadedRef.current = true;
    
    // Guardar en userPreferencesStore (que luego sincroniza con BD)
    console.log('[ScannerFiltersSync] Saving filters to BD:', activeFilters);
    saveFilters(SCANNER_FILTERS_KEY, activeFilters);
  }, [activeFilters, saveFilters]);
}

export default useScannerFiltersSync;

