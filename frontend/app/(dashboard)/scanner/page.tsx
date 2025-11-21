'use client';

import { useEffect, useState } from 'react';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { DraggableTable } from '@/components/scanner/DraggableTable';
import { Navbar, NavbarContent } from '@/components/layout/Navbar';
import { MarketStatusPopover } from '@/components/market/MarketStatusPopover';
import { Settings2 } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';

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

  const activeCategoryData = activeCategories
    .map((id) => AVAILABLE_CATEGORIES.find((cat) => cat.id === id))
    .filter(Boolean) as ScannerCategory[];


  return (
    <>
      {/* Navbar Global con Market Status */}
      <Navbar>
        <NavbarContent
          title="Escáner de Mercado"
          subtitle={`${activeCategories.length} ${activeCategories.length === 1 ? 'tabla activa' : 'tablas activas'}`}
          statusBadge={session && mounted ? <MarketStatusPopover status={adaptMarketSession(session)} /> : null}
        />
      </Navbar>

      {/* Main Content - Con padding-top para el navbar */}
      <main className="min-h-screen bg-slate-50 relative" style={{ paddingTop: '64px' }}>
        {/* Content Area */}
        <div className="relative min-h-screen">
          {/* Overlay cuando panel está abierto - Solo sobre área del scanner */}
          {sidebarOpen && (
            <div
              className="absolute inset-0 bg-black/50 animate-fadeIn"
              style={{ zIndex: Z_INDEX.SCANNER_PANEL_OVERLAY }}
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Sliding Panel - Overlay dentro del scanner */}
          <div
            className={`
            absolute top-0 bottom-0 w-64 bg-white border-r border-slate-200
            shadow-2xl transition-all duration-300 ease-out overflow-y-auto
          `}
            style={{
              left: sidebarOpen ? 0 : '-100%',
              visibility: sidebarOpen ? 'visible' : 'hidden',
              zIndex: Z_INDEX.SCANNER_PANEL
            }}
          >
            <div className="flex flex-col h-full">
              {/* Panel Header - Compacto */}
              <div className="p-3 border-b border-slate-200 bg-slate-50">
                <div className="flex items-center justify-between mb-1.5">
                  <h3 className="text-base font-bold text-slate-900">
                    Categorías
                  </h3>
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="p-1 hover:bg-slate-200 rounded transition-colors"
                  >
                    <svg className="h-4 w-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <p className="text-xs text-slate-600">
                  {activeCategories.length} activas • Solo WS activos
                </p>
              </div>

              {/* Categories List */}
              <div className="flex-1 overflow-y-auto p-3">
                <div className="space-y-1.5">
                  {AVAILABLE_CATEGORIES.map((category) => {
                    const isActive = activeCategories.includes(category.id);

                    return (
                      <label
                        key={category.id}
                        className={`
                      flex items-start gap-2.5 p-2.5 rounded-md cursor-pointer
                      transition-all duration-200
                      ${isActive ? 'bg-blue-50 border border-blue-400' : 'bg-white border border-slate-200'}
                      hover:border-blue-300 hover:shadow-sm
                    `}
                      >
                        <input
                          type="checkbox"
                          checked={isActive}
                          onChange={() => handleToggleCategory(category.id)}
                          className="mt-0.5 h-4 w-4 text-blue-600 rounded border-slate-300
                               focus:ring-2 focus:ring-blue-500"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold text-slate-900 leading-tight mb-0.5">
                            {category.name}
                          </div>
                          <div className="text-[10px] text-slate-500 leading-tight">
                            {category.description}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Panel Footer */}
              <div className="p-2 border-t border-slate-200 bg-slate-50">
                <p className="text-[10px] text-slate-400 text-center">
                  Guardado automático
                </p>
              </div>
            </div>
          </div>

          {/* Mini Button - Botón flotante pegado al sidebar */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="absolute left-0 top-8 bg-blue-600 hover:bg-blue-700 text-white
                     rounded-r-lg shadow-lg hover:shadow-xl
                     flex flex-col items-center justify-center gap-1 py-3 px-2.5
                     transition-all duration-200"
            style={{ zIndex: Z_INDEX.SCANNER_BUTTON }}
            title="Configurar categorías"
          >
            <Settings2 className="h-5 w-5" />
            <div className="text-[10px] font-bold leading-none">
              {activeCategories.length}
            </div>
          </button>

          {/* Draggable Tables Area */}
          <div className="relative w-full h-[calc(100vh-64px)] overflow-hidden">
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
                    zIndex={0}
                    onBringToFront={() => { }}
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


