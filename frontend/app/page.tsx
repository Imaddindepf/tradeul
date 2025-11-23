'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { 
  ScanSearch, 
  TrendingUp, 
  Bell, 
  ArrowRight,
  Activity,
  BarChart3,
  Clock
} from 'lucide-react';

export default function Home() {
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
    PRE_MARKET: 'bg-blue-100 text-blue-700 border-blue-300',
    MARKET_OPEN: 'bg-green-100 text-green-700 border-green-300',
    POST_MARKET: 'bg-orange-100 text-orange-700 border-orange-300',
    CLOSED: 'bg-gray-100 text-gray-700 border-gray-300',
  } as const;

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Hero Section */}
      <div className="px-4 py-16 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-50 border border-blue-200 rounded-full mb-6">
            <Activity className="w-4 h-4 text-blue-600" />
            <span className="text-sm font-medium text-blue-700">Plataforma de Trading Profesional</span>
            </div>
          
          <h1 className="text-5xl font-bold text-slate-900 mb-4">
            Bienvenido a <span className="text-blue-600">Tradeul</span>
          </h1>
          
          <p className="text-xl text-slate-600 mb-8 max-w-2xl mx-auto">
            Tu plataforma profesional de análisis de mercado en tiempo real. 
            Escanea, analiza y toma decisiones informadas.
          </p>

          {/* Market Status */}
            {session && mounted && (
            <div className="flex items-center justify-center gap-4 mb-12">
              <div className={`
                px-6 py-3 rounded-xl text-base font-semibold shadow-lg border-2
                ${sessionColors[session.current_session as keyof typeof sessionColors]}
              `}>
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5" />
                  <span>{session.current_session.replace('_', ' ')}</span>
                </div>
              </div>
              <div className="px-6 py-3 bg-white rounded-xl shadow-lg border border-slate-200">
                <p className="text-sm text-slate-600">Fecha de Trading</p>
                <p className="text-base font-semibold text-slate-900">
                  {new Date(session.trading_date).toLocaleDateString('es-ES', {
                    weekday: 'short',
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                  })}
                </p>
          </div>
        </div>
          )}

          {/* Quick Action - Scanner */}
          <Link 
            href="/workspace"
            className="inline-flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl font-semibold text-lg shadow-xl hover:shadow-2xl hover:from-blue-700 hover:to-blue-600 transition-all duration-200 active:scale-95"
          >
            <ScanSearch className="w-6 h-6" />
            <span>Ir al Workspace</span>
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>

        {/* Feature Cards */}
        <div className="max-w-6xl mx-auto mt-20 grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Scanner Card */}
          <Link 
            href="/workspace"
            className="group p-8 bg-white rounded-2xl shadow-lg border-2 border-slate-200 hover:border-blue-500 hover:shadow-2xl transition-all duration-300"
          >
            <div className="w-14 h-14 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <ScanSearch className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">Workspace</h3>
            <p className="text-slate-600 mb-4">
              Tu espacio de trabajo completo con scanner, dilution tracker y herramientas de análisis en tiempo real.
            </p>
            <div className="flex items-center gap-2 text-blue-600 font-medium group-hover:gap-3 transition-all">
              <span>Explorar ahora</span>
              <ArrowRight className="w-4 h-4" />
            </div>
          </Link>

          {/* Analytics Card */}
          <div className="group p-8 bg-white rounded-2xl shadow-lg border-2 border-slate-200 relative overflow-hidden">
            <div className="absolute top-4 right-4 px-3 py-1 bg-slate-100 text-slate-600 text-xs font-medium rounded-full">
              Próximamente
            </div>
            <div className="w-14 h-14 bg-gradient-to-br from-slate-400 to-slate-500 rounded-xl flex items-center justify-center mb-4 opacity-70">
              <TrendingUp className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">Analytics</h3>
            <p className="text-slate-600 mb-4">
              Análisis profundo de datos históricos y patrones de mercado para optimizar tu estrategia.
            </p>
            <div className="flex items-center gap-2 text-slate-400 font-medium">
              <span>En desarrollo</span>
          </div>
          </div>

          {/* Alerts Card */}
          <div className="group p-8 bg-white rounded-2xl shadow-lg border-2 border-slate-200 relative overflow-hidden">
            <div className="absolute top-4 right-4 px-3 py-1 bg-slate-100 text-slate-600 text-xs font-medium rounded-full">
              Próximamente
            </div>
            <div className="w-14 h-14 bg-gradient-to-br from-slate-400 to-slate-500 rounded-xl flex items-center justify-center mb-4 opacity-70">
              <Bell className="w-7 h-7 text-white" />
            </div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">Alertas Inteligentes</h3>
            <p className="text-slate-600 mb-4">
              Recibe notificaciones instantáneas cuando el mercado cumple tus criterios personalizados.
            </p>
            <div className="flex items-center gap-2 text-slate-400 font-medium">
              <span>En desarrollo</span>
            </div>
          </div>
        </div>

        {/* Stats Section */}
        <div className="max-w-4xl mx-auto mt-16 p-8 bg-white rounded-2xl shadow-lg border border-slate-200">
          <div className="flex items-center justify-center gap-2 mb-4">
            <BarChart3 className="w-6 h-6 text-blue-600" />
            <h3 className="text-2xl font-bold text-slate-900">Estadísticas de la Plataforma</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
            <div className="text-center">
              <p className="text-4xl font-bold text-blue-600 mb-1">+8,000</p>
              <p className="text-sm text-slate-600">Tickers Monitoreados</p>
            </div>
            <div className="text-center">
              <p className="text-4xl font-bold text-emerald-600 mb-1">Real-Time</p>
              <p className="text-sm text-slate-600">Datos en Vivo</p>
            </div>
            <div className="text-center">
              <p className="text-4xl font-bold text-purple-600 mb-1">&lt;100ms</p>
              <p className="text-sm text-slate-600">Latencia de Datos</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
