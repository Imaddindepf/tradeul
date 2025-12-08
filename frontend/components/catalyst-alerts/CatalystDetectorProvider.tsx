'use client';

/**
 * CatalystDetectorProvider
 * 
 * Componente global que se monta siempre en el layout.
 * Se suscribe a noticias en segundo plano cuando las alertas están habilitadas.
 * Detecta catalyst/noticias explosivas y dispara alertas.
 * 
 * IMPORTANTE: Este componente debe estar montado en el layout principal
 * para que las alertas funcionen aunque la ventana de News no esté abierta.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useCatalystAlertsStore, CatalystMetrics, CatalystAlert } from '@/stores/useCatalystAlertsStore';
import { useTickersStore } from '@/stores/useTickersStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useCatalystAlertsSync } from '@/hooks/useCatalystAlertsSync';

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
    
    // Sonido de alerta distintivo
    oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(1200, audioContext.currentTime + 0.1);
    oscillator.frequency.exponentialRampToValueAtTime(800, audioContext.currentTime + 0.2);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.3);
  } catch (e) {
    // Ignorar errores de audio
  }
}

export function CatalystDetectorProvider({ children }: { children: React.ReactNode }) {
  // Sincronizar preferencias con el servidor
  useCatalystAlertsSync();
  
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
  const checkCriteria = useCallback((
    ticker: string,
    metrics: CatalystMetrics
  ): { passes: boolean; reason: string } => {
    const reasons: string[] = [];
    let passes = false;
    
    // Filtro: solo scanner
    if (criteria.filters.onlyScanner && !isInScanner(ticker)) {
      return { passes: false, reason: 'Not in scanner' };
    }
    
    // Criterio: Cambio de precio
    if (criteria.priceChange.enabled) {
      // Nuevo sistema: usar change_recent_pct (últimos 3 min) o change_day_pct
      // El usuario elige "1min" o "5min" pero usamos el mejor dato disponible
      let change: number | null = null;
      let timeLabel = 'recent';
      
      // Prioridad: change_recent_pct (más preciso) > change_day_pct (incluye ahora)
      if (metrics.change_recent_pct !== null && metrics.change_recent_pct !== undefined) {
        change = metrics.change_recent_pct;
        timeLabel = `${metrics.lookback_minutes || 3}min`;
      } else if (metrics.change_day_pct !== null && metrics.change_day_pct !== undefined) {
        change = metrics.change_day_pct;
        timeLabel = 'day';
      }
      // Compatibilidad con sistema legacy
      else if (metrics.change_1m_pct !== null && metrics.change_1m_pct !== undefined) {
        change = metrics.change_1m_pct;
        timeLabel = '1min';
      } else if (metrics.change_5m_pct !== null && metrics.change_5m_pct !== undefined) {
        change = metrics.change_5m_pct;
        timeLabel = '5min';
      }
      
      if (change !== null && Math.abs(change) >= criteria.priceChange.minPercent) {
        passes = true;
        const sign = change > 0 ? '+' : '';
        reasons.push(`${sign}${change.toFixed(1)}% ${timeLabel}`);
      }
    }
    
    // Criterio: RVOL
    if (criteria.rvol.enabled && metrics.rvol && metrics.rvol >= criteria.rvol.minValue) {
      passes = true;
      reasons.push(`RVOL ${(metrics.rvol ?? 0).toFixed(1)}x`);
    }
    
    if (!passes) {
      return { passes: false, reason: 'No criteria met' };
    }
    
    return { passes: true, reason: reasons.join(' | ') };
  }, [criteria, isInScanner]);
  
  // Procesar noticia con métricas de catalyst
  const processNews = useCallback((news: NewsWithMetrics) => {
    if (!news.catalyst_metrics) return;
    if (!news.tickers || news.tickers.length === 0) return;
    
    const newsId = `${news.benzinga_id || news.id || Date.now()}`;
    
    // Evitar duplicados
    if (processedNewsRef.current.has(newsId)) return;
    processedNewsRef.current.add(newsId);
    
    // Limpiar set si crece mucho
    if (processedNewsRef.current.size > 1000) {
      const entries = Array.from(processedNewsRef.current);
      processedNewsRef.current = new Set(entries.slice(-500));
    }
    
    const ticker = news.catalyst_metrics.ticker || news.tickers[0];
    const metrics = news.catalyst_metrics;
    
    // Verificar criterios del usuario (él decide qué alertas ver)
    const { passes, reason } = checkCriteria(ticker, metrics);
    
    if (!passes) {
      console.log('[CatalystProvider] ⏭️ Skipped:', ticker, 'does not meet criteria');
      return;
    }
    
    // Crear alerta
    const alert: CatalystAlert = {
      id: `${newsId}-${ticker}`,
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
    
    console.log('[CatalystProvider] 🔔 ALERT:', ticker, reason);
  }, [checkCriteria, addAlert, criteria.notifications.sound]);
  
  // Suscribirse a noticias cuando las alertas están habilitadas
  useEffect(() => {
    if (!enabled || !ws.isConnected) {
      return;
    }
    
    console.log('[CatalystProvider] 📰 Subscribing to news for catalyst detection...');
    
    // Suscribirse a noticias
    ws.send({ action: 'subscribe_benzinga_news' });
    
    return () => {
      console.log('[CatalystProvider] 📰 Unsubscribing from news...');
      ws.send({ action: 'unsubscribe_benzinga_news' });
    };
  }, [enabled, ws.isConnected, ws]);
  
  // Procesar mensajes entrantes
  useEffect(() => {
    if (!enabled) return;
    
    const subscription = ws.messages$.subscribe((message: any) => {
      // Noticias con métricas de catalyst
      if ((message.type === 'news' || message.type === 'benzinga_news') && message.article) {
        const article = message.article;
        
        // Procesar métricas de catalyst si existen
        if (message.catalyst_metrics) {
          const metrics = typeof message.catalyst_metrics === 'string' 
            ? JSON.parse(message.catalyst_metrics) 
            : message.catalyst_metrics;
          
          processNews({
            ...article,
            catalyst_metrics: metrics,
          });
        }
      }
    });
    
    return () => subscription.unsubscribe();
  }, [enabled, ws.messages$, processNews]);
  
  // Este componente es invisible, solo renderiza children
  return <>{children}</>;
}

export default CatalystDetectorProvider;

