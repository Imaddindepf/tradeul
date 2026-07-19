'use client';

import { useCallback } from 'react';
import { useFloatingWindowActions } from '@/contexts/FloatingWindowContext';
import { useCommandExecutor, type WindowRect } from '@/hooks/useCommandExecutor';
import { NewsContent } from '@/components/news/NewsContent';
import { MarketPulseContent } from '@/components/market-pulse';
import { FinancialsContent } from '@/components/financials/FinancialsContent';
import { FinancialAnalystCanvas } from '@/components/financial-analyst';
import { AnalystRatingsContent } from '@/components/analyst-ratings';
import { RatioAnalysisContent } from '@/components/ratio-analysis';
import { InstitutionalHoldingsContent } from '@/components/institutional-holdings';
import { HeatmapContent } from '@/components/heatmap';
import { EarningsCalendarContent } from '@/components/floating-window/EarningsCalendarContent';
import { OpenULContent } from '@/components/openul';

/** Área reservada por el chrome de la app (navbar arriba, workspace tabs abajo). */
const NAVBAR_H = 40;
const TABS_H = 32;
const PAD = 10;
const GAP = 10;
/** Cascada al abrir las ventanas del layout */
const STAGGER_MS = 70;

type ModuleId =
  | 'news'
  | 'pulse'
  | 'fan'
  | 'fa'
  | 'rtn'
  | 'ratio'
  | 'hds'
  | 'heatmap'
  | 'earnings'
  | 'opn';

/** Tipo de contenido esquemático animado en la vista previa de la tarjeta */
export type TilePreviewKind =
  | 'table'
  | 'feed'
  | 'live'
  | 'pulse'
  | 'chart'
  | 'ratio'
  | 'columns'
  | 'ratings'
  | 'heatmap'
  | 'calendar';

export type LayoutTileKind =
  | { type: 'scanner'; categoryId: string }
  | { type: 'event'; categoryId: string }
  | { type: 'module'; moduleId: ModuleId };

export interface LayoutTile {
  /** Etiqueta corta mostrada en la vista previa esquemática */
  label: string;
  /** Contenido animado de la miniatura */
  preview: TilePreviewKind;
  /** Rect en fracciones [0..1] del área útil del workspace */
  rect: { x: number; y: number; w: number; h: number };
  kind: LayoutTileKind;
  /** Si true, esta ventana carga el ticker compartido del layout */
  tickerAware?: boolean;
}

export interface WorkspaceLayoutPreset {
  id: string;
  /** Claves i18n bajo workspace.layouts.* */
  nameKey: string;
  descKey: string;
  audienceKey: string;
  tiles: LayoutTile[];
}

