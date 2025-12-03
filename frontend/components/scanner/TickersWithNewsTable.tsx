/**
 * Tickers With News Table - SIMPLIFICADO
 * 
 * Muestra tickers que:
 * 1. Están en alguna tabla del scanner (gap up, gap down, etc.)
 * 2. Tienen noticias HOY (día de trading actual)
 * 
 * Al hacer clic en el número de noticias, abre una mini ventana con las noticias.
 */

'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, ColumnResizeMode } from '@tanstack/react-table';
import { formatNumber, formatPercent, formatRVOL } from '@/lib/formatters';
import { PriceCell } from './PriceCell';
import type { Ticker } from '@/lib/types';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { Newspaper, ExternalLink, Info } from 'lucide-react';

// Floating windows
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

// Zustand stores
import { useTickersStore } from '@/stores/useTickersStore';
import { useFiltersStore } from '@/stores/useFiltersStore';
import { passesFilter } from '@/lib/scanner/filterEngine';

// Para procesar snapshots/deltas de todas las categorías
import { useRxWebSocket } from '@/hooks/useRxWebSocket';

// WebSocket
import { useAuthWebSocket } from '@/hooks/useAuthWebSocket';
import { useMultiListSubscription } from '@/hooks/useRxWebSocket';

// Categorías del scanner a considerar
const SCANNER_CATEGORIES = [
  'gappers_up', 'gappers_down', 'momentum_up', 'momentum_down',
  'winners', 'losers', 'new_highs', 'new_lows',
  'anomalies', 'high_volume', 'reversals',
];

interface NewsArticle {
  id: string | number;
  benzinga_id?: string | number;
  title: string;
  author: string;
  published: string;
  url: string;
  tickers: string[];
}

interface TickerWithNews extends Ticker {
  newsCount: number;
  articles: NewsArticle[];
  lastNewsTime: string; // Hora de la última noticia
  scannerCategories: string[]; // Categorías del scanner donde aparece
}

interface TickersWithNewsTableProps {
  title: string;
  onClose?: () => void;
}

// ============================================================================
// HELPER: Obtener el día de trading actual (Eastern Time)
// Pre-market empieza a las 4:00 AM ET
// ============================================================================

function getTradingDay(): string {
  const now = new Date();
  const etFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    hour12: false,
  });

  const parts = etFormatter.formatToParts(now);
  const hour = parseInt(parts.find(p => p.type === 'hour')?.value || '0');
  const year = parts.find(p => p.type === 'year')?.value;
  const month = parts.find(p => p.type === 'month')?.value;
  const day = parts.find(p => p.type === 'day')?.value;

  // Si es antes de las 4 AM ET, usar el día anterior
  if (hour < 4) {
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const yParts = etFormatter.formatToParts(yesterday);
    return `${yParts.find(p => p.type === 'year')?.value}-${yParts.find(p => p.type === 'month')?.value}-${yParts.find(p => p.type === 'day')?.value}`;
  }

  return `${year}-${month}-${day}`;
}

// Verificar si una fecha es del día de trading actual
function isFromTodayTradingSession(published: string): boolean {
  try {
    const pubDate = new Date(published);
    const tradingDay = getTradingDay();

    const etFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });

    const parts = etFormatter.formatToParts(pubDate);
    const pubTradingDay = `${parts.find(p => p.type === 'year')?.value}-${parts.find(p => p.type === 'month')?.value}-${parts.find(p => p.type === 'day')?.value}`;

    return pubTradingDay === tradingDay;
  } catch {
    return false;
  }
}

const columnHelper = createColumnHelper<TickerWithNews>();

// ============================================================================
// MINI NEWS WINDOW COMPONENT
// ============================================================================

