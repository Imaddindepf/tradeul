
'use client';

import { useState, useEffect, useMemo } from 'react';
import { useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';
import { useAuthFetch } from '@/hooks/useAuthFetch';
import { Star, RefreshCw, X, TrendingUp, TrendingDown } from 'lucide-react';
import type { UserFilter } from '@/lib/types/scannerFilters';

interface Props { scan: UserFilter; }
interface Ticker { symbol: string; price: number; change_percent: number; gap_percent: number; volume: number; rvol: number; }

function fmt(v: number | null): string {
    if (v == null) return '-';
    if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
    return String(v);
}

export function UserScanTableContent({ scan }: Props) {
    const closeCurrentWindow = useCloseCurrentWindow();
    const { authFetch } = useAuthFetch();
    const [tickers, setTickers] = useState<Ticker[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchTickers = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            Object.entries(scan.parameters || {}).forEach(([k, v]) => { if (v != null) params.append(k, String(v)); });
            const res = await authFetch('/api/scanner/filtered?' + params.toString());
            if (res.ok) setTickers((await res.json()).tickers || []);
        } catch (e) { console.error(e); }
        finally { setLoading(false); }
    };

    useEffect(() => { fetchTickers(); const i = setInterval(fetchTickers, 30000); return () => clearInterval(i); }, [scan.id]);

    const tags = useMemo(() => Object.entries(scan.parameters || {}).filter(([, v]) => v != null).map(([k, v]) => ({
        k, l: k.replace(/^(min_|max_)/, '').replace(/_/g, ' '), p: k.startsWith('min_') ? '>' : '<', v: fmt(v as number)
    })), [scan.parameters]);

    return (
        <div className="h-full flex flex-col bg-white">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-slate-50 table-drag-handle cursor-move">
                <div className="flex items-center gap-2"><Star className="w-4 h-4 text-amber-500" /><span className="font-semibold text-sm">{scan.name}</span><span className="text-xs text-slate-400">({tickers.length})</span></div>
                <div className="flex gap-1"><button onClick={fetchTickers} className="p-1 text-slate-400"><RefreshCw className={loading ? 'w-4 h-4 animate-spin' : 'w-4 h-4'} /></button><button onClick={closeCurrentWindow} className="p-1 text-slate-400 hover:text-red-500"><X className="w-4 h-4" /></button></div>
            </div>
            <div className="px-3 py-1 border-b bg-slate-50/50 flex flex-wrap gap-1">{tags.map(t => <span key={t.k} className="px-1.5 py-0.5 bg-white rounded text-[10px] border">{t.l} {t.p} {t.v}</span>)}</div>
            <div className="flex-1 overflow-auto">
                {loading && !tickers.length ? <div className="flex items-center justify-center h-full"><div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" /></div>
                    : !tickers.length ? <div className="flex flex-col items-center justify-center h-full text-slate-400"><Star className="w-8 h-8 mb-2 opacity-50" /><p className="text-sm">No tickers match</p></div>
                        : <table className="w-full text-xs"><thead className="sticky top-0 bg-slate-100"><tr><th className="text-left px-2 py-1.5">Symbol</th><th className="text-right px-2 py-1.5">Price</th><th className="text-right px-2 py-1.5">Chg%</th><th className="text-right px-2 py-1.5">Gap%</th><th className="text-right px-2 py-1.5">Vol</th><th className="text-right px-2 py-1.5">RVOL</th></tr></thead><tbody>{tickers.map(t => <tr key={t.symbol} className="border-b hover:bg-slate-50"><td className="px-2 py-1.5"><div className="flex items-center gap-1">{(t.change_percent || 0) >= 0 ? <TrendingUp className="w-3 h-3 text-green-500" /> : <TrendingDown className="w-3 h-3 text-red-500" />}<span className="font-medium">{t.symbol}</span></div></td><td className="text-right px-2 py-1.5 font-mono">${t.price?.toFixed(2)}</td><td className={(t.change_percent || 0) >= 0 ? 'text-right px-2 py-1.5 font-mono text-green-600' : 'text-right px-2 py-1.5 font-mono text-red-600'}>{(t.change_percent || 0) >= 0 ? '+' : ''}{t.change_percent?.toFixed(2)}%</td><td className={(t.gap_percent || 0) >= 0 ? 'text-right px-2 py-1.5 font-mono text-green-600' : 'text-right px-2 py-1.5 font-mono text-red-600'}>{(t.gap_percent || 0) >= 0 ? '+' : ''}{t.gap_percent?.toFixed(2)}%</td><td className="text-right px-2 py-1.5">{fmt(t.volume)}</td><td className="text-right px-2 py-1.5">{t.rvol?.toFixed(1)}x</td></tr>)}</tbody></table>}
            </div>
            <div className="px-3 py-1 border-t bg-slate-50 text-[10px] text-slate-400">Auto-refresh: 30s</div>
        </div>
    );
}
