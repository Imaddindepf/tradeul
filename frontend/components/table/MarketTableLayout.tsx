'use client';

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, X } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { openScannerWindow } from '@/lib/window-injector';
import { useFloatingWindow, useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { LinkGroupSelector } from '@/components/linking/LinkGroupSelector';

interface MarketTableLayoutProps {
  title: string;
  isLive: boolean;
  rightActions?: ReactNode;
  listName?: string;
  onClose?: () => void;
}

export function MarketTableLayout({
  title,
  isLive,
  rightActions,
  listName,
  onClose,
}: MarketTableLayoutProps) {
  const { t } = useTranslation();
  const { windows, updateWindow } = useFloatingWindow();
  const { getToken } = useAuth();
  const windowId = useCurrentWindowId();
  const currentWindow = windowId ? windows.find(w => w.id === windowId) : null;

  const handleOpenNewWindow = async () => {
    if (!listName) return;

    // Patrón Godel Terminal: about:blank + inyección + SharedWorker
    const wsBaseUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';

    // Obtener token JWT para autenticación del WebSocket
    const token = await getToken({ skipCache: true });
    const wsUrl = token ? `${wsBaseUrl}${wsBaseUrl.includes('?') ? '&' : '?'}token=${token}` : wsBaseUrl;

    // URL absoluta del SharedWorker (necesaria para about:blank)
    const workerUrl = `${window.location.origin}/workers/websocket-shared.js`;

    const popOutWindow = await openScannerWindow(
      {
        listName,
        categoryName: title,
        wsUrl,
        workerUrl,
        token: token || undefined,
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
    <div className="table-drag-handle flex items-center justify-between px-2 py-1 bg-[var(--color-table-header)] border-b border-border cursor-move">
      <div className="flex items-center gap-2">
        <h2 className="text-[11px] font-semibold text-foreground">{title}</h2>

        <div className="flex items-center gap-1">
          <div className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-500' : 'bg-muted-fg/50'}`} />
          <span className={`text-[10px] font-medium ${isLive ? 'text-emerald-600' : 'text-muted-fg'}`}>
            {isLive ? t('common.live') : t('common.offline')}
          </span>
        </div>

      </div>

      <div
        className="flex items-center gap-1"
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {/* Link group selector */}
        {windowId && currentWindow && (
          <LinkGroupSelector windowId={windowId} currentLinkGroup={currentWindow.linkGroup ?? null} />
        )}
        {/* Botón de abrir en nueva ventana */}
        {listName && (
          <button
            onClick={handleOpenNewWindow}
            className="p-0.5 rounded hover:bg-blue-500/15 transition-colors group"
            title="Open in new window"
          >
            <ExternalLink className="w-3 h-3 text-muted-fg group-hover:text-primary" />
          </button>
        )}

        {rightActions}

        {/* Botón de cerrar tabla */}
        {onClose && (
          <button
            onClick={onClose}
            className="p-0.5 rounded hover:bg-red-500/15 transition-colors group"
            title="Close table"
          >
            <X className="w-3 h-3 text-muted-fg group-hover:text-red-600" />
          </button>
        )}
      </div>
    </div>
  );
}


