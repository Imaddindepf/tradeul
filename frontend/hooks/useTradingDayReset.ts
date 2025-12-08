/**
 * Hook para detectar cambio de día de trading y resetear stores
 * 
 * ARQUITECTURA PROFESIONAL:
 * - El SERVIDOR es la fuente de verdad del trading_date
 * - Al conectar, el servidor envía trading_date en el mensaje "connected"
 * - Cuando cambia el día, el servidor envía "market_session_change" con is_new_day
 * - El SharedWorker detecta el cambio y hace broadcast "trading_day_changed"
 * - Este hook escucha ese mensaje y resetea los stores
 * 
 * CASOS CUBIERTOS:
 * - App abierta todo el fin de semana → recibe market_session_change el lunes
 * - App cerrada viernes, abierta lunes → al reconectar, trading_date es diferente
 * - Festivos → el servidor sabe qué días son de trading
 */

import { useEffect, useRef } from 'react';
import { useTickersStore } from '@/stores/useTickersStore';
import { useNewsStore } from '@/stores/useNewsStore';
import { useNewsTickersStore } from '@/stores/useNewsTickersStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';

export function useTradingDayReset() {
  const ws = useWebSocket();
  const hasReset = useRef(false);
  
  // Stores que necesitan limpiarse
  const resetTickers = useTickersStore((state) => state.reset);
  const resetNews = useNewsStore((state) => state.reset);
  const resetNewsTickers = useNewsTickersStore((state) => state.resetForNewSession);
  
  useEffect(() => {
    const subscription = ws.messages$.subscribe((message: any) => {
      // El SharedWorker envía este mensaje cuando detecta cambio de trading_date
      if (message.type === 'trading_day_changed' && message.data) {
        const { previousDate, newDate } = message.data;
        
        // Evitar múltiples resets
        if (hasReset.current) {
          return;
        }
        hasReset.current = true;
        
        console.log('🔄 [TradingDayReset] Nuevo día de trading:', {
          from: previousDate,
          to: newDate,
        });
        
        // Reset de todos los stores
        console.log('🧹 [TradingDayReset] Limpiando stores...');
        
        try {
          resetTickers();
          resetNews();
          resetNewsTickers();
          console.log('✅ [TradingDayReset] Stores limpiados');
        } catch (e) {
          console.error('❌ [TradingDayReset] Error:', e);
        }
        
        // Permitir nuevos resets después de 10 segundos
        setTimeout(() => {
          hasReset.current = false;
        }, 10000);
      }
    });
    
    return () => subscription.unsubscribe();
  }, [ws.messages$, resetTickers, resetNews, resetNewsTickers]);
}
