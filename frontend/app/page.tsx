'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { SignIn, SignUp, SignedIn, SignedOut } from '@clerk/nextjs';
import { ArrowRight, TrendingUp, TrendingDown, X, Zap, Newspaper, BarChart3, Shield, SlidersHorizontal, LineChart, Bell, Target, Layers, ChevronDown } from 'lucide-react';
import { useAppTranslation } from '@/hooks/useAppTranslation';
import { motion, useScroll, useTransform, useSpring, MotionValue } from 'framer-motion';

type AuthPanel = 'closed' | 'signin' | 'signup';

// Section reveal animation wrapper
interface RevealSectionProps {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}

function RevealSection({ children, className = '', delay = 0 }: RevealSectionProps) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "start center"]
  });

  const opacity = useTransform(scrollYProgress, [0, 0.5, 1], [0, 0.5, 1]);
  const y = useTransform(scrollYProgress, [0, 0.5, 1], [100, 40, 0]);
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [0.95, 0.98, 1]);

  const smoothY = useSpring(y, { stiffness: 100, damping: 30 });
  const smoothOpacity = useSpring(opacity, { stiffness: 100, damping: 30 });
  const smoothScale = useSpring(scale, { stiffness: 100, damping: 30 });

  return (
    <motion.div
      ref={ref}
      style={{
        opacity: smoothOpacity,
        y: smoothY,
        scale: smoothScale,
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Stagger reveal for children
interface StaggerRevealProps {
  children: React.ReactNode;
  className?: string;
  staggerDelay?: number;
}

function StaggerReveal({ children, className = '', staggerDelay = 0.1 }: StaggerRevealProps) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "start 0.6"]
  });

  const opacity = useTransform(scrollYProgress, [0, 1], [0, 1]);
  const y = useTransform(scrollYProgress, [0, 1], [60, 0]);

  return (
    <motion.div
      ref={ref}
      style={{ opacity, y }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Floating card with scroll-triggered animation
interface FloatingCardProps {
  children: React.ReactNode;
  delay?: number;
  direction?: 'left' | 'right' | 'bottom' | 'top';
  rotate?: number;
  className?: string;
}

function FloatingCard({
  children,
  delay = 0,
  direction = 'bottom',
  rotate = 0,
  className = ''
}: FloatingCardProps) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "start 0.5"]
  });

  const progress = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });

  // Simplified animations - no position changes, only opacity and scale
  const opacity = useTransform(progress, [0, 0.5, 1], [0, 0.7, 1]);
  const scale = useTransform(progress, [0, 1], [0.95, 1]);
  const y = useTransform(progress, [0, 1], [30, 0]);

  return (
    <motion.div
      ref={ref}
      style={{ opacity, scale, y }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Parallax element
function useParallax(value: MotionValue<number>, distance: number) {
  return useTransform(value, [0, 1], [-distance, distance]);
}

export default function Home() {
  const [mounted, setMounted] = useState(false);
  const [authPanel, setAuthPanel] = useState<AuthPanel>('closed');
  const { t } = useAppTranslation();

  // Hero scroll progress for parallax
  const heroRef = useRef(null);
  const { scrollYProgress: heroScrollProgress } = useScroll({
    target: heroRef,
    offset: ["start start", "end start"]
  });

  const heroOpacity = useTransform(heroScrollProgress, [0, 0.5], [1, 0]);
  const heroY = useTransform(heroScrollProgress, [0, 0.5], [0, -100]);
  const heroScale = useTransform(heroScrollProgress, [0, 0.5], [1, 0.95]);

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
    <main className="min-h-screen bg-[#fafafa] text-slate-900 overflow-x-hidden snap-y snap-proximity scroll-smooth">
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

      {/* ========== HERO SECTION - Full Screen ========== */}
      <section
        ref={heroRef}
        className="relative min-h-screen flex flex-col justify-center px-6 snap-start"
      >
        <motion.div
          style={{ opacity: heroOpacity, y: heroY, scale: heroScale }}
          className="max-w-7xl mx-auto w-full pt-20"
        >
          {/* Two column layout: Text left, Image right */}
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left: Text content */}
            <motion.div
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="text-left"
            >
              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight mb-6">
                <span className="text-slate-900">{t('landing.hero.title1')} </span>
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-violet-600">{t('landing.hero.title2')}</span>
              </h1>
              <p className="text-xl text-slate-500 max-w-lg mb-10 leading-relaxed">
                {t('landing.hero.subtitle')}
              </p>
              <div className="flex items-center gap-4">
                <SignedOut>
                  <motion.button
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5, delay: 0.6 }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setAuthPanel('signup')}
                    className="px-8 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all flex items-center gap-2 shadow-lg shadow-slate-900/20"
                  >
                    {t('landing.hero.cta')} <ArrowRight className="w-5 h-5" />
                  </motion.button>
                </SignedOut>
                <SignedIn>
                  <Link href="/workspace" className="px-8 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all flex items-center gap-2 shadow-lg shadow-slate-900/20">
                    {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-5 h-5" />
                  </Link>
                </SignedIn>
              </div>
            </motion.div>

            {/* Right: Platform SVG Image */}
            <motion.div
              initial={{ opacity: 0, x: 60 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 1, delay: 0.4 }}
              className="relative flex justify-center lg:justify-end"
            >
              <motion.div
                animate={{
                  y: [0, -20, 0],
                }}
                transition={{
                  duration: 5,
                  repeat: Infinity,
                  ease: "easeInOut"
                }}
              >
                <Image
                  src="/images/tradeul-landing-image.svg"
                  alt="TradeUL Platform"
                  width={600}
                  height={450}
                  className="w-full max-w-[550px] h-auto drop-shadow-2xl"
                  priority
                />
              </motion.div>
            </motion.div>
          </div>
        </motion.div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5 }}
          className="absolute bottom-6 left-1/2 -translate-x-1/2"
        >
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="flex flex-col items-center gap-2 text-slate-400"
          >
            <span className="text-xs font-medium uppercase tracking-widest">Scroll</span>
            <ChevronDown className="w-5 h-5" />
          </motion.div>
        </motion.div>
      </section>

      {/* ========== LIVE PREVIEW CARDS SECTION ========== */}
      <section className="relative py-32 px-6 min-h-screen snap-start flex flex-col justify-center">
        <div className="max-w-5xl mx-auto">
          {/* Section title */}
          <RevealSection className="text-center mb-20">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">Live Preview</span>
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 mb-4">
              See it in action
            </h2>
            <p className="text-base text-slate-500 max-w-xl mx-auto">
              Real-time data streaming across all instruments
            </p>
          </RevealSection>

          {/* Cards Grid Layout - Clean 2 columns */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-4xl mx-auto">
            {/* Scanner Card */}
            <FloatingCard
              direction="left"
              delay={0}
              rotate={0}
              className=""
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500 h-full">
                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-sm font-medium text-slate-900">{t('landing.cards.scanner')}</span>
                  </div>
                  <span className="text-xs text-slate-400">{t('landing.cards.live')}</span>
                </div>
                <div className="p-4 space-y-2">
                  {scannerData.map((item) => (
                    <div
                      key={item.ticker}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        <span className="px-2.5 py-1 rounded bg-blue-100 font-mono font-bold text-sm text-blue-700">{item.ticker}</span>
                        <span className="text-sm text-slate-700">${item.price}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-slate-400 hidden sm:block">{item.volume}</span>
                        <span className={`flex items-center gap-1 text-sm font-semibold ${item.trend === 'up' ? 'text-emerald-600' : 'text-red-600'}`}>
                          {item.trend === 'up' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                          {item.change}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </FloatingCard>

            {/* Dilution Card */}
            <FloatingCard
              direction="right"
              delay={0.1}
              rotate={0}
              className=""
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500 h-full">
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

            {/* SEC Filings Card */}
            <FloatingCard
              direction="bottom"
              delay={0.2}
              rotate={0}
              className=""
            >
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500 h-full">
                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-900">{t('landing.cards.secFilings')}</span>
                  <span className="text-xs text-slate-400">{t('landing.cards.latest')}</span>
                </div>
                <div className="p-4 space-y-2">
                  {filings.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 transition-all"
                    >
                      <div className="flex items-center gap-3">
                        <span className="px-2.5 py-1 rounded bg-blue-100 font-mono text-sm font-bold text-blue-700">{f.ticker}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-slate-200 text-slate-600">{f.type}</span>
                      </div>
                      <span className="text-xs text-slate-400">{f.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            </FloatingCard>

            {/* Chart Card */}
            <FloatingCard
              direction="left"
              delay={0.3}
              rotate={0}
              className=""
            >
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500 h-full">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="text-sm font-medium text-slate-900">NVDA</span>
                  <span className="text-xs text-slate-400">1D</span>
                  <span className="text-sm text-emerald-500 font-semibold ml-auto">+3.2%</span>
                </div>
                <svg viewBox="0 0 100 50" className="w-full h-20">
                  <defs>
                    <linearGradient id="chartGradient2" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M0,45 L15,38 L30,40 L45,25 L60,30 L75,18 L90,22 L100,12 L100,50 L0,50 Z"
                    fill="url(#chartGradient2)"
                  />
                  <polyline
                    points="0,45 15,38 30,40 45,25 60,30 75,18 90,22 100,12"
                    fill="none"
                    stroke="#22d3ee"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                </svg>
                <div className="flex justify-between text-xs text-slate-400 mt-2">
                  <span>9:30</span>
                  <span>12:00</span>
                  <span>16:00</span>
                </div>
              </div>
            </FloatingCard>

            {/* Price Card */}
            <FloatingCard
              direction="right"
              delay={0.35}
              rotate={0}
              className=""
            >
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xl shadow-slate-200/50 hover:shadow-slate-300/50 hover:border-slate-300 transition-all duration-500 h-full">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="text-sm text-slate-500">Crypto</span>
                    <div className="text-xs text-emerald-500 flex items-center gap-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Live
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  <div className="p-3 rounded-xl bg-slate-50">
                    <span className="text-xs text-slate-500 block mb-1">BTC/USD</span>
                    <span className="text-lg font-bold text-slate-900">$98,432</span>
                    <span className="text-xs text-emerald-600 block">+2.4%</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50">
                    <span className="text-xs text-slate-500 block mb-1">ETH/USD</span>
                    <span className="text-lg font-bold text-slate-900">$3,521</span>
                    <span className="text-xs text-emerald-600 block">+1.8%</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 hidden sm:block">
                    <span className="text-xs text-slate-500 block mb-1">SOL/USD</span>
                    <span className="text-lg font-bold text-slate-900">$198</span>
                    <span className="text-xs text-red-600 block">-0.5%</span>
                  </div>
                </div>
              </div>
            </FloatingCard>

          </div>
        </div>
      </section>

      {/* ========== PRODUCTS - Epic Section ========== */}
      <section id="products" className="relative py-32 px-6 scroll-mt-24 min-h-screen snap-start flex flex-col justify-center">
        <div className="max-w-6xl mx-auto relative">
          {/* Section header */}
          <RevealSection className="text-center mb-20">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">Platform</span>
            <h2 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-6">
              The tools you actually need
            </h2>
            <p className="text-base text-slate-500 max-w-xl mx-auto">
              Real-time market data, analytics, and research — consolidated in one workspace.
            </p>
          </RevealSection>

          {/* Main Products Grid - Bento style */}
          <div className="grid lg:grid-cols-3 gap-4">
            {/* Hero Card - Real-time Scanner (spans 2 cols) */}
            <StaggerReveal className="lg:col-span-2 group">
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
                    ].map((s) => (
                      <div
                        key={s.t}
                        className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100"
                      >
                        <div className="flex items-center gap-3">
                          <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-mono text-sm font-bold">{s.t}</span>
                          <span className="text-slate-600 text-sm">{s.p}</span>
                        </div>
                        <span className={`font-semibold text-sm ${s.up ? 'text-emerald-600' : 'text-red-600'}`}>{s.c}</span>
                      </div>
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
            </StaggerReveal>

            {/* News Card */}
            <StaggerReveal className="group">
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
            </StaggerReveal>

            {/* Dilution Tracker */}
            <StaggerReveal className="group">
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
            </StaggerReveal>

            {/* Screener */}
            <StaggerReveal className="group">
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
            </StaggerReveal>

            {/* Analytics - spans 2 cols */}
            <StaggerReveal className="lg:col-span-2 group">
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
            </StaggerReveal>

            {/* Pattern Matching */}
            <StaggerReveal className="group">
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
            </StaggerReveal>
          </div>
        </div>
      </section>

      {/* ========== TOOLS - Value props with real content ========== */}
      <section id="tools" className="relative py-32 px-6 scroll-mt-24 bg-slate-50/50 min-h-screen snap-start flex flex-col justify-center">
        <div className="max-w-5xl mx-auto space-y-32">
          {/* Scanner showcase */}
          <RevealSection>
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
          </RevealSection>

          {/* Dilution showcase */}
          <RevealSection>
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
          </RevealSection>
        </div>
      </section>

      {/* ========== SOLUTIONS - Use Cases ========== */}
      <section id="solutions" className="relative py-32 px-6 border-t border-slate-200 scroll-mt-24 min-h-screen snap-start flex flex-col justify-center">
        <div className="max-w-5xl mx-auto">
          <RevealSection className="text-center mb-16">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">Use cases</span>
            <h2 className="text-3xl font-bold text-slate-900 mb-4">For different strategies</h2>
          </RevealSection>

          <div className="grid md:grid-cols-3 gap-4">
            {[
              { title: 'Intraday', desc: 'Real-time scanners, momentum alerts, low latency data.', icon: Zap, color: 'blue' },
              { title: 'Small Caps', desc: 'Dilution tracking, SEC filings, float analysis.', icon: Target, color: 'amber' },
              { title: 'Swing & Position', desc: 'Financials, valuations, pattern recognition.', icon: BarChart3, color: 'violet' },
            ].map((item, i) => (
              <StaggerReveal key={item.title}>
                <div className="p-5 rounded-xl bg-white border border-slate-200 hover:border-slate-300 hover:shadow-lg transition-all h-full">
                  <item.icon className={`w-5 h-5 text-${item.color}-600 mb-3`} />
                  <h3 className="text-base font-semibold text-slate-900 mb-1">{item.title}</h3>
                  <p className="text-sm text-slate-500">{item.desc}</p>
                </div>
              </StaggerReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ========== Final CTA ========== */}
      <section className="relative py-32 px-6 bg-gradient-to-br from-slate-100 to-white border-t border-slate-200 min-h-screen snap-start flex flex-col justify-center">
        <RevealSection className="max-w-2xl mx-auto text-center">
          <h2 className="text-4xl sm:text-5xl font-bold text-slate-900 mb-6">
            {t('landing.cta.title')}
          </h2>
          <p className="text-lg text-slate-500 mb-10">
            {t('landing.cta.subtitle')}
          </p>
          <SignedOut>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setAuthPanel('signup')}
              className="px-10 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all flex items-center gap-2 mx-auto shadow-lg shadow-slate-900/20"
            >
              {t('landing.cta.button')} <ArrowRight className="w-5 h-5" />
            </motion.button>
          </SignedOut>
          <SignedIn>
            <Link href="/workspace" className="inline-flex px-10 py-4 rounded-xl bg-slate-900 text-white font-semibold text-lg hover:bg-slate-800 transition-all items-center gap-2 shadow-lg shadow-slate-900/20">
              {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-5 h-5" />
            </Link>
          </SignedIn>
          <p className="mt-6 text-sm text-slate-400">{t('landing.cta.note')}</p>
        </RevealSection>
      </section>

      {/* ========== RESOURCES - Footer ========== */}
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
