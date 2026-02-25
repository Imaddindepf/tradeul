import { memo, useMemo } from 'react';
import type { TickerContextData } from '@/hooks/useMarketPulse';
import { ExternalLink } from 'lucide-react';

const B = '#2563eb';
const R = '#ec4899';

function pct(v: number | null | undefined) {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}
function pct1(v: number | null | undefined) {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}
function num1(v: number | null | undefined) { return v != null ? v.toFixed(1) : '—'; }
function fmtVol(v: number | null | undefined) {
  if (v == null) return '—';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}
function fmtNum(v: number | null | undefined) {
  if (v == null) return '—';
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}
function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }
function vColor(v: number | null | undefined) { return v != null && v >= 0 ? 'text-blue-600' : 'text-rose-500'; }
function fmtTheme(n: string) { return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '); }

function DivBar({ value, min, max }: { value: number; min: number; max: number }) {
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

function PosBar({ value, min, max }: { value: number; min: number; max: number }) {
  const norm = clamp((value - min) / ((max - min) || 1), 0, 1);
  return (
    <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100">
      <div className="h-full rounded-sm" style={{ width: `${norm * 100}%`, backgroundColor: B }} />
    </div>
  );
}

function MetricRow({ label, value, min, max, diverging, fmt, tag }: {
  label: string; value: number | null | undefined; min: number; max: number;
  diverging?: boolean; fmt: (v: number | null | undefined) => string; tag?: string;
}) {
  if (value == null) return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[9px] font-medium text-slate-500 w-[38px] shrink-0">{label}</span>
      {diverging
        ? <DivBar value={value} min={min} max={max} />
        : <PosBar value={value} min={min} max={max} />}
      <span className={`text-[10px] font-bold tabular-nums w-[48px] text-right shrink-0 ${diverging ? vColor(value) : 'text-slate-700'}`}>
        {fmt(value)}
      </span>
      {tag && <span className="text-[7px] font-semibold text-slate-400 w-[42px] shrink-0 truncate">{tag}</span>}
    </div>
  );
}

interface Props {
  data: TickerContextData;
  onOpenTicker?: (sym: string) => void;
}

function TickerContextView({ data, onOpenTicker }: Props) {
  const t = data.ticker;

  const sectorIdx = useMemo(
    () => data.sectors_ranked.findIndex(s => s.name === data.sector),
    [data.sectors_ranked, data.sector],
  );

  const rsiTag = t.daily_rsi != null
    ? (t.daily_rsi < 30 ? 'Oversold' : t.daily_rsi > 70 ? 'Overbought' : 'Neutral')
    : undefined;
  const adxTag = t.daily_adx_14 != null
    ? (t.daily_adx_14 < 20 ? 'Weak' : t.daily_adx_14 < 40 ? 'Moderate' : 'Strong')
    : undefined;
  const bbTag = t.daily_bb_position != null
    ? (t.daily_bb_position < 20 ? 'Lower' : t.daily_bb_position > 80 ? 'Upper' : 'Mid')
    : undefined;

  return (
    <div className="flex-1 overflow-auto px-3 py-2 space-y-2">
      {/* ── Ticker Header ── */}
      <div className="border border-slate-150 rounded-md px-3 py-2">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => onOpenTicker?.(data.symbol)}
              className="text-[18px] font-black text-blue-600 hover:text-blue-800 transition-colors flex items-center gap-1"
            >
              {data.symbol}
              <ExternalLink className="w-3 h-3 text-blue-400" />
            </button>
            <span className="text-[10px] font-medium text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
              {data.sector}
            </span>
            <span className="text-[10px] font-medium text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
              {data.industry}
            </span>
          </div>
          {data.rank_in_industry && (
            <span className="text-[9px] font-semibold text-slate-500">
              #{data.rank_in_industry} of {data.industry_total} in {data.industry}
            </span>
          )}
        </div>
        <div className="grid grid-cols-5 gap-x-3 gap-y-1">
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Price</div>
            <div className="text-[16px] font-bold tabular-nums leading-tight text-slate-900">
              ${t.price != null ? (t.price >= 1 ? t.price.toFixed(2) : t.price.toFixed(4)) : '—'}
            </div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Change</div>
            <div className={`text-[16px] font-bold tabular-nums leading-tight ${vColor(t.change_percent)}`}>
              {pct(t.change_percent)}
            </div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Volume</div>
            <div className="text-[13px] font-bold tabular-nums leading-tight text-slate-800">{fmtNum(t.volume)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">Market Cap</div>
            <div className="text-[13px] font-bold tabular-nums leading-tight text-slate-800">{fmtVol(t.market_cap)}</div>
          </div>
          <div>
            <div className="text-[8px] text-slate-400 font-medium">RVOL</div>
            <div className="text-[13px] font-bold tabular-nums leading-tight text-slate-800">
              {t.rvol != null ? `${t.rvol.toFixed(1)}x` : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* ── Technicals + Trend side by side ── */}
      <div className="grid grid-cols-2 gap-2">
        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Technicals</div>
          <div className="space-y-1">
            <MetricRow label="RSI" value={t.daily_rsi} min={0} max={100} fmt={num1} tag={rsiTag} />
            <MetricRow label="ADX" value={t.daily_adx_14} min={0} max={60} fmt={num1} tag={adxTag} />
            <MetricRow label="BB Pos" value={t.daily_bb_position} min={0} max={100} fmt={num1} tag={bbTag} />
            <MetricRow label="dVWAP" value={t.dist_from_vwap} min={-5} max={5} diverging fmt={pct} />
            <MetricRow label="ATR%" value={t.atr_percent} min={0} max={10} fmt={pct1} />
            <MetricRow label="Gap" value={t.gap_percent} min={-5} max={5} diverging fmt={pct} />
            <MetricRow label="RPos" value={t.pos_in_range} min={0} max={100} fmt={num1} />
          </div>
        </div>

        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Trend</div>
          <div className="space-y-1">
            <MetricRow label="Today" value={t.change_percent} min={-10} max={10} diverging fmt={pct} />
            <MetricRow label="5 Day" value={t.change_5d} min={-15} max={15} diverging fmt={pct} />
            <MetricRow label="10 Day" value={t.change_10d} min={-20} max={20} diverging fmt={pct} />
            <MetricRow label="20 Day" value={t.change_20d} min={-25} max={25} diverging fmt={pct} />
            <MetricRow label="vs 52wH" value={t.from_52w_high} min={-50} max={0} diverging fmt={pct1} />
            <MetricRow label="vs 52wL" value={t.from_52w_low} min={0} max={100} fmt={pct1} />
          </div>
        </div>
      </div>

      {/* ── Sector Ranking (highlighting this ticker's sector) ── */}
      <div className="border border-slate-150 rounded-md px-3 py-2">
        <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Sectors</div>
        <div className="space-y-[3px]">
          {data.sectors_ranked.map((s, i) => {
            const maxAbs = Math.max(...data.sectors_ranked.map(x => Math.abs(x.weighted_change)), 0.1);
            const norm = clamp(s.weighted_change / maxAbs, -1, 1);
            const w = Math.abs(norm) * 100;
            const pos = norm >= 0;
            const isActive = i === sectorIdx;
            return (
              <div key={s.name} className={`flex items-center gap-1.5 h-[18px] rounded-sm px-0.5 ${isActive ? 'bg-blue-50 ring-1 ring-blue-200' : ''}`}>
                <span className={`w-[3px] h-[3px] rounded-full shrink-0 ${isActive ? 'bg-blue-600' : pos ? 'bg-blue-500' : 'bg-rose-400'}`} />
                <span className={`text-[10px] font-semibold w-[95px] shrink-0 truncate ${isActive ? 'text-blue-800' : 'text-slate-700'}`}>{s.name}</span>
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

      {/* ── Industry Peers ── */}
      {data.industry_peers.length > 0 && (
        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">
            Peers — {data.industry}
          </div>
          <div className="space-y-[2px]">
            {data.industry_peers.map(p => {
              const chg = p.change_percent || 0;
              const tickerChg = t.change_percent || 0;
              const relPerf = chg - tickerChg;
              return (
                <div key={p.symbol} className="flex items-center gap-2 h-[20px] group/peer">
                  <button
                    onClick={() => onOpenTicker?.(p.symbol)}
                    className="text-[10px] font-bold text-blue-600 hover:text-blue-800 w-[48px] shrink-0 text-left transition-colors"
                  >
                    {p.symbol}
                  </button>
                  <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100 relative">
                    <div className="absolute top-0 left-1/2 h-full w-px bg-slate-200" />
                    {(() => {
                      const maxAbs = Math.max(...data.industry_peers.map(x => Math.abs(x.change_percent || 0)), Math.abs(tickerChg), 0.1);
                      const norm = clamp(chg / maxAbs, -1, 1);
                      const w2 = Math.abs(norm) * 50;
                      const pos = norm >= 0;
                      return <div className={`absolute top-0 bottom-0 rounded-sm ${pos ? 'left-1/2' : 'right-1/2'}`}
                        style={{ width: `${w2}%`, backgroundColor: pos ? B : R }} />;
                    })()}
                  </div>
                  <span className={`text-[10px] font-bold tabular-nums w-[48px] text-right shrink-0 ${vColor(chg)}`}>{pct(chg)}</span>
                  <span className={`text-[8px] font-mono tabular-nums w-[40px] text-right shrink-0 ${vColor(relPerf)}`}>
                    {relPerf >= 0 ? '+' : ''}{relPerf.toFixed(2)}
                  </span>
                  <span className="text-[8px] text-slate-400 tabular-nums w-[40px] text-right shrink-0">{fmtVol(p.market_cap)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Themes ── */}
      {data.themes.length > 0 && (
        <div className="border border-slate-150 rounded-md px-3 py-2">
          <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">Themes</div>
          <div className="space-y-[3px]">
            {data.themes.map(th => {
              const maxAbs = Math.max(...data.themes.map(x => Math.abs(x.weighted_change)), 0.1);
              const norm = clamp(th.weighted_change / maxAbs, -1, 1);
              const w = Math.abs(norm) * 100;
              const pos = norm >= 0;
              return (
                <div key={th.name} className="flex items-center gap-1.5 h-[18px]">
                  <span className={`w-[3px] h-[3px] rounded-full shrink-0 ${pos ? 'bg-blue-500' : 'bg-rose-400'}`} />
                  <span className="text-[10px] font-semibold text-slate-700 w-[110px] shrink-0 truncate">{fmtTheme(th.name)}</span>
                  <div className="flex-1 h-[10px] rounded-sm overflow-hidden bg-slate-100 relative">
                    <div className="absolute top-0 left-1/2 h-full w-px bg-slate-200" />
                    <div className={`absolute top-0 bottom-0 rounded-sm ${pos ? 'left-1/2' : 'right-1/2'}`}
                      style={{ width: `${w / 2}%`, backgroundColor: pos ? B : R }} />
                  </div>
                  <span className={`text-[10px] font-bold tabular-nums w-[44px] text-right shrink-0 ${vColor(th.weighted_change)}`}>{pct(th.weighted_change)}</span>
                  <span className="text-[8px] text-slate-400 tabular-nums w-[20px] text-right shrink-0">{th.count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(TickerContextView);
