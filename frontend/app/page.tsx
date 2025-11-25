'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { SignInButton, SignUpButton, SignedIn, SignedOut, UserButton } from '@clerk/nextjs';
import { getMarketSession } from '@/lib/api';
import type { MarketSession } from '@/lib/types';
import { 
  Activity,
  ArrowRight,
  Zap,
  Eye,
  Shield,
  Bell,
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

  const getSessionStatus = () => {
    if (!session) return { label: 'Loading...', color: 'bg-slate-200 text-slate-600', dot: 'bg-slate-400' };
    const statusMap: Record<string, { label: string; color: string; dot: string }> = {
      PRE_MARKET: { label: 'PRE-MARKET', color: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
      MARKET_OPEN: { label: 'MARKET OPEN', color: 'bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' },
      POST_MARKET: { label: 'POST-MARKET', color: 'bg-amber-50 text-amber-700', dot: 'bg-amber-500' },
      CLOSED: { label: 'CLOSED', color: 'bg-slate-100 text-slate-600', dot: 'bg-slate-400' },
    };
    return statusMap[session.current_session] || { label: 'OFFLINE', color: 'bg-slate-100 text-slate-600', dot: 'bg-slate-400' };
  };

  const status = getSessionStatus();

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Subtle Grid Background */}
      <div className="fixed inset-0 opacity-[0.4]" style={{
        backgroundImage: `radial-gradient(circle at 1px 1px, rgb(226 232 240) 1px, transparent 0)`,
        backgroundSize: '32px 32px',
      }} />

      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-slate-200 bg-white/90 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-sm">
              <span className="text-white font-bold text-lg">T</span>
            </div>
            <span className="text-xl font-semibold text-slate-900 tracking-tight">Tradeul</span>
          </div>

          {/* Market Status */}
          {mounted && session && (
            <div className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${status.color}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status.dot} animate-pulse`} />
              {status.label}
            </div>
          )}

          {/* Auth */}
          <div className="flex items-center gap-2">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">
                  Iniciar Sesión
                </button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button className="px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-blue-500 to-blue-600 rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all shadow-sm">
                  Comenzar
                </button>
              </SignUpButton>
            </SignedOut>
            
            <SignedIn>
              <Link 
                href="/workspace"
                className="px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700 transition-colors flex items-center gap-1.5"
              >
                Ir al Workspace <ArrowRight className="w-3.5 h-3.5" />
              </Link>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 mb-8 rounded-full border border-slate-200 bg-white shadow-sm">
            <Zap className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-xs font-medium text-slate-600 uppercase tracking-wide">Real-Time Market Intelligence</span>
          </div>

          {/* Main Headline */}
          <h1 className="text-4xl md:text-6xl font-bold text-slate-900 tracking-tight mb-5 leading-tight">
            Trade <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-blue-600">Smarter</span>
            <br />
            <span className="text-slate-400">Not Harder</span>
          </h1>

          {/* Minimal Tagline */}
          <p className="text-lg text-slate-500 mb-10">
            Scanner · Dilution Tracker · Real-Time Data
          </p>

          {/* CTA Buttons */}
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <SignedOut>
              <SignUpButton mode="modal">
                <button className="group px-7 py-3.5 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all shadow-lg hover:shadow-xl flex items-center gap-2">
                  Comenzar Gratis
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </button>
              </SignUpButton>
              <SignInButton mode="modal">
                <button className="px-7 py-3.5 border border-slate-200 bg-white text-slate-700 font-medium rounded-xl hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm">
                  Ya tengo cuenta
                </button>
              </SignInButton>
            </SignedOut>
            
            <SignedIn>
              <Link 
                href="/workspace"
                className="group px-7 py-3.5 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all shadow-lg hover:shadow-xl flex items-center gap-2"
              >
                Abrir Workspace
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </SignedIn>
          </div>
        </div>
      </section>

      {/* Stats Grid */}
      <section className="relative py-12 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { value: '8K+', label: 'Tickers' },
              { value: '<50ms', label: 'Latencia' },
              { value: '24/7', label: 'Monitoreo' },
              { value: 'Real-Time', label: 'Data Feed' },
            ].map((stat) => (
              <div 
                key={stat.label}
                className="p-5 rounded-xl border border-slate-200 bg-white text-center hover:border-blue-200 hover:shadow-md transition-all"
              >
                <p className="text-2xl md:text-3xl font-bold font-mono text-blue-600 mb-0.5">{stat.value}</p>
                <p className="text-xs text-slate-500 uppercase tracking-wider">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative py-16 px-6">
        <div className="max-w-4xl mx-auto">
          {/* Section Header */}
          <div className="text-center mb-12">
            <h2 className="text-2xl md:text-3xl font-bold text-slate-900 mb-2">Todo lo que necesitas</h2>
            <p className="text-slate-500">Herramientas profesionales. Sin complicaciones.</p>
          </div>

          {/* Feature Cards */}
          <div className="grid md:grid-cols-3 gap-5">
            {[
              {
                icon: Eye,
                title: 'Market Scanner',
                features: ['Pre/Post market', 'Gap analysis', 'Volume spikes', 'Custom filters'],
                active: true,
              },
              {
                icon: Shield,
                title: 'Dilution Tracker',
                features: ['SEC filings', 'Share structure', 'ATM offerings', 'Risk alerts'],
                active: true,
              },
              {
                icon: Bell,
                title: 'Smart Alerts',
                features: ['Price triggers', 'Volume alerts', 'Filing notifications', 'Custom rules'],
                active: false,
              },
            ].map((feature) => (
              <div 
                key={feature.title}
                className={`relative p-6 rounded-xl border transition-all ${
                  feature.active 
                    ? 'border-slate-200 bg-white hover:border-blue-200 hover:shadow-lg' 
                    : 'border-slate-100 bg-slate-50/50 opacity-70'
                }`}
              >
                {!feature.active && (
                  <span className="absolute top-3 right-3 text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-200 text-slate-500">
                    PRONTO
                  </span>
                )}
                <div className={`w-11 h-11 rounded-lg flex items-center justify-center mb-4 ${
                  feature.active 
                    ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-sm' 
                    : 'bg-slate-200'
                }`}>
                  <feature.icon className={`w-5 h-5 ${feature.active ? 'text-white' : 'text-slate-400'}`} />
                </div>
                <h3 className="text-lg font-semibold text-slate-900 mb-3">{feature.title}</h3>
                <ul className="space-y-2">
                  {feature.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
                      <span className={`w-1 h-1 rounded-full ${feature.active ? 'bg-blue-500' : 'bg-slate-400'}`} />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Terminal Preview */}
      <section className="relative py-16 px-6">
        <div className="max-w-3xl mx-auto">
          <div className="rounded-xl border border-slate-200 bg-white shadow-lg overflow-hidden">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 bg-slate-50">
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full bg-red-400" />
                <span className="w-3 h-3 rounded-full bg-amber-400" />
                <span className="w-3 h-3 rounded-full bg-emerald-400" />
              </div>
              <span className="text-xs font-mono text-slate-400 ml-2">tradeul://workspace</span>
            </div>
            
            {/* Terminal Content */}
            <div className="p-5 font-mono text-sm bg-white">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-blue-500">$</span>
                  <span className="text-slate-400">scanning pre-market...</span>
                </div>
                <div className="grid grid-cols-4 gap-4 text-xs py-2 border-b border-slate-100">
                  <div><span className="text-slate-400 font-medium">TICKER</span></div>
                  <div className="text-right"><span className="text-slate-400 font-medium">PRICE</span></div>
                  <div className="text-right"><span className="text-slate-400 font-medium">CHG%</span></div>
                  <div className="text-right"><span className="text-slate-400 font-medium">VOL</span></div>
                </div>
                {[
                  { ticker: 'NVDA', price: '142.50', change: '+4.2%', vol: '12.5M', up: true },
                  { ticker: 'TSLA', price: '248.20', change: '+2.8%', vol: '8.3M', up: true },
                  { ticker: 'AMD', price: '165.80', change: '-1.2%', vol: '5.1M', up: false },
                  { ticker: 'AAPL', price: '178.90', change: '+0.5%', vol: '3.2M', up: true },
                ].map((row) => (
                  <div 
                    key={row.ticker}
                    className="grid grid-cols-4 gap-4 text-xs py-2 border-b border-slate-50"
                  >
                    <div className="font-semibold text-slate-900">{row.ticker}</div>
                    <div className="text-right text-slate-700">${row.price}</div>
                    <div className={`text-right font-medium ${row.up ? 'text-emerald-600' : 'text-red-500'}`}>{row.change}</div>
                    <div className="text-right text-slate-500">{row.vol}</div>
                  </div>
                ))}
                <div className="flex items-center gap-2 pt-2">
                  <span className="text-emerald-500">✓</span>
                  <span className="text-slate-400 text-xs">found 847 matches • filtered by: gap &gt; 3%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative py-20 px-6">
        <div className="max-w-xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-slate-900 mb-4">
            ¿Listo para empezar?
          </h2>
          <p className="text-slate-500 mb-8">
            Únete a traders que exigen mejores herramientas.
          </p>
          
          <SignedOut>
            <SignUpButton mode="modal">
              <button className="group px-8 py-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold text-lg rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all shadow-lg hover:shadow-xl flex items-center gap-2 mx-auto">
                Comenzar Gratis
                <ArrowRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
              </button>
            </SignUpButton>
          </SignedOut>
          
          <SignedIn>
            <Link 
              href="/workspace"
              className="group inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold text-lg rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all shadow-lg hover:shadow-xl"
            >
              Abrir Workspace
              <ArrowRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </SignedIn>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-8 px-6">
        <div className="max-w-4xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">T</span>
            </div>
            <span className="text-sm font-medium text-slate-700">Tradeul</span>
          </div>
          <p className="text-xs text-slate-400">
            © {new Date().getFullYear()} Tradeul. Professional market intelligence.
          </p>
        </div>
      </footer>
    </main>
  );
}
