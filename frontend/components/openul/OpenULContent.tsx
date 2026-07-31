'use client';

import { useEffect, useRef, useState, useMemo, useCallback, Fragment } from 'react';
import { createPortal } from 'react-dom';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { Radio, ChevronDown, Clock, ArrowUp, TrendingUp, TrendingDown, Sparkles } from 'lucide-react';
import { useOpenUL, type OpenULNewsItem, type OpenULMedia } from '@/contexts/OpenULContext';
import { AIAgentContent } from '@/components/ai-agent';
import { requestContextBrief } from '@/lib/agentBridge';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useCurrentWindowId, useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { useUserPreferencesStore, selectFont, selectTimezone } from '@/stores/useUserPreferencesStore';
import { StreamPauseButton } from '@/components/common/StreamPauseButton';
import { SquawkButton } from '@/components/common/SquawkButton';
import { useSquawk, type SquawkService } from '@/contexts/SquawkContext';

const FONT_CLASS_MAP: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

const EMOJI_REGEX = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}\u{200D}\u{20E3}\u{E0020}-\u{E007F}\u{2B50}\u{2B55}\u{26AA}\u{26AB}\u{2705}\u{274C}\u{274E}\u{2753}\u{2757}\u{203C}\u{2049}\u{25AA}\u{25AB}\u{25FC}\u{25FB}\u{25FE}\u{25FD}\u{2934}\u{2935}\u{23F0}-\u{23FA}\u{231A}\u{231B}]+/gu;
const TICKER_REGEX = /(\$[A-Z]{1,5})\b/g;

function stripEmojis(text: string): string {
  return text.replace(EMOJI_REGEX, '').replace(/^\s+/, '');
}

function formatTime(isoString: string, tz: string): string {
  try {
    return new Date(isoString).toLocaleTimeString('en-US', {
      timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch { return '--:--:--'; }
}

function formatDate(isoString: string, tz: string): string {
  try {
    return new Date(isoString).toLocaleDateString('en-US', { timeZone: tz, month: 'short', day: 'numeric' });
  } catch { return ''; }
}

function tzAbbrev(tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'short' }).formatToParts(new Date());
    return parts.find((p) => p.type === 'timeZoneName')?.value || '';
  } catch { return ''; }
}

