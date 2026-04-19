'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { SignIn, SignUp, SignedIn, SignedOut } from '@clerk/nextjs';
import { ArrowRight, X, Zap, Newspaper, BarChart3, Shield, SlidersHorizontal, LineChart, Bell, Target, Layers, Star, ExternalLink, Link2 } from 'lucide-react';
import { useAppTranslation } from '@/hooks/useAppTranslation';
import { motion, useScroll, useTransform, useSpring, MotionValue, AnimatePresence } from 'framer-motion';
import { DashboardHero } from '@/components/landing/DashboardHero';
import { useTopMovers, type TopMover } from '@/hooks/useTopMovers';

type AuthPanel = 'closed' | 'signin' | 'signup';

// ─── Tradeul wordmark — calco del logo oficial (texto en bold + barra azul bajo la "t") ──
function TradeulWordmark({
  className = '',
  size = 'md',
  tone = 'dark',
}: {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  tone?: 'dark' | 'light';
}) {
  const sizeCls =
    size === 'sm' ? 'text-[17px]' :
    size === 'lg' ? 'text-[28px]' :
    'text-[20px]';
  const color = tone === 'light' ? 'text-white' : 'text-slate-900';
  return (
    <span className={`relative inline-flex items-baseline leading-none font-semibold tracking-[-0.035em] ${color} ${sizeCls} ${className}`}>
      <span>tradeul</span>
      <span
        aria-hidden
        className="absolute left-0 bottom-[-4px] h-[2.5px] rounded-full bg-[#2563eb]"
        style={{ width: '0.48em' }}
      />
    </span>
  );
}

// ─── Live scanner terminal para el hero ─────────────────────────────────────
const HERO_ROWS = [
  { rank: 1, sym: 'CLOV', price: 2.87,  chg: '+31.05%', rvol: '18.4x', vol5pct: '5640%', pos: '97%', float: '23M' },
  { rank: 2, sym: 'WOLF', price: 4.23,  chg: '+22.15%', rvol: '12.3x', vol5pct: '3821%', pos: '89%', float: '88M' },
  { rank: 3, sym: 'IONQ', price: 12.84, chg: '+18.92%', rvol: '8.7x',  vol5pct: '2104%', pos: '96%', float: '34M' },
  { rank: 4, sym: 'SMCI', price: 38.74, chg: '+15.23%', rvol: '6.8x',  vol5pct: '1842%', pos: '92%', float: '52M' },
  { rank: 5, sym: 'MSTR', price: 42.30, chg: '+8.67%',  rvol: '5.3x',  vol5pct: '1234%', pos: '91%', float: '45M' },
  { rank: 6, sym: 'PLTR', price: 32.15, chg: '+9.45%',  rvol: '2.9x',  vol5pct:  '621%', pos: '87%', float: '78M' },
  { rank: 7, sym: 'CAVA', price: 28.45, chg: '+5.44%',  rvol: '2.1x',  vol5pct:  '512%', pos: '85%', float: '67M' },
];

