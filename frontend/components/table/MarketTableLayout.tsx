'use client';

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, X } from 'lucide-react';
import { openScannerWindow } from '@/lib/window-injector';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { getUserTimezone } from '@/lib/date-utils';

interface MarketTableLayoutProps {
  title: string;
  isLive: boolean;
  count?: number;
  sequence?: number;
  lastUpdateTime?: Date | null;
  rightActions?: ReactNode;
  listName?: string; // Para generar URL standalone
  onClose?: () => void;
}

export function MarketTableLayout({
  title,
  isLive,
  count,
  sequence,
  lastUpdateTime,
  rightActions,
  listName,
  onClose,
}: MarketTableLayoutProps) {
  const { t } = useTranslation();
  const { windows, updateWindow } = useFloatingWindow();

  const handleOpenNewWindow = () => {
    if (!listName) return;

    // Patrón Godel Terminal: about:blank + inyección + SharedWorker
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';

    // URL absoluta del SharedWorker (necesaria para about:blank)
    const workerUrl = `${window.location.origin}/workers/websocket-shared.js`;

    const popOutWindow = openScannerWindow(
      {
        listName,
        categoryName: title,
        wsUrl,
        workerUrl,
      },
      {
        title: `${title} - Tradeul`,
        width: 1400,
        height: 900,
        centered: true,
      }
    );

    // Buscar la ventana flotante padre por título y marcarla como poppedOut
    if (popOutWindow) {
      // Probar diferentes formatos de título
      const possibleTitles = [
        `Scanner: ${title}`,
        title,
      ];

      const parentWindow = windows.find(w => possibleTitles.includes(w.title));
      if (parentWindow) {
        updateWindow(parentWindow.id, { isPoppedOut: true, poppedOutWindow: popOutWindow });
      }
    }
  };

  return (
    <div className="table-drag-handle flex items-center justify-between px-2 py-1 bg-slate-50 border-b border-slate-200 cursor-move">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-slate-700">{title}</h2>

        <div className="flex items-center gap-1">
          <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-500' : 'bg-slate-300'}`} />
          <span className={`text-[10px] font-medium ${isLive ? 'text-emerald-600' : 'text-slate-400'}`}>
            {isLive ? t('common.live') : t('common.offline')}
          </span>
        </div>

        {typeof count === 'number' && (
          <div className="flex items-center gap-1.5">
            <div className="flex items-center gap-0.5 px-1.5 py-0.5 bg-blue-50 rounded border border-blue-200">
              <span className="text-[10px] font-semibold text-blue-600">{count}</span>
            </div>
            {typeof sequence === 'number' && (
              <span className="text-[10px] font-mono text-slate-400">#{sequence}</span>
            )}
          </div>
        )}
      </div>

      <div
        className="flex items-center gap-1"
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {lastUpdateTime && (
          <span className="text-[10px] font-mono text-slate-400">
            {lastUpdateTime.toLocaleTimeString('en-US', { timeZone: getUserTimezone(), hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
          </span>
        )}

        {/* Botón de abrir en nueva ventana */}
        {listName && (
          <button
            onClick={handleOpenNewWindow}
            className="p-0.5 rounded hover:bg-blue-100 transition-colors group"
            title="Open in new window"
          >
            <ExternalLink className="w-3 h-3 text-slate-500 group-hover:text-blue-600" />
          </button>
        )}

        {rightActions}

        {/* Botón de cerrar tabla */}
        {onClose && (
          <button
            onClick={onClose}
            className="p-0.5 rounded hover:bg-red-100 transition-colors group"
            title="Close table"
          >
            <X className="w-3 h-3 text-slate-500 group-hover:text-red-600" />
          </button>
        )}
      </div>
    </div>
  );
}


