'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ExternalLink, History, Maximize2, SlidersHorizontal, Star } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// FAKE DATA
// ─────────────────────────────────────────────────────────────────────────────

// gappers_up columns: price · change_percent · gap_percent · change_from_open · volume_today · rvol
const SCANNER_ROWS = [
  { rank: 1,  sym: 'NVDA',  price: '912.40', chg: '+12.34%', gap: '+8.21%',  vsOpen: '+4.12%', vol: '124.5M', rvol: '4.2x', up: true  },
  { rank: 2,  sym: 'AMD',   price: '178.32', chg: '+7.81%',  gap: '+5.43%',  vsOpen: '+2.38%', vol: '67.3M',  rvol: '3.1x', up: true  },
  { rank: 3,  sym: 'SMCI',  price: '38.74',  chg: '+15.23%', gap: '+11.67%', vsOpen: '+3.56%', vol: '89.4M',  rvol: '6.8x', up: true  },
  { rank: 4,  sym: 'PLTR',  price: '78.92',  chg: '+9.45%',  gap: '+6.12%',  vsOpen: '+3.33%', vol: '52.1M',  rvol: '2.9x', up: true  },
  { rank: 5,  sym: 'MSTR',  price: '412.30', chg: '+8.67%',  gap: '+5.89%',  vsOpen: '+2.78%', vol: '28.4M',  rvol: '5.3x', up: true  },
  { rank: 6,  sym: 'COIN',  price: '298.45', chg: '+6.23%',  gap: '+4.17%',  vsOpen: '+2.06%', vol: '33.7M',  rvol: '2.4x', up: true  },
  { rank: 7,  sym: 'IONQ',  price: '12.84',  chg: '+18.92%', gap: '+14.33%', vsOpen: '+4.59%', vol: '45.6M',  rvol: '8.7x', up: true  },
  { rank: 8,  sym: 'CAVA',  price: '98.23',  chg: '+5.44%',  gap: '+3.21%',  vsOpen: '+2.23%', vol: '18.9M',  rvol: '2.1x', up: true  },
  { rank: 9,  sym: 'WOLF',  price: '4.23',   chg: '+22.15%', gap: '+17.44%', vsOpen: '+4.71%', vol: '234.5M', rvol: '12.3x',up: true  },
  { rank: 10, sym: 'CLOV',  price: '2.87',   chg: '+31.05%', gap: '+24.12%', vsOpen: '+6.93%', vol: '412.1M', rvol: '18.4x',up: true  },
];

// momentum_up columns: price · change_percent · chg_5min · volume_today · rvol · price_vs_vwap
const MOMENTUM_ROWS = [
  { rank: 1, sym: 'TSLA',  price: '248.50', chg: '+3.21%', chg5m: '+0.84%', vol: '87.3M',  rvol: '2.1x', vsVwap: '+1.2%', up: true },
  { rank: 2, sym: 'META',  price: '512.80', chg: '+4.33%', chg5m: '+1.12%', vol: '31.4M',  rvol: '2.4x', vsVwap: '+2.1%', up: true },
  { rank: 3, sym: 'MSFT',  price: '415.20', chg: '+2.14%', chg5m: '+0.52%', vol: '42.1M',  rvol: '1.8x', vsVwap: '+0.8%', up: true },
  { rank: 4, sym: 'AAPL',  price: '189.40', chg: '+1.87%', chg5m: '+0.43%', vol: '55.7M',  rvol: '1.6x', vsVwap: '+0.5%', up: true },
  { rank: 5, sym: 'GOOGL', price: '175.20', chg: '+2.91%', chg5m: '+0.67%', vol: '28.9M',  rvol: '1.9x', vsVwap: '+1.5%', up: true },
  { rank: 6, sym: 'AMZN',  price: '192.30', chg: '+1.54%', chg5m: '+0.31%', vol: '33.6M',  rvol: '1.5x', vsVwap: '+0.4%', up: true },
];

// "Estrategia 3 Daily Breakout Bull Flag Momentum" — columnas de la estrategia real del usuario:
// filters: min_rvol:2, min_vol_5min_pct:500, min_pos_in_range:85, min_todays_range_pct:150
// price: $1-$50, float <100M, chg >2%
const BULL_FLAG_ROWS = [
  { rank: 1, sym: 'CLOV', price: '2.87',  chg: '+31.05%', rvol: '18.4x', vol5pct: '5640%', pos: '97%', float: '23M' },
  { rank: 2, sym: 'WOLF', price: '4.23',  chg: '+22.15%', rvol: '12.3x', vol5pct: '3821%', pos: '89%', float: '88M' },
  { rank: 3, sym: 'IONQ', price: '12.84', chg: '+18.92%', rvol: '8.7x',  vol5pct: '2104%', pos: '96%', float: '34M' },
  { rank: 4, sym: 'SMCI', price: '38.74', chg: '+15.23%', rvol: '6.8x',  vol5pct: '1842%', pos: '92%', float: '52M' },
  { rank: 5, sym: 'MSTR', price: '42.30', chg: '+8.67%',  rvol: '5.3x',  vol5pct: '1234%', pos: '91%', float: '45M' },
  { rank: 6, sym: 'PLTR', price: '32.15', chg: '+9.45%',  rvol: '2.9x',  vol5pct: '621%',  pos: '87%', float: '78M' },
  { rank: 7, sym: 'CAVA', price: '28.45', chg: '+5.44%',  rvol: '2.1x',  vol5pct: '512%',  pos: '85%', float: '67M' },
];

// Chart: 28 candles [open, close, high, low]
const CANDLES_DATA: [number, number, number, number][] = [
  [848, 853, 855, 846],[853, 858, 860, 851],[858, 864, 866, 856],
  [864, 868, 870, 862],[868, 872, 874, 866],
  [882, 895, 898, 879],[895, 888, 896, 884],[888, 893, 895, 886],
  [893, 897, 899, 891],[897, 892, 898, 889],[892, 897, 899, 890],
  [897, 900, 902, 895],[900, 898, 902, 896],[898, 902, 904, 897],
  [902, 905, 907, 900],[905, 903, 906, 901],[903, 906, 908, 902],
  [906, 904, 907, 902],[904, 907, 909, 903],[907, 906, 909, 904],
  [906, 909, 911, 905],[909, 908, 911, 906],[908, 911, 913, 907],
  [911, 909, 912, 908],[909, 912, 914, 908],[912, 910, 913, 909],
  [910, 913, 915, 909],[913, 913, 914, 912],
];
const VOLS = [
  0.22,0.26,0.30,0.28,0.32,
  1.00,0.74,0.64,0.57,0.61,0.53,0.56,0.48,0.54,0.62,
  0.46,0.51,0.44,0.49,0.45,0.53,0.47,0.55,0.49,0.57,
  0.46,0.51,0.36,
];

