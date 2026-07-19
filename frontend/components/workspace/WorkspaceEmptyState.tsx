'use client';

import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  WORKSPACE_LAYOUTS,
  layoutSupportsTicker,
  type TilePreviewKind,
  type WorkspaceLayoutPreset,
} from '@/hooks/useWorkspaceLayouts';

type ScannerTile = {
  id: string;
  nameKey: string;
  descKey: string;
  shortcut?: string;
  tone: 'up' | 'down' | 'neutral';
};

type ModuleTile = {
  id: string;
  label: string;
  descKey: string;
};

const SCANNER_TILES: ScannerTile[] = [
  { id: 'gappers_up', nameKey: 'scanner.gapUp', descKey: 'scanner.gapUpDescription', shortcut: 'Ctrl+1', tone: 'up' },
  { id: 'gappers_down', nameKey: 'scanner.gapDown', descKey: 'scanner.gapDownDescription', shortcut: 'Ctrl+2', tone: 'down' },
  { id: 'momentum_up', nameKey: 'scanner.momentumUp', descKey: 'scanner.momentumUpDescription', shortcut: 'Ctrl+3', tone: 'up' },
  { id: 'momentum_down', nameKey: 'scanner.momentumDown', descKey: 'scanner.momentumDownDescription', shortcut: 'Ctrl+4', tone: 'down' },
  { id: 'winners', nameKey: 'scanner.topGainers', descKey: 'scanner.topGainersDescription', shortcut: 'Ctrl+5', tone: 'up' },
  { id: 'high_volume', nameKey: 'scanner.highVolume', descKey: 'scanner.highVolumeDescription', tone: 'neutral' },
];

const MODULE_TILES: ModuleTile[] = [
  { id: 'news', label: 'NEWS', descKey: 'workspace.modules.news' },
  { id: 'dt', label: 'DT', descKey: 'workspace.modules.dt' },
  { id: 'evt_all', label: 'EVN', descKey: 'workspace.modules.evn' },
  { id: 'ai', label: 'AI', descKey: 'workspace.modules.ai' },
  { id: 'pulse', label: 'PULSE', descKey: 'workspace.modules.pulse' },
  { id: 'screener', label: 'SCREEN', descKey: 'workspace.modules.screener' },
];

const TONE_DOT: Record<ScannerTile['tone'], string> = {
  up: 'bg-emerald-500',
  down: 'bg-red-500',
  neutral: 'bg-primary',
};

const QUICK_TICKERS = ['AAPL', 'NVDA', 'TSLA', 'SPY'];

/* Keyframes de las miniaturas animadas (prefijo wsl- para no colisionar) */
const PREVIEW_KEYFRAMES = `
@keyframes wsl-blink { 0%, 100% { opacity: .25; } 50% { opacity: 1; } }
@keyframes wsl-growx { 0%, 100% { transform: scaleX(.35); } 50% { transform: scaleX(1); } }
@keyframes wsl-growy { 0%, 100% { transform: scaleY(.3); } 50% { transform: scaleY(1); } }
@keyframes wsl-draw { 0% { stroke-dashoffset: 190; } 60%, 100% { stroke-dashoffset: 0; } }
@keyframes wsl-item { 0% { opacity: 0; transform: translateY(3px); } 10%, 85% { opacity: 1; transform: translateY(0); } 100% { opacity: 0; transform: translateY(-2px); } }
@keyframes wsl-ping { 0% { transform: scale(1); opacity: .8; } 75%, 100% { transform: scale(2.6); opacity: 0; } }
`;

interface WorkspaceEmptyStateProps {
  onOpenScanner: (categoryId: string) => void;
  onOpenModule: (commandId: string) => void;
  onOpenLayout: (layoutId: string, ticker?: string) => void;
  onOpenCommandPalette: () => void;
}

