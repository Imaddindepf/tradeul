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
import { Newspaper, ExternalLink } from 'lucide-react';

// Floating windows
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';

// Zustand stores
import { useTickersStore } from '@/stores/useTickersStore';

// WebSocket
import { useAuthWebSocket } from '@/hooks/useAuthWebSocket';

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
        <p className="text-slate-500 text-sm">No hay noticias para {ticker}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="px-3 py-2 bg-slate-50 border-b border-slate-200">
        <span className="text-sm font-bold text-blue-600">{ticker}</span>
        <span className="text-xs text-slate-500 ml-2">{articles.length} noticias hoy</span>
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

  // WebSocket status
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useAuthWebSocket(wsUrl);

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
  // CALCULAR INTERSECCIÓN
  // ======================================================================

  const tickersWithNews = useMemo((): TickerWithNews[] => {
    // 1. Obtener todos los tickers de las tablas del scanner
    const scannerTickers = new Set<string>();
    const tickerDataMap = new Map<string, Ticker>();

    tickerLists.forEach((list, listName) => {
      if (!SCANNER_CATEGORIES.includes(listName)) return;

      list.tickers.forEach((ticker, symbol) => {
        const upper = symbol.toUpperCase();
        scannerTickers.add(upper);
        if (!tickerDataMap.has(upper)) {
          tickerDataMap.set(upper, ticker);
        }
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

        result.push({
          ...tickerData,
          newsCount: articles.length,
          articles: sortedArticles,
        });
      }
    });

    // Ordenar por número de noticias
    result.sort((a, b) => b.newsCount - a.newsCount);

    return result;
  }, [tickerLists, allNews]);

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
        size: 60,
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
            <p className="text-slate-600 text-sm">Cargando noticias...</p>
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
                ? `Hay ${scannerTickersCount} tickers en el scanner, pero ninguno tiene noticias hoy.`
                : 'Abre primero alguna tabla del scanner (Gap Up, Momentum, etc.)'}
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