function HeroScannerTerminal() {
  const [flashSym, setFlashSym] = useState<string | null>(null);
  const [newBadge, setNewBadge] = useState(true);
  const [livePrices, setLivePrices] = useState<Record<string, number>>(
    Object.fromEntries(HERO_ROWS.map(r => [r.sym, r.price]))
  );

  useEffect(() => {
    const badgeTimer = setTimeout(() => setNewBadge(false), 2400);
    const interval = setInterval(() => {
      const row = HERO_ROWS[Math.floor(Math.random() * HERO_ROWS.length)];
      setFlashSym(row.sym);
      setLivePrices(prev => ({
        ...prev,
        [row.sym]: parseFloat((row.price * (1 + (Math.random() * 0.006 - 0.003))).toFixed(2)),
      }));
      setTimeout(() => setFlashSym(null), 420);
    }, 1100);
    return () => { clearInterval(interval); clearTimeout(badgeTimer); };
  }, []);

  return (
    <div className="relative w-full max-w-[540px]">
      {/* Glow halo behind window */}
      <div className="absolute -inset-10 pointer-events-none" style={{
        background: 'radial-gradient(ellipse 500px 400px at 55% 45%, rgba(59,130,246,0.18) 0%, transparent 70%)',
        filter: 'blur(8px)',
      }} />

      {/* Terminal window */}
      <div className="relative bg-[#080809] rounded-2xl border border-white/[0.07] shadow-[0_32px_80px_rgba(0,0,0,0.5)] overflow-hidden">

        {/* Title bar */}
        <div className="flex items-center gap-2 px-3 h-9 bg-[#0c0c0e] border-b border-white/[0.06]">
          {/* Traffic lights */}
          <div className="flex items-center gap-1.5 mr-1">
            <div className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <div className="w-3 h-3 rounded-full bg-[#febc2e]" />
            <div className="w-3 h-3 rounded-full bg-[#28c840]" />
          </div>
          {/* Title */}
          <div className="flex items-center gap-1.5 flex-1">
            <Star className="w-3 h-3 text-[#666]" />
            <span className="text-[11px] font-medium text-[#999] tracking-wide">Daily Breakout BF</span>
          </div>
          {/* Action icons */}
          <div className="flex items-center gap-2">
            <Link2 className="w-3 h-3 text-[#444] hover:text-[#777] transition-colors" />
            <SlidersHorizontal className="w-3 h-3 text-[#444] hover:text-[#777] transition-colors" />
            <ExternalLink className="w-3 h-3 text-[#444] hover:text-[#777] transition-colors" />
            <div className="flex items-center gap-1 ml-1">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[9px] text-emerald-500 font-semibold tracking-widest">LIVE</span>
            </div>
          </div>
        </div>

        {/* Column headers */}
        <div className="grid grid-cols-8 items-center px-3 py-1.5 border-b border-white/[0.04] bg-[#070709]">
          {['#', 'Sym', 'Price', 'Chg%', 'RVOL', '5m V%', 'Pos%', 'Float'].map((h, i) => (
            <span key={h} className={`text-[9px] font-semibold text-[#444] uppercase tracking-widest
              ${i === 0 ? 'text-center' : i === 1 ? '' : 'text-right'}`}>
              {h}
            </span>
          ))}
        </div>

        {/* Rows */}
        <div>
          {HERO_ROWS.map((row, idx) => {
            const isFlash = flashSym === row.sym;
            const price = livePrices[row.sym] ?? row.price;
            const vol5Num = parseFloat(row.vol5pct);
            const posNum = parseFloat(row.pos);
            return (
              <div key={row.sym}
                className={`grid grid-cols-8 items-center px-3 py-1.5 transition-all duration-200 border-b border-white/[0.02]
                  ${isFlash ? 'bg-emerald-500/[0.08]' : idx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.008]'}`}>
                <span className="text-[9px] text-[#3a3a3a] text-center font-mono">{row.rank}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[11px] font-bold text-[#e8e8ed] font-mono">{row.sym}</span>
                  {idx === 0 && newBadge && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-[7px] font-bold text-emerald-400 bg-emerald-500/20 px-1 py-0.5 rounded-sm leading-none"
                    >
                      NEW
                    </motion.span>
                  )}
                </div>
                <span className={`text-[10px] font-mono text-right transition-colors duration-200 ${isFlash ? 'text-emerald-300' : 'text-[#c8c8d0]'}`}>
                  {price.toFixed(2)}
                </span>
                <span className="text-[10px] font-mono text-right text-emerald-500">{row.chg}</span>
                <span className="text-[10px] font-mono text-right text-blue-400">{row.rvol}</span>
                <span className={`text-[10px] font-mono text-right ${vol5Num > 2000 ? 'text-amber-400' : vol5Num > 1000 ? 'text-amber-500/80' : 'text-[#c8c8d0]'}`}>
                  {row.vol5pct}
                </span>
                <span className={`text-[10px] font-mono text-right ${posNum >= 95 ? 'text-emerald-400' : posNum >= 90 ? 'text-emerald-500/80' : 'text-[#c8c8d0]'}`}>
                  {row.pos}
                </span>
                <span className="text-[10px] font-mono text-right text-[#555]">{row.float}</span>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-3 py-2 bg-[#070709] border-t border-white/[0.04]">
          <span className="text-[9px] text-[#3a3a3a]">7 results · min_rvol: 2x · float &lt; 100M</span>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[9px] font-mono text-[#444]">09:32:41 ET</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Marquee ticker ribbon ───────────────────────────────────────────────────
// Fallback estático (pre-market / backend caído). Se usa únicamente si el
// endpoint público no responde. En condiciones normales se pintan los top
// movers reales del snapshot de Redis.
const MARQUEE_FALLBACK: TopMover[] = [
  { symbol: 'NVDA',  price: null, change_percent: 2.14,  volume: null },
  { symbol: 'AAPL',  price: null, change_percent: 0.92,  volume: null },
  { symbol: 'MSFT',  price: null, change_percent: 1.33,  volume: null },
  { symbol: 'TSLA',  price: null, change_percent: -1.85, volume: null },
  { symbol: 'AMD',   price: null, change_percent: 1.72,  volume: null },
  { symbol: 'META',  price: null, change_percent: 0.64,  volume: null },
  { symbol: 'GOOGL', price: null, change_percent: 0.41,  volume: null },
  { symbol: 'AMZN',  price: null, change_percent: -0.52, volume: null },
  { symbol: 'COIN',  price: null, change_percent: 3.10,  volume: null },
  { symbol: 'MSTR',  price: null, change_percent: 2.48,  volume: null },
  { symbol: 'PLTR',  price: null, change_percent: 1.95,  volume: null },
  { symbol: 'SMCI',  price: null, change_percent: -2.21, volume: null },
];

function formatPct(pct: number | null): string {
  if (pct === null || Number.isNaN(pct)) return '';
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function formatPrice(price: number | null): string {
  if (price === null || Number.isNaN(price)) return '';
  if (price >= 1000) return price.toFixed(0);
  if (price >= 100) return price.toFixed(1);
  return price.toFixed(2);
}

function TickerMarquee() {
  const { tickers, loading, error } = useTopMovers({
    limit: 24,
    mix: 'balanced',
    refreshMs: 5000,
  });

  const showing = tickers.length > 0 ? tickers : MARQUEE_FALLBACK;
  const isLive = !loading && !error && tickers.length > 0;
  // Duplicamos para que el loop visual sea perfecto
  const doubled = [...showing, ...showing];

  return (
    <div className="relative overflow-hidden border-y border-slate-200/60 bg-white/70 backdrop-blur-sm py-2">
      {/* Badge LIVE / DELAYED — micro-chip para dar contexto al usuario profesional */}
      <div className="absolute left-3 top-1/2 -translate-y-1/2 z-10 flex items-center gap-1.5 pr-3 bg-white/95 backdrop-blur border-r border-slate-200/70">
        <span className={`w-1.5 h-1.5 rounded-full ${isLive ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
        <span className="text-[9px] font-semibold tracking-[0.12em] uppercase text-slate-600">
          {isLive ? 'Live' : 'Delayed'}
        </span>
      </div>

      <motion.div
        animate={{ x: ['0%', '-50%'] }}
        transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
        className="flex items-center whitespace-nowrap pl-20"
        style={{ willChange: 'transform' }}
      >
        {doubled.map((t, i) => {
          const pct = t.change_percent ?? 0;
          const up = pct >= 0;
          const priceText = formatPrice(t.price);
          return (
            <div key={`${t.symbol}-${i}`} className="flex items-center gap-1.5 px-4">
              <span className="font-mono font-bold text-slate-800 text-xs tracking-wide">
                {t.symbol}
              </span>
              {priceText && (
                <span className="font-mono text-[11px] text-slate-500">{priceText}</span>
              )}
              <span className={`font-mono text-xs font-medium ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
                {formatPct(t.change_percent)}
              </span>
              <span className="text-slate-300 text-[10px] pl-3">·</span>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}

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

// ─── Editorial Modules (light bg, dark product windows inside) ──────────────

// ─── Hero components ────────────────────────────────────────────────────────

// Market-open pill badge: shows live NYSE clock + session status
function MarketStatusPill() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const iv = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(iv);
  }, []);

  const etHour = (now.getUTCHours() - 4 + 24) % 24;
  const etMin = now.getUTCMinutes();
  const etSec = now.getUTCSeconds();
  const minutesSinceMidnight = etHour * 60 + etMin;
  const isWeekday = now.getUTCDay() >= 1 && now.getUTCDay() <= 5;
  const isOpen = isWeekday && minutesSinceMidnight >= 9 * 60 + 30 && minutesSinceMidnight < 16 * 60;
  const isPreMarket = isWeekday && minutesSinceMidnight >= 4 * 60 && minutesSinceMidnight < 9 * 60 + 30;
  const isAfterHours = isWeekday && minutesSinceMidnight >= 16 * 60 && minutesSinceMidnight < 20 * 60;

  const label = isOpen ? 'Market open' : isPreMarket ? 'Pre-market' : isAfterHours ? 'After-hours' : 'Market closed';
  const dot = isOpen ? 'bg-emerald-500' : isPreMarket ? 'bg-amber-500' : isAfterHours ? 'bg-violet-500' : 'bg-slate-400';
  const text = isOpen ? 'text-emerald-700' : isPreMarket ? 'text-amber-700' : isAfterHours ? 'text-violet-700' : 'text-slate-500';
  const timeStr = `${String(etHour).padStart(2, '0')}:${String(etMin).padStart(2, '0')}:${String(etSec).padStart(2, '0')}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="inline-flex items-center gap-2.5 mb-7 pl-2 pr-3.5 py-1.5 rounded-full border border-slate-200/80 bg-white/70 backdrop-blur shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
    >
      <span className="relative flex items-center" aria-hidden>
        {isOpen && <span className={`absolute inline-flex h-2 w-2 rounded-full ${dot} opacity-70 animate-ping`} />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      <span className={`text-[11px] font-semibold tracking-[0.08em] uppercase ${text}`}>{label}</span>
      <span className="w-px h-3 bg-slate-200" />
      <span className="text-[11px] font-mono tabular-nums text-slate-500">{timeStr}</span>
      <span className="text-[10px] font-medium text-slate-400 tracking-wider">ET</span>
      <span className="w-px h-3 bg-slate-200" />
      <span className="text-[10.5px] font-semibold text-slate-600 tracking-[0.12em] uppercase">NYSE · NASDAQ</span>
    </motion.div>
  );
}

// Tiny sparkline showing rolling latency (p50/p99 reference)
function LatencySparkline() {
  const [bars, setBars] = useState<number[]>(() =>
    Array.from({ length: 18 }, () => Math.random() * 0.6 + 0.2)
  );
  useEffect(() => {
    const iv = setInterval(() => {
      setBars(prev => [...prev.slice(1), Math.random() * 0.7 + 0.15]);
    }, 700);
    return () => clearInterval(iv);
  }, []);
  return (
    <svg width="64" height="20" viewBox="0 0 64 20" className="opacity-60" aria-hidden>
      {bars.map((v, i) => (
        <rect
          key={i}
          x={i * 3.4}
          y={20 - v * 20}
          width={2.2}
          height={v * 20}
          fill={v > 0.75 ? '#f59e0b' : v > 0.55 ? '#60a5fa' : '#94a3b8'}
          rx={0.8}
        />
      ))}
    </svg>
  );
}

// Odometer-style rolling number
function OdometerNumber({ value, duration = 1.6 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / (duration * 1000));
          const eased = 1 - Math.pow(1 - t, 3);
          setDisplay(Math.floor(eased * value));
          if (t < 1) requestAnimationFrame(tick);
          else setDisplay(value);
        };
        requestAnimationFrame(tick);
        io.disconnect();
      }
    }, { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, [value, duration]);
  return <span ref={ref} className="tabular-nums">{display.toLocaleString()}</span>;
}

// Real chrome wrappers — EXACT copy from FloatingWindow.tsx / MarketTableLayout.tsx
// Used by the landing page so users see the same UI they'll get in the app.

// FloatingWindowChrome — calco de FloatingWindow.tsx title bar
// Usage: AI Agent, OpenUL, Chart (generic windows without live table chrome)
function ModuleFloatingChrome({ title, extra }: { title: string; extra?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-2 py-1 bg-[#111111] border-b border-[#1d1d1f] cursor-move select-none flex-shrink-0">
      <div className="flex items-center gap-1 flex-1 min-w-0">
        {extra && <div className="flex items-center mr-1">{extra}</div>}
        <h3 className="text-[11px] font-medium text-[#e8e8ed] truncate">{title}</h3>
      </div>
      <div className="flex items-center gap-0.5 ml-2">
        <button className="p-0.5 rounded hover:bg-[#2563eb]/10 transition-colors group">
          <ExternalLink className="w-3 h-3 text-[#515154] group-hover:text-[#2563eb]" />
        </button>
        <button className="p-0.5 rounded hover:bg-[#ef4444]/10 transition-colors group">
          <X className="w-3 h-3 text-[#515154] group-hover:text-[#ef4444]" />
        </button>
      </div>
    </div>
  );
}

// MarketTableLayoutHeader — calco exacto de MarketTableLayout.tsx
// Usage: Scanner tables, Bull Flag, any window with a "live" ticker count / stream
function ModuleTableHeader({
  title, showLive = true, dotColor = 'emerald', extra,
}: {
  title: string; showLive?: boolean; dotColor?: 'emerald' | 'amber' | 'rose' | 'violet';
  extra?: React.ReactNode;
}) {
  const dotMap: Record<string, string> = {
    emerald: 'bg-emerald-500', amber: 'bg-amber-400', rose: 'bg-rose-500', violet: 'bg-violet-400',
  };
  const textMap: Record<string, string> = {
    emerald: 'text-emerald-600', amber: 'text-amber-500', rose: 'text-rose-500', violet: 'text-violet-400',
  };
  return (
    <div className="flex items-center justify-between px-2 py-1 bg-[#0d0d0d] border-b border-[#1d1d1f] cursor-move select-none flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <h2 className="text-[11px] font-semibold text-[#e8e8ed] truncate">{title}</h2>
        {showLive && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <div className={`w-1.5 h-1.5 rounded-full ${dotMap[dotColor]}`} />
            <span className={`text-[10px] font-medium ${textMap[dotColor]}`}>Live</span>
          </div>
        )}
        {extra && <div className="flex items-center gap-2 flex-shrink-0">{extra}</div>}
      </div>
      <div className="flex items-center gap-0.5 flex-shrink-0">
        {/* LinkGroupSelector — chain icon */}
        <button className="p-0.5 rounded hover:bg-[#111111] transition-colors flex items-center" title="Link group">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6.5 8.5h3M9.5 6H11a2.5 2.5 0 0 1 0 5H9.5M6.5 11H5a2.5 2.5 0 0 1 0-5h1.5"
              stroke="#515154" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button className="p-0.5 rounded hover:bg-[#2563eb]/10 transition-colors group">
          <ExternalLink className="w-3 h-3 text-[#515154] group-hover:text-[#2563eb]" />
        </button>
        <button className="p-0.5 rounded hover:bg-[#111111] transition-colors">
          <SlidersHorizontal className="w-3 h-3 text-[#515154]" />
        </button>
        <button className="p-0.5 rounded hover:bg-[#ef4444]/10 transition-colors group">
          <X className="w-3 h-3 text-[#515154] group-hover:text-[#ef4444]" />
        </button>
      </div>
    </div>
  );
}

// Wrapper component: window shell with configurable chrome kind
function ProductWindow({
  kind = 'table', title, showLive = true, dotColor = 'emerald', extra, children, className = '',
}: {
  kind?: 'table' | 'floating';
  title: string;
  showLive?: boolean;
  dotColor?: 'emerald' | 'amber' | 'rose' | 'violet';
  extra?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`relative rounded-lg border border-[#1d1d1f] overflow-hidden bg-[#080808] shadow-[0_30px_80px_-20px_rgba(2,6,23,0.35),0_10px_30px_-10px_rgba(2,6,23,0.2)] flex flex-col ${className}`}>
      {kind === 'floating'
        ? <ModuleFloatingChrome title={title} extra={extra} />
        : <ModuleTableHeader title={title} showLive={showLive} dotColor={dotColor} extra={extra} />}
      <div className="bg-[#080808] flex-1 min-h-0 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}

// Scanner · CALCO de CategoryTableV2 + MarketTableLayout
// Columnas reales: # · Sym · Price · Chg% · Gap% · vs Open · Vol · RVOL
type ScannerRow = { rank: number; sym: string; price: string; chg: string; gap: string; vsOpen: string; vol: string; rvol: string };

const GAPPERS_UP_ROWS: ScannerRow[] = [
  { rank: 1,  sym: 'CLOV',  price: '2.87',   chg: '+31.05%', gap: '+24.12%', vsOpen: '+6.93%', vol: '412.1M', rvol: '18.4x' },
  { rank: 2,  sym: 'WOLF',  price: '4.23',   chg: '+22.15%', gap: '+17.44%', vsOpen: '+4.71%', vol: '234.5M', rvol: '12.3x' },
  { rank: 3,  sym: 'IONQ',  price: '12.84',  chg: '+18.92%', gap: '+14.33%', vsOpen: '+4.59%', vol: '45.6M',  rvol: '8.7x'  },
  { rank: 4,  sym: 'SMCI',  price: '38.74',  chg: '+15.23%', gap: '+11.67%', vsOpen: '+3.56%', vol: '89.4M',  rvol: '6.8x'  },
  { rank: 5,  sym: 'NVDA',  price: '912.40', chg: '+12.34%', gap: '+8.21%',  vsOpen: '+4.12%', vol: '124.5M', rvol: '4.2x'  },
  { rank: 6,  sym: 'PLTR',  price: '78.92',  chg: '+9.45%',  gap: '+6.12%',  vsOpen: '+3.33%', vol: '52.1M',  rvol: '2.9x'  },
  { rank: 7,  sym: 'MSTR',  price: '412.30', chg: '+8.67%',  gap: '+5.89%',  vsOpen: '+2.78%', vol: '28.4M',  rvol: '5.3x'  },
  { rank: 8,  sym: 'AMD',   price: '178.32', chg: '+7.81%',  gap: '+5.43%',  vsOpen: '+2.38%', vol: '67.3M',  rvol: '3.1x'  },
  { rank: 9,  sym: 'COIN',  price: '298.45', chg: '+6.23%',  gap: '+4.17%',  vsOpen: '+2.06%', vol: '33.7M',  rvol: '2.4x'  },
  { rank: 10, sym: 'CAVA',  price: '98.23',  chg: '+5.44%',  gap: '+3.21%',  vsOpen: '+2.23%', vol: '18.9M',  rvol: '2.1x'  },
];

const MOMENTUM_UP_ROWS: ScannerRow[] = [
  { rank: 1,  sym: 'AVGO',  price: '1842.55', chg: '+14.82%', gap: '+4.02%',  vsOpen: '+9.76%', vol: '38.2M',  rvol: '7.8x' },
  { rank: 2,  sym: 'TSM',   price: '198.44',  chg: '+11.64%', gap: '+3.11%',  vsOpen: '+7.89%', vol: '52.9M',  rvol: '5.4x' },
  { rank: 3,  sym: 'ARM',   price: '152.88',  chg: '+10.27%', gap: '+2.48%',  vsOpen: '+7.41%', vol: '41.5M',  rvol: '4.9x' },
  { rank: 4,  sym: 'TSLA',  price: '312.60',  chg: '+9.15%',  gap: '+3.82%',  vsOpen: '+5.14%', vol: '96.7M',  rvol: '3.7x' },
  { rank: 5,  sym: 'MRVL',  price: '88.42',   chg: '+8.73%',  gap: '+1.95%',  vsOpen: '+6.51%', vol: '28.3M',  rvol: '3.2x' },
  { rank: 6,  sym: 'NET',   price: '112.89',  chg: '+7.91%',  gap: '+2.04%',  vsOpen: '+5.62%', vol: '21.4M',  rvol: '2.8x' },
  { rank: 7,  sym: 'SNOW',  price: '176.28',  chg: '+7.22%',  gap: '+1.87%',  vsOpen: '+5.08%', vol: '18.6M',  rvol: '2.6x' },
  { rank: 8,  sym: 'CRWD',  price: '362.41',  chg: '+6.84%',  gap: '+2.11%',  vsOpen: '+4.42%', vol: '14.9M',  rvol: '2.4x' },
  { rank: 9,  sym: 'NOW',   price: '988.16',  chg: '+6.12%',  gap: '+1.54%',  vsOpen: '+4.32%', vol: '8.7M',   rvol: '2.1x' },
  { rank: 10, sym: 'ANET',  price: '412.77',  chg: '+5.48%',  gap: '+1.22%',  vsOpen: '+4.07%', vol: '12.3M',  rvol: '1.9x' },
];

function ScannerMock({
  title,
  rows,
  sortKey = 'Chg%',
}: {
  title: string;
  rows: ScannerRow[];
  sortKey?: 'Chg%' | 'Gap%' | 'vs Open' | 'Vol' | 'RVOL';
}) {
  const [flashRank, setFlashRank] = useState<number | null>(null);

  useEffect(() => {
    const iv = setInterval(() => {
      setFlashRank(Math.floor(Math.random() * rows.length) + 1);
      setTimeout(() => setFlashRank(null), 500);
    }, 1500);
    return () => clearInterval(iv);
  }, [rows.length]);

  const cols = [
    { label: '#',       w: '22px', align: 'center' as const },
    { label: 'Sym',     w: '54px', align: 'left'   as const },
    { label: 'Price',   w: '62px', align: 'right'  as const },
    { label: 'Chg%',    w: '60px', align: 'right'  as const },
    { label: 'Gap%',    w: '56px', align: 'right'  as const },
    { label: 'vs Open', w: '58px', align: 'right'  as const },
    { label: 'Vol',     w: '60px', align: 'right'  as const },
    { label: 'RVOL',    w: '44px', align: 'right'  as const },
  ].map((c) => ({ ...c, sorted: c.label === sortKey }));

  return (
    <ProductWindow kind="table" title={title} dotColor="emerald"
      extra={<span className="text-[9px] font-mono text-[#86868b] tabular-nums">{rows.length}</span>}>
      <div className="flex items-center px-2 h-[22px] border-b border-[#1d1d1f] bg-[#080808]">
        {cols.map((col) => (
          <div key={col.label}
            className={`flex items-center gap-0.5 text-[10px] font-medium select-none flex-shrink-0 ${col.sorted ? 'text-[#e8e8ed]' : 'text-[#515154]'}`}
            style={{ width: col.w, justifyContent: col.align === 'right' ? 'flex-end' : col.align === 'center' ? 'center' : 'flex-start' }}>
            {col.label}
            {col.sorted && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M19 5l-7 7-7-7"/></svg>}
          </div>
        ))}
      </div>
      <div className="divide-y divide-[#0d0d0d]">
        {rows.map((row) => {
          const flash = flashRank === row.rank;
          return (
            <div key={row.rank}
              className={`flex items-center px-2 h-[22px] transition-colors duration-500 ${flash ? 'bg-emerald-500/20' : 'hover:bg-[#111111]'}`}>
              <div className="text-[10px] font-medium text-[#515154] text-center flex-shrink-0" style={{ width: '22px' }}>{row.rank}</div>
              <div className="text-[11px] font-bold text-[#2563eb] flex-shrink-0" style={{ width: '54px' }}>{row.sym}</div>
              <div className="font-mono text-[10.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '62px' }}>{row.price}</div>
              <div className="font-mono font-semibold text-[10.5px] text-emerald-500 text-right flex-shrink-0" style={{ width: '60px' }}>{row.chg}</div>
              <div className="font-mono font-semibold text-[10.5px] text-emerald-500 text-right flex-shrink-0" style={{ width: '56px' }}>{row.gap}</div>
              <div className="font-mono font-semibold text-[10.5px] text-emerald-500 text-right flex-shrink-0" style={{ width: '58px' }}>{row.vsOpen}</div>
              <div className="font-mono text-[10.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '60px' }}>{row.vol}</div>
              <div className="font-mono font-semibold text-[10.5px] text-[#2563eb] text-right flex-shrink-0" style={{ width: '44px' }}>{row.rvol}</div>
            </div>
          );
        })}
      </div>
    </ProductWindow>
  );
}

// SEC Filings — CALCO fiel de SECFilingsContent.tsx
// Layout real: 2 filas de filtros + tabla (Ticker · Form · Description · Date · Time) + footer
function SECFilingsMock() {
  const allFilings = [
    { ticker: 'WOLF', form: 'S-3',   items: null,   desc: 'Shelf registration · $750M ATM · secondary offering',         date: 'Today', time: '09:42:13', color: 'rose',    zap: 'high' },
    { ticker: 'MARA', form: '8-K',   items: '1.01', desc: 'Entry into material definitive agreement · dilution warrants', date: 'Today', time: '09:38:27', color: 'rose',    zap: 'high' },
    { ticker: 'SMCI', form: 'S-3/A', items: null,   desc: 'Registration amendment · secondary offering',                  date: 'Today', time: '09:21:44', color: 'rose',    zap: 'med'  },
    { ticker: 'PLTR', form: '8-K',   items: '5.02', desc: 'Departure of directors or officers · CFO transition',         date: 'Today', time: '08:57:02', color: 'amber',   zap: 'med'  },
    { ticker: 'NVDA', form: '10-K',  items: null,   desc: 'Annual report for fiscal year 2024',                          date: 'Today', time: '08:12:55', color: 'blue',    zap: null   },
    { ticker: 'AMD',  form: '8-K',   items: '2.02', desc: 'Results of operations · Q3 earnings release',                  date: 'Today', time: '07:45:31', color: 'amber',   zap: 'low'  },
    { ticker: 'COIN', form: 'SC 13G',items: null,   desc: 'Beneficial ownership · Vanguard 6.8% → 7.2%',                 date: 'Today', time: '07:03:18', color: 'emerald', zap: null   },
    { ticker: 'CAVA', form: '10-Q',  items: null,   desc: 'Quarterly report · period ending Sep 2024',                    date: 'Yday',  time: '16:32:09', color: 'blue',    zap: null   },
    { ticker: 'IONQ', form: '424B5', items: null,   desc: 'Prospectus supplement · Series A convertible notes',          date: 'Yday',  time: '16:18:42', color: 'rose',    zap: 'high' },
    { ticker: 'MSTR', form: 'Form 4',items: null,   desc: 'Statement of beneficial ownership · Saylor buy 2,300 shares', date: 'Yday',  time: '15:47:21', color: 'violet',  zap: null   },
  ];
  // Simulate new filings arriving — rotate first rows
  const [tickIdx, setTickIdx] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setTickIdx(i => i + 1), 3000);
    return () => clearInterval(iv);
  }, []);
  const newRowIdx = tickIdx % allFilings.length;

  const colorMap: Record<string, string> = {
    rose:    'bg-rose-500/15 text-rose-400 border-rose-500/30',
    amber:   'bg-amber-500/15 text-amber-400 border-amber-500/30',
    blue:    'bg-blue-500/15 text-blue-400 border-blue-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    violet:  'bg-violet-500/15 text-violet-400 border-violet-500/30',
  };
  const zapColor: Record<string, string> = {
    high: 'text-rose-400',
    med:  'text-amber-400',
    low:  'text-blue-400',
  };

  const [activeQF, setActiveQF] = useState('all');
  const quickFilters = [
    { key: 'all',       label: 'All' },
    { key: 'earnings',  label: 'Earnings' },
    { key: 'mna',       label: 'M&A' },
    { key: 'dilution',  label: 'Dilution' },
    { key: 'guidance',  label: 'Guidance' },
    { key: 'insider',   label: 'Insider' },
  ];

  return (
    <ProductWindow kind="table" title="SEC Filings" dotColor="emerald"
      extra={<span className="text-[9px] font-mono text-[#86868b] tabular-nums">{allFilings.length}</span>}>
      {/* Row 1: Ticker search + date range + count + Clear */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#1d1d1f] bg-[#0a0a0a]">
        <div className="flex items-center gap-1">
          <div className="w-20 px-2 py-0.5 text-[10px] border border-[#1d1d1f] rounded bg-[#0d0d0d] text-[#86868b]">Ticker</div>
          <button className="px-2 py-0.5 text-[10px] font-medium bg-[#2563eb] text-white rounded">Go</button>
        </div>
        <span className="text-[#515154]">|</span>
        <div className="flex items-center gap-1 text-[10px]">
          <div className="w-[90px] px-1.5 py-0.5 text-[10px] border border-[#1d1d1f] rounded bg-[#0d0d0d] text-[#86868b] font-mono">2024-10-01</div>
          <span className="text-[#515154]">-</span>
          <div className="w-[90px] px-1.5 py-0.5 text-[10px] border border-[#1d1d1f] rounded bg-[#0d0d0d] text-[#86868b] font-mono">2024-10-24</div>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2 text-[10px] text-[#86868b]">
          <span className="tabular-nums font-medium">{allFilings.length}</span>
          <span className="text-emerald-600 flex items-center gap-1">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />3
          </span>
        </div>
      </div>
      {/* Row 2: Quick filters + More */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-[#1d1d1f] bg-[#080808]">
        {quickFilters.map(qf => (
          <button key={qf.key} onClick={() => setActiveQF(qf.key)}
            className={`px-2 py-0.5 text-[10px] rounded border transition-colors ${
              activeQF === qf.key
                ? 'bg-[#2563eb] text-white border-[#2563eb]'
                : 'text-[#86868b] border-[#1d1d1f] hover:border-[#2d2d2f]'
            }`}>
            {qf.label}
          </button>
        ))}
        <div className="flex-1" />
        <button className="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded border text-[#86868b] border-[#1d1d1f] hover:border-[#2d2d2f]">
          <SlidersHorizontal className="w-3 h-3" />More
        </button>
      </div>
      {/* Table header */}
      <div className="flex items-center px-3 py-1.5 border-b border-[#1d1d1f] bg-[#0a0a0a] text-[9px] font-semibold text-[#515154] uppercase tracking-wider">
        <div style={{ width: '44px' }}>Ticker</div>
        <div style={{ width: '60px' }}>Form</div>
        <div className="flex-1">Description</div>
        <div style={{ width: '56px' }} className="text-right">Date</div>
        <div style={{ width: '56px' }} className="text-right">Time</div>
      </div>
      {/* Rows */}
      <div className="divide-y divide-[#0d0d0d]">
        <AnimatePresence initial={false}>
          {allFilings.map((f, i) => {
            const isNew = i === newRowIdx;
            return (
              <motion.div key={`${f.ticker}-${f.time}`}
                layout
                initial={false}
                animate={{ backgroundColor: isNew ? 'rgba(16,185,129,0.10)' : 'rgba(16,185,129,0)' }}
                transition={{ duration: 0.8 }}
                className="flex items-center px-3 py-1 text-[11px] hover:bg-[#111111] cursor-pointer">
                <div style={{ width: '44px' }} className="font-medium text-[#e8e8ed]">{f.ticker}</div>
                <div style={{ width: '60px' }}>
                  <span className={`inline-block px-1.5 py-0.5 text-[9.5px] rounded border ${colorMap[f.color]}`}>{f.form}</span>
                </div>
                <div className="flex-1 flex items-center gap-1.5 min-w-0">
                  {f.zap && (
                    <span className={`flex-shrink-0 ${zapColor[f.zap]}`}>
                      <Zap className="w-3 h-3" />
                    </span>
                  )}
                  <span className="text-[#c7c7cc] truncate">
                    {f.items && <span className="text-[#86868b] mr-1">[{f.items}]</span>}
                    {f.desc}
                  </span>
                </div>
                <div style={{ width: '56px' }} className="text-right text-[#86868b] font-mono tabular-nums">{f.date}</div>
                <div style={{ width: '56px' }} className="text-right text-[#86868b] font-mono tabular-nums">{f.time}</div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
      {/* Footer */}
      <div className="flex items-center justify-between px-3 py-1 border-t border-[#1d1d1f] bg-[#0a0a0a] text-[9.5px] text-[#86868b]">
        <div className="flex items-center gap-2">
          <span className="tabular-nums">24,317 total</span>
          <span className="text-[#515154]">|</span>
          <span>Page 1 of 487</span>
        </div>
        <div className="flex items-center gap-1 font-mono">
          {['<<', '<', '>', '>>'].map(b => (
            <button key={b} className="w-5 h-5 rounded hover:bg-[#111111] text-[#86868b] flex items-center justify-center">{b}</button>
          ))}
        </div>
      </div>
    </ProductWindow>
  );
}

// Pattern Matching — CALCO fiel de PatternMatchingContent.tsx
// Layout real: search bar (ticker + date + time + mode toggle + settings + Search) +
// pizarra con header · probability bar · stats row · chart con forecast band
function PatternMatchingMock() {
  // Forecast real: mean_trajectory + std_trajectory + neighbors (line chart)
  // Query window (pattern_prices) + forecast continuing from t₀
  const patternPrices = [100, 100.8, 101.4, 101.1, 102.0, 102.7, 103.5, 103.2, 104.1, 105.0, 105.8, 106.5, 107.2];
  const forecastMean = [107.2, 107.8, 108.3, 108.9, 109.4, 110.0, 110.4, 110.9, 111.3, 111.8, 112.2];
  const forecastStd  = [0, 0.5, 0.9, 1.3, 1.6, 1.9, 2.2, 2.4, 2.7, 2.9, 3.1];
  // Neighbors: 50 lines faded (sample first 15 for performance)
  const neighbors = Array.from({ length: 15 }, (_, k) => {
    const offset = (Math.random() - 0.5) * 1.5;
    return forecastMean.map((v, i) => v + offset + (Math.random() - 0.5) * (1 + i * 0.2));
  });

  const W = 600, H = 110;
  const all = [...patternPrices, ...forecastMean];
  const minY = Math.min(...all, ...forecastMean.map((m, i) => m - forecastStd[i] * 2)) - 1;
  const maxY = Math.max(...all, ...forecastMean.map((m, i) => m + forecastStd[i] * 2)) + 1;
  const rangeY = maxY - minY;
  const totalX = patternPrices.length + forecastMean.length - 1;
  const xAt = (i: number, tot: number = totalX) => (i / (tot - 1)) * W;
  const yAt = (v: number) => H - ((v - minY) / rangeY) * H;

  const patternPath = patternPrices.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i)} ${yAt(v)}`).join(' ');
  const forecastPath = forecastMean.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xAt(patternPrices.length - 1 + i)} ${yAt(v)}`).join(' ');
  const bandPath = `${forecastMean.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xAt(patternPrices.length - 1 + i)} ${yAt(v + forecastStd[i])}`).join(' ')} L ${forecastMean.map((v, i) => `${xAt(patternPrices.length - 1 + forecastMean.length - 1 - i)} ${yAt(forecastMean[forecastMean.length - 1 - i] - forecastStd[forecastStd.length - 1 - i])}`).join(' L ')} Z`;

  const probUp = 72;
  const probDown = 28;

  return (
    <ProductWindow kind="floating" title="Pattern Matching">
      {/* Search Bar — calco fiel de PatternMatchingContent */}
      <div className="flex-shrink-0 px-4 py-2.5 border-b border-[#1d1d1f] bg-[#0a0a0a]">
        <div className="flex gap-2 items-center">
          <div className="flex-1 min-w-0">
            <div className="px-2 py-1 bg-[#111111] border border-[#1d1d1f] rounded text-[11px] text-[#e8e8ed] font-mono">NVDA</div>
          </div>
          <div className="flex items-center gap-1 text-[10px] text-[#86868b] font-mono">
            <span>2024-10-24</span>
            <span className="text-[#515154]">@</span>
            <span>15:00</span>
          </div>
          <div className="flex items-center gap-1 text-[9px] text-[#86868b]">
            <button className="px-1.5 py-0.5 rounded bg-[#1d1d1f] text-[#e8e8ed]">live</button>
            <span className="text-[#515154]">|</span>
            <button className="px-1.5 py-0.5 rounded hover:text-[#e8e8ed]">hist</button>
            <span className="text-[#515154]">|</span>
            <button className="px-1.5 py-0.5 rounded hover:text-[#e8e8ed]">chart</button>
          </div>
          <button className="p-1 rounded border border-[#1d1d1f] text-[#86868b]">
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
          <button className="px-2.5 py-1 rounded bg-[#2563eb] text-white font-medium text-[11px] flex items-center gap-1">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            Search
          </button>
        </div>
      </div>

      {/* Body: 2 columnas en lg (stats izq · chart der) para aprovechar el ancho */}
      <div className="p-3.5 grid lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)] gap-5 lg:gap-6">
        {/* ── Col izquierda: header + prob + stats + footer ─────────────── */}
        <div className="flex flex-col gap-3.5 min-w-0">
          <div className="flex items-baseline justify-between">
            <div className="flex items-baseline gap-2.5">
              <span className="text-lg font-semibold text-[#e8e8ed]">NVDA</span>
              <span className="text-[11px] text-[#86868b] font-mono">2024-10-24</span>
            </div>
            <span className="text-[10px] text-[#86868b] font-mono tabular-nums">1.2ms · 50 matches</span>
          </div>

          {/* Probability bar */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5 text-emerald-500 text-[12px]">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                <span className="font-semibold">{probUp}%</span>
                <span className="text-[#86868b] font-normal">bullish</span>
              </div>
              <div className="flex items-center gap-1.5 text-rose-500 text-[12px]">
                <span className="text-[#86868b] font-normal">bearish</span>
                <span className="font-semibold">{probDown}%</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>
              </div>
            </div>
            <div className="h-2 rounded-full overflow-hidden bg-[#111111] flex">
              <motion.div className="bg-emerald-500" initial={{ width: 0 }} whileInView={{ width: `${probUp}%` }} viewport={{ once: true }} transition={{ duration: 0.8 }} />
              <motion.div className="bg-rose-500" initial={{ width: 0 }} whileInView={{ width: `${probDown}%` }} viewport={{ once: true }} transition={{ duration: 0.8, delay: 0.2 }} />
            </div>
          </div>

          {/* Stats grid — 2 filas de 3 cols, compacto en vez de apilar */}
          <div className="grid grid-cols-3 gap-x-4 gap-y-1.5 text-[11px]">
            <div><span className="text-[#86868b]">Mean</span><span className="ml-1.5 font-mono font-semibold text-emerald-500">+4.72%</span></div>
            <div><span className="text-[#86868b]">Median</span><span className="ml-1.5 font-mono font-semibold text-emerald-500">+4.12%</span></div>
            <div><span className="text-[#86868b]">Conf.</span><span className="ml-1.5 font-semibold text-emerald-500">high</span></div>
            <div><span className="text-[#86868b]">Best</span><span className="ml-1.5 font-mono font-semibold text-emerald-500">+11.34%</span></div>
            <div><span className="text-[#86868b]">Worst</span><span className="ml-1.5 font-mono font-semibold text-rose-500">-3.21%</span></div>
            <div><span className="text-[#86868b]">Neighb.</span><span className="ml-1.5 font-mono font-semibold text-[#e8e8ed]">50</span></div>
          </div>

          {/* Footer info al fondo de la columna izquierda */}
          <div className="mt-auto flex items-center justify-between pt-2 border-t border-[#1d1d1f] text-[10px] text-[#86868b]">
            <span>k=50 · 45min · same ticker</span>
            <span className="font-mono tabular-nums">361.2M vectors</span>
          </div>
        </div>

        {/* ── Col derecha: chart ─────────────────────────────────────────── */}
        <div className="min-w-0 flex flex-col">
          <div className="flex items-center gap-4 justify-end mb-2 text-[10px] text-[#86868b]">
            <span className="flex items-center gap-1.5"><span className="w-3 h-[2px] bg-[#2563eb]" /> Forecast</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-[2px] bg-violet-400/50" /> Neighbors</span>
          </div>
          <svg viewBox={`0 0 ${W} ${H + 20}`} className="w-full h-auto block" preserveAspectRatio="none" style={{ aspectRatio: `${W}/${H + 20}` }}>
            <defs>
              <linearGradient id="forecastBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563eb" stopOpacity="0.20" />
                <stop offset="100%" stopColor="#2563eb" stopOpacity="0.03" />
              </linearGradient>
            </defs>
            {/* Grid */}
            {[0.25, 0.5, 0.75].map(p => (
              <line key={p} x1={0} y1={H * p} x2={W} y2={H * p} stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />
            ))}
            {/* t₀ vertical line */}
            <line x1={xAt(patternPrices.length - 1)} y1={0} x2={xAt(patternPrices.length - 1)} y2={H}
              stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
            <text x={xAt(patternPrices.length - 1)} y={H + 14} textAnchor="middle" fontSize="9" fill="#86868b" fontFamily="monospace">t₀</text>

            {/* Neighbors (ghosted) */}
            {neighbors.map((line, k) => (
              <motion.path key={k}
                initial={{ pathLength: 0, opacity: 0 }}
                whileInView={{ pathLength: 1, opacity: 0.18 }}
                viewport={{ once: true }}
                transition={{ delay: 0.1 + k * 0.04, duration: 0.9 }}
                d={line.map((v, j) => `${j === 0 ? 'M' : 'L'} ${xAt(patternPrices.length - 1 + j)} ${yAt(v)}`).join(' ')}
                fill="none" stroke="#a78bfa" strokeWidth="1" strokeLinecap="round"
              />
            ))}
            {/* Forecast band */}
            <path d={bandPath} fill="url(#forecastBand)" />
            {/* Forecast mean line */}
            <motion.path initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }}
              viewport={{ once: true }} transition={{ delay: 0.8, duration: 0.8 }}
              d={forecastPath} fill="none" stroke="#2563eb" strokeWidth="1.8" strokeDasharray="4 3" />
            {/* Pattern (query) line - solid */}
            <motion.path initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }}
              viewport={{ once: true }} transition={{ duration: 1 }}
              d={patternPath} fill="none" stroke="#e8e8ed" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            {/* Current dot */}
            <motion.circle initial={{ scale: 0 }} whileInView={{ scale: 1 }}
              viewport={{ once: true }} transition={{ delay: 1, duration: 0.3 }}
              cx={xAt(patternPrices.length - 1)} cy={yAt(patternPrices[patternPrices.length - 1])}
              r="3.5" fill="#e8e8ed" />
          </svg>
        </div>
      </div>
    </ProductWindow>
  );
}

// Market Pulse · CALCO fiel de MarketPulse.tsx
// Layout real: Header (Market Pulse · view switcher · cap filter · tickers · LiveDot · ts) +
// Tabs (Sectors/Industries/Themes) + ColumnHeaders + filas con DivBar
type PulseRow = { name: string; count: number; wtChg: number; spread: number; breadth: number; chg5d: number; hiVol: number };
const PULSE_SECTORS: PulseRow[] = [
  { name: 'Information Technology', count: 481, wtChg:  1.82, spread:  0.42, breadth: 0.78, chg5d:  4.31, hiVol: 12 },
  { name: 'Consumer Discretionary', count: 386, wtChg:  1.24, spread:  0.11, breadth: 0.71, chg5d:  3.82, hiVol:  9 },
  { name: 'Communication Svcs',    count: 114, wtChg:  0.92, spread:  0.33, breadth: 0.65, chg5d:  2.14, hiVol:  7 },
  { name: 'Financials',             count: 642, wtChg:  0.48, spread: -0.02, breadth: 0.58, chg5d:  1.22, hiVol:  4 },
  { name: 'Industrials',            count: 421, wtChg:  0.31, spread:  0.08, breadth: 0.54, chg5d:  0.82, hiVol:  3 },
  { name: 'Health Care',            count: 738, wtChg: -0.24, spread: -0.15, breadth: 0.42, chg5d: -0.41, hiVol:  2 },
  { name: 'Real Estate',            count: 186, wtChg: -0.58, spread: -0.22, breadth: 0.38, chg5d: -1.12, hiVol:  1 },
  { name: 'Energy',                 count: 298, wtChg: -1.24, spread: -0.42, breadth: 0.29, chg5d: -2.31, hiVol:  2 },
];

function PulseDivBar({ value, domain, label }: { value: number; domain: [number, number]; label: string }) {
  const mid = (domain[0] + domain[1]) / 2;
  const range = (domain[1] - domain[0]) / 2 || 1;
  const norm = Math.max(-1, Math.min(1, (value - mid) / range));
  const pct = Math.abs(norm) * 50;
  const pos = norm >= 0;
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0">
      <div className="relative flex-1 h-[12px] rounded-[3px] overflow-hidden bg-[#111111]">
        <div className="absolute top-0 left-1/2 h-full w-px bg-[#2d2d2f]" />
        <div
          className={`absolute top-0 bottom-0 rounded-[3px] ${pos ? 'left-1/2' : 'right-1/2'}`}
          style={{ width: `${pct}%`, backgroundColor: pos ? '#2563eb' : '#ec4899' }}
        />
      </div>
      <span className={`text-[10px] font-semibold font-mono tabular-nums w-[42px] text-right shrink-0 ${pos ? 'text-[#2563eb]' : 'text-pink-500'}`}>
        {label}
      </span>
    </div>
  );
}

function PulsePosBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0">
      <div className="relative flex-1 h-[12px] rounded-[3px] overflow-hidden bg-[#111111]">
        <div className="absolute top-0 bottom-0 left-0 rounded-[3px]" style={{ width: `${pct}%`, backgroundColor: '#2563eb' }} />
      </div>
      <span className="text-[10px] font-semibold font-mono tabular-nums w-[34px] text-right shrink-0 text-[#e8e8ed]">{label}</span>
    </div>
  );
}

function MarketPulseMock() {
  const [tab, setTab] = useState<'sectors' | 'industries' | 'themes'>('sectors');
  const [cap, setCap] = useState<'All' | '>300M' | '>2B' | '>10B'>('All');
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setTick(t => t + 1), 3000);
    return () => clearInterval(iv);
  }, []);
  const pulseOn = tick % 2 === 0;

  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const fmtPct1 = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  const fmtBreadth = (v: number) => `${Math.round(v * 100)}%`;

  return (
    <ProductWindow kind="table" title="Market Pulse" showLive={false}
      extra={
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="px-1.5 py-0.5 text-[9px] font-medium rounded bg-[#111111] text-[#86868b] border border-[#1d1d1f] flex items-center gap-1">
            Table
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M6 9l6 6 6-6" /></svg>
          </span>
        </div>
      }>
      {/* Sub-header: cap filter + total tickers + live dot + timestamp */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-[#1d1d1f] bg-[#0a0a0a] flex-shrink-0">
        <div className="flex bg-[#0d0d0d] rounded p-px gap-px border border-[#1d1d1f]">
          {(['All', '>300M', '>2B', '>10B'] as const).map(p => (
            <button key={p} onClick={() => setCap(p)}
              className={`px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors ${
                cap === p ? 'bg-[#111111] text-[#e8e8ed]' : 'text-[#86868b] hover:text-[#e8e8ed]'
              }`}>{p}</button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-[#86868b]">
          <span className="tabular-nums font-medium">8,412</span>
          <span className="relative flex items-center">
            <span className={`w-[5px] h-[5px] rounded-full transition-all ${pulseOn ? 'bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.7)]' : 'bg-emerald-500'}`} />
          </span>
          <span className="font-mono tabular-nums">15:42:18</span>
        </div>
      </div>
      {/* Tabs */}
      <div className="flex border-b border-[#1d1d1f] flex-shrink-0">
        {(['sectors', 'industries', 'themes'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-[10px] font-bold tracking-widest uppercase transition-colors ${
              tab === t ? 'text-[#2563eb] border-b-2 border-[#2563eb]' : 'text-[#86868b] hover:text-[#e8e8ed]'
            }`}>{t}</button>
        ))}
      </div>
      {/* Column headers */}
      <div className="flex items-center gap-2 pl-3 pr-2 py-1 border-b border-[#1d1d1f] bg-[#0d0d0d] flex-shrink-0">
        <div className="w-[118px] min-w-[118px] shrink-0 text-[9px] font-bold text-[#e8e8ed] uppercase tracking-wider">Sector</div>
        {['Wt.Chg', 'Sprd', 'Breadth', '5D', 'HiVol'].map((c, i) => (
          <div key={c} className={`flex-1 min-w-[56px] text-[9px] font-bold uppercase tracking-wider flex items-center gap-0.5 ${i === 0 ? 'text-[#2563eb]' : 'text-[#86868b]'}`}>
            {c}
            {i === 0 && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M19 5l-7 7-7-7"/></svg>}
          </div>
        ))}
      </div>
      {/* Rows */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {PULSE_SECTORS.map((r) => (
          <div key={r.name} className="flex items-center gap-2 pl-3 pr-2 h-[26px] border-b border-[#0d0d0d] hover:bg-[#111111] cursor-pointer">
            <div className="w-[118px] min-w-[118px] shrink-0 flex items-center gap-1">
              <span className="text-[10.5px] font-semibold text-[#e8e8ed] truncate">{r.name}</span>
              <span className="text-[9px] text-[#515154] font-mono tabular-nums shrink-0">{r.count}</span>
            </div>
            <div className="flex-1 min-w-[56px] flex items-center">
              <PulseDivBar value={r.wtChg} domain={[-2.5, 2.5]} label={fmtPct(r.wtChg)} />
            </div>
            <div className="flex-1 min-w-[56px] flex items-center">
              <PulseDivBar value={r.spread} domain={[-0.5, 0.5]} label={fmtPct(r.spread)} />
            </div>
            <div className="flex-1 min-w-[56px] flex items-center">
              <PulsePosBar value={r.breadth} label={fmtBreadth(r.breadth)} />
            </div>
            <div className="flex-1 min-w-[56px] flex items-center">
              <PulseDivBar value={r.chg5d} domain={[-5, 5]} label={fmtPct1(r.chg5d)} />
            </div>
            <div className="flex-1 min-w-[56px] flex items-center justify-end pr-1">
              <span className={`text-[10.5px] font-semibold font-mono tabular-nums ${r.hiVol >= 5 ? 'text-emerald-500' : 'text-[#86868b]'}`}>{r.hiVol}</span>
            </div>
          </div>
        ))}
      </div>
    </ProductWindow>
  );
}

// AI Agent — CALCO fiel de AIAgentContent.tsx
// Layout real: Header (History · Chat · Nueva sesión · Pipeline · ● Live) +
// Scrollable timeline (user message right · assistant response left) +
// Input bar (Quick actions · textarea · Enviar button)
function AIAgentMock() {
  const [phase, setPhase] = useState(0);
  const [typed, setTyped] = useState('');
  const userQuery = 'Top gainers today';

  useEffect(() => {
    const run = () => {
      setPhase(0);
      setTyped('');
      let i = 0;
      const typer = setInterval(() => {
        i++;
        setTyped(userQuery.slice(0, i));
        if (i >= userQuery.length) clearInterval(typer);
      }, 55);
      const timers = [
        setTimeout(() => setPhase(1), 1500),
        setTimeout(() => setPhase(2), 2500),
        setTimeout(() => setPhase(3), 3500),
        setTimeout(() => setPhase(4), 4500),
      ];
      return () => { clearInterval(typer); timers.forEach(clearTimeout); };
    };
    const cleanup = run();
    const restart = setInterval(run, 13000);
    return () => { cleanup(); clearInterval(restart); };
  }, []);

  const tableRows = [
    { sym: 'CLOV', name: 'Clover Health',       chg: '+31.05%', vol: '412.1M', rvol: '18.4x' },
    { sym: 'WOLF', name: 'Wolfspeed Inc',       chg: '+22.15%', vol: '234.5M', rvol: '12.3x' },
    { sym: 'IONQ', name: 'IonQ Inc',            chg: '+18.92%', vol: '45.6M',  rvol: '8.7x'  },
    { sym: 'SMCI', name: 'Super Micro',         chg: '+15.23%', vol: '89.4M',  rvol: '6.8x'  },
    { sym: 'NVDA', name: 'NVIDIA Corp',         chg: '+12.34%', vol: '124.5M', rvol: '4.2x'  },
  ];

  return (
    <ProductWindow kind="floating" title="AI Agent" className="h-[560px]">
      {/* Internal header — calco exacto de AIAgentContent.tsx */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-[#1d1d1f] bg-[#0a0a0a]/80 backdrop-blur-sm flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button className="p-1.5 rounded-lg text-[#86868b] hover:text-[#e8e8ed] hover:bg-[#111111] transition-all" title="Historial de conversaciones">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>
            </svg>
          </button>
          <span className="text-[12px] font-medium text-[#e8e8ed]">Chat</span>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <button className="text-[#86868b] hover:text-[#e8e8ed] transition-colors">Nueva sesión</button>
          <button className="text-[#86868b] hover:text-[#e8e8ed] transition-colors">Pipeline</button>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-[#86868b]">Live</span>
          </div>
        </div>
      </div>
      {/* Scrollable conversation canvas — calco del canvas central de AIAgentContent */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 bg-[#080808]">
        <div className="max-w-[780px] mx-auto space-y-3">
          {/* USER MESSAGE (right aligned) — calco ChatMessage user */}
          <div className="flex justify-end">
            <div className="bg-[#2563eb]/10 border border-[#2563eb]/25 text-[#e8e8ed] text-[13px] px-3.5 py-2 rounded-2xl rounded-tr-sm max-w-[80%]">
              {typed}
              {typed.length < userQuery.length && (
                <span className="inline-block w-[6px] h-[14px] bg-[#2563eb]/70 ml-0.5 align-middle animate-pulse" />
              )}
            </div>
          </div>

          {/* ASSISTANT MESSAGE — StepCard pipeline + ResultBlock data table */}
          {phase >= 1 && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex">
              <div className="bg-[#111111] border border-[#1d1d1f] text-[#c7c7cc] text-[13px] px-3.5 py-2.5 rounded-2xl rounded-tl-sm max-w-[82%] w-full">
                <div className="space-y-1.5 mb-3">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-emerald-500">✓</span>
                    <span className="text-[#c7c7cc]">Interpretando query · <span className="text-[#86868b]">clasificación: gainers</span></span>
                  </div>
                  {phase >= 2 && (
                    <motion.div initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2 text-[11px]">
                      <span className="text-emerald-500">✓</span>
                      <span>Generando SQL · <span className="text-[#86868b]">TimescaleDB scanner_ticks</span></span>
                    </motion.div>
                  )}
                  {phase >= 3 && (
                    <motion.div initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2 text-[11px]">
                      <span className="text-emerald-500">✓</span>
                      <span>Ejecutando · <span className="text-[#86868b]">{tableRows.length} resultados · 47ms</span></span>
                    </motion.div>
                  )}
                  {phase < 4 && (
                    <div className="flex items-center gap-2 text-[11px] text-[#86868b]">
                      <span className="w-2 h-2 rounded-full bg-[#2563eb] animate-pulse" />
                      <span>{phase < 3 ? 'Procesando…' : 'Formateando tabla…'}</span>
                    </div>
                  )}
                </div>

                {phase >= 4 && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
                    <div className="mb-2 text-[11px] text-[#86868b]">Top 5 gainers · octubre 24</div>
                    <div className="border border-[#1d1d1f] rounded-lg overflow-hidden bg-[#0a0a0a]">
                      <div className="flex items-center px-3 py-1.5 bg-[#080808] border-b border-[#1d1d1f] text-[9px] font-semibold text-[#515154] uppercase tracking-wider">
                        <div style={{ width: '50px' }}>Sym</div>
                        <div className="flex-1">Name</div>
                        <div style={{ width: '60px' }} className="text-right">Chg%</div>
                        <div style={{ width: '58px' }} className="text-right">Vol</div>
                        <div style={{ width: '46px' }} className="text-right">RVOL</div>
                      </div>
                      {tableRows.map((r, i) => (
                        <motion.div key={r.sym}
                          initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.06 }}
                          className="flex items-center px-3 py-1 text-[11px] border-b border-[#0d0d0d] last:border-b-0 hover:bg-[#111111]">
                          <div style={{ width: '50px' }} className="font-bold text-[#2563eb]">{r.sym}</div>
                          <div className="flex-1 text-[#c7c7cc] truncate">{r.name}</div>
                          <div style={{ width: '60px' }} className="text-right font-mono font-semibold text-emerald-500">{r.chg}</div>
                          <div style={{ width: '58px' }} className="text-right font-mono text-[#c7c7cc]">{r.vol}</div>
                          <div style={{ width: '46px' }} className="text-right font-mono font-semibold text-[#2563eb]">{r.rvol}</div>
                        </motion.div>
                      ))}
                    </div>
                    <div className="mt-2 text-[12px] text-[#c7c7cc] leading-relaxed">
                      Top 5 gainers de hoy. <span className="text-emerald-500 font-semibold">CLOV</span> lidera con +31% y RVOL 18.4×.
                      Pregunta por cualquier ticker para un análisis completo.
                    </div>
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Input bar — calco exacto AIAgentContent input section */}
      <div className="flex-shrink-0 border-t border-[#1d1d1f] bg-[#0a0a0a]/80 backdrop-blur-xl">
        <div className="px-5 py-2.5 max-w-[860px] mx-auto">
          <div className="flex items-center gap-1 mb-2 text-[11px] flex-wrap">
            {['Top Gainers', 'Sector Performance', 'Most Active', 'Gap Analysis'].map((a, i) => (
              <span key={a} className="flex items-center gap-1">
                {i > 0 && <span className="text-[#515154]">·</span>}
                <button className="text-[#86868b] hover:text-[#2563eb] transition-colors">{a}</button>
              </span>
            ))}
          </div>
          <div className="relative flex items-end gap-2">
            <div className="relative flex-1">
              <div className="w-full px-3.5 py-2.5 text-[13px] bg-[#111111] border border-[#1d1d1f] rounded-2xl text-[#515154]">
                Escribe tu consulta o / para comandos...
              </div>
            </div>
            <button className="flex-shrink-0 px-3.5 py-2.5 text-[12px] font-medium text-[#515154] bg-[#111111] border border-[#1d1d1f] rounded-2xl">
              Enviar
            </button>
          </div>
        </div>
      </div>

    </ProductWindow>
  );
}

// ─── 32-Module Feature Index ─────────────────────────────────────────────────
const FEATURE_INDEX: { code: string; name: string; desc: string }[] = [
  { code: 'SC', name: 'Scanner',            desc: 'Real-time market scanner · 8,412 tickers' },
  { code: 'SG', name: 'Gappers Up',         desc: 'Pre-market gap detection' },
  { code: 'MM', name: 'Momentum',           desc: '5-min momentum leaders' },
  { code: 'BF', name: 'Bull Flag',          desc: 'Continuation pattern detector' },
  { code: 'AI', name: 'AI Agent',           desc: 'Multi-agent slash commands' },
  { code: 'CH', name: 'Chart',              desc: 'Candlestick + VWAP + EMA overlay' },
  { code: 'PM', name: 'Pattern Match',      desc: 'FAISS · 360M analog search' },
  { code: 'UL', name: 'Openul',             desc: 'Breaking news firehose' },
  { code: 'SE', name: 'SEC Filings',        desc: 'EDGAR direct stream' },
  { code: 'DT', name: 'Dilution',           desc: 'ATM shelf & warrant tracker' },
  { code: 'FN', name: 'Financials',         desc: 'Statements · ratios · growth' },
  { code: 'SCR',name: 'Screener',           desc: '200+ fundamental filters' },
  { code: 'AL', name: 'Alerts',             desc: 'Custom rule engine' },
  { code: 'WL', name: 'Watchlists',         desc: 'Unlimited · synced' },
  { code: 'PF', name: 'Portfolio',          desc: 'P&L · positions · allocation' },
  { code: 'JR', name: 'Journal',            desc: 'Auto-logged trades & tags' },
  { code: 'BT', name: 'Backtest',           desc: 'Historical strategy replay' },
  { code: 'OP', name: 'Options Flow',       desc: 'Unusual activity detector' },
  { code: 'DL', name: 'Dark Pool',          desc: 'Off-exchange volume alerts' },
  { code: 'SH', name: 'Short Data',         desc: 'Interest · borrow rate · squeeze' },
  { code: 'IS', name: 'Insider Tx',         desc: 'Form 4 SEC filings' },
  { code: 'ET', name: 'Earnings',           desc: 'Calendar · whisper · guidance' },
  { code: 'EC', name: 'Economic',           desc: 'Macro data · FOMC · CPI' },
  { code: 'HM', name: 'Sector Heatmap',     desc: 'Real-time sector rotation' },
  { code: 'RL', name: 'Relative Strength',  desc: 'vs sector · vs SPY' },
  { code: 'VP', name: 'Volume Profile',     desc: 'POC · value area · nodes' },
  { code: 'LV', name: 'Level 2',            desc: 'Order book · market depth' },
  { code: 'TS', name: 'Time & Sales',       desc: 'Print-by-print tape reader' },
  { code: 'WS', name: 'Workspaces',         desc: 'Floating windows · persistent' },
  { code: 'LN', name: 'Link Groups',        desc: 'Sync windows by color' },
  { code: 'CK', name: 'Cmd Palette',        desc: '⌘K → anything, anywhere' },
  { code: 'SQ', name: 'Squawk',             desc: 'Audio news feed · coming soon' },
];

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
    <main className="min-h-screen bg-white text-slate-900 overflow-x-hidden snap-y snap-proximity scroll-smooth">
      {/* Background: fixed clean base — softer glows only in hero viewport */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden -z-10">
        <div className="absolute inset-0 bg-white" />
        {/* Very faint hero glow — blue */}
        <div className="absolute" style={{
          top: '-15%', right: '-10%',
          width: '1000px', height: '700px',
          background: 'radial-gradient(ellipse at center, rgba(59,130,246,0.08) 0%, transparent 60%)',
          filter: 'blur(80px)',
        }} />
        {/* Very faint hero glow — violet */}
        <div className="absolute" style={{
          top: '5%', left: '-10%',
          width: '800px', height: '600px',
          background: 'radial-gradient(ellipse at center, rgba(124,58,237,0.05) 0%, transparent 60%)',
          filter: 'blur(90px)',
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
                      formButtonPrimary: 'bg-[#2563eb] text-white hover:bg-[#1d4ed8]',
                      footerActionLink: 'text-[#2563eb] hover:text-[#1d4ed8]',
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
                      formButtonPrimary: 'bg-[#2563eb] text-white hover:bg-[#1d4ed8]',
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

      {/* Brand — floating top-left, mirrors the centered pill */}
      <div className="fixed top-7 left-6 sm:left-8 z-50 pointer-events-auto">
        <Link
          href="/"
          aria-label="Tradeul — inicio"
          className="group inline-flex items-center gap-2.5 px-3.5 py-2 rounded-full bg-white/80 backdrop-blur-xl border border-slate-200 shadow-lg shadow-slate-200/50 hover:bg-white transition-colors"
        >
          <TradeulWordmark size="sm" />
        </Link>
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
              className="ml-2 px-5 py-2 rounded-full bg-[#2563eb] text-white font-medium text-sm hover:bg-[#1d4ed8] transition-colors shadow-[0_6px_20px_-6px_rgba(37,99,235,0.55)]"
            >
              {t('landing.nav.signUp')}
            </button>
          </SignedOut>
          <SignedIn>
            <Link
              href="/workspace"
              className="ml-2 px-5 py-2 rounded-full bg-[#2563eb] text-white font-medium text-sm hover:bg-[#1d4ed8] transition-colors flex items-center gap-2 shadow-[0_6px_20px_-6px_rgba(37,99,235,0.55)]"
            >
              {t('landing.hero.openApp')} <ArrowRight className="w-4 h-4" />
            </Link>
          </SignedIn>
        </div>
      </nav>

      {/* ========== HERO SECTION — compact, editorial ========== */}
      <section
        ref={heroRef}
        className="relative flex flex-col justify-center px-6 snap-start pt-28 pb-16 lg:pt-24 lg:pb-20"
      >
        <motion.div
          style={{ opacity: heroOpacity, y: heroY, scale: heroScale }}
          className="max-w-7xl mx-auto w-full"
        >
          {/* Two column layout: Text left, Live terminal right */}
          <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-12 items-center">
            {/* Left: Text content */}
            <motion.div
              initial={{ opacity: 0, y: 32 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="text-left"
            >
              {/* Market-open pill badge */}
              <MarketStatusPill />

              <h1 className="text-[44px] sm:text-[58px] lg:text-[68px] leading-[0.98] tracking-[-0.025em] mb-5">
                <span className="text-slate-900 font-semibold">The terminal</span>
                <br />
                <span className="text-slate-400 font-serif italic font-normal">that actually </span>
                <span className="relative inline-block text-slate-900 font-semibold">
                  reads
                  <motion.span
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.9, delay: 1.1, ease: [0.65, 0, 0.35, 1] }}
                    style={{ originX: 0 }}
                    className="absolute left-0 right-0 -bottom-1 h-[5px] rounded-full bg-gradient-to-r from-[#2563eb] via-[#2563eb]/70 to-transparent"
                  />
                </span>
                <br />
                <span className="text-slate-900 font-semibold">the market.</span>
              </h1>
              <p className="text-[15.5px] text-slate-600 max-w-xl mb-7 leading-[1.55]">
                Scanner, AI agent, pattern match, SEC filings and breaking news.
                <span className="text-slate-400"> Every data stream a professional trader needs, on one screen, at tick speed.</span>
              </p>

              {/* Bloomberg-style stat strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6 mb-7 pb-6 border-b border-slate-200/70">
                {/* Latency with mini sparkline */}
                <div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-[28px] font-semibold text-slate-900 leading-none tabular-nums tracking-tight">
                      <OdometerNumber value={47} />
                      <span className="text-sm text-slate-400 font-medium ml-0.5">ms</span>
                    </div>
                    <LatencySparkline />
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1.5 tracking-[0.08em] uppercase font-medium">
                    avg latency <span className="text-slate-400">· p50</span>
                  </div>
                </div>
                {/* Tickers live */}
                <div>
                  <div className="flex items-center gap-2">
                    <div className="text-[28px] font-semibold text-slate-900 leading-none tabular-nums tracking-tight">
                      <OdometerNumber value={8412} />
                    </div>
                    <span className="relative flex items-center" aria-hidden>
                      <span className="absolute inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400 opacity-70 animate-ping" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1.5 tracking-[0.08em] uppercase font-medium">
                    tickers live <span className="text-slate-400">· streaming</span>
                  </div>
                </div>
                {/* Patterns indexed */}
                <div>
                  <div className="text-[28px] font-semibold text-slate-900 leading-none tabular-nums tracking-tight">
                    <OdometerNumber value={360} />
                    <span className="text-sm text-slate-400 font-medium ml-0.5">M</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1.5 tracking-[0.08em] uppercase font-medium">
                    patterns indexed <span className="text-slate-400">· FAISS</span>
                  </div>
                </div>
                {/* Modules */}
                <div>
                  <div className="text-[28px] font-semibold text-slate-900 leading-none tabular-nums tracking-tight">
                    <OdometerNumber value={32} />
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1.5 tracking-[0.08em] uppercase font-medium">
                    modules <span className="text-slate-400">· one workspace</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-2.5">
                <div className="flex items-center gap-3">
                  <SignedOut>
                    <motion.button
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.5, delay: 0.6 }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => setAuthPanel('signup')}
                      className="group relative px-6 py-3 rounded-full bg-[#2563eb] text-white font-medium text-[14.5px] hover:bg-[#1d4ed8] transition-all flex items-center gap-2 shadow-[0_10px_30px_-8px_rgba(37,99,235,0.55)]"
                    >
                      Empezar gratis
                      <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-0.5" />
                    </motion.button>
                    <button
                      onClick={() => setAuthPanel('signin')}
                      className="group px-4 py-3 rounded-full text-slate-700 font-medium text-[14.5px] hover:text-slate-900 transition-colors flex items-center gap-2"
                    >
                      <span className="w-6 h-6 rounded-full border border-slate-300 flex items-center justify-center group-hover:border-slate-900 transition-colors">
                        <svg width="9" height="10" viewBox="0 0 9 10" fill="none"><path d="M1 1l7 4-7 4V1z" fill="currentColor"/></svg>
                      </span>
                      Watch 90s demo
                    </button>
                  </SignedOut>
                  <SignedIn>
                    <Link href="/workspace" className="group px-6 py-3 rounded-full bg-[#2563eb] text-white font-medium text-[14.5px] hover:bg-[#1d4ed8] transition-all flex items-center gap-2 shadow-[0_10px_30px_-8px_rgba(37,99,235,0.55)]">
                      {t('landing.hero.ctaSignedIn')}
                      <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-0.5" />
                    </Link>
                  </SignedIn>
                </div>
                {/* Meta: no credit card + social proof */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><polyline points="20 6 9 17 4 12"/></svg>
                    Free plan
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><polyline points="20 6 9 17 4 12"/></svg>
                    No credit card
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500"><polyline points="20 6 9 17 4 12"/></svg>
                    3-minute setup
                  </span>
                </div>
              </div>
            </motion.div>

            {/* Right: Live strategy terminal */}
            <motion.div
              initial={{ opacity: 0, x: 60 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 1, delay: 0.4 }}
              className="relative flex justify-center lg:justify-end"
            >
              <HeroScannerTerminal />
            </motion.div>
          </div>
        </motion.div>

      </section>

      {/* ========== MARQUEE TICKER RIBBON ========== */}
      <TickerMarquee />

      {/* ========== DASHBOARD DEMO SECTION ========== */}
      <section className="relative py-20 px-6 snap-start flex flex-col justify-center overflow-hidden">
        <div className="max-w-6xl mx-auto w-full">
          {/* Section header */}
          <RevealSection className="text-center mb-10">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-[0.2em] mb-4 block">
              Full Workspace
            </span>
            <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 mb-4">
              One workspace. Every tool.
            </h2>
            <p className="text-base text-slate-500 max-w-xl mx-auto">
              See how Tradeul consolidates scanner, charting, AI analysis and breaking news in a single professional workspace.
            </p>
          </RevealSection>

          {/* Dashboard mockup with radial aurora glow backdrop (Linear-style) */}
          <RevealSection>
            <div className="relative isolate">
              {/* Aurora glow — soft, blurred, directs the eye to the mockup without decorating */}
              <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[130%]">
                  <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 1.4, ease: 'easeOut' }}
                    className="absolute inset-0"
                  >
                    <div className="absolute left-[8%] top-[6%] w-[55%] h-[65%] rounded-full bg-[#2563eb] opacity-[0.32] blur-[120px]" />
                    <div className="absolute right-[6%] top-[18%] w-[48%] h-[58%] rounded-full bg-[#8b5cf6] opacity-[0.28] blur-[130px]" />
                    <div className="absolute left-[28%] bottom-[-4%] w-[50%] h-[58%] rounded-full bg-[#22d3ee] opacity-[0.22] blur-[140px]" />
                    <div className="absolute right-[22%] bottom-[2%] w-[30%] h-[40%] rounded-full bg-[#f472b6] opacity-[0.14] blur-[120px]" />
                  </motion.div>
                </div>
                {/* Subtle grain texture layered over the glow for a film-like finish */}
                <div
                  className="absolute inset-0 opacity-[0.05] mix-blend-overlay"
                  style={{
                    backgroundImage:
                      "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.6 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
                  }}
                />
              </div>
              <DashboardHero />
            </div>
          </RevealSection>
        </div>
      </section>

      {/* ========== EDITORIAL MODULES — LIGHT BG, DARK PRODUCT WINDOWS ========== */}
      <section id="products" className="relative py-28 px-6 scroll-mt-24 bg-white">
        <div className="max-w-6xl mx-auto relative">
          {/* Section header — editorial serif */}
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }} transition={{ duration: 0.6 }}
            className="mb-20 max-w-3xl">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-6 h-px bg-slate-300" />
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.25em]">Platform · 32 modules</span>
            </div>
            <h2 className="text-5xl sm:text-6xl leading-[1.02] font-semibold text-slate-900 tracking-tight">
              Everything a trader reads
              <br />
              <span className="font-serif italic font-normal text-slate-500">before making a move.</span>
            </h2>
          </motion.div>

          {/* Module 1: Speed */}
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }} transition={{ duration: 0.7 }}
            className="mb-28">
            <div className="grid lg:grid-cols-12 gap-8 mb-8 items-end">
              <div className="lg:col-span-5">
                <div className="text-[10px] font-semibold tracking-[0.25em] uppercase text-slate-400 mb-3">01 · Scanner</div>
                <h3 className="text-4xl lg:text-[44px] leading-[1.05] font-semibold text-slate-900 tracking-tight">
                  The whole market,
                  <br />
                  <span className="font-serif italic font-normal text-slate-500">sorted by what matters.</span>
                </h3>
              </div>
              <div className="lg:col-span-7 lg:pl-8">
                <p className="text-slate-600 text-[15px] leading-[1.6] max-w-md">
                  8,412 tickers ranked live by gap, change, RVOL, volume or any filter you compose.
                  The same tables our power users actually trade from, streaming at sub-50ms.
                </p>
              </div>
            </div>
            <div className="grid md:grid-cols-2 gap-5">
              <ScannerMock title="Gappers Up"  rows={GAPPERS_UP_ROWS}  sortKey="Gap%" />
              <ScannerMock title="Momentum Up" rows={MOMENTUM_UP_ROWS} sortKey="Chg%" />
            </div>
          </motion.div>

          {/* Module 2: SEC */}
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }} transition={{ duration: 0.7 }}
            className="mb-28">
            <div className="grid lg:grid-cols-12 gap-8 mb-8 items-end">
              <div className="lg:col-span-5">
                <div className="text-[10px] font-semibold tracking-[0.25em] uppercase text-slate-400 mb-3">02 · SEC Filings</div>
                <h3 className="text-4xl lg:text-[44px] leading-[1.05] font-semibold text-slate-900 tracking-tight">
                  EDGAR filings,
                  <br />
                  <span className="font-serif italic font-normal text-slate-500">the second they drop.</span>
                </h3>
              </div>
              <div className="lg:col-span-7 lg:pl-8">
                <p className="text-slate-600 text-[15px] leading-[1.6] max-w-md">
                  Direct pipe to EDGAR. Every 10-K, 8-K, S-3 and Form 4 in under a second.
                  Weighted by dilution risk, ranked by relevance to your watchlist.
                </p>
              </div>
            </div>
            <SECFilingsMock />
          </motion.div>

          {/* Module 3: Pattern Match */}
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }} transition={{ duration: 0.7 }}
            className="mb-28">
            <div className="grid lg:grid-cols-12 gap-8 mb-8 items-end">
              <div className="lg:col-span-5">
                <div className="text-[10px] font-semibold tracking-[0.25em] uppercase text-slate-400 mb-3">03 · Pattern Match</div>
                <h3 className="text-4xl lg:text-[44px] leading-[1.05] font-semibold text-slate-900 tracking-tight">
                  Every setup
                  <br />
                  <span className="font-serif italic font-normal text-slate-500">has already played out.</span>
                </h3>
              </div>
              <div className="lg:col-span-7 lg:pl-8">
                <p className="text-slate-600 text-[15px] leading-[1.6] max-w-md">
                  360M historical patterns indexed via FAISS vector search.
                  Find the analogs of any current setup in milliseconds and see how they resolved.
                </p>
              </div>
            </div>
            <PatternMatchingMock />
          </motion.div>

          {/* Module 4: Market Pulse */}
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }} transition={{ duration: 0.7 }}
            className="mb-28">
            <div className="grid lg:grid-cols-12 gap-8 mb-8 items-end">
              <div className="lg:col-span-5">
                <div className="text-[10px] font-semibold tracking-[0.25em] uppercase text-slate-400 mb-3">04 · Market Pulse</div>
                <h3 className="text-4xl lg:text-[44px] leading-[1.05] font-semibold text-slate-900 tracking-tight">
                  The tape,
                  <br />
                  <span className="font-serif italic font-normal text-slate-500">sector by sector.</span>
                </h3>
              </div>
              <div className="lg:col-span-7 lg:pl-8">
                <p className="text-slate-600 text-[15px] leading-[1.6] max-w-md">
                  Real-time breadth, rotation and cap-weighted spread across every sector, industry and theme.
                  Drill down to tickers, spot divergences before the headlines catch up.
                </p>
              </div>
            </div>
            <div className="grid lg:grid-cols-12 gap-5 items-start">
              <div className="lg:col-span-7 lg:col-start-4"><MarketPulseMock /></div>
            </div>
          </motion.div>

          {/* Module 5: AI Agent */}
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-100px' }} transition={{ duration: 0.7 }}>
            <div className="grid lg:grid-cols-12 gap-8 mb-8 items-end">
              <div className="lg:col-span-5">
                <div className="text-[10px] font-semibold tracking-[0.25em] uppercase text-slate-400 mb-3">05 · AI Agent</div>
                <h3 className="text-4xl lg:text-[44px] leading-[1.05] font-semibold text-slate-900 tracking-tight">
                  An analyst
                  <br />
                  <span className="font-serif italic font-normal text-slate-500">on your screen.</span>
                </h3>
              </div>
              <div className="lg:col-span-7 lg:pl-8">
                <p className="text-slate-600 text-[15px] leading-[1.6] max-w-md">
                  Multi-agent pipeline with slash commands, live quotes, pattern search and SEC scanning.
                  Structured responses, mini-charts, one-click follow-ups.
                </p>
              </div>
            </div>
            <AIAgentMock />
          </motion.div>
        </div>
      </section>

      {/* ========== USE CASES STRIP (light) ========== */}
      <section id="solutions" className="relative py-24 px-6 scroll-mt-24 bg-slate-50/60 border-y border-slate-200/70">
        <div className="max-w-6xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }} className="max-w-3xl mb-14">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-6 h-px bg-slate-300" />
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.25em]">Use cases</span>
            </div>
            <h2 className="text-4xl sm:text-5xl leading-[1.05] font-semibold text-slate-900 tracking-tight">
              Built for every style
              <br />
              <span className="font-serif italic font-normal text-slate-500">of serious trader.</span>
            </h2>
          </motion.div>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              {
                title: 'Intraday',
                subtitle: 'Momentum · Gaps · Level-2',
                desc: 'Sub-50ms scanners, live momentum alerts, order-book depth and SEC filings the second they drop. Move before the crowd loads its watchlist.',
                tags: ['Scanner', 'Momentum', 'Alerts', 'Level 2', 'Time & Sales'],
              },
              {
                title: 'Small Cap',
                subtitle: 'Dilution · Float · Filings',
                desc: 'ATM shelf monitoring, warrant analysis, float tracking and S-3 registration alerts. Know the dilution risk before the stock prices it in.',
                tags: ['Dilution', 'SEC', 'Float', 'Short Data', 'Insider Tx'],
              },
              {
                title: 'Swing & Quant',
                subtitle: 'Patterns · Fundamentals · Backtest',
                desc: '360M historical patterns via FAISS vector search, full financial statements, volume-profile analytics and backtest replay. Every setup has already played out.',
                tags: ['Patterns', 'Financials', 'FAISS', 'Backtest', 'Volume Profile'],
              },
            ].map((item, i) => (
              <motion.div key={item.title}
                initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }} transition={{ delay: i * 0.1, duration: 0.6 }}
                className="bg-white border border-slate-200/80 rounded-3xl p-7 flex flex-col gap-4 hover:shadow-lg hover:shadow-slate-200/50 transition-shadow">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500 mb-3">{item.subtitle}</div>
                  <h3 className="text-3xl font-semibold text-slate-900 tracking-tight mb-3">
                    <span className="font-serif italic font-normal">{item.title}</span>
                  </h3>
                  <p className="text-slate-600 text-sm leading-relaxed">{item.desc}</p>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-auto pt-4 border-t border-slate-100">
                  {item.tags.map(tag => (
                    <span key={tag} className="text-[10px] font-medium px-2 py-1 rounded-md bg-slate-50 border border-slate-200 text-slate-600">{tag}</span>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== 32-MODULE INDEX GRID ========== */}
      <section className="relative py-24 px-6 bg-white border-t border-slate-200/70">
        <div className="max-w-6xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }} className="max-w-3xl mb-12">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-6 h-px bg-slate-300" />
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.25em]">Module index · {FEATURE_INDEX.length} tools</span>
            </div>
            <h2 className="text-4xl sm:text-5xl leading-[1.05] font-semibold text-slate-900 tracking-tight">
              Every window you'll ever
              <br />
              <span className="font-serif italic font-normal text-slate-500">have on screen.</span>
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-x-10 gap-y-0 border-t border-slate-200/70">
            {FEATURE_INDEX.map((f, i) => (
              <motion.div
                key={f.code}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: (i % 4) * 0.04, duration: 0.4 }}
                className="py-4 border-b border-slate-200/70 flex items-start gap-3 group"
              >
                <span className="font-mono text-[10px] font-semibold text-slate-400 w-7 pt-0.5 tracking-wider">{f.code}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">{f.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5 leading-snug">{f.desc}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ========== Final CTA — light, editorial ========== */}
      <section className="relative py-32 px-6 bg-white border-t border-slate-200/70">
        <RevealSection className="max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-50 border border-slate-200/80 mb-8">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-medium text-slate-600 tracking-wide">Free to start · No credit card required</span>
          </div>
          <h2 className="text-5xl sm:text-6xl leading-[1.02] font-semibold text-slate-900 tracking-tight mb-6">
            Stop trading
            <br />
            <span className="font-serif italic font-normal text-slate-500">on 15-minute delay.</span>
          </h2>
          <p className="text-lg text-slate-600 mb-10 leading-relaxed max-w-lg mx-auto">
            Join traders who use real-time intelligence to move before the market does.
          </p>
          <SignedOut>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setAuthPanel('signup')}
              className="px-10 py-4 rounded-xl bg-[#2563eb] text-white font-semibold text-base hover:bg-[#1d4ed8] transition-all inline-flex items-center gap-2 shadow-lg shadow-[#2563eb]/25"
            >
              Empezar gratis <ArrowRight className="w-4 h-4" />
            </motion.button>
          </SignedOut>
          <SignedIn>
            <Link href="/workspace" className="inline-flex px-10 py-4 rounded-xl bg-[#2563eb] text-white font-semibold text-base hover:bg-[#1d4ed8] transition-all items-center gap-2 shadow-lg shadow-[#2563eb]/25">
              {t('landing.hero.ctaSignedIn')} <ArrowRight className="w-4 h-4" />
            </Link>
          </SignedIn>
        </RevealSection>
      </section>

      {/* ========== Footer — massive wordmark ========== */}
      <footer id="resources" className="relative pt-20 pb-6 px-6 overflow-hidden border-t border-slate-200/70 scroll-mt-24 bg-white">
        <div className="max-w-6xl mx-auto">
          {/* Links row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 pb-16">
            {[
              { title: 'Platform',  links: ['Scanner', 'AI Agent', 'Pattern Match', 'SEC Filings', 'Dilution'] },
              { title: 'Use cases', links: ['Intraday', 'Small Cap', 'Swing & Quant', 'Options Flow'] },
              { title: 'Company',   links: ['About', 'Pricing', 'Blog', 'Contact'] },
              { title: 'Legal',     links: ['Terms', 'Privacy', 'Disclosure'] },
            ].map(col => (
              <div key={col.title}>
                <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400 mb-4">{col.title}</div>
                <ul className="space-y-2.5">
                  {col.links.map(l => (
                    <li key={l}>
                      <a className="text-sm text-slate-600 hover:text-slate-900 transition-colors">{l}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {/* Massive wordmark */}
          <div className="relative select-none pointer-events-none">
            <div
              aria-hidden
              className="font-semibold tracking-tighter text-slate-900/[0.06] leading-[0.8]"
              style={{ fontSize: 'clamp(80px, 22vw, 340px)' }}
            >
              TRADEUL
            </div>
          </div>

          {/* Bottom row */}
          <div className="flex items-center justify-between pt-6 mt-2 border-t border-slate-200/70">
            <div className="flex items-center gap-3">
              <TradeulWordmark size="sm" />
              <span className="w-px h-4 bg-slate-200" />
              <span className="text-[13px] text-slate-500">Real-time market intelligence</span>
            </div>
            <span className="text-xs text-slate-500">© {new Date().getFullYear()}</span>
          </div>
        </div>
      </footer>
    </main>
  );
}
