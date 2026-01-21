'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { Navbar, NavbarContent, UserMenu } from '@/components/layout/Navbar';
import { PinnedCommands } from '@/components/layout/PinnedCommands';
import { MarketStatusPopover } from '@/components/market/MarketStatusPopover';
import { TerminalPalette } from '@/components/ui/TerminalPalette';
import { HelpModal } from '@/components/ui/HelpModal';
import { Settings2, LayoutGrid, HelpCircle } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { WorkspaceTabs } from '@/components/layout/WorkspaceTabs';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import { FilterManagerContent } from '@/components/scanner/FilterManagerContent';
import { TickersWithNewsContent } from '@/components/scanner/TickersWithNewsContent';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';
import { FinancialsContent } from '@/components/financials/FinancialsContent';
import { NewsContent } from '@/components/news/NewsContent';
import { TickerStrip } from '@/components/ticker/TickerStrip';
import { ChatContent } from '@/components/chat/ChatContent';
import { CatalystAlertsConfig } from '@/components/catalyst-alerts';
import { IPOContent } from '@/components/ipos/IPOContent';
import { QuoteMonitor as QuoteMonitorContent } from '@/components/quote-monitor/QuoteMonitor';
import { NotesContent } from '@/components/notes/NotesContent';
import { PatternMatchingContent } from '@/components/pattern-matching';
import { RatioAnalysisContent } from '@/components/ratio-analysis';
import { ScreenerContent } from '@/components/screener';
import { HistoricalMultipleSecurityContent } from '@/components/historical-multiple-security';
import { ChartContent } from '@/components/chart/ChartContent';
import { DescriptionContent } from '@/components/description/DescriptionContent';
import { EarningsCalendarContent } from '@/components/floating-window/EarningsCalendarContent';

// Adaptador para convertir MarketSession a PolygonMarketStatus
function adaptMarketSession(session: MarketSession) {
  let market: 'open' | 'closed' | 'extended-hours' = 'closed';
  let earlyHours = false;
  let afterHours = false;

  if (session.current_session === 'PRE_MARKET') {
    market = 'extended-hours';
    earlyHours = true;
  } else if (session.current_session === 'MARKET_OPEN') {
    market = 'open';
  } else if (session.current_session === 'POST_MARKET') {
    market = 'extended-hours';
    afterHours = true;
  }

  return {
    market,
    serverTime: session.timestamp || new Date().toISOString(),
    earlyHours,
    afterHours,
    exchanges: {
      nasdaq: market === 'open' ? 'open' : market === 'extended-hours' ? 'extended-hours' : 'closed',
      nyse: market === 'open' ? 'open' : market === 'extended-hours' ? 'extended-hours' : 'closed',
      otc: market === 'open' ? 'open' : market === 'extended-hours' ? 'extended-hours' : 'closed',
    },
  };
}

const DEFAULT_CATEGORIES = ['gappers_up', 'gappers_down', 'momentum_up', 'winners', 'new_highs', 'new_lows', 'high_volume', 'post_market'];