const AI_RESPONSE = "NVDA mostrando RVOL 4.2x vs media 30d. Precio actual $912.40 +12.34%, $2.4B dollar vol intraday. Gap pre-market +8.21% confirmado por anuncio CEO. Resistencia clave: $915. Patrón: bull flag activo, consolidación pre-ruptura cerca del HOD.";

const AI_STEPS = [
  'Fetching real-time quotes · NVDA',
  'Analyzing volume profile · RVOL 4.2x',
  'Pattern match: bull flag detected',
];

// Orden cronológico (más viejo primero) — se invierte al mostrar para newest-first
const NEWS_ITEMS = [
  { id: 1, type: 'news'     as const, time: '09:31:42', text: 'CEO confirms $40B AI infrastructure deal with Microsoft', tickers: ['NVDA'] as string[], breaking: true },
  { id: 2, type: 'reaction' as const, time: '09:31:58', ticker: 'NVDA', pct: 4.2, price: 912.40 },
  { id: 3, type: 'news'     as const, time: '09:32:15', text: 'Federal Reserve holds rates at 4.25%–4.50%', tickers: [] as string[], breaking: true },
  { id: 4, type: 'reaction' as const, time: '09:33:04', ticker: 'PLTR', pct: 2.8, price: 78.92 },
];

// ─────────────────────────────────────────────────────────────────────────────
// CHART CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

const PRICE_MIN = 844, PRICE_MAX = 916, PRICE_RANGE = PRICE_MAX - PRICE_MIN;
const CHART_H = 104, VOL_H = 26, SVG_W = 460;
const N = CANDLES_DATA.length, SLOT = SVG_W / N, BODY_W = Math.round(SLOT * 0.62);
const pY = (p: number) => CHART_H - ((p - PRICE_MIN) / PRICE_RANGE) * CHART_H;
const cX = (i: number) => i * SLOT + (SLOT - BODY_W) / 2;
const cMX = (i: number) => cX(i) + BODY_W / 2;
const preMarketEnd = cX(5);
const GRID_PRICES = [850, 864, 878, 892, 906];

const vwapPoints = CANDLES_DATA.map((c, i) => {
  const s = CANDLES_DATA.slice(0, i + 1);
  const avg = s.reduce((sum, x) => sum + (x[2] + x[3] + x[1]) / 3, 0) / s.length;
  return `${cMX(i).toFixed(1)},${pY(avg).toFixed(1)}`;
}).join(' ');

const ema9: number[] = [];
CANDLES_DATA.forEach((c, i) => {
  const k = 2 / 10;
  ema9.push(i === 0 ? c[1] : c[1] * k + ema9[i - 1] * (1 - k));
});
const ema9Points = ema9.map((v, i) => `${cMX(i).toFixed(1)},${pY(v).toFixed(1)}`).join(' ');

// ─────────────────────────────────────────────────────────────────────────────
// WINDOW CHROMES — calco exacto de FloatingWindow.tsx y MarketTableLayout.tsx
// ─────────────────────────────────────────────────────────────────────────────

/**
 * FloatingWindowChrome — calco de FloatingWindow.tsx title bar
 * Usado por: AI Agent, OpenUL, Chart
 * Structure: [portal-extra] [title] ... [ExternalLink] [X]
 */