export function WorkspaceEmptyState({
  onOpenScanner,
  onOpenModule,
  onOpenLayout,
  onOpenCommandPalette,
}: WorkspaceEmptyStateProps) {
  const { t } = useTranslation();

  return (
    <div className="relative flex h-full overflow-y-auto px-4 py-8">
      <style>{PREVIEW_KEYFRAMES}</style>

      {/* Atmosphere — faint terminal grid, stays behind content */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-[0.35]"
        style={{
          backgroundImage: `
            linear-gradient(to right, var(--color-border) 1px, transparent 1px),
            linear-gradient(to bottom, var(--color-border) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(ellipse 70% 55% at 50% 45%, black 20%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse 70% 55% at 50% 45%, black 20%, transparent 75%)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0"
        style={{
          background:
            'radial-gradient(ellipse 55% 40% at 50% 42%, color-mix(in srgb, var(--color-primary) 6%, transparent), transparent 70%)',
        }}
      />

      <div className="relative m-auto w-full max-w-[960px] animate-in fade-in duration-300">
        {/* Header */}
        <div className="mb-5 text-center">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-fg">
            {t('workspace.empty.eyebrow')}
          </p>
          <h2 className="text-[18px] font-semibold tracking-tight text-foreground">
            {t('workspace.empty.title')}
          </h2>
          <p className="mx-auto mt-1.5 max-w-[440px] text-[12px] leading-relaxed text-muted-fg">
            {t('workspace.empty.subtitle')}
          </p>
        </div>

        {/* Command prompt CTA */}
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="group mb-6 flex w-full items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-surface-hover"
        >
          <span className="font-mono text-[13px] text-primary">{'>'}</span>
          <span className="flex-1 text-[12px] text-muted-fg group-hover:text-foreground/80">
            {t('workspace.empty.commandHint')}
          </span>
          <kbd className="inline-flex items-center gap-0.5 rounded border border-border bg-surface-inset px-1.5 py-0.5 font-mono text-[10px] text-foreground/70">
            Ctrl+K
          </kbd>
        </button>

        {/* Preset layouts — gallery of animated miniatures */}
        <SectionLabel>{t('workspace.empty.layouts')}</SectionLabel>
        <div className="mb-6 grid gap-3 sm:grid-cols-2">
          {WORKSPACE_LAYOUTS.map((preset) => (
            <LayoutCard
              key={preset.id}
              preset={preset}
              onOpen={(ticker) => onOpenLayout(preset.id, ticker)}
            />
          ))}
        </div>

        {/* Scanners + Modules, side by side */}
        <div className="mb-5 grid gap-x-6 gap-y-5 sm:grid-cols-2">
          <div>
            <SectionLabel>{t('workspace.empty.scanners')}</SectionLabel>
            <div className="grid grid-cols-2 gap-1.5">
              {SCANNER_TILES.map((tile) => (
                <button
                  key={tile.id}
                  type="button"
                  onClick={() => onOpenScanner(tile.id)}
                  title={t(tile.descKey)}
                  className="group flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-left transition-colors hover:border-primary/35 hover:bg-surface-hover"
                >
                  <span className={`h-1 w-1 shrink-0 rounded-full ${TONE_DOT[tile.tone]}`} />
                  <span className="truncate text-[11.5px] font-medium text-foreground">
                    {t(tile.nameKey)}
                  </span>
                  {tile.shortcut && (
                    <kbd className="ml-auto hidden shrink-0 rounded border border-border bg-surface-inset px-1 py-px font-mono text-[9px] text-muted-fg lg:inline">
                      {tile.shortcut}
                    </kbd>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div>
            <SectionLabel>{t('workspace.empty.modules')}</SectionLabel>
            <div className="grid grid-cols-2 gap-1.5">
              {MODULE_TILES.map((mod) => (
                <button
                  key={mod.id}
                  type="button"
                  onClick={() => onOpenModule(mod.id)}
                  className="group flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-left transition-colors hover:border-primary/35 hover:bg-surface-hover"
                >
                  <span className="shrink-0 font-mono text-[10px] font-semibold tracking-wide text-primary">
                    {mod.label}
                  </span>
                  <span className="truncate text-[10px] text-muted-fg group-hover:text-foreground/80">
                    {t(mod.descKey)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Ticker tip */}
        <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 border-t border-border/60 pt-4 text-[10px] text-muted-fg">
          <span>{t('workspace.empty.tip')}</span>
          <code className="rounded border border-border bg-surface-inset px-1.5 py-0.5 font-mono text-[10px] text-foreground/75">
            AAPL G
          </code>
          <code className="rounded border border-border bg-surface-inset px-1.5 py-0.5 font-mono text-[10px] text-foreground/75">
            NVDA DT
          </code>
          <code className="rounded border border-border bg-surface-inset px-1.5 py-0.5 font-mono text-[10px] text-foreground/75">
            TSLA NEWS
          </code>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Tarjeta de layout — estilo galería de templates: título + descripción y una
   miniatura grande en perspectiva, animada internamente. Al pulsarla pide un
   ticker (si el layout lo admite) y abre todas las ventanas en mosaico.
   ══════════════════════════════════════════════════════════════════════════ */

function LayoutCard({
  preset,
  onOpen,
}: {
  preset: WorkspaceLayoutPreset;
  onOpen: (ticker?: string) => void;
}) {
  const { t } = useTranslation();
  const supportsTicker = layoutSupportsTicker(preset);
  const [prompting, setPrompting] = useState(false);
  const [ticker, setTicker] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const activate = () => {
    if (prompting) return;
    if (supportsTicker) {
      setPrompting(true);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    } else {
      onOpen();
    }
  };

  const confirm = (value?: string) => {
    const symbol = (value ?? ticker).trim().toUpperCase();
    setPrompting(false);
    setTicker('');
    onOpen(symbol || undefined);
  };

  const handleCardKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (prompting) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      activate();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={activate}
      onKeyDown={handleCardKey}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-surface p-4 pb-0 text-left outline-none transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:border-primary/50 focus-visible:ring-1 focus-visible:ring-primary/30"
    >
      {/* Header */}
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[13.5px] font-semibold tracking-tight text-foreground">
            {t(preset.nameKey)}
          </h3>
          <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-fg">
            {t(preset.descKey)}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-surface-inset px-1.5 py-px text-[8.5px] font-semibold uppercase tracking-[0.12em] text-muted-fg transition-colors group-hover:border-primary/30 group-hover:text-primary">
          {t(preset.audienceKey)}
        </span>
      </div>

      {/* Meta row */}
      <div className="mt-2 flex items-center gap-1.5 text-[9.5px] text-muted-fg/80">
        <span>{preset.tiles.length} {t('workspace.empty.windows')}</span>
        {supportsTicker && (
          <>
            <span className="text-muted-fg/40">·</span>
            <span className="font-mono">{t('workspace.empty.sharedTicker')}</span>
          </>
        )}
        <span className="ml-auto font-medium opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-primary">
          {t('workspace.empty.openLayout')} →
        </span>
      </div>

      {/* Animated miniature in perspective, cropped at the card bottom */}
      <div className="relative mt-3 h-[148px] select-none" aria-hidden>
        <div
          className="absolute inset-x-1 top-0 -bottom-6 origin-top rounded-lg border border-border bg-background shadow-xl transition-transform duration-500 ease-out [transform:perspective(1100px)_rotateX(16deg)_rotateY(-6deg)_scale(1.02)] group-hover:[transform:perspective(1100px)_rotateX(5deg)_rotateY(-1deg)_scale(1.05)]"
        >
          {/* Mini navbar */}
          <div className="flex h-[11px] items-center gap-[3px] border-b border-border/70 px-[6px]">
            <span className="h-[3px] w-[3px] rounded-full bg-red-500/60" />
            <span className="h-[3px] w-[3px] rounded-full bg-amber-500/60" />
            <span className="h-[3px] w-[3px] rounded-full bg-emerald-500/60" />
            <span className="ml-[4px] h-[3px] w-[46px] rounded-full bg-muted-fg/15" />
          </div>
          {/* Mini workspace canvas with tiled windows */}
          <div className="absolute inset-x-0 bottom-0 top-[11px] p-[4px]">
            <div className="relative h-full w-full">
              {preset.tiles.map((tile, i) => (
                <div
                  key={i}
                  className="absolute p-[2px]"
                  style={{
                    left: `${tile.rect.x * 100}%`,
                    top: `${tile.rect.y * 100}%`,
                    width: `${tile.rect.w * 100}%`,
                    height: `${tile.rect.h * 100}%`,
                  }}
                >
                  <div className="flex h-full w-full flex-col overflow-hidden rounded-[4px] border border-border/80 bg-surface transition-colors group-hover:border-primary/25">
                    <div className="flex shrink-0 items-center gap-[3px] border-b border-border/60 bg-surface-inset/60 px-[4px] py-[2px]">
                      <span className="h-[3px] w-[3px] shrink-0 rounded-full bg-primary/60" />
                      <span className="truncate font-mono text-[6.5px] font-semibold tracking-wider text-muted-fg">
                        {tile.label}
                      </span>
                    </div>
                    <div className="min-h-0 flex-1 overflow-hidden">
                      <TilePreview kind={tile.preview} seed={i} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Ticker prompt overlay */}
      {prompting && (
        <div
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2.5 rounded-xl bg-background/90 p-4 backdrop-blur-sm animate-in fade-in duration-150"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-fg">
            {t('workspace.empty.openWithTicker')}
          </p>
          <input
            ref={inputRef}
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z0-9.\-]/g, '').slice(0, 8))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                confirm();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                setPrompting(false);
                setTicker('');
              }
            }}
            placeholder="AAPL"
            className="w-36 rounded-lg border border-border bg-surface px-3 py-2 text-center font-mono text-[15px] font-semibold tracking-[0.08em] text-foreground outline-none placeholder:text-muted-fg/40 focus:border-primary/50"
          />
          <div className="flex items-center gap-1.5">
            {QUICK_TICKERS.map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => confirm(sym)}
                className="rounded border border-border bg-surface-inset px-1.5 py-0.5 font-mono text-[9.5px] text-foreground/75 transition-colors hover:border-primary/40 hover:text-primary"
              >
                {sym}
              </button>
            ))}
          </div>
          <p className="max-w-[240px] text-center text-[9.5px] leading-relaxed text-muted-fg">
            {t('workspace.empty.tickerHint')}
          </p>
          <div className="mt-0.5 flex items-center gap-2">
            <button
              type="button"
              onClick={() => confirm()}
              className="rounded-md bg-primary px-3.5 py-1.5 text-[11px] font-semibold text-white transition-opacity hover:opacity-90"
            >
              {t('workspace.empty.open')} ↵
            </button>
            <button
              type="button"
              onClick={() => confirm('')}
              className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-fg transition-colors hover:border-primary/30 hover:text-foreground"
            >
              {t('workspace.empty.withoutTicker')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Contenido esquemático animado de cada mini-ventana de la miniatura
   ══════════════════════════════════════════════════════════════════════════ */

function TilePreview({ kind, seed }: { kind: TilePreviewKind; seed: number }) {
  switch (kind) {
    case 'table':
      return <MiniTable seed={seed} />;
    case 'feed':
      return <MiniFeed live={false} />;
    case 'live':
      return <MiniFeed live />;
    case 'pulse':
      return <MiniPulse />;
    case 'chart':
      return <MiniChart dual={false} />;
    case 'ratio':
      return <MiniChart dual />;
    case 'columns':
      return <MiniColumns />;
    case 'ratings':
      return <MiniRatings />;
    case 'heatmap':
      return <MiniHeatmap />;
    case 'calendar':
      return <MiniCalendar />;
  }
}

function MiniTable({ seed }: { seed: number }) {
  return (
    <div className="flex h-full flex-col gap-[3px] p-[4px]">
      <div className="h-[3px] w-3/4 shrink-0 rounded-full bg-muted-fg/20" />
      {Array.from({ length: 6 }).map((_, i) => {
        const up = (i + seed) % 3 !== 1;
        return (
          <div key={i} className="flex shrink-0 items-center gap-[3px]">
            <span className="h-[3px] flex-[2] rounded-full bg-muted-fg/25" />
            <span className="h-[3px] flex-[1.4] rounded-full bg-muted-fg/15" />
            <span
              className={`h-[5px] w-[13px] rounded-[2px] ${up ? 'bg-emerald-500/70' : 'bg-red-500/60'}`}
              style={{ animation: `wsl-blink 2.4s ease-in-out ${(i * 320 + seed * 190) % 2000}ms infinite` }}
            />
          </div>
        );
      })}
    </div>
  );
}

function MiniFeed({ live }: { live: boolean }) {
  return (
    <div className="flex h-full flex-col gap-[5px] overflow-hidden p-[4px]">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex shrink-0 items-start gap-[3px]"
          style={{ animation: `wsl-item 6s ease-in-out ${i * 1400}ms infinite` }}
        >
          <span className="relative mt-[1px] h-[4px] w-[4px] shrink-0 rounded-full">
            <span className={`absolute inset-0 rounded-full ${live && i === 0 ? 'bg-red-500' : 'bg-primary/60'}`} />
            {live && i === 0 && (
              <span
                className="absolute inset-0 rounded-full bg-red-500"
                style={{ animation: 'wsl-ping 1.8s cubic-bezier(0,0,.2,1) infinite' }}
              />
            )}
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <span className="h-[3px] w-full rounded-full bg-muted-fg/30" />
            <span className="h-[3px] w-3/5 rounded-full bg-muted-fg/15" />
          </span>
        </div>
      ))}
    </div>
  );
}

function MiniPulse() {
  const bars = [
    { cls: 'bg-emerald-500/70', w: '86%', d: 0 },
    { cls: 'bg-amber-500/60', w: '58%', d: 500 },
    { cls: 'bg-red-500/55', w: '34%', d: 1000 },
  ];
  return (
    <div className="flex h-full flex-col justify-center gap-[5px] p-[5px]">
      <div className="mb-[2px] flex items-center gap-[3px]">
        <span className="h-[6px] w-[18px] rounded-[2px] bg-primary/50" style={{ animation: 'wsl-blink 3s ease-in-out infinite' }} />
        <span className="h-[3px] flex-1 rounded-full bg-muted-fg/15" />
      </div>
      {bars.map((b, i) => (
        <div key={i} className="h-[5px] w-full overflow-hidden rounded-full bg-muted-fg/10">
          <div
            className={`h-full origin-left rounded-full ${b.cls}`}
            style={{ width: b.w, animation: `wsl-growx 3.4s ease-in-out ${b.d}ms infinite` }}
          />
        </div>
      ))}
    </div>
  );
}

function MiniChart({ dual }: { dual: boolean }) {
  return (
    <div className="h-full w-full p-[3px]">
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-full w-full">
        <polyline
          points="0,34 12,30 22,32 34,24 46,26 58,18 70,20 82,10 92,13 100,6"
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="190"
          style={{ animation: 'wsl-draw 4.6s ease-in-out infinite' }}
          opacity="0.85"
        />
        {dual && (
          <polyline
            points="0,22 12,26 22,23 34,28 46,25 58,29 70,26 82,30 92,28 100,31"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="190"
            className="text-muted-fg/40"
            style={{ animation: 'wsl-draw 4.6s ease-in-out 800ms infinite' }}
          />
        )}
      </svg>
    </div>
  );
}

function MiniColumns() {
  const heights = [38, 52, 44, 66, 58, 80, 72];
  return (
    <div className="flex h-full items-end gap-[3px] p-[5px]">
      {heights.map((h, i) => (
        <div
          key={i}
          className={`flex-1 origin-bottom rounded-t-[2px] ${i % 2 === 0 ? 'bg-primary/55' : 'bg-muted-fg/25'}`}
          style={{ height: `${h}%`, animation: `wsl-growy 3.6s ease-in-out ${i * 220}ms infinite` }}
        />
      ))}
    </div>
  );
}

function MiniRatings() {
  const rows = [
    { g: 62, a: 26, r: 12 },
    { g: 48, a: 34, r: 18 },
    { g: 70, a: 20, r: 10 },
    { g: 38, a: 40, r: 22 },
  ];
  return (
    <div className="flex h-full flex-col justify-center gap-[5px] p-[5px]">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-[3px]">
          <span className="h-[3px] w-[12px] shrink-0 rounded-full bg-muted-fg/30" />
          <div
            className="flex h-[5px] flex-1 origin-left overflow-hidden rounded-full"
            style={{ animation: `wsl-growx 3.8s ease-in-out ${i * 340}ms infinite` }}
          >
            <span className="h-full bg-emerald-500/70" style={{ width: `${row.g}%` }} />
            <span className="h-full bg-amber-500/60" style={{ width: `${row.a}%` }} />
            <span className="h-full bg-red-500/55" style={{ width: `${row.r}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

const HEATMAP_TONES = [
  'bg-emerald-500/60',
  'bg-emerald-500/30',
  'bg-red-500/50',
  'bg-emerald-500/45',
  'bg-red-500/25',
  'bg-emerald-500/20',
  'bg-red-500/40',
];

function MiniHeatmap() {
  return (
    <div className="grid h-full grid-cols-6 gap-[2px] p-[4px]">
      {Array.from({ length: 24 }).map((_, i) => (
        <div
          key={i}
          className={`rounded-[1.5px] ${HEATMAP_TONES[(i * 5) % HEATMAP_TONES.length]}`}
          style={{ animation: `wsl-blink 3.2s ease-in-out ${(i * 173) % 2200}ms infinite` }}
        />
      ))}
    </div>
  );
}

function MiniCalendar() {
  return (
    <div className="grid h-full grid-cols-7 gap-[2px] p-[4px]">
      {Array.from({ length: 21 }).map((_, i) => {
        const hasEvent = i % 5 === 2 || i % 7 === 4;
        return (
          <div key={i} className="flex items-center justify-center rounded-[2px] border border-border/50">
            {hasEvent && (
              <span
                className="h-[3px] w-[3px] rounded-full bg-primary/70"
                style={{ animation: `wsl-blink 2.6s ease-in-out ${(i * 260) % 1800}ms infinite` }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted-fg">
        {children}
      </span>
      <div className="h-px flex-1 bg-border/70" />
    </div>
  );
}
