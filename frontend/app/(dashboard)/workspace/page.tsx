'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { Navbar, NavbarContent, UserMenu } from '@/components/layout/Navbar';
import { PinnedCommands } from '@/components/layout/PinnedCommands';
import { MarketStatusPopover } from '@/components/market/MarketStatusPopover';
import { CommandPalette } from '@/components/ui/CommandPalette';
import { Settings2, LayoutGrid } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useLayoutPersistence } from '@/hooks/useLayoutPersistence';
import { ScannerTableContent } from '@/components/scanner/ScannerTableContent';
import { SettingsContent } from '@/components/settings/SettingsContent';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { SECFilingsContent } from '@/components/sec-filings/SECFilingsContent';

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

const DEFAULT_CATEGORIES = ['gappers_up', 'gappers_down', 'momentum_up', 'winners'];

export default function ScannerPage() {
  const [session, setSession] = useState<MarketSession | null>(null);
  const [mounted, setMounted] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandInput, setCommandInput] = useState('');

  const { windows, openWindow, closeWindow } = useFloatingWindow();
  const { openScannerTable, closeScannerTable, isScannerTableOpen, SCANNER_CATEGORIES } = useCommandExecutor();
  const { getSavedLayout, hasLayout } = useLayoutPersistence();

  const layoutRestoredRef = useRef(false);
  const initialTablesOpenedRef = useRef(false);

  // Función para reconstruir contenido de ventana por título
  const getWindowContent = useCallback((title: string) => {
    if (title === 'Settings') return <SettingsContent />;
    if (title === 'Dilution Tracker') return <DilutionTrackerContent />;
    if (title === 'SEC Filings') return <SECFilingsContent />;

    // Verificar si es una tabla del scanner
    if (title.startsWith('Scanner: ')) {
      const categoryName = title.replace('Scanner: ', '');
      const categoryEntry = Object.entries(SCANNER_CATEGORIES).find(([_, cat]) => cat.name === categoryName);
      if (categoryEntry) {
        const [categoryId, category] = categoryEntry;
        return <ScannerTableContent categoryId={categoryId} categoryName={category.name} />;
      }
    }
    return null;
  }, [SCANNER_CATEGORIES]);

  // Restaurar layout guardado O abrir tablas por defecto
  useEffect(() => {
    if (!mounted) return;

    // Restaurar layout si existe
    if (hasLayout && !layoutRestoredRef.current) {
      layoutRestoredRef.current = true;
      const savedLayout = getSavedLayout();

      setTimeout(() => {
        savedLayout.forEach((layout) => {
          const content = getWindowContent(layout.title);
          if (content) {
            // Las tablas del scanner tienen cabecera propia
            const hideHeader = layout.title.startsWith('Scanner:');
            openWindow({
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

    // Si no hay layout guardado, abrir tablas por defecto
    if (!hasLayout && !initialTablesOpenedRef.current) {
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
  }, [mounted, hasLayout, getSavedLayout, getWindowContent, openWindow, openScannerTable]);

  // Montaje inicial
  useEffect(() => {
    setMounted(true);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const input = document.querySelector('input[type="text"]') as HTMLInputElement;
        if (input) {
          input.focus();
          setCommandPaletteOpen(true);
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Fetch market session
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
    const interval = setInterval(fetchSession, 30000);
    return () => clearInterval(interval);
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
        <div className="flex items-center h-full w-full gap-4">
          {/* Logo */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 
                        flex items-center justify-center shadow-sm flex-shrink-0">
            <span className="text-white font-bold text-base">T</span>
          </div>

          {/* Command Prompt */}
          <div className="flex-1 flex items-center gap-2 relative">
            <span className="text-slate-400 font-mono text-sm select-none">$</span>
            <input
              type="text"
              value={commandInput}
              onChange={(e) => setCommandInput(e.target.value)}
              onFocus={() => setCommandPaletteOpen(true)}
              placeholder="escribir comando..."
              className="flex-1 px-3 py-2 font-mono text-sm text-slate-900
                       placeholder:text-slate-400 bg-transparent
                       border-b-2 border-transparent focus:border-blue-500
                       outline-none transition-all"
            />
            <kbd className="text-xs text-slate-400 font-mono">Ctrl+K</kbd>
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

      {/* Command Palette */}
      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        onSelectCategory={handleToggleCategory}
        activeCategories={Object.keys(SCANNER_CATEGORIES).filter(id => isScannerTableOpen(id))}
        searchValue={commandInput}
        onSearchChange={setCommandInput}
      />

      {/* Main Content - usa variable CSS para el fondo */}
      <main 
        className="h-[calc(100vh-64px)] relative overflow-hidden transition-colors duration-200"
        style={{ backgroundColor: 'var(--color-background, #f8fafc)' }}
      >
        {/* Empty state cuando no hay ventanas */}
        {hasNoWindows && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-slate-500">
              <LayoutGrid className="h-16 w-16 mx-auto mb-4 text-slate-300" />
              <p className="text-xl font-semibold text-slate-700">No hay ventanas abiertas</p>
              <p className="text-sm mt-2 text-slate-500">
                Usa Ctrl+K o escribe un comando para abrir tablas del scanner
              </p>
              <div className="mt-4 flex gap-2 justify-center">
                {DEFAULT_CATEGORIES.slice(0, 3).map((catId) => (
                  <button
                    key={catId}
                    onClick={() => openScannerTable(catId, 0)}
                    className="px-3 py-1.5 text-xs font-medium bg-blue-500 text-white rounded-md hover:bg-blue-600"
                  >
                    {SCANNER_CATEGORIES[catId]?.name || catId}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Las ventanas flotantes se renderizan automáticamente desde FloatingWindowContext */}
      </main>
    </>
  );
}