function FloatingWindowChrome({ title, extra }: { title: string; extra?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-2 py-1 bg-[#111111] border-b border-[#1d1d1f] cursor-move select-none flex-shrink-0">
      <div className="flex items-center gap-1 flex-1 min-w-0">
        {extra && <div className="flex items-center mr-1">{extra}</div>}
        <h3 className="text-[11px] font-medium text-[#e8e8ed] truncate">{title}</h3>
      </div>
      <div className="flex items-center gap-0.5 ml-2">
        <button className="p-0.5 rounded hover:bg-[#2997ff]/10 transition-colors group">
          <ExternalLink className="w-3 h-3 text-[#515154] group-hover:text-[#2997ff]" />
        </button>
        <button className="p-0.5 rounded hover:bg-[#ef4444]/10 transition-colors group">
          <X className="w-3 h-3 text-[#515154] group-hover:text-[#ef4444]" />
        </button>
      </div>
    </div>
  );
}

/**
 * MarketTableLayoutHeader — calco exacto de MarketTableLayout.tsx
 * Usado por: Scanner, Bull Flag (ventanas con hideHeader=true que usan su propio header)
 * Structure: [title] [● Live/dot] ... [ExternalLink] [rightActions?] [X]
 */
function MarketTableLayoutHeader({
  title,
  dotColor = 'emerald',
  extra,
  showLive = true,
}: {
  title: string;
  dotColor?: 'emerald' | 'amber';
  extra?: React.ReactNode;
  showLive?: boolean;
}) {
  const dotCls = dotColor === 'amber' ? 'bg-amber-400' : 'bg-emerald-500';
  const textCls = dotColor === 'amber' ? 'text-amber-500' : 'text-emerald-600';
  return (
    <div className="flex items-center justify-between px-2 py-1 bg-[#0d0d0d] border-b border-[#1d1d1f] cursor-move select-none flex-shrink-0">
      <div className="flex items-center gap-2">
        <h2 className="text-[11px] font-semibold text-[#e8e8ed]">{title}</h2>
        {showLive && (
          <div className="flex items-center gap-1">
            <div className={`w-1.5 h-1.5 rounded-full ${dotCls}`} />
            <span className={`text-[10px] font-medium ${textCls}`}>Live</span>
          </div>
        )}
        {extra}
      </div>
      <div className="flex items-center gap-0.5">
        {/* LinkGroupSelector — chain icon para vincular ventanas */}
        <button className="p-0.5 rounded hover:bg-[#111111] transition-colors flex items-center" title="Link group">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6.5 8.5h3M9.5 6H11a2.5 2.5 0 0 1 0 5H9.5M6.5 11H5a2.5 2.5 0 0 1 0-5h1.5"
              stroke="#515154" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button className="p-0.5 rounded hover:bg-[#2997ff]/10 transition-colors group">
          <ExternalLink className="w-3 h-3 text-[#515154] group-hover:text-[#2997ff]" />
        </button>
        {/* TableSettings — gear/sliders icon */}
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

// ─────────────────────────────────────────────────────────────────────────────
// GAPPERS SCANNER — calco de CategoryTableV2 + MarketTableLayout
// ─────────────────────────────────────────────────────────────────────────────

function ScannerColHeaders() {
  const cols = [
    { label: '#',       w: '14px', align: 'center' as const },
    { label: 'Sym',     w: '38px', align: 'left'   as const },
    { label: 'Price',   w: '52px', align: 'right'  as const },
    { label: 'Chg%',    w: '48px', align: 'right'  as const, sorted: true },
    { label: 'Gap%',    w: '44px', align: 'right'  as const },
    { label: 'vs Open', w: '44px', align: 'right'  as const },
    { label: 'Vol',     w: '48px', align: 'right'  as const },
    { label: 'RVOL',    w: '34px', align: 'right'  as const },
  ];
  return (
    <div className="flex items-center px-1.5 h-[20px] border-b border-[#1d1d1f] bg-[#080808] flex-shrink-0">
      {cols.map((col) => (
        <div key={col.label}
          className={`flex items-center gap-0.5 text-[9px] font-medium select-none flex-shrink-0 ${col.sorted ? 'text-[#e8e8ed]' : 'text-[#515154]'}`}
          style={{ width: col.w, justifyContent: col.align === 'right' ? 'flex-end' : col.align === 'center' ? 'center' : 'flex-start' }}>
          {col.label}
          {col.sorted && <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M19 5l-7 7-7-7"/></svg>}
        </div>
      ))}
    </div>
  );
}

function ScannerRow({ row, flash }: { row: (typeof SCANNER_ROWS)[number]; flash: boolean }) {
  return (
    <div className={`flex items-center px-1.5 h-[17px] border-b border-[#0d0d0d] transition-colors duration-500 ${flash ? 'bg-emerald-500/20' : 'hover:bg-[#111111]'}`}>
      <div className="text-[8.5px] font-medium text-[#515154] text-center flex-shrink-0" style={{ width: '14px' }}>{row.rank}</div>
      <div className="text-[9.5px] font-bold text-[#2997ff] flex-shrink-0 cursor-pointer" style={{ width: '38px' }}>{row.sym}</div>
      <div className="font-mono text-[8.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '52px' }}>{row.price}</div>
      <div className={`font-mono font-semibold text-[8.5px] text-right flex-shrink-0 ${row.up ? 'text-emerald-500' : 'text-rose-500'}`} style={{ width: '48px' }}>{row.chg}</div>
      <div className={`font-mono font-semibold text-[8.5px] text-right flex-shrink-0 ${row.up ? 'text-emerald-500' : 'text-rose-500'}`} style={{ width: '44px' }}>{row.gap}</div>
      <div className={`font-mono font-semibold text-[8.5px] text-right flex-shrink-0 ${row.up ? 'text-emerald-500' : 'text-rose-500'}`} style={{ width: '44px' }}>{row.vsOpen}</div>
      <div className="font-mono text-[8.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '48px' }}>{row.vol}</div>
      <div className="font-mono font-semibold text-[8.5px] text-[#2997ff] text-right flex-shrink-0" style={{ width: '34px' }}>{row.rvol}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// BULL FLAG MOMENTUM STRATEGY
// ─────────────────────────────────────────────────────────────────────────────


// "Estrategia 3 Daily Breakout Bull Flag Momentum" real columns:
// price · change_percent · rvol · vol_5min_pct · pos_in_range · float_shares
function BullFlagColHeaders() {
  const cols = [
    { label: '#',     w: '14px', align: 'center' as const },
    { label: 'Sym',   w: '36px', align: 'left'   as const },
    { label: 'Price', w: '46px', align: 'right'  as const },
    { label: 'Chg%',  w: '48px', align: 'right'  as const, sorted: true },
    { label: 'RVOL',  w: '38px', align: 'right'  as const },
    { label: '5m V%', w: '52px', align: 'right'  as const },
    { label: 'Pos%',  w: '40px', align: 'right'  as const },
    { label: 'Float', w: '42px', align: 'right'  as const },
  ];
  return (
    <div className="flex items-center px-1.5 h-[20px] border-b border-[#1d1d1f] bg-[#080808] flex-shrink-0">
      {cols.map((col) => (
        <div key={col.label}
          className={`flex items-center gap-0.5 text-[9px] font-medium select-none flex-shrink-0 ${col.sorted ? 'text-amber-400' : 'text-[#515154]'}`}
          style={{ width: col.w, justifyContent: col.align === 'right' ? 'flex-end' : col.align === 'center' ? 'center' : 'flex-start' }}>
          {col.label}
          {col.sorted && <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M19 5l-7 7-7-7"/></svg>}
        </div>
      ))}
    </div>
  );
}

function BullFlagRow({ row, isNew }: { row: (typeof BULL_FLAG_ROWS)[number]; isNew?: boolean }) {
  const vol5Color = parseInt(row.vol5pct) >= 2000 ? '#10b981' : parseInt(row.vol5pct) >= 1000 ? '#f59e0b' : '#86868b';
  const posColor  = parseInt(row.pos) >= 92 ? '#10b981' : '#86868b';
  return (
    <div className={`flex items-center px-1.5 h-[17px] border-b border-[#0d0d0d] transition-colors duration-500 ${isNew ? 'bg-emerald-500/15' : 'hover:bg-[#111111]'}`}>
      <div className="text-[8.5px] font-medium text-[#515154] text-center flex-shrink-0" style={{ width: '14px' }}>{row.rank}</div>
      <div className="text-[9.5px] font-bold text-[#2997ff] flex-shrink-0 cursor-pointer" style={{ width: '36px' }}>{row.sym}</div>
      <div className="font-mono text-[8.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '46px' }}>{row.price}</div>
      <div className="font-mono font-semibold text-[8.5px] text-emerald-500 text-right flex-shrink-0" style={{ width: '48px' }}>{row.chg}</div>
      <div className="font-mono font-semibold text-[8.5px] text-[#2997ff] text-right flex-shrink-0" style={{ width: '38px' }}>{row.rvol}</div>
      <div className="font-mono font-semibold text-[8.5px] text-right flex-shrink-0" style={{ width: '52px', color: vol5Color }}>{row.vol5pct}</div>
      <div className="font-mono font-semibold text-[8.5px] text-right flex-shrink-0" style={{ width: '40px', color: posColor }}>{row.pos}</div>
      <div className="font-mono text-[8.5px] text-[#86868b] text-right flex-shrink-0" style={{ width: '42px' }}>{row.float}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MOMENTUM UP SCANNER
// ─────────────────────────────────────────────────────────────────────────────

// momentum_up columns: price · change_percent · change_from_open · chg_5min · volume_today · rvol · price_vs_vwap
function MomentumColHeaders() {
  const cols = [
    { label: '#',       w: '14px', align: 'center' as const },
    { label: 'Sym',     w: '38px', align: 'left'   as const },
    { label: 'Price',   w: '52px', align: 'right'  as const },
    { label: 'Chg%',    w: '48px', align: 'right'  as const, sorted: true },
    { label: '5m Chg%', w: '50px', align: 'right'  as const },
    { label: 'Vol',     w: '48px', align: 'right'  as const },
    { label: 'RVOL',    w: '34px', align: 'right'  as const },
    { label: 'vs VWAP', w: '44px', align: 'right'  as const },
  ];
  return (
    <div className="flex items-center px-1.5 h-[20px] border-b border-[#1d1d1f] bg-[#080808] flex-shrink-0">
      {cols.map((col) => (
        <div key={col.label}
          className={`flex items-center gap-0.5 text-[9px] font-medium select-none flex-shrink-0 ${col.sorted ? 'text-[#e8e8ed]' : 'text-[#515154]'}`}
          style={{ width: col.w, justifyContent: col.align === 'right' ? 'flex-end' : col.align === 'center' ? 'center' : 'flex-start' }}>
          {col.label}
          {col.sorted && <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M19 5l-7 7-7-7"/></svg>}
        </div>
      ))}
    </div>
  );
}

function MomentumRow({ row }: { row: (typeof MOMENTUM_ROWS)[number] }) {
  return (
    <div className="flex items-center px-1.5 h-[17px] border-b border-[#0d0d0d] hover:bg-[#111111]">
      <div className="text-[8.5px] font-medium text-[#515154] text-center flex-shrink-0" style={{ width: '14px' }}>{row.rank}</div>
      <div className="text-[9.5px] font-bold text-[#2997ff] flex-shrink-0 cursor-pointer" style={{ width: '38px' }}>{row.sym}</div>
      <div className="font-mono text-[8.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '52px' }}>{row.price}</div>
      <div className="font-mono font-semibold text-[8.5px] text-emerald-500 text-right flex-shrink-0" style={{ width: '48px' }}>{row.chg}</div>
      <div className="font-mono font-semibold text-[8.5px] text-emerald-400 text-right flex-shrink-0" style={{ width: '50px' }}>{row.chg5m}</div>
      <div className="font-mono text-[8.5px] text-[#e8e8ed] text-right flex-shrink-0" style={{ width: '48px' }}>{row.vol}</div>
      <div className="font-mono font-semibold text-[8.5px] text-[#2997ff] text-right flex-shrink-0" style={{ width: '34px' }}>{row.rvol}</div>
      <div className="font-mono font-semibold text-[8.5px] text-emerald-400 text-right flex-shrink-0" style={{ width: '44px' }}>{row.vsVwap}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TRADING CHART — calco de TradingChart.tsx
// ─────────────────────────────────────────────────────────────────────────────

function MockChart() {
  return (
    <div className="flex-1 overflow-hidden flex flex-col min-h-0 bg-[#050505]">
      {/* Inner toolbar — calco de TradingChart inner header */}
      <div className="flex items-center gap-0.5 px-1.5 py-[3px] border-b border-[#0d0d0d] bg-[#080808] flex-shrink-0 overflow-hidden">
        {['1m','5m','15m','1h','1D','1W'].map((tf) => (
          <button key={tf} className={`text-[9px] px-1.5 py-[2px] rounded flex-shrink-0 ${tf === '1D' ? 'bg-[#2997ff]/15 text-[#2997ff] font-semibold' : 'text-[#515154]'}`}>{tf}</button>
        ))}
        <div className="w-px h-3 bg-[#1d1d1f] mx-0.5 flex-shrink-0" />
        {['1D','5D','1M','1Y'].map((r, i) => (
          <button key={r} className={`text-[9px] px-1 py-[2px] rounded flex-shrink-0 ${i === 0 ? 'text-[#e8e8ed] font-semibold' : 'text-[#515154]'}`}>{r}</button>
        ))}
        <div className="w-px h-3 bg-[#1d1d1f] mx-0.5 flex-shrink-0" />
        {/* Candle type icon */}
        <button className="p-[3px] rounded text-[#515154] flex-shrink-0">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M9 4v4M9 14v6M15 4v6M15 18v2"/>
            <rect x="7" y="8" width="4" height="6" rx="0.5" fill="currentColor" stroke="none"/>
            <rect x="13" y="10" width="4" height="8" rx="0.5"/>
          </svg>
        </button>
        <div className="w-px h-3 bg-[#1d1d1f] mx-0.5 flex-shrink-0" />
        <button className="flex items-center gap-0.5 px-1 py-[2px] rounded text-[#515154] text-[9px] flex-shrink-0">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 17l4-8 4 4 4-6 4 4"/></svg>
          Indicadores
        </button>
        <div className="flex-1" />
        <button className="p-[3px] rounded text-[#515154] flex-shrink-0">
          <Maximize2 className="w-[10px] h-[10px]" />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Left drawing toolbar — calco de ChartToolbar */}
        <div className="w-[24px] flex-shrink-0 flex flex-col items-center gap-[2px] py-1 bg-[#050505] border-r border-[#0d0d0d]">
          {[
            <><path d="M5 3l14 9-7 1-4 7-3-17z" fill="currentColor" stroke="none"/></>,
            <><line x1="4" y1="20" x2="20" y2="4"/><circle cx="4" cy="20" r="1.5" fill="currentColor"/><circle cx="20" cy="4" r="1.5" fill="currentColor"/></>,
            <><line x1="3" y1="12" x2="21" y2="12"/></>,
            <><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="17" x2="21" y2="17"/></>,
            <><rect x="4" y="6" width="16" height="12" rx="1"/></>,
            <><line x1="5" y1="6" x2="19" y2="6"/><line x1="12" y1="6" x2="12" y2="18"/></>,
          ].map((paths, i) => (
            <button key={i} className={`w-[20px] h-[20px] flex items-center justify-center rounded ${i === 0 ? 'text-[#2997ff] bg-[#2997ff]/10' : 'text-[#515154] hover:bg-[#111111]'}`}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">{paths}</svg>
            </button>
          ))}
          <div className="flex-1" />
          <button className="w-[20px] h-[20px] flex items-center justify-center rounded text-[#515154] mb-1">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="7"/><line x1="16" y1="16" x2="21" y2="21"/>
              <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
            </svg>
          </button>
        </div>

        <div className="relative flex-1 overflow-hidden min-h-0 bg-[#050505]">
          {/* OHLC Legend — calco del TradingChart */}
          <div className="absolute top-1 left-1 z-10 flex items-center gap-[4px] pointer-events-none flex-wrap" style={{ maxWidth: '86%' }}>
            <div className="w-[13px] h-[13px] rounded-sm bg-[#2997ff] flex items-center justify-center flex-shrink-0">
              <span className="text-white font-bold" style={{ fontSize: 6 }}>N</span>
            </div>
            <span className="text-[9.5px] font-semibold text-[#e8e8ed]">NVIDIA</span>
            <span className="text-[8.5px] text-[#515154]">NASDAQ</span>
            <span className="text-[8.5px] text-[#515154]">O<span className="text-[#e8e8ed]/80 font-medium">882</span></span>
            <span className="text-[8.5px] text-[#515154]">H<span className="text-emerald-500 font-medium">915</span></span>
            <span className="text-[8.5px] text-[#515154]">L<span className="text-rose-500 font-medium">879</span></span>
            <span className="text-[8.5px] text-[#515154]">C<span className="text-[#e8e8ed]/80 font-medium">913</span></span>
            <span className="text-[8.5px] font-semibold text-emerald-500">+3.52%</span>
          </div>
          {/* Indicator legend */}
          <div className="absolute top-[17px] left-1 z-10 flex items-center gap-2.5 pointer-events-none">
            <div className="flex items-center gap-1">
              <span className="w-4 h-[2px] rounded" style={{ background: '#f59e0b', opacity: 0.8 }} />
              <span className="text-[8px] text-[#515154]">VWAP</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-4 h-[2px] rounded bg-violet-400" />
              <span className="text-[8px] text-[#515154]">EMA9</span>
            </div>
          </div>

          <svg viewBox={`0 0 ${SVG_W} ${CHART_H + VOL_H}`} preserveAspectRatio="none" className="w-full h-full">
            <rect x="0" y="0" width={preMarketEnd} height={CHART_H} fill="#050d1f" opacity="0.8"/>
            {GRID_PRICES.map((p) => <line key={p} x1="0" y1={pY(p)} x2={SVG_W} y2={pY(p)} stroke="#111116" strokeWidth="0.5"/>)}
            {[5,10,15,20,25].map((i) => <line key={i} x1={cX(i)} y1="0" x2={cX(i)} y2={CHART_H} stroke="#0e0e12" strokeWidth="0.5"/>)}
            <line x1={preMarketEnd} y1="0" x2={preMarketEnd} y2={CHART_H} stroke="#2997ff" strokeWidth="0.6" strokeDasharray="2,3" opacity="0.4"/>
            <polyline points={vwapPoints} fill="none" stroke="#f59e0b" strokeWidth="0.9" opacity="0.75" strokeDasharray="5,3"/>
            <polyline points={ema9Points} fill="none" stroke="#a78bfa" strokeWidth="0.8" opacity="0.7"/>
            {VOLS.map((v, i) => {
              const isGreen = CANDLES_DATA[i][1] >= CANDLES_DATA[i][0];
              const barH = Math.max(1, v * (VOL_H - 3));
              return <rect key={i} x={cX(i)} y={CHART_H + VOL_H - barH} width={BODY_W} height={barH} fill={isGreen ? '#10b981' : '#ef4444'} fillOpacity="0.32"/>;
            })}
            <line x1="0" y1={CHART_H} x2={SVG_W} y2={CHART_H} stroke="#111116" strokeWidth="0.5"/>
            {CANDLES_DATA.map((c, i) => {
              const isGreen = c[1] >= c[0];
              const color = isGreen ? '#10b981' : '#ef4444';
              const top = Math.min(pY(c[0]), pY(c[1])), bot = Math.max(pY(c[0]), pY(c[1]));
              const h = Math.max(1, bot - top), isLast = i === N - 1;
              return (
                <g key={i}>
                  <line x1={cMX(i)} y1={pY(c[2])} x2={cMX(i)} y2={pY(c[3])} stroke={color} strokeWidth="0.7"/>
                  <rect x={cX(i)} y={top} width={BODY_W} height={h}
                    fill={color} fillOpacity={isGreen ? (isLast ? 0.45 : 0.85) : (isLast ? 0.35 : 0.78)}
                    stroke={isLast ? color : 'none'} strokeWidth={isLast ? '0.6' : '0'} strokeDasharray={isLast ? '3,2' : 'none'}/>
                </g>
              );
            })}
            <line x1={cX(N - 1) + BODY_W} y1={pY(913)} x2={SVG_W} y2={pY(913)} stroke="#2997ff" strokeWidth="0.7" strokeDasharray="3,2"/>
            <rect x={SVG_W - 40} y={pY(913) - 6} width={38} height={12} fill="#2997ff" rx="1"/>
            <text x={SVG_W - 21} y={pY(913) + 3.8} textAnchor="middle" fill="white" fontSize="6.5" fontFamily="monospace" fontWeight="700">913.00</text>
          </svg>

          {/* Price scale overlay */}
          <div className="absolute top-0 right-0 bottom-0 w-[42px] flex flex-col justify-between py-1 pr-1 pointer-events-none">
            {[...GRID_PRICES].reverse().map((p) => (
              <span key={p} className="text-[7px] text-[#515154]/70 font-mono text-right tabular-nums">{p}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AI AGENT — calco de AIAgentContent.tsx
// El FloatingWindowChrome muestra "AI Agent" (sin live dot)
// El contenido tiene su propio sub-header interno: px-4 py-2 con History/Chat/Pipeline/Live
// ─────────────────────────────────────────────────────────────────────────────

function MockAIAgent({ showUserMsg, streamedText, stepsVisible }: {
  showUserMsg: boolean; streamedText: string; stepsVisible: number;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [streamedText, stepsVisible]);

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0a0a0a] overflow-hidden">
      {/* Header interno — calco EXACTO de AIAgentContent.tsx línea 284:
          px-4 py-2 border-b border-border bg-surface/60 backdrop-blur-sm */}
      <div className="flex-shrink-0 px-4 py-2 border-b border-[#1d1d1f] bg-[#0a0a0a]/60 backdrop-blur-sm flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button className={`p-1.5 rounded-lg text-[#515154] hover:text-[#e8e8ed]/80 hover:bg-[#111111] transition-all`}>
            <History className="w-4 h-4" />
          </button>
          <span className="text-[12px] font-medium text-[#e8e8ed]">Chat</span>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <button className="text-[#515154] hover:text-[#e8e8ed]/80 transition-colors">Pipeline</button>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
            <span className="text-[#515154]">Live</span>
          </div>
        </div>
      </div>

      {/* Scrollable conversation */}
      <div ref={scrollRef} className="flex-1 overflow-hidden px-4 py-3 min-h-0">
        <AnimatePresence>
          {!showUserMsg && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <p className="text-[11px] font-semibold text-[#e8e8ed] mb-1.5">¿Qué quieres analizar?</p>
              <p className="text-[9.5px] text-[#515154] mb-3 leading-relaxed">Sistema multi-agente: mercados, screeners, financials y noticias en tiempo real.</p>
              <div className="grid grid-cols-2 gap-1.5">
                {['Top Gainers', 'Gap Analysis', 'Unusual Volume', 'Bull Flags'].map((a) => (
                  <button key={a} className="px-2 py-2 bg-[#0d0d0d] border border-[#1d1d1f] rounded-lg text-left hover:border-[#2997ff]/30 transition-all">
                    <span className="text-[9.5px] font-medium text-[#e8e8ed] block">{a}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showUserMsg && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}
              className="flex justify-end mb-3">
              <div className="bg-[#2997ff]/12 border border-[#2997ff]/25 rounded-2xl px-3.5 py-2.5 max-w-[90%]">
                <p className="text-[11px] text-[#e8e8ed]">Analyze NVDA — unusual volume and gap setup</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {stepsVisible > 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-1">
              <div className="flex flex-col gap-[4px] mb-2">
                {AI_STEPS.slice(0, stepsVisible).map((step, i) => (
                  <motion.div key={i} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }}
                    className="flex items-center gap-1.5">
                    <div className="w-[5px] h-[5px] rounded-full bg-emerald-500 flex-shrink-0" />
                    <span className="text-[9px] text-[#515154] line-through">{step}</span>
                  </motion.div>
                ))}
              </div>
              {streamedText.length > 0 && (
                <div className="text-[10px] text-[#e8e8ed] leading-relaxed">
                  {streamedText}
                  <span className="inline-block w-[1.5px] h-[10px] bg-[#2997ff] ml-0.5 animate-pulse align-middle" />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input — calco textarea del AIAgentContent */}
      <div className="flex-shrink-0 border-t border-[#1d1d1f] bg-[#0a0a0a]/80 backdrop-blur-xl px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center px-3.5 py-2 bg-[#111111] border border-[#1d1d1f] rounded-2xl gap-2">
            <span className="text-[9px] font-mono text-[#515154] select-none">/</span>
            <span className="text-[10px] text-[#515154] flex-1">Escribe tu consulta o / para comandos...</span>
          </div>
          <button className="flex-shrink-0 px-3 py-2 text-[11px] font-medium text-[#515154] bg-[#111111] border border-[#1d1d1f] rounded-2xl hover:text-[#e8e8ed] transition-all">
            Enviar
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// OPENUL — calco de OpenULContent.tsx
// SIN header interno (el header está en el FloatingWindowChrome vía HeaderPortal)
// Los items se muestran NEWEST FIRST (los nuevos aparecen ARRIBA)
// Footer en la parte inferior: "N items · ET | openul v1.0"
// ─────────────────────────────────────────────────────────────────────────────

function MockOpenUL({ items, totalShown }: { items: typeof NEWS_ITEMS; totalShown: number }) {
  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0a0a0a] overflow-hidden">
      {/* Feed — newest first, new items slide in from top */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence initial={false}>
          {items.map((item) => (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="border-b border-[#0d0d0d]"
            >
              {item.type === 'reaction' ? (
                /* ReactionItem — calco exacto de ReactionItem */
                <div className="px-3 py-1.5 bg-emerald-500/10 border-b border-[#0d0d0d]">
                  <div className="flex items-center gap-1.5">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2" className="flex-shrink-0">
                      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
                      <polyline points="17 6 23 6 23 12"/>
                    </svg>
                    <span className="text-[10px] font-bold text-emerald-400">REACTION</span>
                    <button className="text-[10px] font-bold text-emerald-400 bg-emerald-500/15 border border-emerald-500/40 rounded px-0.5 py-px cursor-pointer">
                      ${item.ticker}
                    </button>
                    <span className="text-[10px] font-bold text-emerald-400 font-mono">▲ +{item.pct}%</span>
                    <span className="text-[10px] font-mono text-[#e8e8ed]/80">${item.price}</span>
                    <span className="text-[9px] text-[#515154] ml-auto font-mono">{item.time}</span>
                  </div>
                </div>
              ) : (
                /* NewsItem — calco exacto de NewsItem */
                <div className="px-3 py-2">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#515154]">
                      <circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/>
                    </svg>
                    <span className="text-[9px] font-mono text-[#515154]">{item.time} ET</span>
                  </div>
                  <div className="text-[10.5px] leading-[1.5] text-[#e8e8ed]">
                    <div className="flex items-start gap-1.5">
                      {/* BreakingDot — calco exacto */}
                      <span className="inline-flex items-center justify-center w-3 h-3 rounded-full bg-red-600 flex-shrink-0 mt-[2px]">
                        <span className="w-1.5 h-1.5 rounded-full bg-white" />
                      </span>
                      <span>
                        {item.tickers?.map((t) => (
                          <button key={t} className="inline-flex items-center px-0.5 mx-px text-[10px] font-bold text-[#2997ff] bg-[#2997ff]/10 border border-[#1d1d1f] rounded hover:bg-[#2997ff]/15 transition-colors mr-1">
                            ${t}
                          </button>
                        ))}
                        {item.text}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Footer — calco del footer de OpenULContent */}
      <div className="flex items-center justify-between px-3 py-[3px] border-t border-[#1d1d1f] bg-[#080808] flex-shrink-0">
        <span className="text-[8px] font-mono text-[#515154]">{totalShown} items · ET</span>
        <span className="text-[8px] font-mono text-[#515154]/50">openul v1.0</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// NAVBAR PIECES — calco exacto
// ─────────────────────────────────────────────────────────────────────────────

const PINNED_CMDS = ['SC', 'EVN', 'AI', 'CHT', 'UL'];

function MockMarketStatus() {
  const [tick, setTick] = useState(0);
  useEffect(() => { const id = setInterval(() => setTick((t) => t + 1), 1000); return () => clearInterval(id); }, []);
  const total = 9 * 3600 + 31 * 60 + 42 + tick;
  const h = Math.floor(total / 3600) % 24, m = Math.floor((total % 3600) / 60), s = total % 60;
  const time = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return (
    <div className="flex items-center gap-1.5 px-2 py-[3px] rounded-sm cursor-pointer hover:bg-[#111111] transition-colors">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0 animate-pulse" />
      <span className="text-[11px] font-mono font-medium text-[#e8e8ed] tabular-nums leading-none">{time}</span>
      <span className="text-[9px] font-semibold uppercase tracking-wider text-emerald-600 leading-none">OPEN</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN — DashboardHero
// ─────────────────────────────────────────────────────────────────────────────

type FeedItem = (typeof NEWS_ITEMS)[number];

// Breaking news pool — se usa para simular feed vivo (nuevos items llegando al top)
type PoolItem =
  | { type: 'news'; text: string; tickers: string[] }
  | { type: 'reaction'; ticker: string; pct: number; price: number };

const NEWS_POOL: PoolItem[] = [
  { type: 'news',     text: 'AAPL announces $110B share buyback program',     tickers: ['AAPL'] },
  { type: 'reaction', ticker: 'AAPL', pct: 2.4, price: 189.40 },
  { type: 'news',     text: 'MSFT Q3 cloud revenue beats estimates by 3.1%',   tickers: ['MSFT'] },
  { type: 'news',     text: 'Powell cites cooling labor market in FOMC press', tickers: [] },
  { type: 'reaction', ticker: 'MSFT', pct: 1.9, price: 415.20 },
  { type: 'news',     text: 'TSLA delivers record 466k vehicles in Q2',        tickers: ['TSLA'] },
  { type: 'reaction', ticker: 'TSLA', pct: 3.1, price: 248.50 },
  { type: 'news',     text: 'COIN surges after favorable SEC ruling on BTC',   tickers: ['COIN'] },
  { type: 'reaction', ticker: 'NVDA', pct: 1.4, price: 912.40 },
];

export function DashboardHero() {
  // Solo animaciones internas: flash de precios, stream del agente, llegada de breaking news.
  // Las VENTANAS están siempre presentes — no hay cascada de entrada.
  const [aiLoopKey, setAiLoopKey]     = useState(0);
  const [showUserMsg, setShowUserMsg] = useState(false);
  const [aiText, setAiText]           = useState('');
  const [aiSteps, setAiSteps]         = useState(0);
  const [flashRow, setFlashRow]       = useState<string | null>(null);

  // Feed inicial (newest first, ya invertido). Después se van insertando items al top.
  const [newsFeed, setNewsFeed] = useState<FeedItem[]>(() => [...NEWS_ITEMS].reverse());

  // Loop del AI Agent + flashes de precio (reinicia cada ciclo)
  useEffect(() => {
    setShowUserMsg(false); setAiText(''); setAiSteps(0); setFlashRow(null);

    const timers: ReturnType<typeof setTimeout>[] = [];
    const t = (delay: number, fn: () => void) => { timers.push(setTimeout(fn, delay)); };

    // Ciclo conversación — el usuario escribe, el agente piensa y responde en streaming
    t(1400, () => setShowUserMsg(true));
    t(1700, () => setAiSteps(1));
    t(2000, () => setAiSteps(2));
    t(2300, () => setAiSteps(3));
    const streamStart = 2600;
    for (let i = 0; i < AI_RESPONSE.length; i++) {
      t(streamStart + i * 13, () => setAiText(AI_RESPONSE.slice(0, i + 1)));
    }
    const streamEnd = streamStart + AI_RESPONSE.length * 13;

    // Flashes verdes en el scanner (LED de cambio de precio) — independientes del ciclo
    const flashTicker = (ticker: string, delay: number) => {
      t(delay, () => {
        setFlashRow(ticker);
        timers.push(setTimeout(() => setFlashRow(null), 650));
      });
    };
    flashTicker('CLOV', 800);
    flashTicker('NVDA', 2200);
    flashTicker('IONQ', 3600);
    flashTicker('SMCI', 5000);
    flashTicker('AMD',  6400);
    flashTicker('PLTR', 7800);

    t(streamEnd + 3500, () => setAiLoopKey((k) => k + 1));
    return () => timers.forEach(clearTimeout);
  }, [aiLoopKey]);

  // Feed de OpenUL — cada 5s llega un breaking news al top (animación de entrada real)
  useEffect(() => {
    let idx = 0;
    const fmt = (n: number) => String(n).padStart(2, '0');
    const nowTime = () => {
      const d = new Date();
      return `${fmt(d.getHours())}:${fmt(d.getMinutes())}:${fmt(d.getSeconds())}`;
    };
    const interval = setInterval(() => {
      const p = NEWS_POOL[idx % NEWS_POOL.length];
      idx++;
      const next: FeedItem = p.type === 'news'
        ? { id: Date.now() + idx, type: 'news', time: nowTime(), text: p.text, tickers: p.tickers, breaking: true }
        : { id: Date.now() + idx, type: 'reaction', time: nowTime(), ticker: p.ticker, pct: p.pct, price: p.price };
      setNewsFeed((prev) => [next, ...prev].slice(0, 6));
    }, 5500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full max-w-[1060px] mx-auto">
      <div className="relative">
        <div className="absolute -inset-6 bg-gradient-to-r from-blue-600/10 via-violet-600/6 to-blue-600/10 blur-3xl rounded-3xl pointer-events-none" />

        <div className="relative h-[560px] rounded-xl overflow-hidden border border-[#1d1d1f] bg-[#080808] shadow-2xl shadow-black/70 flex flex-col">
          {/* ── NAVBAR ── */}
          <nav className="h-10 bg-[#080808]/90 backdrop-blur-sm border-b border-[#1d1d1f] flex items-center px-3 gap-2 flex-shrink-0">
            <div className="flex items-center gap-1.5 w-[260px] flex-shrink-0">
              <span className="text-[#515154] font-mono text-[11px] select-none">{'>'}</span>
              <div className="flex items-center flex-1 px-1.5 py-[3px] rounded-sm bg-[#0d0d0d] border border-[#1d1d1f]">
                <span className="font-mono text-[10px] text-[#515154]">command</span>
                <span className="inline-block w-[1.5px] h-3 bg-[#2997ff] ml-0.5 animate-pulse align-middle" />
              </div>
            </div>
            <div className="w-px h-5 bg-[#1d1d1f] mx-1 flex-shrink-0" />
            <div className="flex-1 flex justify-center">
              <div className="flex items-center gap-0.5">
                {PINNED_CMDS.map((cmd) => (
                  <button key={cmd} className="px-2 py-[2px] rounded-sm text-[9px] font-medium tracking-wide text-[#2997ff] bg-[#2997ff]/10 hover:bg-[#2997ff]/15 transition-colors">
                    {cmd}
                  </button>
                ))}
                <button className="p-[3px] rounded-sm hover:bg-[#111111] ml-0.5">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                    className="w-[10px] h-[10px] text-[#515154]" style={{ transform: 'rotate(45deg)' }}>
                    <path d="M9.5 2.5L13.5 6.5L11 9L11.5 13L8 9.5L4.5 13L5 9L2.5 6.5L6.5 2.5L9.5 2.5Z"/>
                  </svg>
                </button>
              </div>
            </div>
            <div className="w-px h-5 bg-[#1d1d1f] mx-1 flex-shrink-0" />
            <MockMarketStatus />
            <div className="w-6 h-6 rounded-full bg-[#2997ff]/15 border border-[#2997ff]/25 flex items-center justify-center flex-shrink-0 ml-1">
              <span className="text-[8px] font-bold text-[#2997ff]">TR</span>
            </div>
          </nav>

          {/* ── CONTENT — 3 columns ── */}
          <div className="flex-1 relative overflow-hidden bg-[#040404]">

            {/* COL 1 top: Gappers Up Scanner — siempre presente, solo flash interno en las filas */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#0a0a0a] overflow-hidden flex flex-col shadow-xl"
              style={{ left: 8, top: 8, width: 306, height: 240 }}
            >
              <MarketTableLayoutHeader title="Gappers Up" />
              <ScannerColHeaders />
              <div className="flex-1 overflow-hidden">
                {SCANNER_ROWS.map((row) => (
                  <ScannerRow key={row.sym} row={row} flash={flashRow === row.sym} />
                ))}
              </div>
            </div>

            {/* COL 1 bottom: Momentum Up Scanner — siempre presente */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#0a0a0a] overflow-hidden flex flex-col shadow-xl"
              style={{ left: 8, top: 256, width: 306, bottom: 8 }}
            >
              <MarketTableLayoutHeader title="Momentum Up" />
              <MomentumColHeaders />
              <div className="flex-1 overflow-hidden">
                {MOMENTUM_ROWS.map((row) => (
                  <MomentumRow key={row.sym} row={row} />
                ))}
              </div>
            </div>

            {/* COL 2 top: Chart — siempre presente */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#050505] overflow-hidden flex flex-col shadow-xl"
              style={{ left: 322, right: 348, top: 8, height: 240 }}
            >
              <FloatingWindowChrome
                title="Chart"
                extra={
                  <div className="flex items-center gap-1">
                    <div className="w-[13px] h-[13px] rounded-sm bg-[#2997ff] flex items-center justify-center flex-shrink-0">
                      <span className="text-white font-bold" style={{ fontSize: 6 }}>N</span>
                    </div>
                    <span className="text-[10px] font-medium text-[#e8e8ed]">NVDA</span>
                    <span className="text-[9px] text-emerald-500 font-mono font-semibold">+3.52%</span>
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[#515154]">
                      <path d="M19 9l-7 7-7-7"/>
                    </svg>
                  </div>
                }
              />
              <MockChart />
            </div>

            {/* COL 2 bottom: Bull Flag Momentum — siempre presente */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#0a0a0a] overflow-hidden flex flex-col shadow-xl"
              style={{ left: 322, right: 348, top: 256, bottom: 8 }}
            >
              <MarketTableLayoutHeader
                title="Daily Breakout BF"
                showLive={false}
                extra={<Star className="w-[10px] h-[10px] text-amber-400 ml-1 flex-shrink-0" />}
              />
              <BullFlagColHeaders />
              <div className="flex-1 overflow-hidden">
                {BULL_FLAG_ROWS.map((row) => (
                  <BullFlagRow key={row.sym} row={row} />
                ))}
              </div>
            </div>

            {/* COL 3 top: AI Agent — siempre presente, animación solo dentro (streaming, pipeline) */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#0a0a0a] overflow-hidden flex flex-col shadow-xl"
              style={{ right: 8, width: 340, top: 8, height: 240 }}
            >
              <FloatingWindowChrome title="AI Agent" />
              <MockAIAgent showUserMsg={showUserMsg} streamedText={aiText} stepsVisible={aiSteps} />
            </div>

            {/* COL 3 bottom: OpenUL — siempre presente, breaking news entra al top en intervalos */}
            <div
              className="absolute rounded-lg border border-[#1d1d1f] bg-[#0a0a0a] overflow-hidden flex flex-col shadow-xl"
              style={{ right: 8, width: 340, top: 256, bottom: 8 }}
            >
              <FloatingWindowChrome
                title="Openul"
                extra={
                  <div className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                    <span className="text-[9px] font-mono text-[#515154]">{newsFeed.length} today</span>
                  </div>
                }
              />
              <MockOpenUL items={newsFeed} totalShown={newsFeed.length} />
            </div>

          </div>

          {/* ── WORKSPACE TABS — calco exacto de WorkspaceTabs.tsx ── */}
          <div className="h-7 bg-[#080808]/60 backdrop-blur-md border-t border-white/[0.05] flex items-center flex-shrink-0 select-none">
            {['Main', 'Scalping', 'Bull Flag', 'Swing'].map((ws, i) => (
              <div key={ws} className={`relative flex items-center h-full px-[10px] border-r border-white/[0.05] cursor-pointer transition-colors duration-100 ${
                i === 0 ? 'bg-[#2997ff]/8 text-[#2997ff]' : 'text-[#515154] hover:bg-white/[0.03] hover:text-[#e8e8ed]'
              }`}>
                {i === 0 && <div className="absolute top-0 left-0 right-0 h-[2px] bg-blue-500" />}
                <span className="text-[11px] whitespace-nowrap font-mono">{ws}</span>
              </div>
            ))}
            <button className="flex items-center justify-center px-3 h-full text-[#515154] hover:text-[#2997ff] border-l border-white/[0.05] text-sm transition-colors">+</button>
            <div className="flex-1" />
          </div>

        </div>
      </div>
    </div>
  );
}
