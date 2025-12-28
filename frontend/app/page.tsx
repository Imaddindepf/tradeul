'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { SignIn, SignUp, SignedIn, SignedOut } from '@clerk/nextjs';
import { ArrowRight, TrendingUp, TrendingDown, X, Zap, Newspaper, BarChart3, Shield, SlidersHorizontal, LineChart, Bell, Target, Layers } from 'lucide-react';
import { useAppTranslation } from '@/hooks/useAppTranslation';
import { motion, useScroll, useTransform, useInView, useSpring } from 'framer-motion';

type AuthPanel = 'closed' | 'signin' | 'signup';

// Animated card component with scroll-based parallax
interface FloatingCardProps {
  children: React.ReactNode;
  delay?: number;
  direction?: 'left' | 'right' | 'bottom' | 'top';
  rotate?: number;
  parallaxSpeed?: number;
  className?: string;
  hoverScale?: number;
}

function FloatingCard({
  children,
  delay = 0,
  direction = 'bottom',
  rotate = 0,
  parallaxSpeed = 0,
  hoverScale = 1.02,
  className = ''
}: FloatingCardProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-50px" });

  // Parallax effect based on scroll
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"]
  });

  const springConfig = { stiffness: 100, damping: 30, restDelta: 0.001 };
  const parallaxY = useSpring(
    useTransform(scrollYProgress, [0, 1], [parallaxSpeed * 50, -parallaxSpeed * 50]),
    springConfig
  );

  const variants = {
    hidden: {
      opacity: 0,
      x: direction === 'left' ? -120 : direction === 'right' ? 120 : 0,
      y: direction === 'bottom' ? 100 : direction === 'top' ? -100 : 0,
      rotate: rotate,
      scale: 0.85,
      filter: "blur(10px)",
    },
    visible: {
      opacity: 1,
      x: 0,
      y: 0,
      rotate: 0,
      scale: 1,
      filter: "blur(0px)",
    }
  };

  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={variants}
      style={{ y: parallaxSpeed ? parallaxY : 0 }}
      whileHover={{
        scale: hoverScale,
        rotate: rotate * 0.3,
        transition: { duration: 0.3 }
      }}
      transition={{
        duration: 1,
        delay: delay,
        ease: [0.22, 1, 0.36, 1]
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Floating decorative element
function FloatingOrb({ className, delay = 0 }: { className: string; delay?: number }) {
  return (
    <motion.div
      className={className}
      animate={{
        y: [0, -20, 0],
        x: [0, 10, 0],
        scale: [1, 1.1, 1],
      }}
      transition={{
        duration: 6,
        delay,
        repeat: Infinity,
        ease: "easeInOut"
      }}
    />
  );
}

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
    <main className="min-h-screen bg-[#fafafa] text-slate-900 overflow-hidden">
      {/* Clean light background with subtle texture */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-b from-white via-slate-50 to-slate-100" />
        {/* Subtle dot pattern */}
        <div className="absolute inset-0 opacity-[0.4]" style={{
          backgroundImage: 'radial-gradient(circle, #cbd5e1 1px, transparent 1px)',
          backgroundSize: '24px 24px'
        }} />
      </div>

      {/* Auth Side Panel */}
      <div
        className={`fixed inset-0 z-[100] transition-all duration-500 ${authPanel !== 'closed' ? 'pointer-events-auto' : 'pointer-events-none'
          }`}
      >
        {/* Backdrop */}
        <div
          className={`absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity duration-500 ${authPanel !== 'closed' ? 'opacity-100' : 'opacity-0'
            }`}
          onClick={() => setAuthPanel('closed')}
        />

        {/* Panel */}
        <div
          className={`absolute right-0 top-0 h-full w-full max-w-md bg-white border-l border-slate-200 shadow-2xl transition-transform duration-500 ease-out ${authPanel !== 'closed' ? 'translate-x-0' : 'translate-x-full'
            }`}
        >
          {/* Panel header */}
          <div className="flex items-center justify-between p-6 border-b border-slate-100">
            <div className="flex gap-4">
              <button
                onClick={() => setAuthPanel('signin')}
                className={`text-sm font-medium transition-colors ${authPanel === 'signin' ? 'text-slate-900' : 'text-slate-400 hover:text-slate-600'
                  }`}
              >
                {t('landing.auth.signIn')}
              </button>
              <button
                onClick={() => setAuthPanel('signup')}
                className={`text-sm font-medium transition-colors ${authPanel === 'signup' ? 'text-slate-900' : 'text-slate-400 hover:text-slate-600'
                  }`}
              >
                {t('landing.auth.createAccount')}
              </button>
            </div>
            <button
              onClick={() => setAuthPanel('closed')}
              className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-400 hover:text-slate-600"
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
                      card: 'shadow-none',
                      headerTitle: 'text-slate-900',
                      headerSubtitle: 'text-slate-500',
                      socialButtonsBlockButton: 'bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100',
                      socialButtonsBlockButtonText: 'text-slate-700',
                      dividerLine: 'bg-slate-200',
                      dividerText: 'text-slate-400',
                      formFieldLabel: 'text-slate-600',
                      formFieldInput: 'bg-white border-slate-200 text-slate-900',
                      formButtonPrimary: 'bg-slate-900 text-white hover:bg-slate-800',
                      footerActionLink: 'text-blue-600 hover:text-blue-700',
                      footer: 'hidden',
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
                      card: 'shadow-none',
                      headerTitle: 'text-slate-900',
                      headerSubtitle: 'text-slate-500',
                      socialButtonsBlockButton: 'bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100',
                      socialButtonsBlockButtonText: 'text-slate-700',
                      dividerLine: 'bg-slate-200',
                      dividerText: 'text-slate-400',
                      formFieldLabel: 'text-slate-600',
                      formFieldInput: 'bg-white border-slate-200 text-slate-900',
                      formButtonPrimary: 'bg-slate-900 text-white hover:bg-slate-800',
                      footerActionLink: 'text-blue-600 hover:text-blue-700',
                      footer: 'hidden',
                    },
                  }}
                  routing="hash"
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Navigation - Centered floating pill navbar */}
      <nav className="fixed top-6 left-1/2 -translate-x-1/2 z-50">
        <div className="flex items-center gap-1 px-2 py-2 rounded-full bg-white/80 backdrop-blur-xl border border-slate-200 shadow-lg shadow-slate-200/50">
          {/* Menu items */}
          <div className="flex items-center">
            <button
              onClick={() => document.getElementById('products')?.scrollIntoView({ behavior: 'smooth' })}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition-colors rounded-full hover:bg-slate-100"
            >
              {t('landing.nav.products')}
            </button>
            <button
              onClick={() => document.getElementById('tools')?.scrollIntoView({ behavior: 'smooth' })}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition-colors rounded-full hover:bg-slate-100"
            >
              {t('landing.nav.tools')}
            </button>
            <button
              onClick={() => document.getElementById('solutions')?.scrollIntoView({ behavior: 'smooth' })}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition-colors rounded-full hover:bg-slate-100"
            >
              {t('landing.nav.solutions')}
            </button>
            <button
              onClick={() => document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth' })}
              className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition-colors rounded-full hover:bg-slate-100"
            >
              {t('landing.nav.resources')}
            </button>
          </div>

          {/* CTA button */}
          <SignedOut>
            <button
              onClick={() => setAuthPanel('signup')}
              className="ml-2 px-5 py-2 rounded-full bg-slate-900 text-white font-medium text-sm hover:bg-slate-800 transition-colors"
            >
              {t('landing.nav.signUp')}
            </button>
          </SignedOut>
          <SignedIn>
            <Link
              href="/workspace"
              className="ml-2 px-5 py-2 rounded-full bg-slate-900 text-white font-medium text-sm hover:bg-slate-800 transition-colors flex items-center gap-2"
            >
              {t('landing.hero.openApp')} <ArrowRight className="w-4 h-4" />
            </Link>
          </SignedIn>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          {/* Two column layout: Text left, Image right */}
          <div className="grid lg:grid-cols-2 gap-12 items-center mb-20">
            {/* Left: Text content */}
            <div className="text-left">
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight mb-6">
                <span className="text-slate-900">{t('landing.hero.title1')} </span>
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-violet-600">{t('landing.hero.title2')}</span>
              </h1>
              <p className="text-lg text-slate-500 max-w-lg mb-8">
                {t('landing.hero.subtitle')}
              </p>
              <div className="flex items-center gap-4">
                <SignedOut>
                  <button
                    onClick={() => setAuthPanel('signup')}
                    className="px-8 py-3.5 rounded-xl bg-slate-900 text-white font-semibold hover:bg-slate-800 transition-all flex items-center gap-2"
                  >
                    {t('landing.hero.cta')} <ArrowRight className="w-4 h-4" />
                  </button>
                </SignedOut>
                <SignedIn>
                  <Link href="/workspace" className="px-8 py-3.5 rounded-xl bg-slate-900 text-white font-semibold hover:bg-slate-800 transition-all flex items-center gap-2">
                    {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-4 h-4" />
                  </Link>
                </SignedIn>
              </div>
            </div>

            {/* Right: Platform SVG Image - Floating animation */}
            <motion.div
              className="relative flex justify-center lg:justify-end"
              animate={{
                y: [0, -15, 0],
              }}
              transition={{
                duration: 4,
                repeat: Infinity,
                ease: "easeInOut"
              }}
            >
              <Image
                src="/images/tradeul-landing-image.svg"
                alt="TradeUL Platform"
                width={600}
                height={450}
                className="w-full max-w-[500px] h-auto drop-shadow-2xl"
                priority
              />
            </motion.div>
          </div>

          {/* Live preview cards - Floating animation on scroll with parallax */}
          <div className="relative max-w-5xl mx-auto min-h-[520px]">
            {/* Decorative floating orbs */}
            <FloatingOrb
              className="absolute -left-20 top-20 w-32 h-32 bg-cyan-500/10 rounded-full blur-3xl"
              delay={0}
            />
            <FloatingOrb
              className="absolute -right-10 top-40 w-24 h-24 bg-violet-500/10 rounded-full blur-2xl"
              delay={1.5}
            />
            <FloatingOrb
              className="absolute left-1/3 bottom-10 w-20 h-20 bg-blue-500/10 rounded-full blur-2xl"
              delay={3}
            />

            {/* Scanner Card - enters from left with rotation and parallax */}
            <FloatingCard
              direction="left"
              delay={0}
              rotate={-12}
              parallaxSpeed={0.5}
              hoverScale={1.03}
              className="absolute left-0 top-0 w-[380px] z-10"
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500">
                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-sm font-medium text-slate-900">{t('landing.cards.scanner')}</span>
                  </div>
                  <span className="text-xs text-slate-400">{t('landing.cards.live')}</span>
                </div>
                <div className="p-4 space-y-2">
                  {scannerData.map((item, idx) => (
                    <motion.div
                      key={item.ticker}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.5 + idx * 0.1 }}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        <span className="px-2.5 py-1 rounded bg-blue-100 font-mono font-bold text-sm text-blue-700">{item.ticker}</span>
                        <span className="text-sm text-slate-700">${item.price}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400">{item.volume}</span>
                        <span className={`flex items-center gap-1 text-sm font-semibold ${item.trend === 'up' ? 'text-emerald-600' : 'text-red-600'}`}>
                          {item.trend === 'up' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                          {item.change}
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </FloatingCard>

            {/* Dilution Card - enters from right with rotation and parallax */}
            <FloatingCard
              direction="right"
              delay={0.2}
              rotate={10}
              parallaxSpeed={-0.3}
              hoverScale={1.03}
              className="absolute right-0 top-12 w-[340px] z-20"
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500">
                <div className="px-5 py-4 border-b border-slate-100">
                  <span className="text-sm font-medium text-slate-900">{t('landing.cards.dilution')}</span>
                </div>
                <div className="p-4">
                  <div className="flex items-center justify-between mb-4">
                    <span className="px-2.5 py-1 rounded bg-violet-100 font-mono font-bold text-violet-700">SMCI</span>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                      MEDIUM RISK
                    </span>
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">{t('landing.cards.atmShelf')}</span>
                      <span className="text-slate-900 font-medium">$2.5B remaining</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">{t('landing.cards.recentS3')}</span>
                      <span className="text-slate-900 font-medium">Dec 15, 2024</span>
                    </div>
                  </div>
                </div>
              </div>
            </FloatingCard>

            {/* Filings Card - enters from bottom with parallax */}
            <FloatingCard
              direction="bottom"
              delay={0.4}
              rotate={-5}
              parallaxSpeed={0.2}
              hoverScale={1.03}
              className="absolute left-1/2 -translate-x-1/2 top-[260px] w-[360px] z-30"
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500">
                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-900">{t('landing.cards.secFilings')}</span>
                  <span className="text-xs text-slate-400">{t('landing.cards.latest')}</span>
                </div>
                <div className="p-4 space-y-2">
                  {filings.map((f, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.8 + i * 0.1 }}
                      className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        <span className="px-2.5 py-1 rounded bg-blue-100 font-mono text-sm font-bold text-blue-700">{f.ticker}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-slate-200 text-slate-600">{f.type}</span>
                      </div>
                      <span className="text-xs text-slate-400">{f.time}</span>
                    </motion.div>
                  ))}
                </div>
              </div>
            </FloatingCard>

            {/* Small chart decoration - enters from left bottom */}
            <FloatingCard
              direction="left"
              delay={0.6}
              rotate={8}
              parallaxSpeed={0.4}
              hoverScale={1.05}
              className="absolute left-[10%] top-[340px] w-[180px] z-5"
            >
              <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-lg hover:shadow-xl transition-all duration-300">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                  <span className="text-[10px] text-slate-400">NVDA 1D</span>
                  <span className="text-[10px] text-emerald-400 ml-auto">+3.2%</span>
                </div>
                <svg viewBox="0 0 100 40" className="w-full h-10">
                  <defs>
                    <linearGradient id="chartGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M0,35 L15,30 L30,32 L45,20 L60,25 L75,15 L90,18 L100,10 L100,40 L0,40 Z"
                    fill="url(#chartGradient)"
                  />
                  <polyline
                    points="0,35 15,30 30,32 45,20 60,25 75,15 90,18 100,10"
                    fill="none"
                    stroke="#22d3ee"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
            </FloatingCard>

            {/* Extra small price card - enters from right bottom */}
            <FloatingCard
              direction="right"
              delay={0.75}
              rotate={-6}
              parallaxSpeed={-0.5}
              hoverScale={1.05}
              className="absolute right-[8%] top-[380px] w-[150px] z-5"
            >
              <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-lg hover:shadow-xl transition-all duration-300">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-500">BTC/USD</span>
                  <span className="text-[10px] text-emerald-600">Live</span>
                </div>
                <div className="text-lg font-bold text-slate-900 mt-1">$98,432</div>
                <div className="text-[10px] text-emerald-600">+2.4% today</div>
              </div>
            </FloatingCard>
          </div>
        </div>
      </section>

      {/* PRODUCTS - Epic Section */}
      <section id="products" className="relative py-32 px-6 scroll-mt-24">
        <div className="max-w-6xl mx-auto relative">
          {/* Section header */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="text-center mb-20"
          >
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">Platform</span>
            <h2 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-6">
              The tools you actually need
            </h2>
            <p className="text-base text-slate-500 max-w-xl mx-auto">
              Real-time market data, analytics, and research — consolidated in one workspace.
            </p>
          </motion.div>

          {/* Main Products Grid - Bento style */}
          <div className="grid lg:grid-cols-3 gap-4">
            {/* Hero Card - Real-time Scanner (spans 2 cols) */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="lg:col-span-2 group"
            >
              <div className="relative h-full p-8 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2.5 rounded-xl bg-blue-50 border border-blue-100">
                      <Zap className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="text-xl font-semibold text-slate-900">Real-Time Scanner</h3>
                      <p className="text-slate-400 text-sm">&lt;50ms latency</p>
                    </div>
                  </div>

                  <p className="text-slate-500 text-sm mb-6 max-w-lg leading-relaxed">
                    8,000+ tickers. Gap scanners, momentum alerts, volume spikes. Custom filters with real-time streaming.
                  </p>

                  {/* Mini preview */}
                  <div className="bg-slate-50 rounded-xl border border-slate-100 p-4 space-y-2">
                    {[
                      { t: 'NVDA', p: '$142.58', c: '+8.42%', up: true },
                      { t: 'SMCI', p: '$38.74', c: '+12.15%', up: true },
                      { t: 'MSTR', p: '$412.30', c: '-2.31%', up: false },
                    ].map((s, i) => (
                      <motion.div
                        key={s.t}
                        initial={{ opacity: 0, x: -20 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.3 + i * 0.1 }}
                        className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100"
                      >
                        <div className="flex items-center gap-3">
                          <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-mono text-sm font-bold">{s.t}</span>
                          <span className="text-slate-600 text-sm">{s.p}</span>
                        </div>
                        <span className={`font-semibold text-sm ${s.up ? 'text-emerald-600' : 'text-red-600'}`}>{s.c}</span>
                      </motion.div>
                    ))}
                  </div>

                  <div className="flex items-center gap-4 mt-6">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      Live streaming
                    </div>
                    <span className="text-xs text-slate-300">•</span>
                    <span className="text-xs text-slate-500">8,000+ tickers</span>
                    <span className="text-xs text-slate-300">•</span>
                    <span className="text-xs text-slate-500">Custom filters</span>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* News Card */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="group"
            >
              <div className="relative h-full p-6 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10">
                  <div className="p-2.5 rounded-xl bg-violet-50 border border-violet-100 w-fit mb-4">
                    <Newspaper className="w-4 h-4 text-violet-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">News Feed</h3>
                  <p className="text-slate-500 text-sm mb-4">
                    Real-time news with price correlation. Filter by ticker, sector, or impact.
                  </p>

                  <div className="space-y-2">
                    {['AAPL earnings beat expectations', 'FDA approves MRNA drug'].map((n, i) => (
                      <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 border border-slate-100 text-xs">
                        <Bell className="w-3 h-3 text-violet-600" />
                        <span className="text-slate-600 truncate">{n}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Dilution Tracker */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="group"
            >
              <div className="relative h-full p-6 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10">
                  <div className="p-2.5 rounded-xl bg-amber-50 border border-amber-100 w-fit mb-4">
                    <Shield className="w-4 h-4 text-amber-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">Dilution Tracker</h3>
                  <p className="text-slate-500 text-sm mb-4">
                    SEC filing analysis. ATM shelves, warrants, risk scoring.
                  </p>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-100">
                    <span className="font-mono text-amber-700 font-bold">SMCI</span>
                    <span className="px-2 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">MEDIUM RISK</span>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Screener */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="group"
            >
              <div className="relative h-full p-6 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10">
                  <div className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-100 w-fit mb-4">
                    <SlidersHorizontal className="w-4 h-4 text-emerald-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">Screener</h3>
                  <p className="text-slate-500 text-sm mb-4">
                    200+ filters. Fundamentals, technicals, float, short interest.
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {['P/E < 15', 'Float < 10M', 'Vol > 1M'].map((f) => (
                      <span key={f} className="px-2 py-1 rounded-full text-xs bg-emerald-100 text-emerald-700 border border-emerald-200">{f}</span>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Analytics - spans 2 cols */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="lg:col-span-2 group"
            >
              <div className="relative h-full p-8 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10 flex flex-col lg:flex-row gap-8">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="p-2.5 rounded-xl bg-blue-50 border border-blue-100">
                        <BarChart3 className="w-5 h-5 text-blue-600" />
                      </div>
                      <h3 className="text-xl font-semibold text-slate-900">Financials & Analytics</h3>
                    </div>

                    <p className="text-slate-500 text-sm mb-6 leading-relaxed">
                      Financial statements, valuation ratios, technical indicators. All the data in one place.
                    </p>

                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { icon: LineChart, label: 'Charts', color: 'blue' },
                        { icon: Target, label: 'Patterns', color: 'violet' },
                        { icon: Layers, label: 'Financials', color: 'emerald' },
                      ].map((item) => (
                        <div key={item.label} className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-center">
                          <item.icon className={`w-5 h-5 mx-auto mb-1 text-${item.color}-600`} />
                          <span className="text-xs text-slate-600">{item.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Mini chart */}
                  <div className="flex-1 flex items-center justify-center">
                    <svg viewBox="0 0 200 100" className="w-full max-w-[250px] h-auto">
                      <defs>
                        <linearGradient id="areaGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.15" />
                          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <path d="M0,80 Q25,70 50,60 T100,40 T150,50 T200,20 V100 H0 Z" fill="url(#areaGrad)" />
                      <path d="M0,80 Q25,70 50,60 T100,40 T150,50 T200,20" fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" />
                      <circle cx="200" cy="20" r="4" fill="#3b82f6" />
                    </svg>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Pattern Matching */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.5 }}
              className="group"
            >
              <div className="relative h-full p-6 rounded-3xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-xl transition-all duration-500 overflow-hidden">
                <div className="relative z-10">
                  <div className="p-2.5 rounded-xl bg-pink-50 border border-pink-100 w-fit mb-4">
                    <Target className="w-4 h-4 text-pink-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">Pattern Matching</h3>
                  <p className="text-slate-500 text-sm mb-4">
                    Historical similarity search. 360M+ patterns indexed.
                  </p>

                  <div className="text-xs text-slate-400 font-mono">
                    FAISS vector search
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* TOOLS - Value props with real content */}
      <section id="tools" className="relative py-24 px-6 scroll-mt-24 bg-slate-50/50">
        <div className="max-w-5xl mx-auto space-y-20">
          {/* Scanner showcase */}
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <div className="inline-block px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-medium mb-4">
                {t('landing.showcase.scanner.badge')}
              </div>
              <h3 className="text-3xl font-bold text-slate-900 mb-4">
                {t('landing.showcase.scanner.title')}
              </h3>
              <p className="text-slate-500 leading-relaxed mb-6">
                {t('landing.showcase.scanner.desc')}
              </p>
              <ul className="space-y-3 text-sm">
                {[t('landing.showcase.scanner.bullet1'), t('landing.showcase.scanner.bullet2'), t('landing.showcase.scanner.bullet3')].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-slate-600">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-lg">
              <div className="space-y-3">
                {[
                  { t: 'NVDA', p: '142.58', c: '+8.42%', v: '89.2M', up: true },
                  { t: 'AMD', p: '178.32', c: '+4.21%', v: '42.1M', up: true },
                  { t: 'SMCI', p: '38.74', c: '+12.15%', v: '45.8M', up: true },
                  { t: 'MSTR', p: '412.30', c: '+5.67%', v: '28.4M', up: true },
                  { t: 'COIN', p: '298.45', c: '-1.23%', v: '18.7M', up: false },
                ].map((s) => (
                  <div key={s.t} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <div className="flex items-center gap-4">
                      <span className="font-mono font-bold w-14 text-blue-600">{s.t}</span>
                      <span className="text-slate-600 text-sm">${s.p}</span>
                    </div>
                    <div className="flex items-center gap-6">
                      <span className="text-slate-400 text-xs">{s.v}</span>
                      <span className={`font-semibold text-sm ${s.up ? 'text-emerald-600' : 'text-red-600'}`}>{s.c}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Dilution showcase */}
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="lg:order-2">
              <div className="inline-block px-3 py-1 rounded-full bg-violet-100 text-violet-700 text-xs font-medium mb-4">
                {t('landing.showcase.dilution.badge')}
              </div>
              <h3 className="text-3xl font-bold text-slate-900 mb-4">
                {t('landing.showcase.dilution.title')}
              </h3>
              <p className="text-slate-500 leading-relaxed mb-6">
                {t('landing.showcase.dilution.desc')}
              </p>
              <ul className="space-y-3 text-sm">
                {[t('landing.showcase.dilution.bullet1'), t('landing.showcase.dilution.bullet2'), t('landing.showcase.dilution.bullet3')].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-slate-600">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="lg:order-1 bg-white rounded-2xl border border-slate-200 p-6 shadow-lg">
              <div className="space-y-4">
                {[
                  { ticker: 'SMCI', risk: 'MEDIUM', riskColor: 'text-amber-700 bg-amber-100', shelf: '$2.5B', date: 'Dec 15' },
                  { ticker: 'MARA', risk: 'HIGH', riskColor: 'text-red-700 bg-red-100', shelf: '$1.8B', date: 'Dec 18' },
                  { ticker: 'NVDA', risk: 'LOW', riskColor: 'text-emerald-700 bg-emerald-100', shelf: 'None', date: '-' },
                ].map((d) => (
                  <div key={d.ticker} className="p-4 rounded-lg bg-slate-50 border border-slate-100">
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono font-bold text-violet-600">{d.ticker}</span>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${d.riskColor}`}>
                        {d.risk}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-slate-400 text-xs block mb-1">{t('landing.cards.atmShelf')}</span>
                        <span className="text-slate-900 font-medium">{d.shelf}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 text-xs block mb-1">{t('landing.cards.lastFiling')}</span>
                        <span className="text-slate-900 font-medium">{d.date}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SOLUTIONS - Use Cases */}
      <section id="solutions" className="relative py-24 px-6 border-t border-slate-200 scroll-mt-24">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">Use cases</span>
            <h2 className="text-3xl font-bold text-slate-900 mb-4">For different strategies</h2>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-4">
            {[
              { title: 'Intraday', desc: 'Real-time scanners, momentum alerts, low latency data.', icon: Zap, color: 'blue' },
              { title: 'Small Caps', desc: 'Dilution tracking, SEC filings, float analysis.', icon: Target, color: 'amber' },
              { title: 'Swing & Position', desc: 'Financials, valuations, pattern recognition.', icon: BarChart3, color: 'violet' },
            ].map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="p-5 rounded-xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-lg transition-all"
              >
                <item.icon className={`w-5 h-5 text-${item.color}-600 mb-3`} />
                <h3 className="text-base font-semibold text-slate-900 mb-1">{item.title}</h3>
                <p className="text-sm text-slate-500">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative py-24 px-6 bg-gradient-to-br from-slate-100 to-white border-t border-slate-200">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-6">
            {t('landing.cta.title')}
          </h2>
          <p className="text-lg text-slate-500 mb-10">
            {t('landing.cta.subtitle')}
          </p>
          <SignedOut>
            <button
              onClick={() => setAuthPanel('signup')}
              className="px-10 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all flex items-center gap-2 mx-auto"
            >
              {t('landing.cta.button')} <ArrowRight className="w-5 h-5" />
            </button>
          </SignedOut>
          <SignedIn>
            <Link href="/workspace" className="inline-flex px-10 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all items-center gap-2">
              {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-5 h-5" />
            </Link>
          </SignedIn>
          <p className="mt-6 text-sm text-slate-400">{t('landing.cta.note')}</p>
        </div>
      </section>

      {/* RESOURCES - Footer */}
      <footer id="resources" className="py-8 px-6 border-t border-slate-200 scroll-mt-24 bg-white">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center">
              <span className="text-white font-bold text-xs">T</span>
            </div>
            <span className="text-sm text-slate-500">Tradeul</span>
          </div>
          <span className="text-xs text-slate-400">{new Date().getFullYear()}</span>
        </div>
      </footer>
    </main>
  );
}
