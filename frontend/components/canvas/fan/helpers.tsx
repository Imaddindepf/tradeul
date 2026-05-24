'use client';

import { Loader2 } from 'lucide-react';

export const fmt = (n: number | null | undefined, d = 2) =>
    n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

export const pct = (n: number | null | undefined) =>
    n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n)}%`;

export const money = (n: number | null | undefined) =>
    n == null ? '—' : `$${fmt(n, 0)}`;

export const ratingColor = (r: string | null | undefined) => {
    if (!r) return 'text-muted-fg';
    const l = r.toLowerCase();
    if (l.includes('strong buy') || l.includes('overweight') || l.includes('outperform')) return 'text-emerald-500';
    if (l.includes('buy') || l.includes('bullish') || l.includes('positive')) return 'text-green-500';
    if (l.includes('hold') || l.includes('neutral')) return 'text-amber-500';
    if (l.includes('sell') || l.includes('underweight') || l.includes('bearish') || l.includes('negative')) return 'text-red-500';
    return 'text-muted-fg';
};

export const gradeColor = (g: string | undefined) => {
    if (!g) return 'text-muted-fg';
    if (g.startsWith('A')) return 'text-emerald-500';
    if (g.startsWith('B')) return 'text-blue-500';
    if (g.startsWith('C')) return 'text-amber-500';
    return 'text-red-500';
};

export function Row({ label, value, valueClass = '', loading }: {
    label: string; value: React.ReactNode; valueClass?: string; loading?: boolean;
}) {
    return (
        <div className="flex justify-between items-center leading-[18px]">
            <span className="text-[10px] text-foreground/80">{label}</span>
            {loading ? (
                <span className="text-[10px] text-muted-fg/50">...</span>
            ) : (
                <span className={`text-[10px] font-medium tabular-nums ${valueClass || 'text-foreground'}`}>{value}</span>
            )}
        </div>
    );
}

export function GeminiLoading({ text }: { text: string }) {
    return (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-fg">
            <Loader2 className="w-3 h-3 animate-spin text-primary" />
            <span>{text}</span>
        </div>
    );
}
