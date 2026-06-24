'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { SignIn, SignUp } from '@clerk/nextjs';
import { motion } from 'framer-motion';
import { SlidersHorizontal, ExternalLink, X } from 'lucide-react';
import { useAppTranslation } from '@/hooks/useAppTranslation';

type AuthMode = 'signin' | 'signup';

// ─── Tradeul wordmark — calco del logo oficial (texto bold + barra azul bajo la "t") ──
function TradeulWordmark({
  size = 'md',
}: {
  size?: 'sm' | 'md' | 'lg';
}) {
  const sizeCls =
    size === 'sm' ? 'text-[17px]' : size === 'lg' ? 'text-[28px]' : 'text-[20px]';
  return (
    <span
      className={`relative inline-flex items-baseline leading-none font-semibold tracking-[-0.035em] text-slate-900 ${sizeCls}`}
    >
      <span>tradeul</span>
      <span
        aria-hidden
        className="absolute left-0 bottom-[-4px] h-[2.5px] rounded-full bg-[#2563eb]"
        style={{ width: '0.48em' }}
      />
    </span>
  );
}

// ─── Mini scanner — CALCO FIEL del HeroScannerTerminal del landing (page.tsx) ──
type HeroDRisk = 'Low' | 'Medium' | 'High';
const HERO_ROWS: Array<{
  rank: number;
  sym: string;
  price: number;
  chg: string;
  rvol: string;
  vol5pct: string;
  pos: string;
  float: string;
  dRisk: HeroDRisk;
}> = [
  { rank: 1, sym: 'MSTR', price: 166.25, chg: '+11.62%', rvol: '8.4x', vol5pct: '2890%', pos: '92%', float: '267M', dRisk: 'Medium' },
  { rank: 2, sym: 'SOUN', price: 8.09, chg: '+9.04%', rvol: '6.1x', vol5pct: '2140%', pos: '88%', float: '378M', dRisk: 'High' },
  { rank: 3, sym: 'CAVA', price: 94.78, chg: '+7.38%', rvol: '4.8x', vol5pct: '1560%', pos: '91%', float: '100M', dRisk: 'Low' },
  { rank: 4, sym: 'GRRR', price: 12.98, chg: '+6.92%', rvol: '7.2x', vol5pct: '1820%', pos: '87%', float: '20M', dRisk: 'Medium' },
  { rank: 5, sym: 'BBAI', price: 3.91, chg: '+5.44%', rvol: '5.6x', vol5pct: '1305%', pos: '86%', float: '431M', dRisk: 'High' },
  { rank: 6, sym: 'CLOV', price: 2.23, chg: '+4.86%', rvol: '3.9x', vol5pct: '904%', pos: '89%', float: '389M', dRisk: 'Medium' },
  { rank: 7, sym: 'IONQ', price: 45.62, chg: '+3.67%', rvol: '3.2x', vol5pct: '712%', pos: '85%', float: '290M', dRisk: 'Medium' },
  { rank: 8, sym: 'RILY', price: 7.85, chg: '+2.95%', rvol: '4.1x', vol5pct: '612%', pos: '85%', float: '21M', dRisk: 'High' },
];

type HeroCol = {
  key: string;
  label: string;
  w: string;
  align: 'center' | 'left' | 'right';
  sorted?: boolean;
};
const HERO_COLS: HeroCol[] = [
  { key: 'rank', label: '#', w: '26px', align: 'center' },
  { key: 'sym', label: 'Sym', w: '52px', align: 'left' },
  { key: 'price', label: 'Price', w: '62px', align: 'right' },
  { key: 'chg', label: 'Chg%', w: '64px', align: 'right', sorted: true },
  { key: 'rvol', label: 'RVOL', w: '50px', align: 'right' },
  { key: 'vol5', label: '5m V%', w: '62px', align: 'right' },
  { key: 'pos', label: 'Pos%', w: '48px', align: 'right' },
  { key: 'float', label: 'Float', w: '50px', align: 'right' },
  { key: 'drisk', label: 'D.Risk', w: '60px', align: 'right' },
];

function dRiskClass(v: HeroDRisk): string {
  if (v === 'High') return 'text-rose-500 font-bold';
  if (v === 'Medium') return 'text-amber-400 font-semibold';
  return 'text-emerald-500 font-semibold';
}