export default function ScannerPage() {
  const { t } = useTranslation();
  const [session, setSession] = useState<MarketSession | null>(null);
  const [mounted, setMounted] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandInput, setCommandInput] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  // Quote inline: ticker activo y si está mostrando la tira
  const [activeQuoteTicker, setActiveQuoteTicker] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { windows, openWindow, closeWindow } = useFloatingWindow();
  const { openScannerTable, closeScannerTable, isScannerTableOpen, executeTickerCommand, getScannerCategory } = useCommandExecutor();
  const { getSavedLayout, hasLayout, isLayoutInitialized } = useLayoutPersistence();
  const { activeWorkspace, saveCurrentLayout } = useWorkspaces();

  // WebSocket (ya autenticado desde AuthWebSocketProvider)
  const ws = useWebSocket();

  const layoutRestoredRef = useRef(false);
  const initialTablesOpenedRef = useRef(false);

  // Función para reconstruir contenido de ventana por título
  const getWindowContent = useCallback((title: string) => {
    // === Ventanas generales (sin ticker específico) ===
    if (title === 'Settings') return <SettingsContent />;
    if (title === 'Filter Manager' || title === 'Filtros') return <FilterManagerContent />;
    if (title === 'Dilution Tracker') return <DilutionTrackerContent />;
    if (title === 'SEC Filings') return <SECFilingsContent />;
    if (title === 'News') return <NewsContent />;
    if (title === 'Financial Analysis') return <FinancialsContent />;
    if (title === 'Community Chat') return <ChatContent />;
    if (title === 'Catalyst Alerts') return <CatalystAlertsConfig />;
    if (title === 'IPOs') return <IPOContent />;
    if (title === 'Quote Monitor') return <QuoteMonitorContent />;
    if (title === 'Notes') return <NotesContent />;
    if (title === 'Pattern Matching') return <PatternMatchingContent />;
    if (title === 'Ratio Analysis') return <RatioAnalysisContent />;
    if (title === 'Stock Screener') return <ScreenerContent />;
    if (title === 'Historical Multiple Security') return <HistoricalMultipleSecurityContent />;
    if (title === 'Earnings Calendar') return <EarningsCalendarContent />;

    // === Ventanas con ticker específico ===
    // Chart: TICKER
    if (title.startsWith('Chart: ')) {
      const ticker = title.replace('Chart: ', '');
      return <ChartContent ticker={ticker} exchange="US" />;
    }
    // Description: TICKER
    if (title.startsWith('Description: ')) {
      const ticker = title.replace('Description: ', '');
      return <DescriptionContent ticker={ticker} exchange="US" />;
    }
    // DT: TICKER (Dilution Tracker con ticker)
    if (title.startsWith('DT: ')) {
      const ticker = title.replace('DT: ', '');
      return <DilutionTrackerContent initialTicker={ticker} />;
    }
    // FA: TICKER (Financial Analysis con ticker)
    if (title.startsWith('FA: ')) {
      const ticker = title.replace('FA: ', '');
      return <FinancialsContent initialTicker={ticker} />;
    }
    // SEC: TICKER
    if (title.startsWith('SEC: ')) {
      const ticker = title.replace('SEC: ', '');
      return <SECFilingsContent initialTicker={ticker} />;
    }
    // News (con o sin ticker en título - el ticker se persiste en componentState)
    if (title === 'News' || title.startsWith('News: ')) {
      // Para compatibilidad con ventanas guardadas con formato antiguo
      const ticker = title.startsWith('News: ') ? title.replace('News: ', '') : undefined;
      return <NewsContent initialTicker={ticker} />;
    }
    // Patterns: TICKER
    if (title.startsWith('Patterns: ')) {
      const ticker = title.replace('Patterns: ', '');
      return <PatternMatchingContent initialTicker={ticker} />;
    }
    // Quote: TICKER (tira de precio) - NO restauramos porque es muy específico

    // === Tablas del scanner ===
    if (title.startsWith('Scanner: ')) {
      const categoryName = title.replace('Scanner: ', '');
      const categoryIds = ['gappers_up', 'gappers_down', 'momentum_up', 'momentum_down', 'winners', 'losers', 'new_highs', 'new_lows', 'anomalies', 'high_volume', 'reversals', 'post_market', 'with_news'];
      for (const categoryId of categoryIds) {
        const category = getScannerCategory(categoryId);
        if (category && category.name === categoryName) {
          if (categoryId === 'with_news') {
            return <TickersWithNewsContent title={category.name} />;
          }
          return (
            <ScannerTableContent
              categoryId={categoryId}
              categoryName={category.name}
            />
          );
        }
      }
    }

    return null;
  }, [getScannerCategory]);

  // Restaurar layout del workspace activo O abrir tablas por defecto
  useEffect(() => {
    if (!mounted) return;

    // NUEVO: Usar workspaces si está disponible
    const workspaceLayouts = activeWorkspace?.windowLayouts || [];
    const hasWorkspaceLayouts = workspaceLayouts.length > 0;

    // Caso 1: Workspace tiene ventanas guardadas → restaurarlas
    if (hasWorkspaceLayouts && !layoutRestoredRef.current) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;

      setTimeout(() => {
        workspaceLayouts.forEach((layout) => {
          const content = getWindowContent(layout.title);
          if (content) {
            const hideHeader = layout.title.startsWith('Scanner:');
            openWindow({
              id: layout.id,
              title: layout.title,
              content,
              x: layout.position.x,
              y: layout.position.y,
              width: layout.size.width,
              height: layout.size.height,
              hideHeader,
            });
          }
        });
      }, 100);
      return;
    }

    // LEGACY: Compatibilidad con sistema antiguo (windowLayouts sin workspaces)
    if (!hasWorkspaceLayouts && hasLayout && !layoutRestoredRef.current) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;
      const savedLayout = getSavedLayout();

      setTimeout(() => {
        savedLayout.forEach((layout) => {
          const content = getWindowContent(layout.title);
          if (content) {
            const hideHeader = layout.title.startsWith('Scanner:');
            openWindow({
              id: layout.id,
              title: layout.title,
              content,
              x: layout.x,
              y: layout.y,
              width: layout.width,
              height: layout.height,
              hideHeader,
            });
          }
        });
      }, 100);
      return;
    }

    // Caso 2: Usuario ya usó el sistema pero cerró todas las ventanas
    if (isLayoutInitialized && !hasLayout && !hasWorkspaceLayouts) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;
      return;
    }

    // Caso 3: Primera vez (nunca ha usado el sistema)
    if (!isLayoutInitialized && !hasLayout && !hasWorkspaceLayouts && !initialTablesOpenedRef.current) {
      initialTablesOpenedRef.current = true;

      // Cargar categorías de localStorage o usar default
      let categories = DEFAULT_CATEGORIES;
      try {
        const saved = localStorage.getItem('scanner_categories');
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length > 0) {
            categories = parsed;
          }
        }
      } catch (e) {
        console.error('Error loading saved categories:', e);
      }

      // Abrir las tablas por defecto con delay para escalonar
      setTimeout(() => {
        categories.forEach((categoryId, index) => {
          setTimeout(() => {
            openScannerTable(categoryId, index);
          }, index * 50);
        });
      }, 100);
    }
  }, [mounted, hasLayout, isLayoutInitialized, activeWorkspace, getSavedLayout, getWindowContent, openWindow, openScannerTable]);

  // Montaje inicial y keyboard shortcuts
  useEffect(() => {
    setMounted(true);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+K: Abrir terminal
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const input = document.querySelector('input[type="text"]') as HTMLInputElement;
        if (input) {
          input.focus();
          setCommandPaletteOpen(true);
        }
      }

      // ?: Abrir ayuda (solo si no estamos escribiendo en un input)
      if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault();
        setHelpOpen(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Fetch market session inicial
  useEffect(() => {
    const fetchSession = async () => {
      try {
        const sessionData = await getMarketSession();
        setSession(sessionData);
      } catch (error) {
        console.error('Error fetching session:', error);
      }
    };

    fetchSession();
    // Polling de respaldo cada 60 segundos (el WebSocket maneja cambios en tiempo real)
    const interval = setInterval(fetchSession, 60000);
    return () => clearInterval(interval);
  }, []);

  // Escuchar cambios de sesión en tiempo real vía WebSocket
  useEffect(() => {
    const subscription = ws.messages$.subscribe((message: any) => {
      if (message.type === 'market_session_change' && message.data) {
        console.log('📊 Market session changed:', message.data);

        // Actualizar el estado de sesión inmediatamente
        setSession((prev) => ({
          ...prev,
          current_session: message.data.current_session,
          trading_date: message.data.trading_date,
          timestamp: message.data.timestamp,
        } as MarketSession));
      }
    });

    return () => subscription.unsubscribe();
  }, [ws.messages$]);

  // Toggle de categoría del scanner (desde CommandPalette)
  const handleToggleCategory = useCallback((categoryId: string) => {
    if (isScannerTableOpen(categoryId)) {
      closeScannerTable(categoryId);
    } else {
      openScannerTable(categoryId, windows.length);
    }
  }, [isScannerTableOpen, closeScannerTable, openScannerTable, windows.length]);

  // Verificar si hay ventanas del scanner abiertas
  const scannerWindowsCount = windows.filter(w => w.title.startsWith('Scanner:')).length;
  const hasNoWindows = windows.length === 0;

  return (
    <>
      {/* Navbar */}
      <Navbar>
        <div className="flex items-center h-full w-full gap-3">
          {/* Command Prompt / Quote Strip */}
          <div className="flex-1 flex items-center gap-2 relative">
            <span className="text-slate-400 font-mono text-sm select-none">{'>'}</span>

            <div className="flex-1 relative">
              {/* Input siempre presente */}
              <input
                ref={inputRef}
                type="text"
                value={commandInput}
                onChange={(e) => {
                  const newValue = e.target.value.toUpperCase();

                  // Si hay un ticker activo y el usuario escribe algo nuevo
                  if (activeQuoteTicker && !commandInput && newValue) {
                    // Prefijar con el ticker activo
                    setCommandInput(activeQuoteTicker + ' ' + newValue);
                  } else {
                    setCommandInput(newValue);
                  }

                  // Abrir paleta cuando el usuario empieza a escribir
                  if (!commandPaletteOpen) {
                    setCommandPaletteOpen(true);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape' && activeQuoteTicker) {
                    setActiveQuoteTicker(null);
                    setCommandInput('');
                  }
                }}
                onFocus={() => {
                  if (!activeQuoteTicker) {
                    setCommandPaletteOpen(true);
                  }
                }}
                className={`w-full px-3 py-2 font-mono text-sm text-slate-900 bg-transparent
                         border-b-2 border-transparent focus:border-blue-500
                         outline-none transition-all ${activeQuoteTicker && !commandInput ? 'opacity-0 absolute' : ''}`}
              />

              {/* Mostrar TickerStrip encima cuando hay quote activo y no hay input */}
              {activeQuoteTicker && !commandInput && (
                <div
                  className="flex items-center py-2 cursor-text"
                  onClick={() => inputRef.current?.focus()}
                >
                  <TickerStrip symbol={activeQuoteTicker} exchange="US" />
                </div>
              )}

              {/* Placeholder con cursor parpadeante */}
              {!commandInput && !activeQuoteTicker && (
                <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none flex items-center">
                  <span className="text-slate-400 font-mono text-sm">type a command</span>
                  <span className="w-0.5 h-4 bg-blue-500 ml-0.5 animate-pulse" />
                </div>
              )}
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => setHelpOpen(true)}
                className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
                title="Ayuda (?)"
              >
                <HelpCircle className="w-4 h-4" />
              </button>
              <kbd className="text-xs text-slate-400 font-mono px-1.5 py-0.5 bg-slate-100 rounded">Ctrl+K</kbd>
            </div>
          </div>

          {/* Pinned Commands */}
          <div className="flex items-center px-4">
            <PinnedCommands
              onOpenCommandPalette={(value) => {
                setCommandInput(value);
                setCommandPaletteOpen(true);
              }}
            />
          </div>

          {/* Market Status + User Menu */}
          <div className="flex-1 flex items-center justify-end gap-4">
            {session && mounted && <MarketStatusPopover status={adaptMarketSession(session)} />}
            <UserMenu />
          </div>
        </div>
      </Navbar>

      {/* Terminal Palette */}
      <TerminalPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        searchValue={commandInput}
        onSearchChange={setCommandInput}
        onOpenHelp={() => setHelpOpen(true)}
        onExecuteTickerCommand={(ticker, command, exchange) => {
          // Quick Quote (Q) se muestra inline en la navbar, no abre ventana
          if (command === 'quote' || command === 'span') {
            setActiveQuoteTicker(ticker);
            setCommandPaletteOpen(false);
            setCommandInput('');
            // Enfocar el input oculto para capturar teclas
            setTimeout(() => inputRef.current?.focus(), 50);
            return;
          }
          // Limpiar el quote activo cuando se ejecuta otro comando
          setActiveQuoteTicker(null);
          executeTickerCommand(ticker, command, exchange);
        }}
      />

      {/* Help Modal */}
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />

      {/* Main Content - usa variable CSS para el fondo */}
      {/* Altura: 100vh - 64px (navbar) - 32px (workspace tabs) */}
      <main
        className="h-[calc(100vh-64px-32px)] relative overflow-hidden transition-colors duration-200"
        style={{ backgroundColor: 'var(--color-background, #f8fafc)' }}
      >
        {/* Empty state cuando no hay ventanas */}
        {hasNoWindows && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-slate-500">
              <LayoutGrid className="h-16 w-16 mx-auto mb-4 text-slate-300" />
              <p className="text-xl font-semibold text-slate-700">{t('workspace.noWindowsOpen')}</p>
              <p className="text-sm mt-2 text-slate-500">
                {t('workspace.useCommandToOpen')}
              </p>
              <div className="mt-4 flex gap-2 justify-center">
                {DEFAULT_CATEGORIES.slice(0, 3).map((catId) => {
                  const category = getScannerCategory(catId);
                  return (
                    <button
                      key={catId}
                      onClick={() => openScannerTable(catId, 0)}
                      className="px-3 py-1.5 text-xs font-medium bg-blue-500 text-white rounded-md hover:bg-blue-600"
                    >
                      {category?.name || catId}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Las ventanas flotantes se renderizan automáticamente desde FloatingWindowContext */}
      </main>

      {/* Workspace Tabs - Barra inferior estilo GODEL/IBKR */}
      <WorkspaceTabs getWindowContent={getWindowContent} />
    </>
  );
}
