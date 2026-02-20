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

/**
 * Tipos de alerta:
 * - early: Ticker ya en movimiento cuando llega la noticia (inmediata)
 * - confirmed: Movimiento confirmado después de la noticia (diferida)
 */
export type AlertType = 'early' | 'confirmed';

export interface CatalystMetrics {
  // Identificación
  ticker: string;
  news_id: string;
  news_title?: string;
  news_time: string;
  
  // Precios
  price_at_news: number;       // Precio cuando llegó la noticia
  price_current: number;       // Precio en evaluación
  
  // Cambios (lo más importante)
  change_since_news_pct: number;  // Cambio REAL desde la noticia
  seconds_since_news: number;     // Tiempo desde la noticia
  
  // Velocidad (momentum)
  velocity_pct_per_min: number;   // % de cambio por minuto
  
  // Volumen
  rvol: number;                   // RVOL del día
  volume_spike_ratio: number;     // Spike de volumen reciente vs normal
  current_volume: number;         // Volumen actual
  
  // Clasificación
  alert_type: AlertType;          // "early" o "confirmed"
  evaluation_window: number;      // Ventana de evaluación en segundos
  
  // Contexto adicional
  change_day_pct?: number | null; // Cambio del día
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
  reason: string;          // Ej: "+4.2% in 30s | RVOL 5.2x"
  alertType: AlertType;    // "early" o "confirmed"
}

export interface AlertCriteria {
  // Cambio de precio desde la noticia
  priceChange: {
    enabled: boolean;
    minPercent: number;  // Ej: 2 = 2% mínimo
  };
  
  // Velocidad del movimiento
  velocity: {
    enabled: boolean;
    minPerMinute: number;  // Ej: 0.5 = 0.5% por minuto mínimo
  };
  
  // RVOL
  rvol: {
    enabled: boolean;
    minValue: number;  // Ej: 2.0 = 2x volumen normal
  };
  
  // Volume Spike (ventana corta)
  volumeSpike: {
    enabled: boolean;
    minRatio: number;  // Ej: 3 = 3x volumen normal reciente
  };
  
  // Tipos de alerta a recibir
  alertTypes: {
    early: boolean;      // Alertas inmediatas (ticker ya en movimiento)
    confirmed: boolean;  // Alertas confirmadas (después de evaluación)
  };
  
  // Filtros adicionales
  filters: {
    onlyScanner: boolean;     // Solo tickers en scanner
    onlyWatchlist: boolean;   // Solo tickers en watchlist
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
    minPercent: 2,  // 2% mínimo desde la noticia
  },
  velocity: {
    enabled: false,
    minPerMinute: 0.5,  // 0.5% por minuto mínimo
  },
  rvol: {
    enabled: true,
    minValue: 2.0,  // 2x volumen normal
  },
  volumeSpike: {
    enabled: false,
    minRatio: 3,  // 3x volumen reciente
  },
  alertTypes: {
    early: true,      // Recibir alertas inmediatas
    confirmed: true,  // Recibir alertas confirmadas
  },
  filters: {
    onlyScanner: false,
    onlyWatchlist: false,
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

// Helper para merge profundo con defaults
function mergeWithDefaults(stored: Partial<AlertCriteria> | undefined): AlertCriteria {
  if (!stored) return defaultCriteria;
  
  return {
    priceChange: {
      ...defaultCriteria.priceChange,
      ...(stored.priceChange || {}),
    },
    velocity: {
      ...defaultCriteria.velocity,
      ...(stored.velocity || {}),
    },
    rvol: {
      ...defaultCriteria.rvol,
      ...(stored.rvol || {}),
    },
    volumeSpike: {
      ...defaultCriteria.volumeSpike,
      ...(stored.volumeSpike || {}),
    },
    alertTypes: {
      ...defaultCriteria.alertTypes,
      ...(stored.alertTypes || {}),
    },
    filters: {
      ...defaultCriteria.filters,
      ...(stored.filters || {}),
    },
    notifications: {
      ...defaultCriteria.notifications,
      ...(stored.notifications || {}),
    },
  };
}

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
        criteria: mergeWithDefaults({
          ...state.criteria,
          ...newCriteria,
          priceChange: {
            ...state.criteria.priceChange,
            ...(newCriteria.priceChange || {}),
          },
          velocity: {
            ...state.criteria.velocity,
            ...(newCriteria.velocity || {}),
          },
          rvol: {
            ...state.criteria.rvol,
            ...(newCriteria.rvol || {}),
          },
          volumeSpike: {
            ...state.criteria.volumeSpike,
            ...(newCriteria.volumeSpike || {}),
          },
          alertTypes: {
            ...state.criteria.alertTypes,
            ...(newCriteria.alertTypes || {}),
          },
          filters: {
            ...state.criteria.filters,
            ...(newCriteria.filters || {}),
          },
          notifications: {
            ...state.criteria.notifications,
            ...(newCriteria.notifications || {}),
          },
        }),
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
          // La estructura de criteria ya incluye notifications
          const payload = {
            newsAlerts: {
              enabled: state.enabled,
              criteria: state.criteria,
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
          
        } catch (error) {
          console.error('[CatalystAlerts] Sync error:', error);
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
            // Merge con defaults para campos nuevos
            const loadedCriteria = mergeWithDefaults(newsAlerts.criteria);
            
            set({
              enabled: newsAlerts.enabled ?? false,
              criteria: loadedCriteria,
            });
          }
        } catch (error) {
          console.error('[CatalystAlerts] Load error:', error);
        }
      },
    }),
    {
      name: 'catalyst-alerts-storage',
      version: 2, // Incrementar version para forzar migración
      partialize: (state) => ({
        enabled: state.enabled,
        criteria: state.criteria,
        // No persistimos alertas ni estado de sync
      }),
      migrate: (persistedState: any, version: number) => {
        // Migrar desde versiones anteriores
        if (version < 2) {
          // Aplicar defaults para campos nuevos
          return {
            ...persistedState,
            criteria: mergeWithDefaults(persistedState?.criteria),
          };
        }
        return persistedState;
      },
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


