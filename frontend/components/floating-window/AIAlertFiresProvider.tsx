'use client';

/**
 * AIAlertFiresProvider — conexión WebSocket al feed de disparos de alertas IA.
 *
 * Se monta una vez en AppShell. Conecta a /ws/alerts del agente (JWT de
 * Clerk), escribe cada disparo en useAIAlertFiresStore y reproduce un sonido
 * para los disparos en vivo (no para el backlog de reconexión).
 * Reconexión con backoff + token fresco + visibility/online kick.
 */
import { useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useAIAlertFiresStore, AIAlertFire } from '@/stores/useAIAlertFiresStore';

const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';
const WS_BASE = AGENT_BASE.replace('https://', 'wss://').replace('http://', 'ws://');

const PING_INTERVAL_MS = 25_000;

function playFireSound() {
  if (typeof window === 'undefined') return;
  try {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AC();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(520, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(780, ctx.currentTime + 0.09);
    osc.frequency.setValueAtTime(520, ctx.currentTime + 0.16);
    osc.frequency.exponentialRampToValueAtTime(1040, ctx.currentTime + 0.28);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.42);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.42);
  } catch {
    // sin audio disponible — silencioso
  }
}

export function AIAlertFiresProvider() {
  const { getToken, isSignedIn } = useAuth();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);
  const pingRef = useRef<NodeJS.Timeout | null>(null);
  const attemptsRef = useRef(0);
  const stoppedRef = useRef(false);
  const connectRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    if (!isSignedIn) return;
    stoppedRef.current = false;

    const scheduleReconnect = () => {
      if (stoppedRef.current) return;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      const attempt = attemptsRef.current;
      attemptsRef.current = attempt + 1;
      const delay = Math.min(800 * Math.pow(2, attempt) + Math.random() * 400, 15_000);
      reconnectRef.current = setTimeout(() => { void connectRef.current(); }, delay);
    };

    const connect = async () => {
      if (stoppedRef.current) return;
      if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

      let token: string | null = null;
      try {
        // Siempre fresco: JWT Clerk ~60s. Cache = fallos de handshake tras un blip.
        token = await getToken({ skipCache: true });
      } catch {
        token = null;
      }
      if (!token || stoppedRef.current) {
        scheduleReconnect();
        return;
      }

      let ws: WebSocket;
      try {
        ws = new WebSocket(`${WS_BASE}/ws/alerts?token=${encodeURIComponent(token)}`);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        useAIAlertFiresStore.getState().setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'keepalive' || data.type === 'ping' || data.type === 'pong') return;
          if (data.type !== 'alert_fire' || !data.fire) return;
          const f = data.fire;
          const fire: AIAlertFire = {
            id: String(f.id),
            spec_id: f.spec_id || null,
            trigger_id: f.trigger_id || null,
            trigger_name: f.trigger_name || '',
            symbol: f.symbol || '',
            event_type: f.event_type || '',
            price: typeof f.price === 'number' ? f.price : null,
            rvol: typeof f.rvol === 'number' ? f.rvol : null,
            volume: typeof f.volume === 'number' ? f.volume : null,
            message: f.message || '',
            timestamp: typeof f.timestamp === 'number' ? f.timestamp : Date.now() / 1000,
            backlog: Boolean(data.backlog),
            receivedAt: Date.now(),
            dismissed: false,
            snapshot: f.snapshot || null,
          };
          const store = useAIAlertFiresStore.getState();
          const isNew = !store.fires.some((x) => x.id === fire.id);
          store.addFire(fire);
          // Los snapshots programados llegan cada N segundos: sin sonido.
          const isSnapshot = fire.event_type === 'scheduled_snapshot';
          if (isNew && !fire.backlog && !isSnapshot && store.soundEnabled) playFireSound();
        } catch {
          // frame no-JSON — ignorar
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        useAIAlertFiresStore.getState().setConnected(false);
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose gestiona el retry; no spamear consola
      };
    };

    connectRef.current = connect;
    void connect();

    pingRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try { wsRef.current.send('ping'); } catch { /* noop */ }
      }
    }, PING_INTERVAL_MS);

    const kick = () => {
      if (document.visibilityState === 'hidden') return;
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      attemptsRef.current = 0;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      void connect();
    };
    document.addEventListener('visibilitychange', kick);
    window.addEventListener('online', kick);

    return () => {
      stoppedRef.current = true;
      document.removeEventListener('visibilitychange', kick);
      window.removeEventListener('online', kick);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (pingRef.current) clearInterval(pingRef.current);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
      useAIAlertFiresStore.getState().setConnected(false);
    };
  }, [isSignedIn, getToken]);

  return null;
}