function timeAgo(isoString: string): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'connected' ? 'bg-emerald-500' : status === 'connecting' ? 'bg-amber-500 animate-pulse' : 'bg-red-500';
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${color}`} />;
}

function BreakingDot() {
  return (
    <span className="inline-flex items-center justify-center w-3 h-3 rounded-full bg-red-600 flex-shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-white" />
    </span>
  );
}

function TickerText({ text, onTickerClick }: { text: string; onTickerClick: (ticker: string) => void }) {
  const parts = text.split(TICKER_REGEX);
  return (
    <>
      {parts.map((part, i) => {
        if (TICKER_REGEX.test(part)) {
          TICKER_REGEX.lastIndex = 0;
          const symbol = part.slice(1);
          return (
            <button
              key={i}
              onClick={(e) => { e.stopPropagation(); onTickerClick(symbol); }}
              className="inline-flex items-center px-0.5 mx-px text-[11px] font-bold text-primary bg-primary/10 border border-border rounded hover:bg-primary/15 hover:border-primary transition-colors cursor-pointer"
            >
              ${symbol}
            </button>
          );
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}

function ReactionItem({ item, tz, onTickerClick }: { item: OpenULNewsItem; tz: string; onTickerClick: (t: string) => void }) {
  const isUp = item.direction === 'up';
  const abbrev = tzAbbrev(tz);
  const ticker = item.tickers?.[0] || '';

  return (
    <div className={`border-b border-border-subtle ${isUp ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
      <div className="px-3 py-1.5">
        <div className="flex items-center gap-1.5">
          {isUp
            ? <TrendingUp className="w-3 h-3 text-emerald-600 flex-shrink-0" />
            : <TrendingDown className="w-3 h-3 text-red-600 flex-shrink-0" />
          }
          <span className={`text-[10px] font-bold ${isUp ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
            REACTION
          </span>
          <button
            onClick={() => onTickerClick(ticker)}
            className={`text-[11px] font-bold px-0.5 rounded border cursor-pointer transition-colors ${isUp ? 'text-emerald-700 dark:text-emerald-400 bg-emerald-500/15 border-emerald-500/40 hover:bg-emerald-500/20' : 'text-red-700 dark:text-red-400 bg-red-500/15 border-red-500/40 hover:bg-red-500/20'}`}
          >
            ${ticker}
          </button>
          <span className={`text-[11px] font-bold font-mono ${isUp ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
            {isUp ? '▲' : '▼'} {isUp ? '+' : ''}{item.change_pct?.toFixed(1)}%
          </span>
          <span className="text-[10px] font-mono text-foreground/80">
            ${item.price?.toFixed(2)}
          </span>
          <span className="text-[9px] text-muted-fg ml-auto">
            {formatTime(item.received_at, tz)} {abbrev}
          </span>
        </div>
      </div>
    </div>
  );
}

function MediaThumbnail({ media }: { media: OpenULMedia }) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);

  if (error || !media.url) return null;

  return (
    <button
      onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
      className={`block mt-1.5 ml-[18px] rounded overflow-hidden border border-border hover:border-primary transition-all cursor-pointer ${expanded ? 'max-w-full' : 'max-w-[180px]'}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={media.url}
        alt=""
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className={`w-full h-auto object-contain transition-all ${loaded ? 'opacity-100' : 'opacity-0'} ${expanded ? 'max-h-[500px]' : 'max-h-[100px]'}`}
      />
    </button>
  );
}

function NewsItem({ item, isNew, tz, onTickerClick, onOpenBrief }: { item: OpenULNewsItem; isNew: boolean; tz: string; onTickerClick: (t: string) => void; onOpenBrief: (item: OpenULNewsItem) => void }) {
  const [expanded, setExpanded] = useState(false);
  const cleanText = stripEmojis(item.text);
  const lines = cleanText.split('\n').filter((l) => l.trim());
  const isMultiline = lines.length > 3;
  const displayLines = expanded ? lines : lines.slice(0, 3);
  const abbrev = tzAbbrev(tz);

  return (
    <div className={`group border-b border-border-subtle transition-colors ${isNew ? 'bg-red-500/10' : 'hover:bg-surface-hover'}`}>
      <div className="px-3 py-2">
        <div className="flex items-center gap-1.5 mb-0.5">
          {isNew && (
            <span className="px-1 py-px text-[7px] font-bold bg-red-600 text-white rounded tracking-wider animate-pulse">
              LIVE
            </span>
          )}
          <Clock className="w-2.5 h-2.5 text-muted-fg" />
          <span className="text-[9px] font-mono text-muted-fg">
            {formatTime(item.received_at, tz)} {abbrev}
          </span>
          <span className="text-[9px] text-muted-fg ml-auto">{timeAgo(item.received_at)}</span>
        </div>

        <div className="text-[11px] leading-[1.5] text-foreground whitespace-pre-wrap break-words">
          {displayLines.map((line, i) => (
            <div key={i} className="flex items-start gap-1.5">
              {i === 0 && <BreakingDot />}
              {i > 0 && <span className="w-3 flex-shrink-0" />}
              <span><TickerText text={line} onTickerClick={onTickerClick} /></span>
            </div>
          ))}
        </div>

        {isMultiline && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="flex items-center gap-0.5 mt-0.5 text-[9px] text-primary hover:text-primary ml-[18px]"
          >
            <ChevronDown className="w-2.5 h-2.5" />
            Show more
          </button>
        )}

        {item.media && item.media.length > 0 && (
          <div className="flex gap-1.5 flex-wrap">
            {item.media.map((m, i) => (
              <MediaThumbnail key={i} media={m} />
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mt-1 ml-[18px]">
          <span className="text-[8px] font-mono text-muted-fg">{formatDate(item.created_at, tz)}</span>
          {item.tickers && item.tickers.length > 0 && (
            <div className="flex gap-1">
              {item.tickers.map((t) => (
                <button
                  key={t}
                  onClick={() => onTickerClick(t)}
                  className="px-1 py-px text-[8px] font-mono font-bold text-primary bg-primary/10 border border-border rounded hover:bg-primary/15 cursor-pointer transition-colors"
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onOpenBrief(item); }}
            title="Brief Fundamental con IA"
            className="ml-auto flex items-center gap-0.5 px-1 py-px text-[8px] font-mono font-bold text-primary border border-primary/30 bg-primary/5 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 hover:bg-primary/15 hover:border-primary transition-all"
          >
            <Sparkles className="w-2.5 h-2.5" />
            Brief
          </button>
        </div>
      </div>
    </div>
  );
}

function HeaderPortal({ windowId, todayCount, status, isPaused, onTogglePause, buffered, squawk }: {
  windowId: string; todayCount: number; status: string;
  isPaused: boolean; onTogglePause: () => void; buffered: number; squawk: SquawkService;
}) {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const el = document.getElementById(`window-header-extra-${windowId}`);
    if (el) setTarget(el);
  }, [windowId]);

  if (!target) return null;

  return createPortal(
    <div className="flex items-center gap-1.5 mr-1">
      <StatusDot status={status} />
      <span className="text-[9px] font-mono text-muted-fg">{todayCount} today</span>
      {isPaused && buffered > 0 && (
        <span className="text-[9px] font-mono text-amber-500">+{buffered}</span>
      )}
      <StreamPauseButton isPaused={isPaused} onToggle={onTogglePause} size="sm" />
      <SquawkButton
        isEnabled={squawk.isEnabled}
        isSpeaking={squawk.isSpeaking}
        queueSize={squawk.queueSize}
        onToggle={squawk.toggleEnabled}
        size="sm"
      />
    </div>,
    target,
  );
}

export function OpenULContent() {
  const { items, status, clearUnread, setWindowOpen, loadOlder, loadingOlder, hasMore } = useOpenUL();
  const { executeTickerCommand } = useCommandExecutor();
  const { openWindow, bringToFront } = useFloatingWindowActions();
  const windowsList = useFloatingWindowsList();
  const windowId = useCurrentWindowId();
  const font = useUserPreferencesStore(selectFont);
  const tz = useUserPreferencesStore(selectTimezone);
  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const abbrev = tzAbbrev(tz);
  const squawk = useSquawk();

  // Pausa: congela la lista visible; lo nuevo queda en buffer hasta reanudar
  const [frozen, setFrozen] = useState<OpenULNewsItem[] | null>(null);
  const displayItems = frozen ?? items;
  const bufferedCount = frozen ? Math.max(0, items.length - frozen.length) : 0;
  const handleTogglePause = useCallback(() => {
    setFrozen((prev) => (prev ? null : items));
  }, [items]);

  // Voz: lee cada noticia nueva cuando el squawk está activo
  const lastSpokenRef = useRef<string | null>(null);
  useEffect(() => {
    if (items.length === 0) return;
    const newest = items[0];
    if (lastSpokenRef.current === null) { lastSpokenRef.current = newest.id; return; }
    if (newest.type === 'reaction' || lastSpokenRef.current === newest.id) return;
    lastSpokenRef.current = newest.id;
    if (squawk.isEnabled) squawk.speak(stripEmojis(newest.text).slice(0, 280));
  }, [items, squawk]);

  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [atTop, setAtTop] = useState(true);
  const [newItemIds, setNewItemIds] = useState<Set<string>>(new Set());
  const prevCountRef = useRef(items.length);

  const handleTickerClick = useCallback((ticker: string) => {
    executeTickerCommand(ticker, 'chart');
  }, [executeTickerCommand]);

  // Abre (o reutiliza) la ventana del Agente IA, miniaturizada, y pide el
  // Brief de Contexto de la noticia (persiste en el hilo, follow-ups en vivo).
  const handleOpenBrief = useCallback((item: OpenULNewsItem) => {
    const news = {
      text: item.text,
      tickers: item.tickers || [],
      created_at: item.created_at,
      received_at: item.received_at,
      id: item.id,
    };
    const existing = windowsList.find((w) => w.title === 'AI Agent');
    if (existing) {
      bringToFront(existing.id);
    } else {
      const sw = typeof window !== 'undefined' ? window.innerWidth : 1280;
      openWindow({
        title: 'AI Agent',
        content: <AIAgentContent />,
        width: 540,
        height: 660,
        x: Math.max(40, sw - 580),
        y: 80,
        minWidth: 380,
        minHeight: 440,
      });
    }
    requestContextBrief(news);
  }, [windowsList, openWindow, bringToFront]);

  useEffect(() => {
    setWindowOpen(true);
    clearUnread();
    return () => setWindowOpen(false);
  }, [setWindowOpen, clearUnread]);

  useEffect(() => { clearUnread(); }, [items.length, clearUnread]);

  useEffect(() => {
    if (items.length > prevCountRef.current) {
      const newIds = new Set(items.slice(0, items.length - prevCountRef.current).map((i) => i.id));
      setNewItemIds(newIds);
      const timer = setTimeout(() => setNewItemIds(new Set()), 3000);
      prevCountRef.current = items.length;
      return () => clearTimeout(timer);
    }
    prevCountRef.current = items.length;
  }, [items]);

  useEffect(() => {
    if (frozen) return; // en pausa no se auto-desplaza
    if (atTop && virtuosoRef.current) {
      virtuosoRef.current.scrollToIndex({ index: 0, behavior: 'smooth' });
    }
  }, [items.length, atTop, frozen]);

  const scrollToTop = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({ index: 0, behavior: 'smooth' });
  }, []);

  const todayCount = useMemo(() => {
    const todayStr = new Date().toLocaleDateString('en-US', { timeZone: tz });
    return items.filter((item) => {
      const d = new Date(item.received_at).toLocaleDateString('en-US', { timeZone: tz });
      return d === todayStr;
    }).length;
  }, [items, tz]);

  const renderItem = useCallback((_index: number, item: OpenULNewsItem) => {
    if (item.type === 'reaction') {
      return <ReactionItem item={item} tz={tz} onTickerClick={handleTickerClick} />;
    }
    return <NewsItem item={item} isNew={newItemIds.has(item.id)} tz={tz} onTickerClick={handleTickerClick} onOpenBrief={handleOpenBrief} />;
  }, [tz, handleTickerClick, newItemIds, handleOpenBrief]);

  // Clave estable por item: evita que Virtuoso re-monte filas cuando llegan
  // noticias nuevas por arriba (los indices se desplazan, las claves no).
  const computeItemKey = useCallback((_index: number, item: OpenULNewsItem) => item.id, []);

  const Footer = useCallback(() => {
    if (loadingOlder) {
      return (
        <div className="flex items-center justify-center gap-1.5 py-2 text-[9px] font-mono text-muted-fg">
          <span className="w-2 h-2 rounded-full border border-muted-fg border-t-transparent animate-spin" />
          Loading older news…
        </div>
      );
    }
    if (!hasMore && items.length > 0) {
      return (
        <div className="py-2 text-center text-[9px] font-mono text-muted-fg/40">
          — end of history —
        </div>
      );
    }
    return null;
  }, [loadingOlder, hasMore, items.length]);

  return (
    <div className={`relative flex flex-col h-full bg-surface select-text ${fontClass}`}>
      {windowId && (
        <HeaderPortal
          windowId={windowId} todayCount={todayCount} status={status}
          isPaused={!!frozen} onTogglePause={handleTogglePause}
          buffered={bufferedCount} squawk={squawk}
        />
      )}

      {items.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-fg gap-2">
          <Radio className="w-6 h-6" />
          <span className="text-[11px] font-mono">Waiting for breaking news...</span>
          <span className="text-[9px] text-muted-fg/50">
            {status === 'connected' ? 'Stream connected \u2014 listening' : 'Connecting to stream...'}
          </span>
        </div>
      ) : (
        <Virtuoso
          ref={virtuosoRef}
          data={displayItems}
          itemContent={renderItem}
          computeItemKey={computeItemKey}
          atTopStateChange={setAtTop}
          endReached={loadOlder}
          increaseViewportBy={{ top: 0, bottom: 600 }}
          overscan={400}
          components={{ Footer }}
          className="flex-1"
        />
      )}

      {!atTop && items.length > 0 && (
        <button
          onClick={scrollToTop}
          className="absolute bottom-2 right-3 flex items-center gap-1 px-2 py-1 bg-red-600 text-white text-[9px] font-mono rounded shadow-lg hover:bg-red-700 transition-colors z-10"
        >
          <ArrowUp className="w-2.5 h-2.5" />
          Latest
        </button>
      )}

      <div className="flex items-center justify-between px-3 py-0.5 border-t border-border bg-surface-hover">
        <span className="text-[8px] font-mono text-muted-fg">
          {displayItems.length} items{frozen ? ` · paused (+${bufferedCount})` : ''} · {abbrev}
        </span>
        <span className="text-[8px] font-mono text-muted-fg/50">openul v1.0</span>
      </div>
    </div>
  );
}
