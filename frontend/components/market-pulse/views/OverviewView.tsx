import { memo, useMemo } from 'react';
import type { PulseViewProps } from '../types';

const B = '#2563eb';
const R = '#ec4899';

function pct(v: number) { return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`; }
function fmtB(v: number) { return v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`; }
function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }

function Bar({ value, min, max, diverging }: { value: number; min: number; max: number; diverging?: boolean }) {
  if (diverging) {
    const norm = clamp((value - (min + max) / 2) / (((max - min) / 2) || 1), -1, 1);
    const w = Math.abs(norm) * 50;
    const pos = norm >= 0;
    return (
      <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100 relative">
        <div className="absolute top-0 left-1/2 h-full w-px bg-slate-200" />
        <div className={`absolute top-0 bottom-0 rounded-sm ${pos ? 'left-1/2' : 'right-1/2'}`}
          style={{ width: `${w}%`, backgroundColor: pos ? B : R }} />
      </div>
    );
  }
  const norm = clamp((value - min) / ((max - min) || 1), 0, 1);
  return (
    <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100">
      <div className="h-full rounded-sm" style={{ width: `${norm * 100}%`, backgroundColor: B }} />
    </div>
  );
}

function OverviewView({ data }: PulseViewProps) {
  const m = useMemo(() => {
    if (!data.length) return null;
    const totalCount = data.reduce((s, d) => s + d.count, 0);
    const totalAdv = data.reduce((s, d) => s + d.advancing, 0);
    const totalDec = data.reduce((s, d) => s + d.declining, 0);
    const totalMcap = data.reduce((s, d) => s + d.total_market_cap, 0);
    const totalDv = data.reduce((s, d) => s + d.total_dollar_volume, 0);

    const wtdChange = totalMcap > 0 ? data.reduce((s, d) => s + d.weighted_change * d.total_market_cap, 0) / totalMcap : 0;
    const eqChange = totalCount > 0 ? data.reduce((s, d) => s + d.avg_change * d.count, 0) / totalCount : 0;
    const adRatio = totalDec > 0 ? totalAdv / totalDec : 0;

    const wavg = (key: keyof typeof data[0]) =>
      totalCount > 0 ? data.reduce((s, d) => s + (d[key] as number) * d.count, 0) / totalCount : 0;

    const rsi = wavg('avg_daily_rsi');
    const adx = wavg('avg_daily_adx');
    const bb = wavg('avg_bb_position');
    const sma20 = wavg('avg_dist_sma20');
    const sma50 = wavg('avg_dist_sma50');
    const volPct = wavg('avg_vol_today_pct');
    const c5 = wavg('avg_change_5d');
    const c10 = wavg('avg_change_10d');
    const c20 = wavg('avg_change_20d');
    const h52 = wavg('avg_from_52w_high');
    const l52 = wavg('avg_from_52w_low');

    const sectors = [...data].sort((a, b) => b.weighted_change - a.weighted_change);

    return {
      wtdChange, eqChange, spread: wtdChange - eqChange,
      adRatio, totalAdv, totalDec, totalDv, volPct, totalCount,
      rsi, adx, bb, sma20, sma50,
      c5, c10, c20, h52, l52,
      sectors,
    };
  }, [data]);

  if (!m) return (
    <div className="flex-1 flex items-center justify-center text-[12px] text-slate-400">No data</div>
  );

  const vColor = (v: number) => v >= 0 ? 'text-blue-600' : 'text-rose-500';

  return (
    <div className="flex-1 overflow-auto px-3 py-2 space-y-2">
      {/* Market Summary */}
      <div className="border border-slate-150 rounded-md px-3 py-2">
        <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Market Summary</div>
        <div className="grid grid-cols-3 gap-x-4 gap-y-1.5">
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Cap-Weighted</div>
            <div className={`text-[16px] font-bold tabular-nums leading-tight ${vColor(m.wtdChange)}`}>{pct(m.wtdChange)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Equal-Weight</div>
            <div className={`text-[14px] font-bold tabular-nums leading-tight ${vColor(m.eqChange)}`}>{pct(m.eqChange)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Spread</div>
            <div className={`text-[14px] font-bold tabular-nums leading-tight ${vColor(m.spread)}`}>{pct(m.spread)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">A/D Ratio</div>
            <div className="text-[13px] font-bold tabular-nums leading-tight text-slate-800">{m.adRatio.toFixed(2)}</div>
            <div className="text-[8px] text-slate-400 tabular-nums">{m.totalAdv.toLocaleString()} vs {m.totalDec.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Dollar Volume</div>
            <div className="text-[13px] font-bold tabular-nums leading-tight text-slate-800">{fmtB(m.totalDv)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Vol % Done</div>
            <div className="flex items-center gap-1.5">
              <div className="flex-1 h-[6px] rounded-full bg-slate-100 overflow-hidden">
                <div className="h-full rounded-full bg-blue-500" style={{ width: `${clamp(m.volPct, 0, 100)}%` }} />
              </div>
              <span className="text-[11px] font-bold tabular-nums text-slate-700">{m.volPct.toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Technicals + Trend side by side */}
      <div className="grid grid-cols-2 gap-2">
        {/* Technicals */}
        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Technicals</div>
          <div className="space-y-1">
            {([
              ['RSI', m.rsi, 0, 100, false, m.rsi < 30 ? 'Oversold' : m.rsi > 70 ? 'Overbought' : 'Neutral'],
              ['ADX', m.adx, 0, 60, false, m.adx < 20 ? 'Weak' : m.adx < 40 ? 'Moderate' : 'Strong'],
              ['BB Pos', m.bb, 0, 100, false, m.bb < 20 ? 'Lower' : m.bb > 80 ? 'Upper' : 'Mid'],
              ['SMA20', m.sma20, -10, 10, true, ''],
              ['SMA50', m.sma50, -15, 15, true, ''],
            ] as [string, number, number, number, boolean, string][]).map(([label, val, mn, mx, div, tag]) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="text-[9px] font-medium text-slate-500 w-[34px] shrink-0">{label}</span>
                <Bar value={val} min={mn} max={mx} diverging={div} />
                <span className={`text-[10px] font-bold tabular-nums w-[42px] text-right shrink-0 ${div ? vColor(val) : 'text-slate-700'}`}>
                  {div ? pct(val) : val.toFixed(1)}
                </span>
                {tag && <span className="text-[7px] font-semibold text-slate-400 w-[38px] shrink-0 truncate">{tag}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Trend */}
        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Trend</div>
          <div className="space-y-1">
            {([
              ['Today', m.wtdChange],
              ['5 Day', m.c5],
              ['10 Day', m.c10],
              ['20 Day', m.c20],
              ['vs 52wH', m.h52],
              ['vs 52wL', m.l52],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="text-[9px] font-medium text-slate-500 w-[38px] shrink-0">{label}</span>
                <Bar value={val} min={-30} max={30} diverging />
                <span className={`text-[10px] font-bold tabular-nums w-[48px] text-right shrink-0 ${vColor(val)}`}>{pct(val)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sector Ranking */}
      <div className="border border-slate-150 rounded-md px-3 py-2">
        <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Sectors</div>
        <div className="space-y-[3px]">
          {m.sectors.map(s => {
            const maxAbs = Math.max(...m.sectors.map(x => Math.abs(x.weighted_change)), 0.1);
            const norm = clamp(s.weighted_change / maxAbs, -1, 1);
            const w = Math.abs(norm) * 100;
            const pos = norm >= 0;
            return (
              <div key={s.name} className="flex items-center gap-1.5 h-[18px]">
                <span className={`w-[3px] h-[3px] rounded-full shrink-0 ${pos ? 'bg-blue-500' : 'bg-rose-400'}`} />
                <span className="text-[10px] font-semibold text-slate-700 w-[95px] shrink-0 truncate">{s.name}</span>
                <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100 relative">
                  <div className="absolute top-0 left-1/2 h-full w-px bg-slate-200" />
                  <div className={`absolute top-0 bottom-0 rounded-sm ${pos ? 'left-1/2' : 'right-1/2'}`}
                    style={{ width: `${w / 2}%`, backgroundColor: pos ? B : R }} />
                </div>
                <span className={`text-[10px] font-bold tabular-nums w-[44px] text-right shrink-0 ${vColor(s.weighted_change)}`}>{pct(s.weighted_change)}</span>
                <span className="text-[8px] text-slate-400 tabular-nums w-[36px] text-right shrink-0">{(s.breadth * 100).toFixed(0)}% adv</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default memo(OverviewView);
