'use client';

/**
 * AssetMonitorTable — motor compartido de los monitores de clase de activo
 * (FUT: futuros, FX: forex). Cada ventana es un componente propio que solo
 * define sus grupos y labels.
 *
 * Datos en dos capas, como las tablas del escáner:
 *   1. Seed + reconciliación: snapshot REST /api/v1/realtime/class/{clase}
 *      (nombres, previous_close, pares sin tick reciente) cada RECONCILE_MS.
 *   2. Tiempo real: subscribe_quotes por símbolo sobre el WebSocket
 *      autenticado compartido (AuthWebSocketProvider). Cada quote actualiza
 *      SOLO la fila afectada (useSyncExternalStore por símbolo) y las celdas
 *      LAST/CHG/CHG% flashean individualmente al cambiar su valor mostrado,
 *      estilo terminal profesional. CHG/CHG% se recalculan en cliente contra
 *      previous_close del snapshot.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';

const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

export interface MonitorGroup {
  title: string;
  symbols: string[];
}

export interface AssetEntry {
  symbol: string;
  name?: string | null;
  price: number;
  change?: number | null;
  change_percent?: number | null;
  previous_close?: number | null;
  day_low?: number | null;
  day_high?: number | null;
  updated_at?: number;
}

interface LiveEntry extends AssetEntry {
  /** Dirección del último cambio de precio (para el color del flash). */
  dir: 'up' | 'down' | null;
}

interface AssetMonitorTableProps {
  assetClass: 'future' | 'forex';
  groups: MonitorGroup[];
  labels?: Record<string, string>;
  /** Intervalo de reconciliación REST (el tiempo real va por WS). */
  pollMs?: number;
}

function formatPrice(value: number): string {
  if (value >= 1000) return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (value >= 100) return value.toFixed(2);
  if (value >= 1) return value.toFixed(4).replace(/0{1,2}$/, '');
  return value.toFixed(5);
}

function formatChange(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(3).replace(/0$/, '');
  return value.toFixed(5).replace(/0{1,2}$/, '');
}

// ─────────────────────────────────────────────────────────────────────────────
// MonitorEngine — estado por símbolo fuera de React: cada quote notifica solo
// a la fila de su símbolo, el resto de la tabla ni se entera.
// ─────────────────────────────────────────────────────────────────────────────
class MonitorEngine {
  private entries = new Map<string, LiveEntry>();
  private prevClose = new Map<string, number>();
  private rowListeners = new Map<string, Set<() => void>>();
  private metaListeners = new Set<() => void>();
  private meta = { lastUpdate: 0, count: 0 };

  subscribeRow(symbol: string, cb: () => void): () => void {
    let set = this.rowListeners.get(symbol);
    if (!set) this.rowListeners.set(symbol, (set = new Set()));
    set.add(cb);
    return () => { set!.delete(cb); };
  }

  getRow(symbol: string): LiveEntry | undefined {
    return this.entries.get(symbol);
  }

  subscribeMeta(cb: () => void): () => void {
    this.metaListeners.add(cb);
    return () => { this.metaListeners.delete(cb); };
  }

  getMeta() {
    return this.meta;
  }

  private notifyRow(symbol: string) {
    this.rowListeners.get(symbol)?.forEach((cb) => cb());
  }

  private bumpMeta(ts: number) {
    // El footer muestra hh:mm:ss — con re-render 1/seg basta
    const changed =
      this.entries.size !== this.meta.count ||
      Math.floor(ts / 1000) !== Math.floor(this.meta.lastUpdate / 1000);
    this.meta = { lastUpdate: ts, count: this.entries.size };
    if (changed) this.metaListeners.forEach((cb) => cb());
  }

  /** Snapshot REST: seed inicial y reconciliación periódica. */
  seed(list: AssetEntry[]) {
    let ts = this.meta.lastUpdate;
    for (const e of list) {
      if (!e.symbol || e.price == null) continue;
      const pc = e.previous_close ?? (e.change != null ? e.price - e.change : undefined);
      if (pc && pc > 0) this.prevClose.set(e.symbol, pc);
      const cur = this.entries.get(e.symbol);
      // El WS es la fuente caliente: el snapshot solo pisa si aporta algo nuevo
      if (cur && cur.price === e.price && cur.change === e.change) continue;
      this.entries.set(e.symbol, {
        ...cur,
        ...e,
        dir: cur && e.price !== cur.price ? (e.price > cur.price ? 'up' : 'down') : cur?.dir ?? null,
      });
      if (e.updated_at && e.updated_at > ts) ts = e.updated_at;
      this.notifyRow(e.symbol);
    }
    this.bumpMeta(ts || Date.now());
  }