function HeroScannerTerminal() {
  const [flashSym, setFlashSym] = useState<string | null>(null);
  const [newBadge, setNewBadge] = useState(true);
  const [livePrices, setLivePrices] = useState<Record<string, number>>(
    Object.fromEntries(HERO_ROWS.map((r) => [r.sym, r.price]))
  );

  useEffect(() => {
    const badgeTimer = setTimeout(() => setNewBadge(false), 2800);
    const priceTimer = setInterval(() => {
      const row = HERO_ROWS[Math.floor(Math.random() * HERO_ROWS.length)];
      setFlashSym(row.sym);
      setLivePrices((prev) => ({
        ...prev,
        [row.sym]: parseFloat((row.price * (1 + (Math.random() * 0.006 - 0.003))).toFixed(2)),
      }));
      setTimeout(() => setFlashSym(null), 420);
    }, 1100);
    return () => {
      clearInterval(priceTimer);
      clearTimeout(badgeTimer);
    };
  }, []);

  return (
    <div className="relative w-full max-w-[540px]">
      {/* Glow halo behind window */}
      <div
        className="absolute -inset-10 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 500px 400px at 55% 45%, rgba(59,130,246,0.18) 0%, transparent 70%)',
          filter: 'blur(8px)',
        }}
      />

      {/* Floating window — calco de FloatingWindow.tsx + MarketTableLayout.tsx */}
      <div className="relative bg-[#0a0a0a] rounded-xl border border-[#1d1d1f] shadow-[0_32px_80px_rgba(0,0,0,0.55)] overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center justify-between px-2.5 h-[30px] bg-[#0d0d0d] border-b border-[#1d1d1f] select-none">
          <div className="flex items-center gap-2 min-w-0">
            <h3 className="text-[11.5px] font-semibold text-[#e8e8ed] truncate">Daily Breakout BF</h3>
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-[10px] font-medium text-emerald-600">Live</span>
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <button className="p-1 rounded hover:bg-[#1a1a1a] transition-colors" title="Link group">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                <path
                  d="M6.5 8.5h3M9.5 6H11a2.5 2.5 0 0 1 0 5H9.5M6.5 11H5a2.5 2.5 0 0 1 0-5h1.5"
                  stroke="#6b6b70"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            <button className="p-1 rounded hover:bg-[#1a1a1a] transition-colors" title="Table settings">
              <SlidersHorizontal className="w-[11px] h-[11px] text-[#6b6b70]" />
            </button>
            <button className="p-1 rounded hover:bg-[#1a1a1a] transition-colors" title="Open in new window">
              <ExternalLink className="w-[11px] h-[11px] text-[#6b6b70]" />
            </button>
            <button className="p-1 rounded hover:bg-rose-500/15 transition-colors" title="Close">
              <X className="w-[11px] h-[11px] text-[#6b6b70]" />
            </button>
          </div>
        </div>

        {/* Column headers */}
        <div className="flex items-center px-2.5 h-[24px] bg-[#080808] border-b border-[#1d1d1f]">
          {HERO_COLS.map((col) => (
            <div
              key={col.key}
              className={`flex items-center gap-0.5 text-[10px] font-medium select-none flex-shrink-0 ${
                col.sorted ? 'text-amber-400' : 'text-[#6b6b70]'
              }`}
              style={{
                width: col.w,
                justifyContent:
                  col.align === 'right' ? 'flex-end' : col.align === 'center' ? 'center' : 'flex-start',
              }}
            >
              {col.label}
              {col.sorted && (
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <path d="M19 5l-7 7-7-7" />
                </svg>
              )}
            </div>
          ))}
        </div>

        {/* Rows */}
        <div>
          {HERO_ROWS.map((row, idx) => {
            const isFlash = flashSym === row.sym;
            const price = livePrices[row.sym] ?? row.price;
            const vol5Num = parseFloat(row.vol5pct);
            const posNum = parseFloat(row.pos);
            const vol5Color =
              vol5Num >= 2000 ? 'text-emerald-500' : vol5Num >= 1000 ? 'text-amber-400' : 'text-[#9a9aa0]';
            const posColor = posNum >= 92 ? 'text-emerald-500' : 'text-[#9a9aa0]';
            return (
              <div
                key={row.sym}
                className={`flex items-center px-2.5 h-[24px] border-b border-[#0d0d0d] transition-colors duration-200 ${
                  isFlash ? 'bg-emerald-500/[0.10]' : 'hover:bg-[#111111]'
                }`}
              >
                <div
                  className="text-[10px] font-medium text-[#515154] flex-shrink-0"
                  style={{ width: HERO_COLS[0].w, textAlign: 'center' }}
                >
                  {row.rank}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0" style={{ width: HERO_COLS[1].w }}>
                  <span className="text-[11px] font-bold text-[#2997ff]">{row.sym}</span>
                  {idx === 0 && newBadge && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.6 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-[7px] font-bold text-emerald-400 bg-emerald-500/20 px-1 rounded-sm leading-none"
                    >
                      NEW
                    </motion.span>
                  )}
                </div>
                <div
                  className={`font-mono text-[10.5px] text-right flex-shrink-0 transition-colors duration-200 ${
                    isFlash ? 'text-emerald-300' : 'text-[#e8e8ed]'
                  }`}
                  style={{ width: HERO_COLS[2].w }}
                >
                  {price.toFixed(2)}
                </div>
                <div
                  className="font-mono font-semibold text-[10.5px] text-emerald-500 text-right flex-shrink-0"
                  style={{ width: HERO_COLS[3].w }}
                >
                  {row.chg}
                </div>
                <div
                  className="font-mono font-semibold text-[10.5px] text-[#2997ff] text-right flex-shrink-0"
                  style={{ width: HERO_COLS[4].w }}
                >
                  {row.rvol}
                </div>
                <div
                  className={`font-mono font-semibold text-[10.5px] text-right flex-shrink-0 ${vol5Color}`}
                  style={{ width: HERO_COLS[5].w }}
                >
                  {row.vol5pct}
                </div>
                <div
                  className={`font-mono font-semibold text-[10.5px] text-right flex-shrink-0 ${posColor}`}
                  style={{ width: HERO_COLS[6].w }}
                >
                  {row.pos}
                </div>
                <div
                  className="font-mono text-[10.5px] text-[#86868b] text-right flex-shrink-0"
                  style={{ width: HERO_COLS[7].w }}
                >
                  {row.float}
                </div>
                <div
                  className={`text-[10.5px] text-right flex-shrink-0 ${dRiskClass(row.dRisk)}`}
                  style={{ width: HERO_COLS[8].w }}
                >
                  {row.dRisk}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.1 + i * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const },
  }),
};

