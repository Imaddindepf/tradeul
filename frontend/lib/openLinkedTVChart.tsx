'use client';

import React from 'react';
import { TVChartContent } from '@/components/tvchart';
import type { LinkGroup } from '@/contexts/FloatingWindowContext';

type OpenWindowFn = (config: {
    title: string;
    content: React.ReactNode;
    width: number;
    height: number;
    x: number;
    y: number;
    minWidth: number;
    minHeight: number;
    linkGroup?: LinkGroup;
}) => string;

/** Abre TC (TradingView) ya unido a un link group — destino del click en SC/EVN/Screener. */
export function openLinkedTVChart(
    openWindow: OpenWindowFn,
    symbol: string,
    linkGroup: LinkGroup,
): string {
    const sw = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const sh = typeof window !== 'undefined' ? window.innerHeight : 1080;
    const sym = symbol.toUpperCase();
    return openWindow({
        title: `TradingView: ${sym}`,
        content: <TVChartContent initialSymbol={sym} />,
        width: Math.min(1100, sw - 120),
        height: Math.min(660, sh - 160),
        x: Math.max(50, sw / 2 - 550),
        y: Math.max(80, sh / 2 - 330),
        minWidth: 560,
        minHeight: 380,
        linkGroup: linkGroup ?? undefined,
    });
}

/** Elige el link group activo entre ventanas publisher (scanner / events / screener). */
export function pickActiveLinkGroup(
    windows: Array<{ title: string; linkGroup?: LinkGroup | null }>,
): LinkGroup {
    const counts = new Map<Exclude<LinkGroup, null>, number>();
    for (const w of windows) {
        const g = w.linkGroup;
        if (!g) continue;
        const isPublisher =
            w.title.startsWith('Scanner:') ||
            w.title.startsWith('Events:') ||
            w.title === 'Stock Screener';
        if (!isPublisher) continue;
        counts.set(g, (counts.get(g) ?? 0) + 1);
    }
    let best: LinkGroup = null;
    let bestN = 0;
    for (const [g, n] of counts) {
        if (n > bestN) {
            best = g;
            bestN = n;
        }
    }
    return best;
}
