/**
 * AI Alert Fires Store
 *
 * Disparos en vivo de las alertas IA (LLM-compiled), alimentado por el
 * WebSocket /ws/alerts del agente (relay de stream:alerts:{user_id}).
 * El provider (AIAlertFiresProvider) es el único escritor; popup, badge y
 * panel leen de aquí.
 */
import { create } from 'zustand';

/** Captura de un workflow programado (tier scheduled): tabla rankeada. */
export interface AIAlertSnapshot {
  category: string;
  session: string;
  rows: Array<{
    symbol?: string;
    price?: number;
    change_percent?: number;
    gap_percent?: number;
    postmarket_change_percent?: number;
    premarket_change_percent?: number;
    volume?: number;
    rvol?: number;
    market_cap?: number;
    sector?: string;
  }>;
}

export interface AIAlertFire {
  id: string;             // Redis stream entry id (único y ordenado)
  spec_id: string | null;
  trigger_id: string | null;
  trigger_name: string;
  symbol: string;
  event_type: string;
  price: number | null;
  rvol: number | null;
  volume: number | null;
  message: string;
  timestamp: number;      // epoch seconds
  backlog: boolean;       // true = replay histórico al conectar (sin popup/sonido)
  receivedAt: number;     // epoch ms local
  dismissed: boolean;     // oculto del popup (sigue en el feed)
  snapshot?: AIAlertSnapshot | null; // solo workflows programados (T4)
}

const MAX_FIRES = 100;

interface AIAlertFiresState {
  fires: AIAlertFire[];
  connected: boolean;
  soundEnabled: boolean;
  lastSeenAt: number;     // epoch ms: para el contador de no-vistos

  addFire: (fire: AIAlertFire) => void;
  dismissFire: (id: string) => void;
  markAllSeen: () => void;
  setConnected: (connected: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  clear: () => void;
}

export const useAIAlertFiresStore = create<AIAlertFiresState>()((set) => ({
  fires: [],
  connected: false,
  soundEnabled: true,
  lastSeenAt: Date.now(),

  addFire: (fire) => set((state) => {
    if (state.fires.some((f) => f.id === fire.id)) return state;
    return { fires: [fire, ...state.fires].slice(0, MAX_FIRES) };
  }),

  dismissFire: (id) => set((state) => ({
    fires: state.fires.map((f) => (f.id === id ? { ...f, dismissed: true } : f)),
  })),

  markAllSeen: () => set({ lastSeenAt: Date.now() }),
  setConnected: (connected) => set({ connected }),
  setSoundEnabled: (soundEnabled) => set({ soundEnabled }),
  clear: () => set({ fires: [] }),
}));

/** Disparos en vivo aún no descartados y recientes (para el popup).
 *  Los snapshots programados (T4, cada N segundos) van al canvas, no al popup. */
export const selectPopupFires = (state: AIAlertFiresState) =>
  state.fires.filter(
    (f) => !f.backlog && !f.dismissed && f.event_type !== 'scheduled_snapshot'
      && Date.now() - f.receivedAt < 30_000,
  );

/** Nº de disparos en vivo desde la última vez que el usuario miró el feed. */
export const useUnseenFireCount = () =>
  useAIAlertFiresStore(
    (state) => state.fires.filter(
      (f) => !f.backlog && f.event_type !== 'scheduled_snapshot' && f.receivedAt > state.lastSeenAt,
    ).length,
  );
