'use client';

import type { ReactNode } from 'react';
import { ExternalLink, X } from 'lucide-react';
import { openScannerWindow } from '@/lib/window-injector';

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

  const handleOpenNewWindow = () => {
    if (!listName) return;

    // Patrón Godel Terminal: about:blank + inyección + SharedWorker
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';

    // URL absoluta del SharedWorker (necesaria para about:blank)
    const workerUrl = `${window.location.origin}/workers/websocket-shared.js`;

    openScannerWindow(
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
  };

  return (
    <div className="table-drag-handle flex items-center justify-between px-3 py-2 bg-white border-b-2 border-blue-500 cursor-move">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-1 h-6 bg-blue-500 rounded-full"></div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">{title}</h2>
        </div>

        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-500' : 'bg-slate-300'}`} />
          <span className={`text-xs font-medium ${isLive ? 'text-emerald-600' : 'text-slate-500'}`}>
            {isLive ? 'Live' : 'Offline'}
          </span>
        </div>

        {typeof count === 'number' && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 rounded border border-blue-200">
              <span className="text-xs font-semibold text-blue-600">{count}</span>
              <span className="text-xs text-slate-600">tickers</span>
            </div>
            {typeof sequence === 'number' && (
              <div className="flex items-center gap-1 px-2 py-0.5 bg-slate-50 rounded border border-slate-200">
                <span className="text-xs text-slate-500">seq</span>
                <span className="text-xs font-mono font-semibold text-slate-900">{sequence}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div
        className="flex items-center gap-2"
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {lastUpdateTime && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-slate-500">Updated</span>
            <span className="font-mono font-medium text-slate-700">
              {lastUpdateTime.toLocaleTimeString()}
            </span>
          </div>
        )}

        {/* Botón de abrir en nueva ventana */}
        {listName && (
          <button
            onClick={handleOpenNewWindow}
            className="p-1.5 rounded hover:bg-blue-100 transition-colors group"
            title="Abrir en nueva ventana"
          >
            <ExternalLink className="w-4 h-4 text-slate-600 group-hover:text-blue-600" />
          </button>
        )}

        {rightActions}

        {/* Botón de cerrar tabla */}
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-red-100 transition-colors group"
            title="Cerrar tabla"
          >
            <X className="w-4 h-4 text-slate-600 group-hover:text-red-600" />
          </button>
        )}
      </div>
    </div>
  );
}


