'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import type { MarketSession } from '@/lib/types';
import { Navbar, NavbarContent, UserMenu } from '@/components/layout/Navbar';
import { PinnedCommands } from '@/components/layout/PinnedCommands';
import { MarketStatusPopover } from '@/components/market/MarketStatusPopover';
import { TerminalPalette } from '@/components/ui/TerminalPalette';
import { HelpModal } from '@/components/ui/HelpModal';
import { Settings2 } from 'lucide-react';
import { WorkspaceEmptyState } from '@/components/workspace/WorkspaceEmptyState';
import { Z_INDEX, floatingFocusManager } from '@/lib/z-index';
import { hasTickerSearch, typeIntoTickerSearch } from '@/lib/tickerSearchRegistry';
import { useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useWorkspaceLayouts } from '@/hooks/useWorkspaceLayouts';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { WorkspaceTabs } from '@/components/layout/WorkspaceTabs';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
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
import { PredictionMarketsContent } from '@/components/floating-window';
import { EventTableContent } from '@/components/events';
import { useEventFiltersStore, type ActiveEventFilters } from '@/stores/useEventFiltersStore';
import { useMarketSessionStore, selectSession } from '@/stores/useMarketSessionStore';
import { SYSTEM_EVENT_CATEGORIES } from '@/lib/commands';
// Phase 1: All window types for full restoration
import { FinancialAnalystCanvas } from '@/components/financial-analyst';
import { InsightsPanel } from '@/components/insights';
import { HeatmapContent } from '@/components/heatmap';
import { ImapContent } from '@/components/imap';
import { GlossaryContent } from '@/components/glossary';
import { PatternRealtimeContent } from '@/components/pattern-realtime';
import { InsiderTradingContent, InsiderGlossaryContent } from '@/components/insider-trading';
import { AIAgentContent } from '@/components/ai-agent';
import { InstitutionalHoldingsContent } from '@/components/institutional-holdings';
import { AnalystRatingsContent } from '@/components/analyst-ratings';
import { MarketPulseContent } from '@/components/market-pulse';
import { OpenULContent } from '@/components/openul/OpenULContent';
import { ConfigWindow, type AlertWindowConfig } from '@/components/config/ConfigWindow';
import { UserScanTableContent } from '@/components/scanner/UserScanTableContent';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { BugReportsAdminContent } from '@/components/dashboard-toolbar/BugReportsAdminContent';
import { TimeAndSalesContent } from '@/components/tape/TimeAndSalesContent';
import { TVChartContent } from '@/components/tvchart';
import { FuturesMonitorContent } from '@/components/markets/FuturesMonitorContent';
import { ForexMonitorContent } from '@/components/markets/ForexMonitorContent';
import { TopNewsContent } from '@/components/news/TopNewsContent';
import { BacktestPanelContent } from '@/components/backtest-floating/BacktestFloatingWindow';
import { APIContent } from '@/components/floating-window/APIContent';
import { useAuth } from '@clerk/nextjs';

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

