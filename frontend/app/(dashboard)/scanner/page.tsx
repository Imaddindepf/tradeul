'use client';

import { useEffect, useState } from 'react';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import CategoryTable from '@/components/scanner/CategoryTable';
import { Settings2 } from 'lucide-react';

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
    <main className="min-h-screen bg-white relative">
      {/* Header - Full Width */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-30 shadow-sm w-full">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Escáner de Mercado</h1>
              <p className="text-sm text-slate-600 mt-0.5">
                {activeCategories.length} {activeCategories.length === 1 ? 'tabla activa' : 'tablas activas'} • Solo WebSockets de tablas seleccionadas
              </p>
            </div>
            {session && mounted && (
              <div className={`
                px-3 py-1.5 rounded-lg text-sm font-medium
                ${sessionColors[session.current_session as keyof typeof sessionColors]}
              `}>
                {session.current_session.replace('_', ' ')}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Content Area */}
      <div className="relative min-h-screen">
        {/* Overlay cuando panel está abierto - Solo sobre área del scanner */}
        {sidebarOpen && (
          <div
            className="absolute inset-0 bg-black/50 z-40 animate-fadeIn"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sliding Panel - Overlay dentro del scanner */}
        <div
          className={`
            absolute top-0 bottom-0 w-64 bg-white border-r border-slate-200
            shadow-2xl z-50 transition-all duration-300 ease-out overflow-y-auto
          `}
          style={{ 
            left: sidebarOpen ? 0 : '-100%',
            visibility: sidebarOpen ? 'visible' : 'hidden'
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

        {/* Mini Button - Dentro del área del scanner */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="absolute left-0 top-8 z-[60]
                     bg-blue-600 hover:bg-blue-700 text-white
                     rounded-r-lg shadow-lg hover:shadow-xl
                     flex flex-col items-center justify-center gap-1 py-3 px-2.5
                     transition-all duration-200"
          title="Configurar categorías"
        >
          <Settings2 className="h-5 w-5" />
          <div className="text-[10px] font-bold leading-none">
            {activeCategories.length}
          </div>
        </button>

        {/* Tables Grid - No se desplaza */}
        <div className="w-full px-6 py-6">
          {activeCategoryData.length === 0 ? (
            <div className="flex items-center justify-center h-[calc(100vh-200px)]">
              <div className="text-center text-slate-500">
                <Settings2 className="h-16 w-16 mx-auto mb-4 text-slate-300" />
                <p className="text-xl font-semibold text-slate-700">No hay tablas seleccionadas</p>
                <p className="text-sm mt-2 text-slate-500">
                  Haz clic en el botón azul del lado izquierdo para configurar
                </p>
              </div>
            </div>
          ) : (
        <div className="grid grid-cols-12 gap-4 grid-flow-dense" data-grid-root>
              {activeCategoryData.map((category) => (
                <div key={category.id} className="col-span-12 lg:col-span-6 m-0 p-0">
                  <CategoryTable title={category.name} listName={category.id} />
                </div>
              ))}
          </div>
          )}
        </div>
      </div>
    </main>
  );
}


