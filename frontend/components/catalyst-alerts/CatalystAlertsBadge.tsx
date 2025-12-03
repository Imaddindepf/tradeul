/**
 * CatalystAlertsBadge
 * 
 * Badge en navbar para toggle rápido y ver contador de alertas
 */

'use client';

import { Bell, BellOff, Zap } from 'lucide-react';
import { useAlertCount, useAlertsEnabled, useCatalystAlertsStore } from '@/stores/useCatalystAlertsStore';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { CatalystAlertsConfig } from './CatalystAlertsConfig';

export function CatalystAlertsBadge() {
  const enabled = useAlertsEnabled();
  const count = useAlertCount();
  const setEnabled = useCatalystAlertsStore((state) => state.setEnabled);
  const { openWindow } = useFloatingWindow();
  
  const handleClick = () => {
    setEnabled(!enabled);
  };
  
  const handleRightClick = (e: React.MouseEvent) => {
    e.preventDefault();
    openWindow({
      title: 'Catalyst Alerts Config',
      content: <CatalystAlertsConfig />,
      width: 400,
      height: 500,
      x: window.innerWidth / 2 - 200,
      y: 100,
      minWidth: 350,
      minHeight: 400,
    });
  };
  
  return (
    <button
      onClick={handleClick}
      onContextMenu={handleRightClick}
      className={`
        relative flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all
        ${enabled 
          ? 'bg-amber-100 text-amber-700 hover:bg-amber-200' 
          : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
        }
      `}
      title={enabled ? 'Catalyst Alerts ON (right-click to configure)' : 'Catalyst Alerts OFF (click to enable)'}
    >
      {enabled ? (
        <>
          <Zap className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Alerts</span>
          {count > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center bg-rose-500 text-white text-[10px] font-bold rounded-full">
              {count > 9 ? '9+' : count}
            </span>
          )}
        </>
      ) : (
        <>
          <BellOff className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Alerts</span>
        </>
      )}
    </button>
  );
}

