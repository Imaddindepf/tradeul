'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X, ExternalLink } from 'lucide-react';
import { useAuth, useUser } from '@clerk/nextjs';
import { FloatingWindow as FloatingWindowType, useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { FloatingWindowBase } from '@/components/ui/FloatingWindowBase';

interface FloatingWindowProps {
  window: FloatingWindowType;
}

export function FloatingWindow({ window }: FloatingWindowProps) {
  const { t } = useTranslation();
  const { closeWindow, updateWindow } = useFloatingWindow();
  const { getToken, userId } = useAuth();
  const { user } = useUser();
  const checkIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Detectar si la ventana externa se cerró (desde su pestaña o botón X)
  useEffect(() => {
    if (window.isPoppedOut && window.poppedOutWindow) {
      // Verificar cada 500ms si la ventana sigue abierta
      checkIntervalRef.current = setInterval(() => {
        if (window.poppedOutWindow?.closed) {
          // La ventana externa se cerró, restaurar contenido
          updateWindow(window.id, { isPoppedOut: false, poppedOutWindow: null });
          
          // Si es el chat, invalidar mensajes para forzar recarga desde servidor
          if (window.title === 'Community Chat') {
            const { useChatStore } = require('@/stores/useChatStore');
            const activeTarget = useChatStore.getState().activeTarget;
            if (activeTarget) {
              const key = `${activeTarget.type}:${activeTarget.id}`;
              // Usar invalidateMessages en lugar de clearMessages para forzar recarga
              useChatStore.getState().invalidateMessages(key);
            }
          }
          
          if (checkIntervalRef.current) {
            clearInterval(checkIntervalRef.current);
            checkIntervalRef.current = null;
          }
        }
      }, 500);

      return () => {
        if (checkIntervalRef.current) {
          clearInterval(checkIntervalRef.current);
          checkIntervalRef.current = null;
        }
      };
    }
  }, [window.isPoppedOut, window.poppedOutWindow, window.id, updateWindow]);

  const handleClose = () => {
    closeWindow(window.id);
  };

  const handlePositionChange = (position: { x: number; y: number }) => {
    updateWindow(window.id, position);
  };

  const handleSizeChange = (size: { width: number; height: number }) => {
    updateWindow(window.id, size);
  };

  const handleOpenNewWindow = async () => {
    let popOutWindow: Window | null = null;

    if (window.title === 'Dilution Tracker') {
      // Extraer ticker actual del input de búsqueda
      let currentTicker = '';

      const windowElement = document.getElementById(`floating-window-${window.id}`);
      if (windowElement) {
        const searchInput = windowElement.querySelector('input[type="text"]') as HTMLInputElement;
        if (searchInput && searchInput.value) {
          currentTicker = searchInput.value.trim().toUpperCase();
        }
      }

      // Usar window-injector para about:blank (como scanner)
      const { openDilutionTrackerWindow } = require('@/lib/window-injector');
      popOutWindow = openDilutionTrackerWindow(
        {
          ticker: currentTicker || undefined,
          apiBaseUrl: globalThis.location.origin
        },
        {
          title: `Dilution Tracker${currentTicker ? ` - ${currentTicker}` : ''}`,
          width: 1400,
          height: 900,
          centered: true
        }
      );
    } else if (window.title === 'News') {
      // Abrir News en about:blank con WebSocket
      const { openNewsWindow } = require('@/lib/window-injector');
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
      const workerUrl = `${globalThis.location.origin}/workers/websocket-shared.js`;
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

      popOutWindow = await openNewsWindow(
        {
          wsUrl,
          workerUrl,
          apiBaseUrl
        },
        {
          title: 'News - Tradeul',
          width: 1200,
          height: 800,
          centered: true
        }
      );
    } else if (window.title === 'SEC Filings') {
      // Abrir SEC Filings en about:blank con WebSocket
      const { openSECFilingsWindow } = require('@/lib/window-injector');
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
      const workerUrl = `${globalThis.location.origin}/workers/websocket-shared.js`;

      popOutWindow = openSECFilingsWindow(
        {
          wsUrl,
          workerUrl,
          secApiBaseUrl: process.env.NEXT_PUBLIC_SEC_FILINGS_URL || 'http://localhost:8012'
        },
        {
          title: 'SEC Filings - Tradeul',
          width: 1300,
          height: 850,
          centered: true
        }
      );
    } else if (window.title.includes(' — ')) {
      // Gráfico financiero: "AAPL — Revenue"
      const { openFinancialChartWindow } = require('@/lib/window-injector');

      // Extraer ticker y metricLabel del título "AAPL — Revenue"
      const [ticker, metricLabel] = window.title.split(' — ');

      // Buscar en el registro global de datos de gráficos
      const globalChartData = (globalThis as any).__financialChartData || {};

      // Buscar por ticker y cualquier métrica que coincida
      let chartData = null;
      for (const key of Object.keys(globalChartData)) {
        if (key.startsWith(`${ticker}-`)) {
          const data = globalChartData[key];
          if (data.metricLabel === metricLabel) {
            chartData = data;
            break;
          }
        }
      }

      if (chartData) {
        popOutWindow = openFinancialChartWindow(
          chartData,
          {
            title: window.title,
            width: 1000,
            height: 650,
            centered: true
          }
        );
      } else {
        console.warn('Chart data not found for', window.title);
      }
    } else if (window.title === 'Community Chat') {
      // Abrir Chat en about:blank con WebSocket
      const { openChatWindow } = require('@/lib/window-injector');
      const wsUrl = process.env.NEXT_PUBLIC_CHAT_WS_URL || 'wss://wschat.tradeul.com';
      const apiUrl = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
      
      const token = await getToken();
      if (token) {
        popOutWindow = openChatWindow(
          {
            wsUrl,
            apiUrl,
            token,
            userId: userId || '',
            userName: user?.username || user?.fullName || user?.firstName || 'User',
            userAvatar: user?.imageUrl,
          },
          {
            title: 'Community Chat - Tradeul',
            width: 950,
            height: 700,
            centered: true
          }
        );
      }
    } else if (window.title === 'IPOs') {
      // Abrir IPOs en about:blank
      const { openIPOWindow } = require('@/lib/window-injector');
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

      popOutWindow = openIPOWindow(
        { apiBaseUrl },
        {
          title: 'IPOs - Tradeul',
          width: 1000,
          height: 700,
          centered: true
        }
      );
    } else if (window.title === 'Notes') {
      // Abrir Notes en about:blank
      const { openNotesWindow } = require('@/lib/window-injector');
      
      // Obtener las notas actuales del store
      const { useNotesStore } = require('@/stores/useNotesStore');
      const notesState = useNotesStore.getState();
      
      popOutWindow = openNotesWindow(
        {
          notes: notesState.notes,
          activeNoteId: notesState.activeNoteId,
        },
        {
          title: 'Notes - Tradeul',
          width: 600,
          height: 550,
          centered: true
        }
      );
    } else if (window.title.startsWith('Scanner:')) {
      // Abrir Scanner en about:blank con WebSocket
      const { openScannerWindow } = require('@/lib/window-injector');
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
      const workerUrl = `${globalThis.location.origin}/workers/websocket-shared.js`;

      // Extraer listName del título (ej: "Scanner: Gap Up" -> buscar en el componente)
      const windowElement = document.getElementById(`floating-window-${window.id}`);
      let listName = '';
      let categoryName = window.title.replace('Scanner: ', '');

      // Buscar el listName del componente ScannerTableContent
      if (windowElement) {
        const dataListName = windowElement.getAttribute('data-list-name');
        if (dataListName) {
          listName = dataListName;
        }
      }

      // Mapeo de nombres a listNames (usando traducciones)
      const LIST_NAME_MAP: Record<string, string> = {
        [t('scanner.gapUp')]: 'gappers_up',
        [t('scanner.gapDown')]: 'gappers_down',
        [t('scanner.momentumUp')]: 'momentum_up',
        [t('scanner.momentumDown')]: 'momentum_down',
        [t('scanner.topGainers')]: 'winners',
        [t('scanner.topLosers')]: 'losers',
        [t('scanner.newHighs')]: 'new_highs',
        [t('scanner.newLows')]: 'new_lows',
        [t('scanner.anomalies')]: 'anomalies',
        [t('scanner.highVolume')]: 'high_volume',
        [t('scanner.reversals')]: 'reversals',
      };

      listName = listName || LIST_NAME_MAP[categoryName] || '';

      if (listName) {
        popOutWindow = openScannerWindow(
          {
            listName,
            categoryName,
            wsUrl,
            workerUrl,
          },
          {
            title: `${categoryName} - Tradeul`,
            width: 1400,
            height: 900,
            centered: true
          }
        );
      }
    }

    // Si se abrió la ventana externa, marcar esta como poppedOut y guardar la referencia
    if (popOutWindow) {
      updateWindow(window.id, { isPoppedOut: true, poppedOutWindow: popOutWindow });
    }
  };

  // Cerrar ventana externa y restaurar contenido original
  const handleClosePopOut = () => {
    if (window.poppedOutWindow && !window.poppedOutWindow.closed) {
      window.poppedOutWindow.close();
    }
    updateWindow(window.id, { isPoppedOut: false, poppedOutWindow: null });
  };

  // Si está minimizado, no usar FloatingWindowBase
  if (window.isMinimized) {
    return (
      <div
        className="fixed bottom-0 left-0 bg-white border-t border-l border-r border-slate-300 rounded-t-lg shadow-lg cursor-pointer hover:bg-slate-50 transition-colors"
        style={{
          zIndex: window.zIndex,
          minWidth: '200px',
          padding: '8px 16px',
        }}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-sm font-medium text-slate-700">{window.title}</span>
        </div>
      </div>
    );
  }

  const handleZIndexChange = (zIndex: number) => {
    updateWindow(window.id, { zIndex });
  };

  // Para contenido con cabecera propia, usar su clase de drag handle
  const dragHandleClassName = window.hideHeader ? 'table-drag-handle' : 'window-title-bar';

  return (
    <FloatingWindowBase
      dragHandleClassName={dragHandleClassName}
      initialSize={{ width: window.width, height: window.height }}
      initialPosition={{ x: window.x, y: window.y }}
      initialZIndex={window.zIndex}
      minWidth={window.minWidth || 400}
      minHeight={window.minHeight || 300}
      maxWidth={window.maxWidth || 1600}
      maxHeight={window.maxHeight || 1000}
      enableResizing={true}
      onPositionChange={handlePositionChange}
      onSizeChange={handleSizeChange}
      onZIndexChange={handleZIndexChange}
      className="bg-white"
    >
      <div id={`floating-window-${window.id}`} className="flex flex-col h-full overflow-hidden">
        {/* Title Bar - Solo mostrar si hideHeader es false */}
        {!window.hideHeader && (
          <div className="window-title-bar flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-slate-50 to-white border-b border-slate-200 cursor-move select-none">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <div className="w-2 h-2 rounded-full bg-blue-500" />
              <h3 className="text-sm font-semibold text-slate-800 truncate">{window.title}</h3>
            </div>

            <div className="flex items-center gap-1 ml-4">
              {/* Open in New Window Button */}
              <button
                onMouseDown={(e) => {
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpenNewWindow();
                }}
                className="p-1.5 rounded hover:bg-blue-100 transition-colors group"
                aria-label={t('floatingWindow.openInNewWindow')}
                title={t('floatingWindow.openInNewWindow')}
              >
                <ExternalLink className="w-3.5 h-3.5 text-slate-600 group-hover:text-blue-600" />
              </button>

              {/* Close Button */}
              <button
                onMouseDown={(e) => {
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  handleClose();
                }}
                className="p-1.5 rounded hover:bg-red-100 transition-colors group"
                aria-label={t('common.close')}
              >
                <X className="w-4 h-4 text-slate-600 group-hover:text-red-600" />
              </button>
            </div>
          </div>
        )}

        {/* Floating Close Button for hideHeader windows */}
        {window.hideHeader && (
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              handleClose();
            }}
            className="absolute top-1 right-1 z-10 p-1 rounded bg-white/80 hover:bg-red-100 transition-colors group shadow-sm border border-slate-200"
            aria-label={t('common.close')}
            title={t('common.close')}
          >
            <X className="w-3.5 h-3.5 text-slate-500 group-hover:text-red-600" />
          </button>
        )}

        {/* Content */}
        <div className={`flex-1 overflow-auto bg-white ${window.hideHeader ? 'h-full' : ''}`}>
          {window.isPoppedOut ? (
            // Placeholder cuando el contenido está en ventana externa
            <div className="flex flex-col items-center justify-center h-full bg-slate-50 p-8">
              <div className="w-16 h-16 mb-4 rounded-full bg-blue-100 flex items-center justify-center">
                <ExternalLink className="w-8 h-8 text-blue-600" />
              </div>
              <p className="text-slate-700 font-medium text-center mb-2">
                {t('floatingWindow.poppedOutMessage')}
              </p>
              <p className="text-slate-500 text-sm text-center mb-6">
                {t('floatingWindow.poppedOutDescription')}
              </p>
              <button
                onClick={handleClosePopOut}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
              >
                {t('floatingWindow.closeExternalResume')}
              </button>
            </div>
          ) : (
            window.content
          )}
        </div>
      </div>
    </FloatingWindowBase>
  );
}

