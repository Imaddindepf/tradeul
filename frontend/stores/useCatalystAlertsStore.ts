/**
 * Catalyst Alerts Store
 * 
 * Gestiona las alertas de noticias con movimiento explosivo:
 * - Criterios configurables por el usuario
 * - Lista de alertas activas
 * - Estado de activación
 * - Sincronización con BD (squawk, etc.)
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// API URL para sincronización
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ============================================================================
// Types
// ============================================================================

export interface CatalystMetrics {
  // Nuevo sistema simplificado
  price: number;
  change_recent_pct: number | null;  // Cambio últimos 3 minutos (más preciso)
  change_day_pct: number | null;     // Cambio del día (incluye momento actual)
  rvol: number;
  volume: number;
  ticker?: string;
  lookback_minutes?: number;
  
  // Campos legacy (compatibilidad)
  price_at_news?: number;
  change_1m_pct?: number | null;
  change_5m_pct?: number | null;
  snapshot_time?: number;
}

export interface CatalystAlert {
  id: string;
  ticker: string;
  title: string;
  url: string;
  published: string;
  metrics: CatalystMetrics;
  triggeredAt: number;
  dismissed: boolean;
  reason: string; // Ej: "Price +4.2% in 5min"
}

export interface AlertCriteria {
  // Movimiento de precio
  priceChange: {
    enabled: boolean;
    minPercent: number;  // Ej: 3 = 3%
    timeWindow: 1 | 5;   // 1 o 5 minutos
  };
  
  // Volumen
  volumeSpike: {
    enabled: boolean;
    minMultiplier: number;  // Ej: 3 = 3x promedio
  };
  
  // RVOL
  rvol: {
    enabled: boolean;
    minValue: number;  // Ej: 2.5
  };
  
  // Filtros adicionales
  filters: {
    onlyScanner: boolean;     // Solo tickers en scanner
    onlyWatchlist: boolean;   // Solo tickers en watchlist
    maxMarketCap: number | null;  // Ej: 1000000000 (1B)
  };
  
  // Notificaciones
  notifications: {
    popup: boolean;
    sound: boolean;
    squawk: boolean;
  };
}

interface CatalystAlertsState {
  // Estado global
  enabled: boolean;
  
  // Criterios del usuario
  criteria: AlertCriteria;
  
  // Alertas activas
  alerts: CatalystAlert[];
  
  // Sincronización
  _syncing: boolean;
  _lastSyncError: string | null;
  
  // Acciones
  setEnabled: (enabled: boolean) => void;
  setCriteria: (criteria: Partial<AlertCriteria>) => void;
  addAlert: (alert: CatalystAlert) => void;
  dismissAlert: (id: string) => void;
  clearAlerts: () => void;
  clearDismissed: () => void;
  
  // Sincronización con BD
  syncToServer: (token: string) => Promise<void>;
  loadFromServer: (token: string) => Promise<void>;
}

// ============================================================================
// Default Values
// ============================================================================

const defaultCriteria: AlertCriteria = {
  priceChange: {
    enabled: true,
    minPercent: 3,
    timeWindow: 5,
  },
  volumeSpike: {
    enabled: false,
    minMultiplier: 3,
  },
  rvol: {
    enabled: false,
    minValue: 2.5,
  },
  filters: {
    onlyScanner: false,
    onlyWatchlist: false,
    maxMarketCap: null,
  },
  notifications: {
    popup: true,
    sound: true,
    squawk: false,
  },
};

// ============================================================================
// Store
// ============================================================================

export const useCatalystAlertsStore = create<CatalystAlertsState>()(
  persist(
    (set, get) => ({
      enabled: false,
      criteria: defaultCriteria,
      alerts: [],
      _syncing: false,
      _lastSyncError: null,
      
      setEnabled: (enabled) => set({ enabled }),
      
      setCriteria: (newCriteria) => set((state) => ({
        criteria: {
          ...state.criteria,
          ...newCriteria,
          priceChange: {
            ...state.criteria.priceChange,
            ...(newCriteria.priceChange || {}),
          },
          volumeSpike: {
            ...state.criteria.volumeSpike,
            ...(newCriteria.volumeSpike || {}),
          },
          rvol: {
            ...state.criteria.rvol,
            ...(newCriteria.rvol || {}),
          },
          filters: {
            ...state.criteria.filters,
            ...(newCriteria.filters || {}),
          },
          notifications: {
            ...state.criteria.notifications,
            ...(newCriteria.notifications || {}),
          },
        },
      })),
      
      addAlert: (alert) => set((state) => {
        // Evitar duplicados (mismo ticker + misma noticia)
        const exists = state.alerts.some(
          (a) => a.ticker === alert.ticker && a.title === alert.title
        );
        if (exists) return state;
        
        // Máximo 50 alertas, eliminar las más antiguas
        const newAlerts = [alert, ...state.alerts].slice(0, 50);
        return { alerts: newAlerts };
      }),
      
      dismissAlert: (id) => set((state) => ({
        alerts: state.alerts.map((a) =>
          a.id === id ? { ...a, dismissed: true } : a
        ),
      })),
      
      clearAlerts: () => set({ alerts: [] }),
      
      clearDismissed: () => set((state) => ({
        alerts: state.alerts.filter((a) => !a.dismissed),
      })),
      
      // Sincronizar preferencias con el servidor
      syncToServer: async (token: string) => {
        const state = get();
        if (state._syncing) return;
        
        set({ _syncing: true, _lastSyncError: null });
        
        try {
          const payload = {
            newsAlerts: {
              enabled: state.enabled,
              criteria: state.criteria,
              notifications: state.criteria.notifications,
            }
          };
          
          const response = await fetch(`${API_BASE_URL}/api/v1/user/preferences`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify(payload),
          });
          
          if (!response.ok) {
            throw new Error(`Failed to sync: ${response.status}`);
          }
          
          console.log('[CatalystAlerts] ✅ Synced to server');
        } catch (error) {
          console.error('[CatalystAlerts] ❌ Sync error:', error);
          set({ _lastSyncError: String(error) });
        } finally {
          set({ _syncing: false });
        }
      },
      
      // Cargar preferencias desde el servidor
      loadFromServer: async (token: string) => {
        try {
          const response = await fetch(`${API_BASE_URL}/api/v1/user/preferences`, {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });
          
          if (!response.ok) return;
          
          const data = await response.json();
          
          if (data.newsAlerts) {
            const newsAlerts = data.newsAlerts;
            set({
              enabled: newsAlerts.enabled ?? false,
              criteria: {
                ...defaultCriteria,
                ...newsAlerts.criteria,
                notifications: {
                  ...defaultCriteria.notifications,
                  ...newsAlerts.notifications,
                },
              },
            });
            console.log('[CatalystAlerts] ✅ Loaded from server');
          }
        } catch (error) {
          console.error('[CatalystAlerts] ❌ Load error:', error);
        }
      },
    }),
    {
      name: 'catalyst-alerts-storage',
      partialize: (state) => ({
        enabled: state.enabled,
        criteria: state.criteria,
        // No persistimos alertas ni estado de sync
      }),
    }
  )
);

// ============================================================================
// Selector Helpers
// ============================================================================

export const useActiveAlerts = () =>
  useCatalystAlertsStore((state) => state.alerts.filter((a) => !a.dismissed));

export const useAlertCount = () =>
  useCatalystAlertsStore((state) => state.alerts.filter((a) => !a.dismissed).length);

export const useAlertsEnabled = () =>
  useCatalystAlertsStore((state) => state.enabled);