export const WORKSPACE_LAYOUTS: WorkspaceLayoutPreset[] = [
  {
    id: 'day_trading',
    nameKey: 'workspace.layouts.dayTrading.name',
    descKey: 'workspace.layouts.dayTrading.desc',
    audienceKey: 'workspace.layouts.dayTrading.audience',
    tiles: [
      { label: 'GAP UP', preview: 'table', rect: { x: 0, y: 0, w: 0.4, h: 0.5 }, kind: { type: 'scanner', categoryId: 'gappers_up' } },
      { label: 'MOMENTUM', preview: 'table', rect: { x: 0, y: 0.5, w: 0.4, h: 0.5 }, kind: { type: 'scanner', categoryId: 'momentum_up' } },
      { label: 'EVENTS', preview: 'table', rect: { x: 0.4, y: 0, w: 0.34, h: 0.5 }, kind: { type: 'event', categoryId: 'evt_high_vol_runners' } },
      { label: 'NEWS', preview: 'feed', rect: { x: 0.4, y: 0.5, w: 0.34, h: 0.5 }, kind: { type: 'module', moduleId: 'news' }, tickerAware: true },
      { label: 'PULSE', preview: 'pulse', rect: { x: 0.74, y: 0, w: 0.26, h: 1 }, kind: { type: 'module', moduleId: 'pulse' } },
    ],
  },
  {
    id: 'investor',
    nameKey: 'workspace.layouts.investor.name',
    descKey: 'workspace.layouts.investor.desc',
    audienceKey: 'workspace.layouts.investor.audience',
    tiles: [
      { label: 'OVERVIEW', preview: 'chart', rect: { x: 0, y: 0, w: 0.54, h: 0.6 }, kind: { type: 'module', moduleId: 'fan' }, tickerAware: true },
      { label: 'FINANCIALS', preview: 'columns', rect: { x: 0, y: 0.6, w: 0.54, h: 0.4 }, kind: { type: 'module', moduleId: 'fa' }, tickerAware: true },
      { label: 'RATINGS', preview: 'ratings', rect: { x: 0.54, y: 0, w: 0.46, h: 0.5 }, kind: { type: 'module', moduleId: 'rtn' }, tickerAware: true },
      { label: 'RATIOS', preview: 'ratio', rect: { x: 0.54, y: 0.5, w: 0.46, h: 0.5 }, kind: { type: 'module', moduleId: 'ratio' }, tickerAware: true },
    ],
  },
  {
    id: 'news_catalysts',
    nameKey: 'workspace.layouts.newsCatalysts.name',
    descKey: 'workspace.layouts.newsCatalysts.desc',
    audienceKey: 'workspace.layouts.newsCatalysts.audience',
    tiles: [
      { label: 'NEWS', preview: 'feed', rect: { x: 0, y: 0, w: 0.46, h: 1 }, kind: { type: 'module', moduleId: 'news' }, tickerAware: true },
      { label: 'BREAKING', preview: 'live', rect: { x: 0.46, y: 0, w: 0.24, h: 1 }, kind: { type: 'module', moduleId: 'opn' } },
      { label: 'TICKERS', preview: 'table', rect: { x: 0.7, y: 0, w: 0.3, h: 0.55 }, kind: { type: 'scanner', categoryId: 'with_news' } },
      { label: 'EARNINGS', preview: 'calendar', rect: { x: 0.7, y: 0.55, w: 0.3, h: 0.45 }, kind: { type: 'module', moduleId: 'earnings' } },
    ],
  },
  {
    id: 'market_overview',
    nameKey: 'workspace.layouts.marketOverview.name',
    descKey: 'workspace.layouts.marketOverview.desc',
    audienceKey: 'workspace.layouts.marketOverview.audience',
    tiles: [
      { label: 'HEATMAP', preview: 'heatmap', rect: { x: 0, y: 0, w: 0.55, h: 0.62 }, kind: { type: 'module', moduleId: 'heatmap' } },
      { label: 'GAINERS', preview: 'table', rect: { x: 0, y: 0.62, w: 0.55, h: 0.38 }, kind: { type: 'scanner', categoryId: 'winners' } },
      { label: 'PULSE', preview: 'pulse', rect: { x: 0.55, y: 0, w: 0.45, h: 0.58 }, kind: { type: 'module', moduleId: 'pulse' } },
      { label: 'VOLUME', preview: 'table', rect: { x: 0.55, y: 0.58, w: 0.45, h: 0.42 }, kind: { type: 'scanner', categoryId: 'high_volume' } },
    ],
  },
];

/** Un layout admite ticker compartido si alguna de sus ventanas lo puede cargar */
export function layoutSupportsTicker(preset: WorkspaceLayoutPreset): boolean {
  return preset.tiles.some((t) => t.tickerAware);
}

/**
 * Hook para aplicar layouts predefinidos: abre un conjunto de ventanas
 * flotantes en mosaico, ocupando todo el área útil del workspace, con una
 * cascada suave. Si se pasa un ticker, todas las ventanas compatibles lo
 * cargan directamente (búsqueda ya resuelta vía initialTicker).
 * Los títulos y componentState coinciden con los usados por el resto de la
 * app, de forma que la persistencia/restauración de workspaces funciona igual.
 */
