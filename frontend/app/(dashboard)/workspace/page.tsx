'use client';

import { useEffect, useState } from 'react';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { DraggableTable } from '@/components/scanner/DraggableTable';
import { Navbar, NavbarContent } from '@/components/layout/Navbar';
import { PinnedCommands } from '@/components/layout/PinnedCommands';
import { MarketStatusPopover } from '@/components/market/MarketStatusPopover';
import { CommandPalette } from '@/components/ui/CommandPalette';
import { Settings2 } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { SettingsContent } from '@/components/settings/SettingsContent';

type ScannerCategory = {
  id: string;
  name: string;
  description: string;
};

const AVAILABLE_CATEGORIES: ScannerCategory[] = [
  { id: 'gappers_up', name: 'Gap Up', description: 'Gap up ≥ 2%' },
  { id: 'gappers_down', name: 'Gap Down', description: 'Gap down ≤ -2%' },
  { id: 'momentum_up', name: 'Momentum Alcista', description: 'Cambio ≥ 3%' },
  { id: 'momentum_down', name: 'Momentum Bajista', description: 'Cambio ≤ -3%' },
  { id: 'winners', name: 'Mayores Ganadores', description: 'Cambio ≥ 5%' },
  { id: 'losers', name: 'Mayores Perdedores', description: 'Cambio ≤ -5%' },
  { id: 'new_highs', name: 'Nuevos Máximos', description: 'Máximos del día' },
  { id: 'new_lows', name: 'Nuevos Mínimos', description: 'Mínimos del día' },
  { id: 'anomalies', name: 'Anomalías', description: 'RVOL ≥ 3.0' },
  { id: 'high_volume', name: 'Alto Volumen', description: 'RVOL ≥ 2.0' },
  { id: 'reversals', name: 'Reversals', description: 'Cambios de dirección' },
];

const DEFAULT_CATEGORIES = ['gappers_up', 'gappers_down', 'momentum_up', 'winners'];

// Adaptador para convertir MarketSession a PolygonMarketStatus
function adaptMarketSession(session: MarketSession) {
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  const currentTime = currentHour * 60 + currentMinute; // minutos desde medianoche

  // Pre-market: 4:00 AM - 9:30 AM (240 - 570)
  // Market Open: 9:30 AM - 4:00 PM (570 - 960)
  // Post-market: 4:00 PM - 8:00 PM (960 - 1200)

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
  } else {
    market = 'closed';
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
  const [session, setSession] = useState<MarketSession | null>(null);
  const [mounted, setMounted] = useState(false);
  const [activeCategories, setActiveCategories] = useState<string[]>(DEFAULT_CATEGORIES);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandInput, setCommandInput] = useState('');
  const { openWindow } = useFloatingWindow();

  useEffect(() => {
    setMounted(true);
    // Cargar preferencias del localStorage (solo en cliente)
    if (typeof window !== 'undefined') {
      try {
        const saved = localStorage.getItem('scanner_categories');
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setActiveCategories(parsed);
          }
        }
      } catch (e) {
        console.error('Error loading saved categories:', e);
      }
    }

    // Handler para Ctrl+K - Enfocar input
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

  const sessionColors = {
    PRE_MARKET: 'bg-blue-100 text-blue-700',
    MARKET_OPEN: 'bg-green-100 text-green-700',
    POST_MARKET: 'bg-orange-100 text-orange-700',
    CLOSED: 'bg-gray-100 text-gray-700',
  } as const;

  const handleToggleCategory = (categoryId: string) => {
    setActiveCategories((prev) => {
      let newCategories: string[];

      if (prev.includes(categoryId)) {
        // Remover
        newCategories = prev.filter((id) => id !== categoryId);
      } else {
        // Agregar
        newCategories = [...prev, categoryId];
      }

      // Guardar en localStorage (solo en cliente)
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem('scanner_categories', JSON.stringify(newCategories));
        } catch (e) {
          console.error('Error saving categories:', e);
        }
      }
      return newCategories;
    });
  };

  // Handler para comandos pinned (solo comandos principales: SC, DT, SET)
  const handlePinnedCommandClick = (commandId: string) => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;

    switch (commandId) {
      case 'sc':
        // Scanner: Abrir paleta de comandos con "SC " pre-llenado
        setCommandInput('SC ');
        setCommandPaletteOpen(true);
        break;

      case 'dt':
        // Dilution Tracker: Abrir floating window
        openWindow({
          title: 'Dilution Tracker',
          content: <DilutionTrackerContent />,
          width: 700,
          height: 600,
          x: screenWidth / 2 - 350,
          y: screenHeight / 2 - 300,
          minWidth: 500,
          minHeight: 400,
        });
        break;

      case 'settings':
        // Settings: Abrir floating window
        openWindow({
          title: 'Settings',
          content: <SettingsContent />,
          width: 900,
          height: 750,
          x: screenWidth / 2 - 450,
          y: screenHeight / 2 - 375,
          minWidth: 700,
          minHeight: 600,
        });
        break;

      default:
        console.warn('Comando pinned desconocido:', commandId);
    }
  };

  const activeCategoryData = activeCategories
    .map((id) => AVAILABLE_CATEGORIES.find((cat) => cat.id === id))
    .filter(Boolean) as ScannerCategory[];


  return (
    <>
      {/* Navbar con Command Prompt, Logo Centrado y Market Status */}
      <Navbar>
        <div className="flex items-center h-full w-full gap-4">
          {/* Logo compacto */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 
                        flex items-center justify-center shadow-sm flex-shrink-0">
            <span className="text-white font-bold text-base">T</span>
          </div>

          {/* Left: Command Prompt Line */}
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

          {/* Center: Pinned Commands (Favoritos del usuario) */}
          <div className="flex items-center px-4">
            <PinnedCommands 
              onCommandClick={handlePinnedCommandClick}
            />
          </div>

          {/* Right: Market Status */}
          <div className="flex-1 flex items-center justify-end gap-4">
            {session && mounted && <MarketStatusPopover status={adaptMarketSession(session)} />}
          </div>
        </div>
      </Navbar>

      {/* Command Palette - Integrado debajo del input */}
      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        onSelectCategory={handleToggleCategory}
        activeCategories={activeCategories}
        searchValue={commandInput}
        onSearchChange={setCommandInput}
      />

      {/* Main Content - Sin padding-top porque AppShell ya lo tiene */}
      <main className="h-[calc(100vh-64px)] bg-slate-50 relative overflow-hidden">
        {/* Content Area */}
        <div className="relative h-full">
          {/* Overlay cuando panel está abierto - Solo sobre área del scanner */}
          {sidebarOpen && (
            <div
              className="absolute inset-0 bg-black/50 animate-fadeIn"
              style={{ zIndex: Z_INDEX.SCANNER_PANEL_OVERLAY }}
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Draggable Tables Area */}
          <div className="relative w-full h-full overflow-hidden">
            {activeCategoryData.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-slate-500">
                  <Settings2 className="h-16 w-16 mx-auto mb-4 text-slate-300" />
                  <p className="text-xl font-semibold text-slate-700">No hay tablas seleccionadas</p>
                  <p className="text-sm mt-2 text-slate-500">
                    Haz clic en el botón azul del lado izquierdo para configurar
                  </p>
                </div>
              </div>
            ) : (
              <>
                {activeCategoryData.map((category, index) => (
                  <DraggableTable
                    key={category.id}
                    category={category}
                    index={index}
                    onClose={() => handleToggleCategory(category.id)}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      </main>
    </>
  );
}


