/**
 * useCatalystDetector Hook
 * 
 * Detecta noticias que cumplen los criterios de alerta del usuario
 * y dispara notificaciones (popup, sonido, squawk)
 */

'use client';

import { useRef, useCallback } from 'react';
import { useCatalystAlertsStore, CatalystMetrics, CatalystAlert } from '@/stores/useCatalystAlertsStore';
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
function playAlertSound() {
  if (typeof window === 'undefined') return;
  
  try {
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    // Configurar sonido de alerta (tono ascendente)
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
      
      // Prioridad: change_recent_pct > change_day_pct > legacy
      let change: number | null = null;
      let timeLabel = 'recent';
      
      if (metrics.change_recent_pct !== null && metrics.change_recent_pct !== undefined) {
        change = metrics.change_recent_pct;
        timeLabel = `${metrics.lookback_minutes || 3}min`;
      } else if (metrics.change_day_pct !== null && metrics.change_day_pct !== undefined) {
        change = metrics.change_day_pct;
        timeLabel = 'day';
      } else if (criteria.priceChange.timeWindow === 1 && metrics.change_1m_pct !== null) {
        change = metrics.change_1m_pct;
        timeLabel = '1min';
      } else if (metrics.change_5m_pct !== null) {
        change = metrics.change_5m_pct;
        timeLabel = '5min';
      }
      
      if (change !== null && Math.abs(change) >= criteria.priceChange.minPercent) {
        passedCount++;
        const sign = change > 0 ? '+' : '';
        reasons.push(`${sign}${change.toFixed(1)}% ${timeLabel}`);
      }
    }
    
    // Criterio: RVOL
    if (criteria.rvol.enabled) {
      enabledCount++;
      if (metrics.rvol && metrics.rvol >= criteria.rvol.minValue) {
        passedCount++;
        reasons.push(`RVOL ${metrics.rvol.toFixed(1)}x`);
      }
    }
    
    // Para pasar, TODOS los criterios habilitados deben cumplirse (AND)
    if (enabledCount === 0 || passedCount < enabledCount) {
      return { passes: false, reason: 'Not all criteria met' };
    }
    
    return { passes: true, reason: reasons.join(' | ') };
  }, [criteria, isInScanner]);
  
  // Reproducir sonido
  const playSound = useCallback(() => {
    if (criteria.notifications.sound) {
      playAlertSound();
    }
  }, [criteria.notifications.sound]);
  
  // Procesar noticia entrante
  const processNews = useCallback((news: NewsWithMetrics) => {
    if (!enabled) return;
    if (!news.catalyst_metrics) return;
    if (!news.tickers || news.tickers.length === 0) return;
    
    const ticker = news.catalyst_metrics.ticker || news.tickers[0];
    const metrics = news.catalyst_metrics;
    
    // Verificar criterios
    const { passes, reason } = checkCriteria(ticker, metrics);
    
    if (!passes) return;
    
    // Crear alerta
    const alert: CatalystAlert = {
      id: `${news.benzinga_id || news.id || Date.now()}-${ticker}`,
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
    playSound();
    
    console.log('[Catalyst] 🔔 Alert triggered:', ticker, reason);
  }, [enabled, checkCriteria, addAlert, playSound]);
  
  return {
    processNews,
    enabled,
  };
}