export function useWorkspaceLayouts() {
  const { openWindow } = useFloatingWindowActions();
  const { openScannerTable, openEventTable, executeTickerCommand } = useCommandExecutor();

  const openModuleAt = useCallback((moduleId: ModuleId, rect: WindowRect, ticker?: string) => {
    const base = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    switch (moduleId) {
      case 'news':
        openWindow({ title: 'News', content: <NewsContent initialTicker={ticker} />, ...base, minWidth: 420, minHeight: 320 });
        return;
      case 'pulse':
        openWindow({
          title: 'Market Pulse',
          content: <MarketPulseContent onOpenTicker={(sym) => executeTickerCommand(sym, 'chart')} />,
          ...base,
          minWidth: 380,
          minHeight: 360,
          hideHeader: true,
        });
        return;
      case 'fan':
        openWindow({ title: 'Financial Analyst', content: <FinancialAnalystCanvas initialTicker={ticker} />, ...base, minWidth: 640, minHeight: 420 });
        return;
      case 'fa':
        // Con ticker usamos el título "FA: X" (mismo convenio que el terminal),
        // así la restauración del workspace conserva el símbolo.
        openWindow({
          title: ticker ? `FA: ${ticker}` : 'Financial Analysis',
          content: <FinancialsContent initialTicker={ticker} />,
          ...base,
          minWidth: 480,
          minHeight: 320,
        });
        return;
      case 'rtn':
        openWindow({ title: 'Analyst Ratings', content: <AnalystRatingsContent initialTicker={ticker} />, ...base, minWidth: 440, minHeight: 320 });
        return;
      case 'ratio':
        openWindow({
          title: 'Ratio Analysis',
          content: ticker
            ? <RatioAnalysisContent initialSymbolY={ticker} initialSymbolX="SPY" />
            : <RatioAnalysisContent />,
          ...base,
          minWidth: 520,
          minHeight: 380,
        });
        return;
      case 'hds':
        openWindow({ title: 'Institutional Holdings', content: <InstitutionalHoldingsContent initialTicker={ticker} />, ...base, minWidth: 560, minHeight: 360 });
        return;
      case 'heatmap':
        openWindow({ title: 'Market Heatmap', content: <HeatmapContent />, ...base, minWidth: 600, minHeight: 380 });
        return;
      case 'earnings':
        openWindow({ title: 'Earnings Calendar', content: <EarningsCalendarContent />, ...base, minWidth: 480, minHeight: 280 });
        return;
      case 'opn':
        openWindow({ title: 'Openul — Breaking News', content: <OpenULContent />, ...base, minWidth: 340, minHeight: 380 });
        return;
    }
  }, [openWindow, executeTickerCommand]);

  const applyLayout = useCallback((layoutId: string, ticker?: string) => {
    const preset = WORKSPACE_LAYOUTS.find((l) => l.id === layoutId);
    if (!preset || typeof window === 'undefined') return;

    const sharedTicker = ticker?.trim().toUpperCase() || undefined;

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const areaX = PAD;
    const areaY = NAVBAR_H + PAD;
    const areaW = Math.max(720, vw - PAD * 2);
    const areaH = Math.max(420, vh - NAVBAR_H - TABS_H - PAD * 2);

    preset.tiles.forEach((tile, index) => {
      const { x: fx, y: fy, w: fw, h: fh } = tile.rect;
      const touchesRight = fx + fw >= 0.999;
      const touchesBottom = fy + fh >= 0.999;

      const rect: WindowRect = {
        x: Math.round(areaX + fx * areaW),
        y: Math.round(areaY + fy * areaH),
        width: Math.round(fw * areaW - (touchesRight ? 0 : GAP)),
        height: Math.round(fh * areaH - (touchesBottom ? 0 : GAP)),
      };

      // Cascada: las ventanas aparecen escalonadas, como un layout que se monta
      window.setTimeout(() => {
        switch (tile.kind.type) {
          case 'scanner':
            openScannerTable(tile.kind.categoryId, 0, rect);
            break;
          case 'event':
            openEventTable(tile.kind.categoryId, 0, rect);
            break;
          case 'module':
            openModuleAt(tile.kind.moduleId, rect, tile.tickerAware ? sharedTicker : undefined);
            break;
        }
      }, index * STAGGER_MS);
    });
  }, [openScannerTable, openEventTable, openModuleAt]);

  return { applyLayout };
}