export default function AuthExperience({ mode }: { mode: AuthMode }) {
  const { t } = useAppTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const features = [
    t('landing.authPage.feature1'),
    t('landing.authPage.feature2'),
    t('landing.authPage.feature3'),
  ];

  const clerkAppearance = {
    variables: {
      colorPrimary: '#2563eb',
      borderRadius: '0.625rem',
      fontSize: '14px',
    },
    elements: {
      rootBox: 'w-full',
      card: 'shadow-none bg-transparent p-0 w-full',
      headerTitle: 'text-slate-900 text-[22px] font-semibold tracking-tight',
      headerSubtitle: 'text-slate-500',
      socialButtonsBlockButton:
        'bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors',
      socialButtonsBlockButtonText: 'text-slate-700 font-medium',
      dividerLine: 'bg-slate-200',
      dividerText: 'text-slate-400',
      formFieldLabel: 'text-slate-600 font-medium',
      formFieldInput:
        'bg-white border-slate-200 text-slate-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15',
      formButtonPrimary:
        'bg-[#2563eb] hover:bg-[#1d4ed8] text-white normal-case text-sm font-semibold shadow-sm shadow-blue-500/20 transition-colors',
      footerActionLink: 'text-[#2563eb] hover:text-[#1d4ed8] font-medium',
      footer: 'hidden',
      identityPreviewText: 'text-slate-900',
      identityPreviewEditButton: 'text-[#2563eb]',
      otpCodeFieldInput: 'border-slate-200 text-slate-900',
      formResendCodeLink: 'text-[#2563eb] hover:text-[#1d4ed8]',
    },
  } as const;

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-white">
      {/* Glows muy sutiles — calco del landing hero (sobre fondo claro) */}
      <div
        className="absolute pointer-events-none"
        style={{
          top: '-15%',
          right: '-10%',
          width: '1000px',
          height: '700px',
          background: 'radial-gradient(ellipse at center, rgba(59,130,246,0.08) 0%, transparent 60%)',
          filter: 'blur(80px)',
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          top: '5%',
          left: '-10%',
          width: '800px',
          height: '600px',
          background: 'radial-gradient(ellipse at center, rgba(124,58,237,0.05) 0%, transparent 60%)',
          filter: 'blur(90px)',
        }}
      />

      <div className="relative z-10 flex min-h-screen">
        {/* ───────── Brand panel (left, lg+) ───────── */}
        <div className="relative hidden lg:flex lg:w-[55%] flex-col justify-between px-10 xl:px-16 py-12">
          {/* Top: brand */}
          <motion.div initial="hidden" animate="show" custom={0} variants={fadeUp}>
            <Link href="/" className="inline-flex">
              <TradeulWordmark size="lg" />
            </Link>
          </motion.div>

          {/* Middle: headline + scanner + features */}
          <div className="flex flex-col gap-8 my-auto">
            <motion.h1
              initial="hidden"
              animate="show"
              custom={1}
              variants={fadeUp}
              className="text-slate-900 text-[40px] xl:text-[46px] font-semibold leading-[1.05] tracking-[-0.02em] max-w-[460px]"
            >
              {t('landing.authPage.brandHeadline1')}{' '}
              <span className="bg-gradient-to-r from-blue-600 to-violet-600 bg-clip-text text-transparent">
                {t('landing.authPage.brandHeadline2')}
              </span>
            </motion.h1>

            <motion.p
              initial="hidden"
              animate="show"
              custom={2}
              variants={fadeUp}
              className="text-slate-500 text-[15px] leading-relaxed max-w-[420px]"
            >
              {t('landing.authPage.brandSubtitle')}
            </motion.p>

            <motion.div initial="hidden" animate="show" custom={3} variants={fadeUp}>
              <HeroScannerTerminal />
            </motion.div>

            <motion.ul
              initial="hidden"
              animate="show"
              custom={4}
              variants={fadeUp}
              className="flex flex-col gap-2.5"
            >
              {features.map((f) => (
                <li key={f} className="flex items-center gap-2.5 text-slate-600 text-[14px]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#2563eb] flex-shrink-0" />
                  {f}
                </li>
              ))}
            </motion.ul>
          </div>

          {/* Bottom: trust */}
          <motion.p
            initial="hidden"
            animate="show"
            custom={5}
            variants={fadeUp}
            className="text-slate-400 text-[13px]"
          >
            {t('landing.authPage.trust')}
          </motion.p>
        </div>

        {/* ───────── Auth panel (right) ───────── */}
        <div className="relative flex flex-1 flex-col items-center justify-center px-6 sm:px-10 py-10 lg:border-l lg:border-slate-200/60 lg:bg-white/60 lg:backdrop-blur-sm">
          {/* Back to home — top right */}
          <Link
            href="/"
            className="absolute top-6 right-6 text-[13px] font-medium text-slate-500 hover:text-slate-900 transition-colors"
          >
            {t('landing.authPage.backHome')}
          </Link>

          {/* Mobile brand */}
          <div className="lg:hidden mb-8">
            <Link href="/" className="inline-flex">
              <TradeulWordmark size="lg" />
            </Link>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-[400px]"
          >
            {/* Eyebrow */}
            <div className="mb-6">
              <span className="inline-flex items-center rounded-full bg-blue-50 border border-blue-100 px-3 py-1 text-[12px] font-medium text-blue-700">
                {mode === 'signin'
                  ? t('landing.authPage.eyebrowSignIn')
                  : t('landing.authPage.eyebrowSignUp')}
              </span>
            </div>

            {mounted ? (
              mode === 'signin' ? (
                <SignIn signUpUrl="/sign-up" fallbackRedirectUrl="/workspace" appearance={clerkAppearance} />
              ) : (
                <SignUp signInUrl="/sign-in" fallbackRedirectUrl="/workspace" appearance={clerkAppearance} />
              )
            ) : (
              <div className="flex justify-center py-16">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
              </div>
            )}

            {/* Footer toggle */}
            <div className="mt-6 text-center text-[14px] text-slate-500">
              {mode === 'signin' ? (
                <>
                  {t('landing.authPage.noAccount')}{' '}
                  <Link
                    href="/sign-up"
                    className="font-semibold text-[#2563eb] hover:text-[#1d4ed8] transition-colors"
                  >
                    {t('landing.auth.createAccount')}
                  </Link>
                </>
              ) : (
                <>
                  {t('landing.authPage.haveAccount')}{' '}
                  <Link
                    href="/sign-in"
                    className="font-semibold text-[#2563eb] hover:text-[#1d4ed8] transition-colors"
                  >
                    {t('landing.auth.signIn')}
                  </Link>
                </>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
