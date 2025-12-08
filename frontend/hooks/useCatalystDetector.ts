/**
 * useCatalystDetector Hook
 * 
 * Hook auxiliar para detección de catalyst.
 * La lógica principal está en CatalystDetectorProvider.
 * 
 * Este hook se puede usar para procesar noticias manualmente
 * o integrar con otros componentes.
 */

'use client';

import { useRef, useCallback } from 'react';
import { useCatalystAlertsStore, CatalystMetrics, CatalystAlert, AlertType } from '@/stores/useCatalystAlertsStore';
import { useTickersStore } from '@/stores/useTickersStore';

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
function playAlertSound(type: AlertType = 'early') {
  if (typeof window === 'undefined') return;
  
  try {
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    if (type === 'confirmed') {
      // Sonido más enfático para alertas confirmadas
      oscillator.frequency.setValueAtTime(600, audioContext.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(1000, audioContext.currentTime + 0.1);
      oscillator.frequency.exponentialRampToValueAtTime(600, audioContext.currentTime + 0.15);
      oscillator.frequency.exponentialRampToValueAtTime(1200, audioContext.currentTime + 0.25);
      
      gainNode.gain.setValueAtTime(0.35, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.4);
    } else {
      // Sonido simple para early alerts
      oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(1200, audioContext.currentTime + 0.1);
      oscillator.frequency.exponentialRampToValueAtTime(800, audioContext.currentTime + 0.2);
      
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.3);
    }
  } catch (e) {
    // Ignorar errores de audio
  }
}

export function useCatalystDetector() {
  const enabled = useCatalystAlertsStore((state) => state.enabled);
  const criteria = useCatalystAlertsStore((state) => state.criteria);
  const addAlert = useCatalystAlertsStore((state) => state.addAlert);
  
  // Referencia para evitar alertas duplicadas
  const processedRef = useRef<Set<string>>(new Set());
  
  // Tickers en scanner (para filtro)
  const tickerLists = useTickersStore((state) => state.lists);
  
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
  
  // Verificar si cumple criterios
  // LÓGICA AND: cuando hay múltiples criterios habilitados, TODOS deben cumplirse
  const checkCriteria = useCallback((
    ticker: string,
    metrics: CatalystMetrics
  ): { passes: boolean; reason: string } => {
    const reasons: string[] = [];
    
    // Verificar tipo de alerta permitido
    const alertType = metrics.alert_type || 'early';
    if (alertType === 'early' && !criteria.alertTypes.early) {
      return { passes: false, reason: 'Early alerts disabled' };
    }
    if (alertType === 'confirmed' && !criteria.alertTypes.confirmed) {
      return { passes: false, reason: 'Confirmed alerts disabled' };
    }
    
    // Filtro: solo scanner
    if (criteria.filters.onlyScanner && !isInScanner(ticker)) {
      return { passes: false, reason: 'Not in scanner' };
    }
    
    // Contar criterios habilitados y cuántos pasan
    let enabledCount = 0;
    let passedCount = 0;
    
    // Criterio: Cambio de precio
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
    
    // Criterio: Velocidad
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
  
  // Reproducir sonido
  const playSound = useCallback((type: AlertType = 'early') => {
    if (criteria.notifications.sound) {
      playAlertSound(type);
    }
  }, [criteria.notifications.sound]);
  
  // Procesar noticia entrante
  const processNews = useCallback((news: NewsWithMetrics) => {
    if (!enabled) return;
    if (!news.catalyst_metrics) return;
    if (!news.tickers || news.tickers.length === 0) return;
    
    const ticker = news.catalyst_metrics.ticker || news.tickers[0];
    const metrics = news.catalyst_metrics;
    const alertType = (metrics.alert_type || 'early') as AlertType;
    
    // Verificar criterios
    const { passes, reason } = checkCriteria(ticker, metrics);
    
    if (!passes) return;
    
    // Crear alerta
    const alert: CatalystAlert = {
      id: `${news.benzinga_id || news.id || Date.now()}-${ticker}-${alertType}`,
      ticker,
      title: news.title,
      url: news.url,
      published: news.published,
      metrics,
      triggeredAt: Date.now(),
      dismissed: false,
      reason,
      alertType,
    };
    
    // Añadir alerta
    addAlert(alert);
    
    // Reproducir sonido
    playSound(alertType);
    
    console.log(`[Catalyst] ALERT ${alertType.toUpperCase()}:`, ticker, reason);
  }, [enabled, checkCriteria, addAlert, playSound]);
  
  return {
    processNews,
    checkCriteria,
    enabled,
  };
}
