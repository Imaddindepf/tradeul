'use client';

/**
 * CatalystDetectorProvider
 * 
 * Sistema profesional de detección de catalyst para traders de breaking news.
 * 
 * Detecta el IMPACTO REAL de noticias en tiempo real via WebSocket:
 * - Cuando llega una noticia, captura el precio actual
 * - Monitorea el ticker en tiempo real
 * - Alerta cuando detecta movimiento significativo desde la noticia + RVOL alto
 * 
 * NO usa el cambio del día (inútil para catalyst).
 * SI usa el cambio desde que llegó la noticia.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useCatalystAlertsStore, CatalystMetrics, CatalystAlert } from '@/stores/useCatalystAlertsStore';
import { useTickersStore } from '@/stores/useTickersStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useCatalystAlertsSync } from '@/hooks/useCatalystAlertsSync';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface NewsWithMetrics {
  benzinga_id?: string | number;
  id?: string;
  title: string;
  url: string;
  published: string;
  tickers?: string[];
  catalyst_metrics?: CatalystMetrics;
}

// Generar sonido de alerta usando Web Audio API
function playAlertSound() {
  if (typeof window === 'undefined') return;
  
  try {
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    // Sonido distintivo para alertas de catalyst
    oscillator.frequency.setValueAtTime(600, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(1000, audioContext.currentTime + 0.1);
    oscillator.frequency.exponentialRampToValueAtTime(600, audioContext.currentTime + 0.15);
    oscillator.frequency.exponentialRampToValueAtTime(1200, audioContext.currentTime + 0.25);
    
    gainNode.gain.setValueAtTime(0.35, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.4);
  } catch (e) {
    // Ignorar errores de audio
  }
}

export function CatalystDetectorProvider({ children }: { children: React.ReactNode }) {
  // Sincronizar preferencias con el servidor
  useCatalystAlertsSync();
  
  // Auth para TTS
  const { getToken } = useAuth();
  
  // Store de alertas
  const enabled = useCatalystAlertsStore((state) => state.enabled);
  const criteria = useCatalystAlertsStore((state) => state.criteria);
  const addAlert = useCatalystAlertsStore((state) => state.addAlert);
  
  // Tickers en scanner (para filtro)
  const tickerLists = useTickersStore((state) => state.lists);
  
  // WebSocket (ya autenticado desde AuthWebSocketProvider)
  const ws = useWebSocket();
  
  // Ref para tracking de noticias procesadas (evitar duplicados)
  const processedNewsRef = useRef<Set<string>>(new Set());
  
  // Ref para cola de TTS
  const ttsQueueRef = useRef<string[]>([]);
  const ttsProcessingRef = useRef(false);
  
  // Procesar cola de TTS (squawk)
  const processTTSQueue = useCallback(async () => {
    if (ttsProcessingRef.current || ttsQueueRef.current.length === 0) return;
    
    ttsProcessingRef.current = true;
    
    while (ttsQueueRef.current.length > 0) {
      const text = ttsQueueRef.current.shift()!;
      
      try {
        const token = await getToken();
        
        const response = await fetch(`${API_BASE_URL}/api/v1/tts/speak`, {
          method: 'POST',
          headers: {
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            text,
            voice_id: '21m00Tcm4TlvDq8ikWAM', // Rachel - voz multilingue
          }),
        });
        
        if (!response.ok) {
          console.error('[CatalystProvider] TTS error:', response.status);
          continue;
        }
        
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        
        await new Promise<void>((resolve) => {
          const audio = new Audio(audioUrl);
          audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            resolve();
          };
          audio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            resolve();
          };
          audio.play().catch(() => resolve());
        });
        
      } catch (error) {
        console.error('[CatalystProvider] TTS error:', error);
      }
    }
    
    ttsProcessingRef.current = false;
  }, [getToken]);
  
  // Hablar texto (squawk)
  const speakAlert = useCallback((ticker: string, reason: string) => {
    const text = `${ticker} catalyst alert. ${reason}`;
    
    // Limpiar y acortar
    const cleanText = text.substring(0, 150);
    
    ttsQueueRef.current.push(cleanText);
    processTTSQueue();
  }, [processTTSQueue]);
  
  // Verificar si un ticker está en el scanner
  const isInScanner = useCallback((ticker: string): boolean => {
    const upperTicker = ticker.toUpperCase();
    let found = false;
    tickerLists.forEach((list) => {
      if (list.tickers.has(upperTicker)) {
        found = true;
      }
    });
    return found;
  }, [tickerLists]);
  
  // Verificar si cumple criterios del usuario
  // LÓGICA AND: cuando hay múltiples criterios habilitados, TODOS deben cumplirse
  const checkCriteria = useCallback((
    ticker: string,
    metrics: CatalystMetrics
  ): { passes: boolean; reason: string } => {
    const reasons: string[] = [];
    
    // Filtro: solo scanner
    if (criteria.filters.onlyScanner && !isInScanner(ticker)) {
      return { passes: false, reason: 'Not in scanner' };
    }
    
    // Contar criterios habilitados y cuántos pasan
    let enabledCount = 0;
    let passedCount = 0;
    
    // Criterio: Cambio de precio desde la noticia
    if (criteria.priceChange.enabled) {
      enabledCount++;
      const change = metrics.change_since_news_pct ?? metrics.change_day_pct ?? 0;
      
      if (Math.abs(change) >= criteria.priceChange.minPercent) {
        passedCount++;
        const sign = change > 0 ? '+' : '';
        const timeLabel = metrics.seconds_since_news 
          ? `${metrics.seconds_since_news}s`
          : 'now';
        reasons.push(`${sign}${change.toFixed(1)}% in ${timeLabel}`);
      }
    }
    
    // Criterio: Velocidad del movimiento
    if (criteria.velocity.enabled) {
      enabledCount++;
      const velocity = metrics.velocity_pct_per_min ?? 0;
      
      if (velocity >= criteria.velocity.minPerMinute) {
        passedCount++;
        reasons.push(`${velocity.toFixed(2)}%/min`);
      }
    }
    
    // Criterio: RVOL
    if (criteria.rvol.enabled) {
      enabledCount++;
      const rvol = metrics.rvol ?? 0;
      
      if (rvol >= criteria.rvol.minValue) {
        passedCount++;
        reasons.push(`RVOL ${rvol.toFixed(1)}x`);
      }
    }
    
    // Criterio: Volume Spike
    if (criteria.volumeSpike.enabled) {
      enabledCount++;
      const spike = metrics.volume_spike_ratio ?? 1;
      
      if (spike >= criteria.volumeSpike.minRatio) {
        passedCount++;
        reasons.push(`Spike ${spike.toFixed(1)}x`);
      }
    }
    
    // Para pasar, TODOS los criterios habilitados deben cumplirse (AND)
    if (enabledCount === 0 || passedCount < enabledCount) {
      return { passes: false, reason: 'Not all criteria met' };
    }
    
    return { passes: true, reason: reasons.join(' | ') };
  }, [criteria, isInScanner]);
  
  // Procesar alerta de catalyst
  const processNews = useCallback((news: NewsWithMetrics) => {
    if (!news.catalyst_metrics) return;
    if (!news.tickers || news.tickers.length === 0) return;
    
    const newsId = `${news.benzinga_id || news.id || Date.now()}`;
    const uniqueId = `catalyst-${newsId}`;
    
    // Evitar duplicados
    if (processedNewsRef.current.has(uniqueId)) return;
    processedNewsRef.current.add(uniqueId);
    
    // Limpiar set si crece mucho
    if (processedNewsRef.current.size > 1000) {
      const entries = Array.from(processedNewsRef.current);
      processedNewsRef.current = new Set(entries.slice(-500));
    }
    
    const ticker = news.catalyst_metrics.ticker || news.tickers[0];
    const metrics = news.catalyst_metrics;
    
    // Verificar criterios del usuario
    const { passes, reason } = checkCriteria(ticker, metrics);
    
    if (!passes) {
      console.log(`[CatalystProvider] Skipped:`, ticker, reason);
      return;
    }
    
    // Crear alerta
    const alert: CatalystAlert = {
      id: uniqueId,
      ticker,
      title: news.title,
      url: news.url,
      published: news.published,
      metrics,
      triggeredAt: Date.now(),
      dismissed: false,
      reason,
    };
    
    // Añadir alerta
    addAlert(alert);
    
    // Reproducir sonido
    if (criteria.notifications.sound) {
      playAlertSound();
    }
    
    // Squawk (TTS)
    if (criteria.notifications.squawk) {
      speakAlert(ticker, reason);
    }
    
    console.log(`[CatalystProvider] ALERT:`, ticker, reason);
  }, [checkCriteria, addAlert, criteria.notifications.sound, criteria.notifications.squawk, speakAlert]);
  
  // Suscribirse a noticias cuando las alertas están habilitadas
  useEffect(() => {
    if (!enabled || !ws.isConnected) {
      return;
    }
    
    console.log('[CatalystProvider] Subscribing to catalyst alerts (WebSocket realtime)...');
    
    // Suscribirse a noticias
    ws.send({ action: 'subscribe_benzinga_news' });
    
    return () => {
      console.log('[CatalystProvider] Unsubscribing from news...');
      ws.send({ action: 'unsubscribe_benzinga_news' });
    };
  }, [enabled, ws.isConnected, ws]);
  
  // Procesar mensajes entrantes
  useEffect(() => {
    if (!enabled) return;
    
    const subscription = ws.messages$.subscribe((message: any) => {
      // Alertas de catalyst (impacto real detectado por WebSocket)
      if (message.type === 'catalyst_alert' && message.ticker && message.metrics) {
        const metrics = typeof message.metrics === 'string'
          ? JSON.parse(message.metrics)
          : message.metrics;
        
        // Procesar la alerta
        processNews({
          benzinga_id: metrics.news_id,
          title: metrics.news_title || `${message.ticker} catalyst`,
          url: '',
          published: metrics.news_time,
          tickers: [message.ticker],
          catalyst_metrics: metrics,
        });
      }
    });
    
    return () => subscription.unsubscribe();
  }, [enabled, ws.messages$, processNews]);
  
  // Este componente es invisible, solo renderiza children
  return <>{children}</>;
}

export default CatalystDetectorProvider;
