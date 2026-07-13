/**
 * useMarketClockSync — mantiene useMarketSessionStore como única fuente de
 * verdad de la sesión de mercado. Montar UNA sola vez (AppShell).
 *
 * Fuentes de sincronización (en orden de frescura):
 *   1. WS `market_session_change` — transiciones en tiempo real.
 *   2. WS `connected` — snapshot de sesión que el servidor envía al
 *      (re)conectar. CRÍTICO para el caso "pestaña dormida": si el socket
 *      estuvo muerto durante una transición (p.ej. CLOSED→PRE_MARKET a las
 *      4:00 AM ET), este snapshot es lo que corrige el estado obsoleto.
 *   3. Refetch REST al volver la pestaña a visible y al reconectar el WS
 *      (cinturón y tirantes: cubre servidores que aún no envíen
 *      current_session en `connected`).
 *   4. Polling REST de respaldo cada 60s.
 *
 * Antes de esto, la sesión solo se actualizaba con eventos de transición:
 * cualquier evento perdido dejaba charts sin línea de pre-market, badge LIVE
 * apagado, etc. hasta la SIGUIENTE transición (bug de CBRS).
 */

import { useEffect, useRef } from 'react';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useMarketSessionStore } from '@/stores/useMarketSessionStore';
import { getMarketHolidays } from '@/lib/api';
import { nextSessionTransitionUtcSeconds, setMarketCalendar } from '@/lib/marketTime';
import { isConnectedWithSessionMsg, isMarketSessionChangeMsg } from '@/lib/wsContracts';
import type { MarketSession } from '@/lib/types';

const BACKUP_POLL_MS = 60_000;
const CALENDAR_REFRESH_MS = 6 * 60 * 60 * 1000; // 4x/día es de sobra

export function useMarketClockSync() {
  const ws = useWebSocket();
  const wasConnectedRef = useRef(ws.isConnected);

  // ── 1+2: eventos WS ─────────────────────────────────────────────────────
  useEffect(() => {
    const subscription = ws.messages$.subscribe((message: any) => {
      if (isMarketSessionChangeMsg(message)) {
        useMarketSessionStore.getState().setSession({
          current_session: message.data.current_session,
          trading_date: message.data.trading_date,
          timestamp: message.data.timestamp,
        } as MarketSession);
      } else if (isConnectedWithSessionMsg(message)) {
        // Snapshot al (re)conectar — repara sesión obsoleta tras eventos perdidos.
        useMarketSessionStore.getState().setSession({
          current_session: message.current_session,
          trading_date: message.trading_date,
          timestamp: message.timestamp,
        } as MarketSession);
      }
    });
    return () => subscription.unsubscribe();
  }, [ws.messages$]);

  // ── 3a: refetch al volver a visible ─────────────────────────────────────
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        useMarketSessionStore.getState().fetchSession();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    // Page Lifecycle API (Chrome): resume tras freeze profundo.
    document.addEventListener('resume', onVisible);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      document.removeEventListener('resume', onVisible);
    };
  }, []);

  // ── 3b: refetch al reconectar el WS ─────────────────────────────────────
  useEffect(() => {
    if (ws.isConnected && !wasConnectedRef.current) {
      useMarketSessionStore.getState().fetchSession();
    }
    wasConnectedRef.current = ws.isConnected;
  }, [ws.isConnected]);

  // ── 4: polling de respaldo ──────────────────────────────────────────────
  useEffect(() => {
    useMarketSessionStore.getState().startPolling(BACKUP_POLL_MS);
    return () => useMarketSessionStore.getState().stopPolling();
  }, []);

  // ── 4b: refetch en boundaries de sesión ─────────────────────────────────
  // Evita el lag de ~55s en cambios tipo MARKET_OPEN→POST_MARKET cuando el
  // evento WS se pierde: programamos un fetch justo después del siguiente
  // boundary calculado en ET (respeta half-days si hay calendario).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const schedule = () => {
      if (cancelled) return;
      const nowSecs = Math.floor(Date.now() / 1000);
      const next = nextSessionTransitionUtcSeconds(nowSecs);
      if (!next) return;
      const delayMs = Math.max(250, (next * 1000 - Date.now()) + 1500); // +1.5s para dejar que el backend asiente
      timer = setTimeout(async () => {
        if (cancelled) return;
        await useMarketSessionStore.getState().fetchSession();
        schedule(); // reprogramar el siguiente boundary
      }, delayMs);
    };

    schedule();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  // ── 5: calendario de festivos/half-days ────────────────────────────────
  // Instala el calendario en lib/marketTime para que getSessionKind e
  // isRegularHours respeten cierres anticipados (13:00 ET) y festivos.
  useEffect(() => {
    let cancelled = false;
    const loadCalendar = async () => {
      const holidays = await getMarketHolidays(60);
      if (!cancelled && holidays.length > 0) {
        setMarketCalendar(holidays);
      }
    };
    loadCalendar();
    const timer = setInterval(loadCalendar, CALENDAR_REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);
}