  /** Tick en tiempo real del canal QUOTE. */
  quote(symbol: string, bidPrice?: number, askPrice?: number, tsMs?: number) {
    const bid = Number(bidPrice) || 0;
    const ask = Number(askPrice) || 0;
    const price = bid && ask ? (bid + ask) / 2 : bid || ask;
    if (!price) return;
    const cur = this.entries.get(symbol);
    if (cur && cur.price === price) return;
    const pc = this.prevClose.get(symbol);
    const change = pc ? +(price - pc).toFixed(6) : cur?.change ?? null;
    const pct = pc ? +(((price - pc) / pc) * 100).toFixed(5) : cur?.change_percent ?? null;
    const ts = tsMs || Date.now();
    this.entries.set(symbol, {
      ...(cur ?? { symbol }),
      symbol,
      price,
      change,
      change_percent: pct,
      updated_at: ts,
      dir: cur ? (price > cur.price ? 'up' : 'down') : null,
    });
    this.notifyRow(symbol);
    this.bumpMeta(ts);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Celda con flash propio: el <span> se remonta SOLO cuando cambia el valor
// mostrado (key=value) y eso re-dispara la animación CSS — flash por celda,
// no por fila.
// ─────────────────────────────────────────────────────────────────────────────
function FlashCell({
  value,
  dir,
  className = '',
}: {
  value: string;
  dir: 'up' | 'down' | null;
  className?: string;
}) {
  return (
    <td className={`px-2 py-[3px] text-right font-mono tabular-nums ${className}`}>
      <span
        key={value}
        className={`block rounded-[2px] ${dir === 'up' ? 'cell-flash-up' : dir === 'down' ? 'cell-flash-down' : ''}`}
      >
        {value}
      </span>
    </td>
  );
}

const MonitorRow = React.memo(function MonitorRow({
  symbol,
  label,
  engine,
}: {
  symbol: string;
  label?: string;
  engine: MonitorEngine;
}) {
  const subscribe = useCallback((cb: () => void) => engine.subscribeRow(symbol, cb), [engine, symbol]);
  const getSnapshot = useCallback(() => engine.getRow(symbol), [engine, symbol]);
  const e = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  if (!e) return null;

  const pct = e.change_percent;
  const chg = e.change;
  const up = (pct ?? chg ?? 0) >= 0;
  const chgColor = up ? 'text-emerald-500' : 'text-rose-500';

  return (
    <tr className="border-b border-border-subtle hover:bg-surface-hover">
      <td className="px-2 py-[3px]">
        <span className="font-mono font-bold text-foreground">{symbol}</span>
        <span className="ml-2 text-[10px] text-muted-fg">{label || e.name || ''}</span>
      </td>
      <FlashCell value={formatPrice(e.price)} dir={e.dir} className="font-semibold text-foreground" />
      <FlashCell
        value={chg != null ? `${chg >= 0 ? '+' : ''}${formatChange(chg)}` : '—'}
        dir={e.dir}
        className={chgColor}
      />
      <FlashCell
        value={pct != null ? `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(2)}%` : '—'}
        dir={e.dir}
        className={`pr-3 ${chgColor}`}
      />
    </tr>
  );
});

export function AssetMonitorTable({ assetClass, groups, labels = {}, pollMs = 30000 }: AssetMonitorTableProps) {
  const { t } = useTranslation();
  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];

  const engineRef = useRef<MonitorEngine | null>(null);
  if (!engineRef.current) engineRef.current = new MonitorEngine();
  const engine = engineRef.current;

  const ws = useWebSocket();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const symbols = useMemo(() => groups.flatMap((g) => g.symbols), [groups]);
  const symbolSet = useMemo(() => new Set(symbols), [symbols]);

  // ── Capa 1: seed + reconciliación REST ──
  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    let cancelled = false;

    const fetchSnapshot = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/realtime/class/${assetClass}`);
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        if (cancelled) return;
        engine.seed(data.results || []);
        setError(false);
      } catch (err) {
        if (!cancelled) setError(true);
        console.error(`[AssetMonitor:${assetClass}] snapshot error:`, err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, pollMs);
    return () => { cancelled = true; clearInterval(interval); };
  }, [assetClass, pollMs, engine]);

  // ── Capa 2: quotes en tiempo real por el WS compartido ──
  useEffect(() => {
    if (!ws.isConnected) return;
    ws.send({ action: 'subscribe_quotes', symbols });
    const sub = ws.messages$.subscribe((m: any) => {
      if (m?.type === 'quote' && m.symbol && symbolSet.has(m.symbol)) {
        const ts = Number(m.data?.timestamp) || undefined;
        engine.quote(m.symbol, m.data?.bidPrice, m.data?.askPrice, ts);
      }
    });
    return () => {
      sub.unsubscribe();
      ws.send({ action: 'unsubscribe_quotes', symbols });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.isConnected, symbols, symbolSet, engine]);

  // ── Footer reactivo (1 update/seg como mucho) ──
  const subscribeMeta = useCallback((cb: () => void) => engine.subscribeMeta(cb), [engine]);
  const getMeta = useCallback(() => engine.getMeta(), [engine]);
  const meta = useSyncExternalStore(subscribeMeta, getMeta, getMeta);

  const totalShown = useMemo(
    () => groups.reduce((acc, g) => acc + g.symbols.filter((s) => engine.getRow(s)).length, 0),
    // meta.count cambia cuando entran símbolos nuevos al engine
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [groups, engine, meta.count]
  );

  const live = ws.isConnected || (meta.lastUpdate > 0 && Date.now() - meta.lastUpdate < 120000);

  if (loading && meta.count === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-surface">
        <Loader2 className="w-5 h-5 animate-spin text-muted-fg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface" style={{ fontFamily }}>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes cellFlashUp { 0% { background-color: rgba(16,185,129,0.30); } 100% { background-color: transparent; } }
        @keyframes cellFlashDown { 0% { background-color: rgba(244,63,94,0.30); } 100% { background-color: transparent; } }
        .cell-flash-up { animation: cellFlashUp 0.7s ease-out; }
        .cell-flash-down { animation: cellFlashDown 0.7s ease-out; }
      ` }} />
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-[11px]" style={{ borderCollapse: 'collapse' }}>
          <thead className="sticky top-0 z-10">
            <tr className="text-left uppercase tracking-wide text-foreground/80 bg-surface-inset text-[10px]">
              <th className="px-2 py-1 font-medium">{t('markets.instrument')}</th>
              <th className="px-2 py-1 font-medium text-right w-24">{t('markets.last')}</th>
              <th className="px-2 py-1 font-medium text-right w-20">{t('markets.chg')}</th>
              <th className="px-2 py-1 font-medium text-right w-20 pr-3">{t('markets.chgPct')}</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => {
              const rows = group.symbols.filter((s) => engine.getRow(s));
              if (rows.length === 0) return null;
              return (
                <React.Fragment key={group.title}>
                  <tr>
                    <td colSpan={4}
                      className="px-2 py-[3px] text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-fg bg-surface-inset/60 border-y border-border-subtle select-none">
                      {group.title}
                    </td>
                  </tr>
                  {rows.map((sym) => (
                    <MonitorRow key={sym} symbol={sym} label={labels[sym]} engine={engine} />
                  ))}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-border bg-surface-hover text-[10px] shrink-0">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${error && !live ? 'bg-rose-500' : 'bg-emerald-500'}`} />
          <span className={error && !live ? 'text-rose-500' : 'text-emerald-600'}>
            {error && !live ? t('common.offline') : t('common.live')}
          </span>
          {meta.lastUpdate > 0 && (
            <span className="text-muted-fg">
              · {new Date(meta.lastUpdate).toLocaleTimeString('en-US', { hour12: false })}
            </span>
          )}
        </div>
        <span className="text-foreground/80">{totalShown} {t('markets.instruments')}</span>
      </div>
    </div>
  );
}
