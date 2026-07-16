'use client';

/**
 * AIAlertFiresPopup — notificaciones flotantes de disparos de alertas IA.
 *
 * Muestra los disparos en vivo (no backlog) durante 30s, hasta 3 a la vez,
 * debajo de los popups de Catalyst. Click en el ticker abre el chart; el
 * cuerpo abre el panel AI Alerts.
 */
import { useEffect, useMemo, useState } from 'react';
import { BellRing, X, Volume2 } from 'lucide-react';
import { useAIAlertFiresStore, selectPopupFires } from '@/stores/useAIAlertFiresStore';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';

export function AIAlertFiresPopup() {
  const fires = useAIAlertFiresStore(selectPopupFires);
  const dismissFire = useAIAlertFiresStore((s) => s.dismissFire);
  const { executeTickerCommand } = useCommandExecutor();

  // Re-render periódico para que el corte de 30s expire solo
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (fires.length === 0) return;
    const t = setInterval(() => forceTick((n) => n + 1), 5000);
    return () => clearInterval(t);
  }, [fires.length]);

  const visible = useMemo(() => fires.slice(0, 3), [fires]);
  if (visible.length === 0) return null;

  const fmtTime = (epochS: number) => {
    const diff = Math.floor(Date.now() / 1000 - epochS);
    if (diff < 60) return `${Math.max(diff, 0)}s`;
    return `${Math.floor(diff / 60)}m`;
  };

  return (
    <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2">
      {visible.map((fire, index) => (
        <div
          key={fire.id}
          className="w-96 bg-surface rounded-lg shadow-2xl border-l-4 border-l-primary overflow-hidden
                     animate-in slide-in-from-top-3 fade-in duration-300"
          style={{ animationDelay: `${index * 80}ms` }}
        >
          <div className="flex items-center justify-between px-3 py-2 bg-primary/5 border-b border-border">
            <div className="flex items-center gap-2 min-w-0">
              <BellRing className="w-3.5 h-3.5 text-primary flex-shrink-0" />
              <button
                onClick={() => executeTickerCommand(fire.symbol, 'chart')}
                className="font-bold text-primary hover:underline text-sm"
              >
                {fire.symbol}
              </button>
              <span className="text-[11px] font-medium text-foreground/80 truncate">
                {fire.trigger_name}
              </span>
            </div>
            <button
              onClick={() => dismissFire(fire.id)}
              className="text-muted-fg hover:text-foreground p-0.5 flex-shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={() => {
              dismissFire(fire.id);
              window.dispatchEvent(new CustomEvent('tradeul:open-ai-alerts'));
            }}
            className="w-full text-left px-3 py-2 hover:bg-surface-hover transition-colors"
          >
            <div className="flex items-center gap-2 text-[11px] text-foreground/80">
              <span className="px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono text-[9.5px]">
                {fire.event_type}
              </span>
              {fire.price != null && (
                <span className="font-mono font-semibold tabular-nums">${fire.price.toFixed(2)}</span>
              )}
              {fire.rvol != null && (
                <span className="flex items-center gap-0.5 text-muted-fg">
                  <Volume2 className="w-3 h-3" /> RVOL {fire.rvol.toFixed(1)}x
                </span>
              )}
              <span className="ml-auto text-[9.5px] text-muted-fg">hace {fmtTime(fire.timestamp)}</span>
            </div>
          </button>
        </div>
      ))}
    </div>
  );
}
