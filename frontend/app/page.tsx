'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { SignIn, SignUp, SignedIn, SignedOut, UserButton } from '@clerk/nextjs';
import { ChristmasEffects } from '@/components/layout/ChristmasEffects';
import { ArrowRight, TrendingUp, TrendingDown, X } from 'lucide-react';
import { useAppTranslation } from '@/hooks/useAppTranslation';

type AuthPanel = 'closed' | 'signin' | 'signup';

export default function Home() {
  const [mounted, setMounted] = useState(false);
  const [authPanel, setAuthPanel] = useState<AuthPanel>('closed');
  const { t } = useAppTranslation();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Cerrar panel con Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAuthPanel('closed');
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, []);

  // Datos de ejemplo para visualización
  const scannerData = [
    { ticker: 'NVDA', price: '142.58', change: '+8.42%', volume: '89.2M', trend: 'up' },
    { ticker: 'SMCI', price: '38.74', change: '+12.15%', volume: '45.8M', trend: 'up' },
    { ticker: 'MSTR', price: '412.30', change: '+5.67%', volume: '28.4M', trend: 'up' },
    { ticker: 'PLTR', price: '78.92', change: '-2.31%', volume: '52.1M', trend: 'down' },
  ];

  const filings = [
    { ticker: 'AAPL', type: '10-K', time: '2m ago' },
    { ticker: 'TSLA', type: '8-K', time: '15m ago' },
    { ticker: 'MSFT', type: 'S-3', time: '1h ago' },
  ];

  return (
    <main className="min-h-screen bg-[#0a0a12] text-white overflow-hidden">
      <ChristmasEffects />

      {/* Background gradient */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[150px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px]" />
      </div>

      {/* Auth Side Panel */}
      <div 
        className={`fixed inset-0 z-[100] transition-all duration-500 ${
          authPanel !== 'closed' ? 'pointer-events-auto' : 'pointer-events-none'
        }`}
      >
        {/* Backdrop */}
        <div 
          className={`absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-500 ${
            authPanel !== 'closed' ? 'opacity-100' : 'opacity-0'
          }`}
          onClick={() => setAuthPanel('closed')}
        />
        
        {/* Panel */}
        <div 
          className={`absolute right-0 top-0 h-full w-full max-w-md bg-[#0a0a12] border-l border-white/10 shadow-2xl transition-transform duration-500 ease-out ${
            authPanel !== 'closed' ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          {/* Panel header */}
          <div className="flex items-center justify-between p-6 border-b border-white/5">
            <div className="flex gap-4">
              <button
                onClick={() => setAuthPanel('signin')}
                className={`text-sm font-medium transition-colors ${
                  authPanel === 'signin' ? 'text-white' : 'text-white/40 hover:text-white/60'
                }`}
              >
                {t('landing.auth.signIn')}
              </button>
              <button
                onClick={() => setAuthPanel('signup')}
                className={`text-sm font-medium transition-colors ${
                  authPanel === 'signup' ? 'text-white' : 'text-white/40 hover:text-white/60'
                }`}
              >
                {t('landing.auth.createAccount')}
              </button>
            </div>
            <button 
              onClick={() => setAuthPanel('closed')}
              className="p-2 rounded-lg hover:bg-white/5 transition-colors text-white/40 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Panel content */}
          <div className="p-6 overflow-y-auto h-[calc(100%-73px)]">
            <div className={`transition-all duration-300 ${authPanel === 'signin' ? 'opacity-100' : 'opacity-0 absolute pointer-events-none'}`}>
              {authPanel === 'signin' && (
                <SignIn 
                  appearance={{
                    elements: {
                      rootBox: 'w-full',
                      card: 'bg-transparent shadow-none p-0',
                      headerTitle: 'text-white text-2xl font-bold',
                      headerSubtitle: 'text-white/50',
                      socialButtonsBlockButton: 'bg-white/10 border-white/20 text-white hover:bg-white/20',
                      socialButtonsBlockButtonText: 'text-white font-medium',
                      socialButtonsProviderIcon__apple: 'invert',
                      dividerLine: 'bg-white/10',
                      dividerText: 'text-white/30',
                      formFieldLabel: 'text-white/70',
                      formFieldInput: 'bg-white/5 border-white/10 text-white placeholder:text-white/30 focus:border-blue-500 focus:ring-blue-500/20',
                      formButtonPrimary: 'bg-white text-black hover:bg-white/90 font-semibold',
                      footerActionLink: 'text-blue-400 hover:text-blue-300',
                      identityPreviewText: 'text-white',
                      identityPreviewEditButton: 'text-blue-400',
                      formFieldInputShowPasswordButton: 'text-white/50 hover:text-white',
                      alert: 'bg-red-500/10 border-red-500/20 text-red-400',
                      alertText: 'text-red-400',
                    },
                  }}
                  routing="hash"
                />
              )}
            </div>
            <div className={`transition-all duration-300 ${authPanel === 'signup' ? 'opacity-100' : 'opacity-0 absolute pointer-events-none'}`}>
              {authPanel === 'signup' && (
                <SignUp 
                  appearance={{
                    elements: {
                      rootBox: 'w-full',
                      card: 'bg-transparent shadow-none p-0',
                      headerTitle: 'text-white text-2xl font-bold',
                      headerSubtitle: 'text-white/50',
                      socialButtonsBlockButton: 'bg-white/10 border-white/20 text-white hover:bg-white/20',
                      socialButtonsBlockButtonText: 'text-white font-medium',
                      socialButtonsProviderIcon__apple: 'invert',
                      dividerLine: 'bg-white/10',
                      dividerText: 'text-white/30',
                      formFieldLabel: 'text-white/70',
                      formFieldInput: 'bg-white/5 border-white/10 text-white placeholder:text-white/30 focus:border-blue-500 focus:ring-blue-500/20',
                      formButtonPrimary: 'bg-white text-black hover:bg-white/90 font-semibold',
                      footerActionLink: 'text-blue-400 hover:text-blue-300',
                      identityPreviewText: 'text-white',
                      identityPreviewEditButton: 'text-blue-400',
                      formFieldInputShowPasswordButton: 'text-white/50 hover:text-white',
                      alert: 'bg-red-500/10 border-red-500/20 text-red-400',
                      alertText: 'text-red-400',
                    },
                  }}
                  routing="hash"
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a12]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
              <span className="text-white font-black text-sm">T</span>
            </div>
            <span className="text-white font-semibold">Tradeul</span>
          </Link>

          <div className="flex items-center gap-3">
            <SignedOut>
              <button 
                onClick={() => setAuthPanel('signin')}
                className="px-4 py-2 text-sm text-white/60 hover:text-white transition-colors"
              >
                {t('landing.hero.signIn')}
              </button>
              <button 
                onClick={() => setAuthPanel('signup')}
                className="px-5 py-2 rounded-lg bg-white text-black font-medium text-sm hover:bg-white/90 transition-colors"
              >
                {t('landing.hero.getStarted')}
              </button>
            </SignedOut>
            <SignedIn>
              <Link href="/workspace" className="px-5 py-2 rounded-lg bg-white text-black font-medium text-sm hover:bg-white/90 transition-colors flex items-center gap-2">
                {t('landing.hero.openApp')} <ArrowRight className="w-4 h-4" />
              </Link>
              <UserButton />
            </SignedIn>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-32 pb-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h1 className="text-5xl sm:text-6xl md:text-7xl font-black tracking-tight mb-6">
              <span className="text-white">{t('landing.hero.title1')} </span>
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-400">{t('landing.hero.title2')}</span>
            </h1>
            <p className="text-lg text-white/50 max-w-xl mx-auto mb-10">
              {t('landing.hero.subtitle')}
            </p>
            <div className="flex items-center justify-center gap-4">
              <SignedOut>
                <button 
                  onClick={() => setAuthPanel('signup')}
                  className="px-8 py-3.5 rounded-xl bg-white text-black font-semibold hover:bg-white/90 transition-all flex items-center gap-2"
                >
                  {t('landing.hero.cta')} <ArrowRight className="w-4 h-4" />
                </button>
              </SignedOut>
              <SignedIn>
                <Link href="/workspace" className="px-8 py-3.5 rounded-xl bg-white text-black font-semibold hover:bg-white/90 transition-all flex items-center gap-2">
                  {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-4 h-4" />
                </Link>
              </SignedIn>
            </div>
          </div>

          {/* Live preview cards */}
          <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            {/* Scanner Card */}
            <div className="bg-[#12121a] rounded-2xl border border-white/10 overflow-hidden">
              <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-sm font-medium text-white">{t('landing.cards.scanner')}</span>
                </div>
                <span className="text-xs text-white/40">{t('landing.cards.live')}</span>
              </div>
              <div className="p-4 space-y-2">
                {scannerData.map((item) => (
                  <div key={item.ticker} className="flex items-center justify-between p-3 rounded-lg bg-[#1a1a24] hover:bg-[#1f1f2a] transition-colors">
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-blue-500/20 font-mono font-bold text-sm" style={{ color: '#60a5fa' }}>{item.ticker}</span>
                      <span className="text-sm text-white/70">${item.price}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-white/50">{item.volume}</span>
                      <span className={`flex items-center gap-1 text-sm font-semibold ${item.trend === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {item.trend === 'up' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                        {item.change}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Dilution + Filings Card */}
            <div className="space-y-6">
              {/* Dilution */}
              <div className="bg-[#12121a] rounded-2xl border border-white/10 overflow-hidden">
                <div className="px-5 py-4 border-b border-white/10">
                  <span className="text-sm font-medium text-white">{t('landing.cards.dilution')}</span>
                </div>
                <div className="p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="px-2 py-0.5 rounded bg-violet-500/20 font-mono font-bold" style={{ color: '#a78bfa' }}>SMCI</span>
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-400">
                      MEDIUM RISK
                    </span>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/40">{t('landing.cards.atmShelf')}</span>
                      <span className="text-white">$2.5B remaining</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/40">{t('landing.cards.recentS3')}</span>
                      <span className="text-white">Dec 15, 2024</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Filings */}
              <div className="bg-[#12121a] rounded-2xl border border-white/10 overflow-hidden">
                <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
                  <span className="text-sm font-medium text-white">{t('landing.cards.secFilings')}</span>
                  <span className="text-xs text-white/40">{t('landing.cards.latest')}</span>
                </div>
                <div className="p-4 space-y-2">
                  {filings.map((f, i) => (
                    <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-[#1a1a24] hover:bg-[#1f1f2a] transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="px-2 py-0.5 rounded bg-cyan-500/20 font-mono text-sm font-bold" style={{ color: '#22d3ee' }}>{f.ticker}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/20" style={{ color: '#93c5fd' }}>{f.type}</span>
                      </div>
                      <span className="text-xs text-white/60">{f.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative py-24 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              {t('landing.features.title')}
            </h2>
            <p className="text-white/40">
              {t('landing.features.subtitle')}
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { key: 'scanner', name: t('landing.features.scanner.name'), desc: t('landing.features.scanner.desc') },
              { key: 'dilution', name: t('landing.features.dilution.name'), desc: t('landing.features.dilution.desc') },
              { key: 'sec', name: t('landing.features.sec.name'), desc: t('landing.features.sec.desc') },
              { key: 'fundamentals', name: t('landing.features.fundamentals.name'), desc: t('landing.features.fundamentals.desc') },
              { key: 'news', name: t('landing.features.news.name'), desc: t('landing.features.news.desc') },
              { key: 'squawk', name: t('landing.features.squawk.name'), desc: t('landing.features.squawk.desc'), soon: true },
            ].map((f) => (
              <div key={f.key} className="group p-6 rounded-xl bg-[#12121a] border border-white/5 hover:border-white/10 transition-all">
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-semibold text-white group-hover:text-blue-400 transition-colors">{f.name}</h3>
                  {f.soon && <span className="text-[10px] text-white/30 uppercase tracking-wider">{t('landing.features.squawk.soon')}</span>}
                </div>
                <p className="text-sm text-white/40 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Value props with real content */}
      <section className="relative py-24 px-6">
        <div className="max-w-5xl mx-auto space-y-20">
          {/* Scanner showcase */}
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <div className="inline-block px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-medium mb-4">
                {t('landing.showcase.scanner.badge')}
              </div>
              <h3 className="text-3xl font-bold text-white mb-4">
                {t('landing.showcase.scanner.title')}
              </h3>
              <p className="text-white/40 leading-relaxed mb-6">
                {t('landing.showcase.scanner.desc')}
              </p>
              <ul className="space-y-3 text-sm">
                {[t('landing.showcase.scanner.bullet1'), t('landing.showcase.scanner.bullet2'), t('landing.showcase.scanner.bullet3')].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-white/60">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-[#12121a] rounded-2xl border border-white/10 p-6">
              <div className="space-y-3">
                {[
                  { t: 'NVDA', p: '142.58', c: '+8.42%', v: '89.2M', up: true },
                  { t: 'AMD', p: '178.32', c: '+4.21%', v: '42.1M', up: true },
                  { t: 'SMCI', p: '38.74', c: '+12.15%', v: '45.8M', up: true },
                  { t: 'MSTR', p: '412.30', c: '+5.67%', v: '28.4M', up: true },
                  { t: 'COIN', p: '298.45', c: '-1.23%', v: '18.7M', up: false },
                ].map((s) => (
                  <div key={s.t} className="flex items-center justify-between p-3 rounded-lg bg-[#1a1a24]">
                    <div className="flex items-center gap-4">
                      <span className="font-mono font-bold w-14" style={{ color: '#60a5fa' }}>{s.t}</span>
                      <span className="text-white/70 text-sm">${s.p}</span>
                    </div>
                    <div className="flex items-center gap-6">
                      <span className="text-white/50 text-xs">{s.v}</span>
                      <span className={`font-semibold text-sm ${s.up ? 'text-emerald-400' : 'text-red-400'}`}>{s.c}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Dilution showcase */}
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="lg:order-2">
              <div className="inline-block px-3 py-1 rounded-full bg-violet-500/10 text-violet-400 text-xs font-medium mb-4">
                {t('landing.showcase.dilution.badge')}
              </div>
              <h3 className="text-3xl font-bold text-white mb-4">
                {t('landing.showcase.dilution.title')}
              </h3>
              <p className="text-white/40 leading-relaxed mb-6">
                {t('landing.showcase.dilution.desc')}
              </p>
              <ul className="space-y-3 text-sm">
                {[t('landing.showcase.dilution.bullet1'), t('landing.showcase.dilution.bullet2'), t('landing.showcase.dilution.bullet3')].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-white/60">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="lg:order-1 bg-[#12121a] rounded-2xl border border-white/10 p-6">
              <div className="space-y-4">
                {[
                  { ticker: 'SMCI', risk: 'MEDIUM', riskColor: 'text-amber-400 bg-amber-500/20', shelf: '$2.5B', date: 'Dec 15' },
                  { ticker: 'MARA', risk: 'HIGH', riskColor: 'text-red-400 bg-red-500/20', shelf: '$1.8B', date: 'Dec 18' },
                  { ticker: 'NVDA', risk: 'LOW', riskColor: 'text-emerald-400 bg-emerald-500/20', shelf: 'None', date: '-' },
                ].map((d) => (
                  <div key={d.ticker} className="p-4 rounded-lg bg-[#1a1a24] border border-white/5">
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono font-bold" style={{ color: '#a78bfa' }}>{d.ticker}</span>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${d.riskColor}`}>
                        {d.risk}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-white/40 text-xs block mb-1">{t('landing.cards.atmShelf')}</span>
                        <span className="text-white font-medium">{d.shelf}</span>
                      </div>
                      <div>
                        <span className="text-white/40 text-xs block mb-1">{t('landing.cards.lastFiling')}</span>
                        <span className="text-white font-medium">{d.date}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative py-24 px-6 border-t border-white/5">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-4xl sm:text-5xl font-bold text-white mb-6">
            {t('landing.cta.title')}
          </h2>
          <p className="text-lg text-white/40 mb-10">
            {t('landing.cta.subtitle')}
          </p>
          <SignedOut>
            <button 
              onClick={() => setAuthPanel('signup')}
              className="px-10 py-4 rounded-xl bg-white text-black font-semibold text-lg hover:bg-white/90 transition-all flex items-center gap-2 mx-auto"
            >
              {t('landing.cta.button')} <ArrowRight className="w-5 h-5" />
            </button>
          </SignedOut>
          <SignedIn>
            <Link href="/workspace" className="inline-flex px-10 py-4 rounded-xl bg-white text-black font-semibold text-lg hover:bg-white/90 transition-all items-center gap-2">
              {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-5 h-5" />
            </Link>
          </SignedIn>
          <p className="mt-6 text-sm text-white/30">{t('landing.cta.note')}</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-white/5">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center">
              <span className="text-white font-bold text-xs">T</span>
            </div>
            <span className="text-sm text-white/40">Tradeul</span>
          </div>
          <span className="text-xs text-white/30">{new Date().getFullYear()}</span>
        </div>
      </footer>
    </main>
  );
}