function MiniNewsWindow({ ticker, articles }: { ticker: string; articles: NewsArticle[] }) {
  const { t } = useTranslation();
  
  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
      return '—';
    }
  };

  if (articles.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-white p-4">
        <p className="text-slate-500 text-sm">{t('news.noNewsForTicker', { ticker })}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="px-3 py-2 bg-slate-50 border-b border-slate-200">
        <span className="text-sm font-bold text-blue-600">{ticker}</span>
        <span className="text-xs text-slate-500 ml-2">
          {articles.length} {t('news.articles', { count: articles.length })}
        </span>
      </div>
      <div className="flex-1 overflow-auto divide-y divide-slate-100">
        {articles.map((article, i) => (
          <a
            key={article.benzinga_id || article.id || i}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-3 py-2 hover:bg-slate-50 group"
          >
            <div className="flex items-start gap-2">
              <span className="text-xs text-slate-800 flex-1 leading-snug">{article.title}</span>
              <ExternalLink className="w-3 h-3 text-slate-400 group-hover:text-blue-500 flex-shrink-0" />
            </div>
            <div className="text-xs text-slate-400 mt-1">
              {formatTime(article.published)} · {article.author}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function TickersWithNewsTable({ title, onClose }: TickersWithNewsTableProps) {
  const { t } = useTranslation();
  const { openWindow } = useFloatingWindow();
  const { executeTickerCommand } = useCommandExecutor();

  // Estado
  const [allNews, setAllNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);

  // Tickers del scanner
  const tickerLists = useTickersStore((state) => state.lists);
  const initializeList = useTickersStore((state) => state.initializeList);
  const applyDeltas = useTickersStore((state) => state.applyDeltas);

  // WebSocket para procesar snapshots de todas las categorías
  const rxWs = useRxWebSocket();

  // User Filters - Zustand store para reactividad en tiempo real
  const activeFilters = useFiltersStore((state) => state.activeFilters);
  const hasActiveFilters = useFiltersStore((state) => state.hasActiveFilters);
  const filtersKey = JSON.stringify(activeFilters); // Para detectar cambios

  // WebSocket status
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useAuthWebSocket(wsUrl);

  // ======================================================================
  // SUSCRIBIRSE A TODAS LAS CATEGORÍAS DEL SCANNER
  // Esto permite que la tabla funcione aunque no tengas otras tablas abiertas
  // ======================================================================
  
  useMultiListSubscription(SCANNER_CATEGORIES);

  // ======================================================================
  // PROCESAR SNAPSHOTS Y DELTAS DE TODAS LAS CATEGORÍAS
  // Sin esto, los datos no se guardan en el store
  // ======================================================================

  useEffect(() => {
    if (!rxWs.isConnected) return;

    // Procesar snapshots
    const snapshotSub = rxWs.snapshots$.subscribe((snapshot: any) => {
      if (!snapshot.list || !SCANNER_CATEGORIES.includes(snapshot.list)) return;
      if (!snapshot.rows || !Array.isArray(snapshot.rows)) return;
      initializeList(snapshot.list, snapshot);
    });

    // Procesar deltas
    const deltaSub = rxWs.deltas$.subscribe((delta: any) => {
      if (!delta.list || !SCANNER_CATEGORIES.includes(delta.list)) return;
      if (!delta.deltas || !Array.isArray(delta.deltas)) return;
      applyDeltas(delta.list, delta.deltas, delta.sequence);
    });

    return () => {
      snapshotSub.unsubscribe();
      deltaSub.unsubscribe();
    };
  }, [rxWs.isConnected, rxWs.snapshots$, rxWs.deltas$, initializeList, applyDeltas]);

  // ======================================================================
  // CARGAR NOTICIAS
  // ======================================================================

  useEffect(() => {
    const fetchNews = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/news/api/v1/news?limit=500`);

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        if (data.results) {
          // Filtrar solo noticias con tickers y de HOY
          const todayNews = data.results.filter((a: NewsArticle) =>
            a.tickers && a.tickers.length > 0 && isFromTodayTradingSession(a.published)
          );
          setAllNews(todayNews);
        }
      } catch (err) {
        console.error('Error fetching news:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, []);

  // ======================================================================
  // CONTAR TICKERS DEL SCANNER
  // ======================================================================

  const scannerTickersCount = useMemo(() => {
    let count = 0;
    tickerLists.forEach((list, listName) => {
      if (SCANNER_CATEGORIES.includes(listName)) {
        count += list.tickers.size;
      }
    });
    return count;
  }, [tickerLists]);

  // ======================================================================
  // CALCULAR INTERSECCIÓN (sin filtros)
  // ======================================================================

  const baseTickersWithNews = useMemo((): TickerWithNews[] => {
    // 1. Obtener todos los tickers de las tablas del scanner Y en qué categorías están
    const scannerTickers = new Set<string>();
    const tickerDataMap = new Map<string, Ticker>();
    const tickerCategoriesMap = new Map<string, string[]>(); // ticker -> categorías

    tickerLists.forEach((list, listName) => {
      if (!SCANNER_CATEGORIES.includes(listName)) return;

      list.tickers.forEach((ticker, symbol) => {
        const upper = symbol.toUpperCase();
        scannerTickers.add(upper);
        
        // Guardar el ticker data
        if (!tickerDataMap.has(upper)) {
          tickerDataMap.set(upper, ticker);
        }
        
        // Añadir la categoría a la lista de categorías del ticker
        if (!tickerCategoriesMap.has(upper)) {
          tickerCategoriesMap.set(upper, []);
        }
        tickerCategoriesMap.get(upper)!.push(listName);
      });
    });

    // 2. Agrupar noticias por ticker (solo las que están en el scanner)
    const newsByTicker = new Map<string, NewsArticle[]>();

    allNews.forEach((article) => {
      article.tickers.forEach((ticker) => {
        const upper = ticker.toUpperCase();
        if (scannerTickers.has(upper)) {
          if (!newsByTicker.has(upper)) {
            newsByTicker.set(upper, []);
          }
          newsByTicker.get(upper)!.push(article);
        }
      });
    });

    // 3. Crear resultado
    const result: TickerWithNews[] = [];

    newsByTicker.forEach((articles, symbol) => {
      const tickerData = tickerDataMap.get(symbol);
      if (tickerData) {
        // Ordenar artículos por fecha (más recientes primero)
        const sortedArticles = [...articles].sort((a, b) =>
          new Date(b.published).getTime() - new Date(a.published).getTime()
        );

        // Obtener hora de la última noticia
        const lastNewsTime = sortedArticles[0]?.published || '';

        // Obtener categorías del scanner
        const scannerCategories = tickerCategoriesMap.get(symbol) || [];

        result.push({
          ...tickerData,
          newsCount: articles.length,
          articles: sortedArticles,
          lastNewsTime,
          scannerCategories,
        });
      }
    });

    // Ordenar por número de noticias
    result.sort((a, b) => b.newsCount - a.newsCount);

    return result;
  }, [tickerLists, allNews]);

  // ======================================================================
  // APLICAR FILTROS DEL FILTER MANAGER
  // ======================================================================

  const tickersWithNews = useMemo(() => {
    if (!hasActiveFilters) {
      return baseTickersWithNews; // Sin filtros = mostrar todos
    }

    // Aplicar filtros del store
    return baseTickersWithNews.filter(ticker => passesFilter(ticker, activeFilters));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseTickersWithNews, filtersKey, hasActiveFilters]);

  // ======================================================================
  // ABRIR MINI VENTANA DE NOTICIAS
  // ======================================================================

  const handleOpenNews = useCallback((symbol: string, articles: NewsArticle[]) => {
    openWindow({
      title: `News: ${symbol}`,
      content: <MiniNewsWindow ticker={symbol} articles={articles} />,
      width: 400,
      height: 350,
      x: 250,
      y: 150,
      minWidth: 320,
      minHeight: 200,
    });
  }, [openWindow]);

  // ======================================================================
  // TABLE CONFIG
  // ======================================================================

  const [sorting, setSorting] = useState<SortingState>([{ id: 'newsCount', desc: true }]);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [columnVisibility, setColumnVisibility] = useState({});
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'row_number',
        header: '#',
        size: 40,
        cell: (info) => <div className="text-center text-slate-400">{info.row.index + 1}</div>,
      }),
      columnHelper.accessor('symbol', {
        header: t('scanner.tableHeaders.symbol'),
        size: 75,
        cell: (info) => {
          const symbol = info.getValue();
          const exchange = info.row.original.exchange;
          return (
            <button
              type="button"
              className="font-bold text-blue-600 cursor-pointer hover:underline text-left"
              onClick={() => {
                console.log('Opening description for:', symbol, exchange);
                executeTickerCommand(symbol, 'description', exchange);
              }}
            >
              {symbol}
            </button>
          );
        },
      }),
      columnHelper.accessor('newsCount', {
        header: () => (
          <div className="flex items-center gap-1">
            <Newspaper className="w-3.5 h-3.5" />
            <span>News</span>
          </div>
        ),
        size: 55,
        cell: (info) => {
          const count = info.getValue();
          const row = info.row.original;
          return (
            <button
              type="button"
              className={`font-mono font-semibold text-center cursor-pointer hover:underline w-full ${count >= 3 ? 'text-orange-600' : count >= 2 ? 'text-amber-600' : 'text-blue-600'
                }`}
              onClick={() => handleOpenNews(row.symbol, row.articles)}
              title="Click para ver noticias"
            >
              {count}
            </button>
          );
        },
      }),
      columnHelper.accessor('lastNewsTime', {
        header: t('scanner.tableHeaders.lastNews') || 'Last News',
        size: 70,
        cell: (info) => {
          const isoTime = info.getValue();
          if (!isoTime) return <span className="text-slate-400">—</span>;
          try {
            const d = new Date(isoTime);
            const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
            const isRecent = Date.now() - d.getTime() < 30 * 60 * 1000; // < 30 min
            return (
              <div className={`font-mono text-xs ${isRecent ? 'text-emerald-600 font-semibold' : 'text-slate-600'}`}>
                {time}
              </div>
            );
          } catch {
            return <span className="text-slate-400">—</span>;
          }
        },
      }),
      columnHelper.accessor('scannerCategories', {
        header: () => (
          <div className="flex items-center gap-1">
            <span>{t('scanner.tableHeaders.tables') || 'Tables'}</span>
            {/* Tooltip container with CSS hover - appears instantly */}
            <div className="relative inline-block group/tip">
              <Info className="w-3 h-3 text-slate-400 group-hover/tip:text-blue-500 cursor-help" />
              <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 hidden group-hover/tip:block z-[99999] pointer-events-none">
                <div className="bg-slate-900 text-white text-[10px] rounded-lg shadow-2xl px-3 py-2 whitespace-nowrap border border-slate-600">
                  <div className="font-bold text-blue-400 mb-1">{t('scanner.tablesLegend')}</div>
                  <div className="space-y-0.5">
                    <div><span className="text-emerald-400 font-bold">G↑</span> Gap Up  <span className="text-rose-400 font-bold">G↓</span> Gap Down</div>
                    <div><span className="text-emerald-400 font-bold">M↑</span> Mom Up  <span className="text-rose-400 font-bold">M↓</span> Mom Down</div>
                    <div><span className="text-emerald-400 font-bold">W</span> Winners  <span className="text-rose-400 font-bold">L</span> Losers</div>
                    <div><span className="text-emerald-400 font-bold">H</span> Highs  <span className="text-rose-400 font-bold">Lo</span> Lows</div>
                    <div><span className="text-amber-400 font-bold">A</span> Anomalies  <span className="text-blue-400 font-bold">V</span> Volume  <span className="text-purple-400 font-bold">R</span> Reversals</div>
                  </div>
                  {/* Arrow */}
                  <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-slate-900"></div>
                </div>
              </div>
            </div>
          </div>
        ),
        size: 140,
        cell: (info) => {
          // Mapear nombres de categorías a etiquetas MUY cortas
          const categoryLabels: Record<string, string> = {
            'gappers_up': 'G↑',
            'gappers_down': 'G↓',
            'momentum_up': 'M↑',
            'momentum_down': 'M↓',
            'winners': 'W',
            'losers': 'L',
            'new_highs': 'H',
            'new_lows': 'Lo',
            'anomalies': 'A',
            'high_volume': 'V',
            'reversals': 'R',
          };
          
          // Filtrar: solo categorías válidas que tengan label
          const rawCategories = info.getValue() || [];
          const categories = rawCategories.filter((cat): cat is string => 
            typeof cat === 'string' && cat.length > 0 && categoryLabels[cat] !== undefined
          );
          
          if (categories.length === 0) return <span className="text-slate-400">—</span>;
          
          // Mostrar como texto simple separado por espacios (no se corta)
          return (
            <span className="text-[10px] font-medium text-slate-600">
              {categories.map(cat => categoryLabels[cat]).join(' ')}
            </span>
          );
        },
      }),
      columnHelper.accessor('price', {
        header: t('scanner.tableHeaders.price'),
        size: 80,
        cell: (info) => <PriceCell price={info.getValue()} symbol={info.row.original.symbol} />,
      }),
      columnHelper.accessor('change_percent', {
        header: t('scanner.tableHeaders.gapPercent'),
        size: 85,
        cell: (info) => {
          const value = info.getValue();
          return (
            <div className={`font-mono font-semibold ${(value || 0) > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('volume_today', {
        header: t('scanner.tableHeaders.volume'),
        size: 90,
        cell: (info) => <div className="font-mono text-slate-700">{formatNumber(info.getValue())}</div>,
      }),
      columnHelper.accessor((row) => row.rvol_slot ?? row.rvol, {
        id: 'rvol',
        header: t('scanner.tableHeaders.rvol'),
        size: 70,
        cell: (info) => {
          const value = info.getValue() ?? 0;
          return (
            <div className={`font-mono font-semibold ${value > 3 ? 'text-blue-700' : value > 1.5 ? 'text-blue-600' : 'text-slate-500'}`}>
              {formatRVOL(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('market_cap', {
        header: t('scanner.tableHeaders.marketCap'),
        size: 100,
        cell: (info) => <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>,
      }),
    ],
    [t, executeTickerCommand, handleOpenNews]
  );

  const table = useReactTable({
    data: tickersWithNews,
    columns,
    state: { sorting, columnOrder, columnVisibility },
    onSortingChange: setSorting,
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode,
  });

  // ======================================================================
  // RENDER
  // ======================================================================

  // Loading
  if (loading) {
    return (
      <div className="h-full flex flex-col">
        <MarketTableLayout title={title} isLive={ws.isConnected} count={0} listName="with_news" onClose={onClose} />
        <div className="flex-1 flex items-center justify-center bg-slate-50">
          <div className="text-center">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3" />
            <p className="text-slate-600 text-sm">{t('news.loadingNews')}</p>
          </div>
        </div>
      </div>
    );
  }

  // Sin datos
  if (tickersWithNews.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <MarketTableLayout title={title} isLive={ws.isConnected} count={0} listName="with_news" onClose={onClose} />
        <div className="flex-1 flex items-center justify-center bg-slate-50">
          <div className="text-center p-6">
            <Newspaper className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-lg font-semibold text-slate-700 mb-2">
              {t('scanner.noTickersWithNews')}
            </h3>
            <p className="text-sm text-slate-500 max-w-xs">
              {scannerTickersCount > 0
                ? t('scanner.noTickersWithNewsButScanner', { count: scannerTickersCount })
                : t('scanner.noTickersWithNewsDescription')}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Tabla con datos
  return (
    <VirtualizedDataTable
      table={table}
      showResizeHandles={false}
      stickyHeader={true}
      isLoading={false}
      estimateSize={18}
      overscan={10}
      enableVirtualization={true}
      getRowClassName={() => ''}
    >
      <MarketTableLayout
        title={title}
        isLive={ws.isConnected}
        count={tickersWithNews.length}
        listName="with_news"
        onClose={onClose}
        rightActions={<TableSettings table={table} />}
      />
    </VirtualizedDataTable>
  );
}
