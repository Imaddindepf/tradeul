'use client';

import { useEffect, useState } from 'react';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import CategoryTable from '@/components/scanner/CategoryTable';

export default function ScannerPage() {
  const [session, setSession] = useState<MarketSession | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
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

  return (
    <main className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white sticky top-0 z-50 shadow-sm">
        <div className="w-full px-0 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Tradeul Scanner</h1>
              <p className="text-sm text-gray-500 mt-0.5">Professional Real-Time Market Scanner</p>
            </div>
            {session && mounted && (
              <div className="flex items-center gap-4">
                <div className={`px-3 py-1 rounded-full text-sm font-medium ${sessionColors[session.current_session as keyof typeof sessionColors]}`}>
                  {session.current_session.replace('_', ' ')}
                </div>
                <div className="text-sm text-gray-600">
                  {new Date(session.trading_date).toLocaleDateString()}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="w-full px-0 py-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-gray-900">Escáner general</h2>
          <p className="text-sm text-gray-600 mt-1">Actualización en tiempo real • Click en headers para ordenar</p>
        </div>

        <div className="grid grid-cols-12 gap-2 grid-flow-dense" data-grid-root>
          {/* Fila 1: dos columnas */}
          <div className="col-span-12 lg:col-span-6 m-0 p-0">
            <CategoryTable title="Gappers Up" listName="gappers_up" />
          </div>
          <div className="col-span-12 lg:col-span-6 m-0 p-0">
            <CategoryTable title="Gappers Down" listName="gappers_down" />
          </div>

          {/* Fila 2: tres columnas en desktop */}
          <div className="col-span-12 md:col-span-6 lg:col-span-4 m-0 p-0">
            <CategoryTable title="High Volume" listName="high_volume" />
          </div>
          <div className="col-span-12 md:col-span-6 lg:col-span-4 m-0 p-0">
            <CategoryTable title="Anomalies" listName="anomalies" />
          </div>
          <div className="col-span-12 lg:col-span-4 m-0 p-0">
            {/* Reservado para otra tabla futura */}
          </div>
        </div>
      </div>
    </main>
  );
}