export default function ScannerPage() {
  // Sesión desde el store global único (sincronizado por useMarketClockSync).
  const session = useMarketSessionStore(selectSession);
  const [mounted, setMounted] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandInput, setCommandInput] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  // Quote inline: ticker activo y si está mostrando la tira
  const [activeQuoteTicker, setActiveQuoteTicker] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Refs sincronizados para que el listener global de teclado (deps []) lea
  // siempre el estado actual sin re-suscribirse.
  const commandPaletteOpenRef = useRef(commandPaletteOpen);
  commandPaletteOpenRef.current = commandPaletteOpen;
  const helpOpenRef = useRef(helpOpen);
  helpOpenRef.current = helpOpen;

  const { openWindow, closeWindow } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();
  const {
    openScannerTable,
    closeScannerTable,
    isScannerTableOpen,
    executeTickerCommand,
    getScannerCategory,
    executeCommand,
    openEventTable,
    } = useCommandExecutor();
  const { applyLayout } = useWorkspaceLayouts();
  const { getSavedLayout, hasLayout, isLayoutInitialized } = useLayoutPersistence();
  const { activeWorkspace, saveCurrentLayout } = useWorkspaces();

  const layoutRestoredRef = useRef(false);
  const initialTablesOpenedRef = useRef(false);

  // ── Gate: do NOT restore the layout until the backend state is known ──
  // The store hydrates from THIS browser's localStorage, which can be stale
  // (another browser has the real layout) or empty (Safari ITP eviction).
  // Restoring from it and auto-saving 3s later overwrites the server copy.
  // We wait for loadFromBackend to resolve; fallback timeout covers offline
  // sessions and signed-out users (where the load never runs).
  const backendLoadComplete = useUserPreferencesStore((s) => s.backendLoadComplete);
  const { isLoaded: authLoaded, isSignedIn } = useAuth();
  const [restoreGateOpen, setRestoreGateOpen] = useState(false);
  useEffect(() => {
    if (restoreGateOpen) return;
    if (backendLoadComplete || (authLoaded && !isSignedIn)) {
      setRestoreGateOpen(true);
      return;
    }
    const t = setTimeout(() => setRestoreGateOpen(true), 5000);
    return () => clearTimeout(t);
  }, [restoreGateOpen, backendLoadComplete, authLoaded, isSignedIn]);
  // Suppresses the "No windows open" empty state during the brief gap between
  // mount and layout restoration. Without this, F5 reload flashes the empty
  // state for ~100–250 ms while persisted layouts hydrate and open.
  const [layoutReady, setLayoutReady] = useState(false);

  // Función para reconstruir contenido de ventana por título y componentState
  const getWindowContent = useCallback((layout: { title: string; componentState?: Record<string, unknown> }) => {
    const { title, componentState } = layout;

    // === Ventanas generales (sin ticker específico) ===
    if (title === 'Settings') return <SettingsContent />;
    if (title === 'Dilution Tracker') return <DilutionTrackerContent />;
    if (title === 'SEC Filings') return <SECFilingsContent />;
    if (title === 'News') return <NewsContent />;
    if (title === 'Financial Analysis') return <FinancialsContent />;
    if (title === 'Financials') return <FinancialsContent />;
    if (title === 'Community Chat') return <ChatContent />;
    if (title === 'Catalyst Alerts') return <CatalystAlertsConfig />;
    // Legacy: ventanas restauradas como "AI Alerts" → Agent (Mis workflows)
    if (title === 'AI Alerts') return <AIAgentContent />;
    if (title === 'IPOs') return <IPOContent />;
    if (title === 'Quote Monitor') return <QuoteMonitorContent />;
    if (title === 'Notes') return <NotesContent />;
    if (title === 'Pattern Matching') return <PatternMatchingContent />;
    if (title === 'Ratio Analysis') return <RatioAnalysisContent />;
    if (title === 'Stock Screener') return <ScreenerContent />;
    if (title === 'Historical Multiple Security') return <HistoricalMultipleSecurityContent />;
    if (title === 'Earnings Calendar') return <EarningsCalendarContent />;
    // New window types — full restoration
    if (title === 'Financial Analyst') return <FinancialAnalystCanvas />;
    if (title === 'Insights') return <InsightsPanel />;
    if (title === 'Prediction Markets') return <PredictionMarketsContent />;
    if (title === 'Market Heatmap') return <HeatmapContent />;
    if (title === 'World Venue Map') return <ImapContent />;
    if (title === 'Indicators') return <GlossaryContent />;
    if (title === 'Pattern Real-Time') return <PatternRealtimeContent />;
    if (title === 'Insider Trading') return <InsiderTradingContent />;
    if (title === 'Insider Trading Guide') return <InsiderGlossaryContent />;
    if (title === 'AI Agent') return <AIAgentContent />;
    if (title === 'Institutional Holdings') return <InstitutionalHoldingsContent />;
    if (title === 'Analyst Ratings') return <AnalystRatingsContent />;
    if (title === 'Market Pulse') return <MarketPulseContent onOpenTicker={(sym) => executeTickerCommand(sym, 'chart')} />;
    if (title === 'Openul — Breaking News') return <OpenULContent />;
    if (title === 'Bug Reports Admin') return <BugReportsAdminContent />;
    if (title === 'Time & Sales') return <TimeAndSalesContent />;
    if (title === 'TradingView') return <TVChartContent />;
    if (title === 'Futures' || title === 'Futuros') return <FuturesMonitorContent />;
    if (title === 'Forex') return <ForexMonitorContent />;
    if (title === 'Top News') return <TopNewsContent />;
    if (title === 'OddsMaker — Backtester') return <BacktestPanelContent />;
    if (title === 'API — Developer Access' || title === 'API — Acceso desarrollador') return <APIContent />;
    // Alias ES de Indicators (el título guardado depende del idioma activo)
    if (title === 'Indicadores') return <GlossaryContent />;
    // Alias del título actual del comando MP
    if (title === 'Multi-Security') return <HistoricalMultipleSecurityContent />;
    if (title === 'Chart') return <ChartContent ticker={(componentState?.ticker as string) || 'AAPL'} />;
    // Strategy Builder - restore with full callbacks for creating event/scanner windows
    if (title === 'Strategy Builder') return (
      <ConfigWindow
        onCreateAlertWindow={(config: AlertWindowConfig) => {
          const filterStore = useEventFiltersStore.getState();
          const prefStore = useUserPreferencesStore.getState();
          const categoryId = `evt_custom_${Date.now()}`;
          filterStore.setAllFilters(categoryId, { ...config.filters, event_types: config.eventTypes });
          const cs = { restoreType: 'event_table', categoryId, categoryName: config.name, eventTypes: config.eventTypes };
          const winId = openWindow({
            title: `Events: ${config.name}`,
            content: <EventTableContent categoryId={categoryId} categoryName={config.name} eventTypes={config.eventTypes} />,
            width: 800, height: 500, x: 220, y: 170, minWidth: 500, minHeight: 300, hideHeader: true,
            componentState: cs,
          });
          prefStore.updateWindowComponentState(winId, cs);
        }}
        onCreateScannerWindow={(savedFilter: any) => {
          const prefStore = useUserPreferencesStore.getState();
          const categoryId = `uscan_${savedFilter.id}`;
          const cs = { restoreType: 'user_scan', categoryId, categoryName: savedFilter.name, scanId: savedFilter.id };
          const winId = openWindow({
            title: `Scanner: ${savedFilter.name}`,
            content: <ScannerTableContent categoryId={categoryId} categoryName={savedFilter.name} />,
            width: 850, height: 500, x: 400, y: 200, minWidth: 500, minHeight: 300, hideHeader: true,
            componentState: cs,
          });
          prefStore.updateWindowComponentState(winId, cs);
        }}
      />
    );

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
    // Time & Sales: TICKER (comando TAPE)
    if (title.startsWith('Time & Sales: ')) {
      const ticker = title.replace('Time & Sales: ', '');
      return <TimeAndSalesContent initialSymbol={ticker} />;
    }
    // TradingView: TICKER (comando TVC)
    if (title.startsWith('TradingView: ')) {
      const ticker = title.replace('TradingView: ', '');
      return <TVChartContent initialSymbol={ticker} />;
    }
    // Quote: TICKER (tira de precio) - NO restauramos porque es muy específico

    // === Tablas del scanner ===
    if (title.startsWith('Scanner: ')) {
      const categoryName = title.replace('Scanner: ', '');

      // 1) Intentar restaurar desde componentState (user scans)
      if (componentState?.restoreType === 'user_scan' && componentState.categoryId && componentState.categoryName) {
        return (
          <ScannerTableContent
            categoryId={componentState.categoryId as string}
            categoryName={componentState.categoryName as string}
          />
        );
      }

      // 2) Buscar en categorías predefinidas del scanner
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

    // === Tablas de eventos ===
    if (title.startsWith('Events: ')) {
      const eventName = title.replace('Events: ', '');

      // 1) Restaurar desde componentState (tiene toda la metadata guardada)
      if (componentState?.restoreType) {
        const restoreType = componentState.restoreType as string;

        if (restoreType === 'event_table' || restoreType === 'user_strategy') {
          const categoryId = componentState.categoryId as string;
          const categoryName = componentState.categoryName as string;
          const eventTypes = componentState.eventTypes as string[] || [];
          const strategyId = componentState.strategyId as number | undefined;

          // Aplicar los filtros del snapshot del workspace como punto de partida.
          // Si hay strategyId, EventTableContent sincronizará desde la API al montar.
          if (componentState.filters && categoryId) {
            useEventFiltersStore.getState().setAllFilters(categoryId, componentState.filters as ActiveEventFilters);
          }

          return (
            <EventTableContent
              categoryId={categoryId}
              categoryName={categoryName}
              eventTypes={eventTypes}
              strategyId={strategyId}
              defaultFilters={componentState.defaultFilters as any}
            />
          );
        }
      }

      // 2) Fallback: buscar en categorías del sistema por label (ventanas sin componentState)
      const systemCat = SYSTEM_EVENT_CATEGORIES.find(c => c.label === eventName);
      if (systemCat) {
        return (
          <EventTableContent
            categoryId={systemCat.id}
            categoryName={systemCat.label}
            eventTypes={systemCat.eventTypes}
            defaultFilters={systemCat.defaultFilters}
          />
        );
      }
    }

    return null;
  }, [getScannerCategory, openWindow]);

  // Restaurar layout del workspace activo O abrir tablas por defecto
  useEffect(() => {
    if (!mounted) return;
    // Wait until the server state is applied to the store (or the gate times
    // out). Restoring earlier reads a stale/empty local snapshot and the
    // subsequent auto-save propagates it to the backend, destroying the
    // layout saved from other browsers.
    if (!restoreGateOpen) return;
    // Already restored — skip all branches
    if (layoutRestoredRef.current) return;

    const workspaceLayouts = activeWorkspace?.windowLayouts || [];
    const hasWorkspaceLayouts = workspaceLayouts.length > 0;

    // Caso 1: Workspace tiene ventanas guardadas → restaurarlas
    if (hasWorkspaceLayouts) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;

      setTimeout(() => {
        workspaceLayouts.forEach((layout) => {
          const content = getWindowContent(layout);
          if (content) {
            const hideHeader = layout.title.startsWith('Scanner:') || layout.title.startsWith('Events:') || layout.title === 'Market Pulse';
            openWindow({
              id: layout.id,
              title: layout.title,
              content,
              x: layout.position.x,
              y: layout.position.y,
              width: layout.size.width,
              height: layout.size.height,
              hideHeader,
              componentState: layout.componentState,
              linkGroup: (layout as any).linkGroup || undefined,
            } as any);
          }
        });
        setLayoutReady(true);
      }, 100);
      return;
    }

    // LEGACY: Compatibilidad con sistema antiguo (windowLayouts sin workspaces)
    if (!hasWorkspaceLayouts && hasLayout) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;
      const savedLayout = getSavedLayout();

      setTimeout(() => {
        savedLayout.forEach((layout) => {
          const content = getWindowContent({ title: layout.title });
          if (content) {
            const hideHeader = layout.title.startsWith('Scanner:') || layout.title.startsWith('Events:') || layout.title === 'Market Pulse';
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
        setLayoutReady(true);
      }, 100);
      return;
    }

    // Caso 2: Usuario ya usó el sistema pero cerró todas las ventanas
    if (isLayoutInitialized && !hasLayout && !hasWorkspaceLayouts) {
      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;
      setLayoutReady(true);
      return;
    }

    // Caso 3: Primera vez — no abrimos nada. El usuario nuevo ve el empty
    // state con los layouts predefinidos y elige cómo montar su workspace.
    if (!isLayoutInitialized && !hasLayout && !hasWorkspaceLayouts && !initialTablesOpenedRef.current) {
      // Check if Zustand has finished hydrating from localStorage.
      // If it hasn't, skip and let the effect re-run after hydration.
      const hasHydrated = useUserPreferencesStore.persist?.hasHydrated?.() ?? true;
      if (!hasHydrated) return;

      layoutRestoredRef.current = true;
      initialTablesOpenedRef.current = true;
      setLayoutReady(true);
    }
  }, [mounted, restoreGateOpen, hasLayout, isLayoutInitialized, activeWorkspace, getSavedLayout, getWindowContent, openWindow]);

  // Safety net: if layout restoration never completes (edge case), reveal the
  // empty state after 1.5s so the user is never left staring at a blank canvas.
  useEffect(() => {
    if (layoutReady) return;
    const t = setTimeout(() => setLayoutReady(true), 1500);
    return () => clearTimeout(t);
  }, [layoutReady]);

  // Montaje inicial y keyboard shortcuts
  useEffect(() => {
    setMounted(true);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd+K: Abrir terminal y enfocar el prompt (ref directo, robusto)
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        inputRef.current?.focus();
        setCommandPaletteOpen(true);
      }

      // ?: Abrir ayuda (solo si no estamos escribiendo en un input)
      if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault();
        setHelpOpen(true);
      }

      // Type-ahead: al teclear una LETRA con una ventana enfocada, enrutamos la
      // pulsación al buscador de ticker de esa ventana. Excepciones: con la
      // paleta de comandos (Cmd+K) o la ayuda abiertas, con modificadores, o si
      // ya estamos escribiendo en un campo.
      if (
        /^[a-zA-Z]$/.test(e.key) &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !commandPaletteOpenRef.current &&
        !helpOpenRef.current
      ) {
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName;
        const isTyping =
          tag === 'INPUT' ||
          tag === 'TEXTAREA' ||
          tag === 'SELECT' ||
          !!target?.isContentEditable;

        if (!isTyping) {
          const focusedId = floatingFocusManager.getCurrent();
          if (focusedId && hasTickerSearch(focusedId)) {
            e.preventDefault();
            typeIntoTickerSearch(focusedId, e.key);
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

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
        <div className="flex items-center h-full w-full">
          {/* Left: Command Prompt / Quote Strip */}
          <div className="flex items-center gap-1.5 relative min-w-0 w-[450px] shrink-0">
            <span className="text-muted-fg/50 font-mono text-xs select-none pl-1">{'>'}</span>

            <div className="flex-1 relative min-w-0">
              {/* Input siempre presente */}
              <input
                ref={inputRef}
                type="text"
                value={commandInput}
                onChange={(e) => {
                  const newValue = e.target.value.toUpperCase();

                  if (activeQuoteTicker && !commandInput && newValue) {
                    setCommandInput(activeQuoteTicker + ' ' + newValue);
                  } else {
                    setCommandInput(newValue);
                  }

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
                className={`w-full px-2 py-1.5 font-mono text-xs text-foreground bg-transparent
                         border-b border-transparent focus:border-primary/40
                         outline-none transition-all ${activeQuoteTicker && !commandInput ? 'opacity-0 absolute' : ''}`}
              />

              {/* Mostrar TickerStrip encima cuando hay quote activo y no hay input */}
              {activeQuoteTicker && !commandInput && (
                <div
                  className="flex items-center py-1.5 cursor-text"
                  onClick={() => inputRef.current?.focus()}
                >
                  <TickerStrip symbol={activeQuoteTicker} exchange="US" />
                </div>
              )}

              {/* Placeholder con cursor parpadeante */}
              {!commandInput && !activeQuoteTicker && (
                <div className="absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none flex items-center">
                  <span className="text-muted-fg font-mono text-xs">command</span>
                  <span className="w-[1.5px] h-3.5 bg-blue-400 ml-0.5 animate-pulse" />
                </div>
              )}
            </div>
          </div>

          {/* Separator */}
          <div className="w-px h-5 bg-muted mx-1" />

          {/* Center: Pinned Commands (centrados) */}
          <div className="flex-1 flex justify-center min-w-0">
            <PinnedCommands
              onOpenCommandPalette={(value) => {
                setCommandInput(value);
                setCommandPaletteOpen(true);
              }}
            />
          </div>

          {/* Separator */}
          <div className="w-px h-5 bg-muted mx-1" />

          {/* Right: Market Status + User Menu */}
          <div className="flex items-center gap-3 shrink-0">
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
      {/* Altura: 100vh - 40px (navbar h-10) - 32px (workspace tabs) */}
      <main
        className="h-[calc(100vh-40px-32px)] relative overflow-hidden transition-colors duration-200"
        style={{ backgroundColor: 'var(--color-background, inherit)' }}
      >
        {/* Empty state cuando no hay ventanas — only after layout restore completes */}
        {hasNoWindows && layoutReady && (
          <WorkspaceEmptyState
            onOpenScanner={(categoryId) => openScannerTable(categoryId, 0)}
            onOpenLayout={(layoutId, ticker) => applyLayout(layoutId, ticker)}
            onOpenCommandPalette={() => setCommandPaletteOpen(true)}
            onOpenModule={(commandId) => {
              if (commandId.startsWith('evt_')) {
                openEventTable(commandId);
                return;
              }
              executeCommand(commandId);
            }}
          />
        )}

        {/* Las ventanas flotantes se renderizan automáticamente desde FloatingWindowContext */}
      </main>

      {/* Workspace Tabs - Barra inferior estilo GODEL/IBKR */}
      <WorkspaceTabs getWindowContent={getWindowContent} />
    </>
  );
}
