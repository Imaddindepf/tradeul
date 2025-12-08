/**
 * CatalystAlertsPopup
 * 
 * Popup flotante que muestra alertas de catalyst en tiempo real
 */

'use client';

import { useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X, ExternalLink, TrendingUp, TrendingDown, Volume2, Clock } from 'lucide-react';
import { useCatalystAlertsStore, CatalystAlert } from '@/stores/useCatalystAlertsStore';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';

export function CatalystAlertsPopup() {
  const { t } = useTranslation();
  const alerts = useCatalystAlertsStore((state) => state.alerts);
  const dismissAlert = useCatalystAlertsStore((state) => state.dismissAlert);
  const enabled = useCatalystAlertsStore((state) => state.enabled);
  const { executeTickerCommand, openNewsWithArticle } = useCommandExecutor();
  
  // Usar useMemo en lugar de useState + useEffect para evitar bucles
  const visibleAlerts = useMemo(() => {
    if (!enabled) return [];
    
    const now = Date.now();
    return alerts
      .filter((a) => !a.dismissed && now - a.triggeredAt < 30000)
      .slice(0, 3); // Máximo 3 popups
  }, [alerts, enabled]);
  
  if (visibleAlerts.length === 0) return null;
  
  const formatTime = (timestamp: number) => {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 60) return `${diff}s`;
    return `${Math.floor(diff / 60)}m`;
  };
  
  return (
    <div className="fixed top-20 right-4 z-[9999] flex flex-col gap-3">
      {visibleAlerts.map((alert, index) => {
        // Determinar el cambio: prioridad recent > day > legacy
        const change = alert.metrics.change_recent_pct 
          ?? alert.metrics.change_day_pct 
          ?? alert.metrics.change_1m_pct 
          ?? alert.metrics.change_5m_pct 
          ?? 0;
        const isPositive = change > 0;
        
        return (
          <div
            key={alert.id}
            className={`
              w-80 bg-white rounded-lg shadow-2xl border-l-4 overflow-hidden
              animate-in slide-in-from-right-5 fade-in duration-300
              ${isPositive ? 'border-l-emerald-500' : 'border-l-rose-500'}
            `}
            style={{ 
              animationDelay: `${index * 100}ms`,
              transform: `translateY(${index * 4}px)` 
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
              <div className="flex items-center gap-2">
                {isPositive ? (
                  <TrendingUp className="w-4 h-4 text-emerald-600" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-rose-600" />
                )}
                <button
                  onClick={() => executeTickerCommand(alert.ticker, 'description')}
                  className="font-bold text-blue-600 hover:underline"
                >
                  {alert.ticker}
                </button>
                <span className={`text-sm font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {alert.reason}
                </span>
              </div>
              <button
                onClick={() => dismissAlert(alert.id)}
                className="text-slate-400 hover:text-slate-600 p-0.5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            {/* Content */}
            <div className="px-3 py-2">
              <p className="text-xs text-slate-700 line-clamp-2 mb-2">
                {alert.title}
              </p>
              
              {/* Metrics */}
              <div className="flex items-center gap-3 text-[10px] text-slate-500">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatTime(alert.triggeredAt)} ago
                </span>
                {alert.metrics.rvol && alert.metrics.rvol > 0 && (
                  <span className="flex items-center gap-1">
                    <Volume2 className="w-3 h-3" />
                    RVOL {alert.metrics.rvol.toFixed(1)}x
                  </span>
                )}
                {(alert.metrics.price || alert.metrics.price_at_news) && (
                <span className="font-mono">
                    ${(alert.metrics.price ?? alert.metrics.price_at_news ?? 0).toFixed(2)}
                </span>
                )}
              </div>
            </div>
            
            {/* Actions */}
            <div className="flex border-t border-slate-100">
              <button
                onClick={() => openNewsWithArticle(alert.id, alert.ticker)}
                className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 text-xs text-blue-600 hover:bg-blue-50 transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
                {t('common.viewNews') || 'View News'}
              </button>
              <button
                onClick={() => executeTickerCommand(alert.ticker, 'chart')}
                className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 transition-colors border-l border-slate-100"
              >
                {t('common.openChart') || 'Chart'}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
