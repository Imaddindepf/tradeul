/**
 * Category Table V2 - Nueva Arquitectura
 * 
 * Stack:
 * - Zustand para state management global
 * - RxJS para WebSocket streams
 * - TanStack Table + TanStack Virtual para virtualización
 * 
 * Mejoras vs V1:
 * - Escala a 10,000+ filas sin lag
 * - Estado compartido entre tabs
 * - Streams composables con RxJS
 * - Mejor separación de concerns
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
import type { SortingState, ColumnResizeMode, Row } from '@tanstack/react-table';
import { formatNumber, formatPercent, formatRVOL } from '@/lib/formatters';
import { PriceCell } from './PriceCell';
import type { Ticker } from '@/lib/types';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';

// Zustand store
import { useTickersStore, selectOrderedTickers } from '@/stores/useTickersStore';

// RxJS WebSocket (ya autenticado desde AuthWebSocketProvider)
import { useListSubscription } from '@/hooks/useRxWebSocket';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';

// User Filters - Zustand store para reactividad en tiempo real
import { useFiltersStore } from '@/stores/useFiltersStore';
import { passesFilter } from '@/lib/scanner/filterEngine';

// User Preferences Store - para persistir configuración de columnas en BD
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

const columnHelper = createColumnHelper<Ticker>();

// ============================================================================
// DEFAULT VISIBLE COLUMNS PER CATEGORY
// ============================================================================
// Define qué columnas mostrar por defecto en cada categoría.
// El usuario puede cambiar esto en Settings y se guarda en localStorage.
// Columnas no listadas = ocultas por defecto (excepto row_number y symbol que no se ocultan)

const DEFAULT_VISIBLE_COLUMNS: Record<string, string[]> = {
  // Gappers: enfocado en gap % y volumen relativo
  gappers_up: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap', 'free_float'],
  gappers_down: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap', 'free_float'],

  // Momentum: cambio % + chg_5min (vela de ignición) + RVOL alto
  momentum_up: ['price', 'change_percent', 'chg_5min', 'volume_today', 'rvol', 'price_vs_vwap', 'market_cap'],
  momentum_down: ['price', 'change_percent', 'chg_5min', 'volume_today', 'rvol', 'price_vs_vwap', 'market_cap'],

  // Winners/Losers: top movers del día
  winners: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap', 'dollar_volume'],
  losers: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap', 'dollar_volume'],

  // New Highs/Lows: precio histórico
  new_highs: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap'],
  new_lows: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap'],

  // Anomalies: Z-Score de trades (actividad anormal)
  anomalies: ['price', 'change_percent', 'trades_z_score', 'trades_today', 'avg_trades_5d', 'volume_today', 'rvol', 'market_cap'],

  // High Volume: métricas de volumen detalladas
  high_volume: ['price', 'change_percent', 'volume_today', 'rvol', 'dollar_volume', 'vol_1min', 'vol_5min'],

  // Reversals: VWAP y momentum corto
  reversals: ['price', 'change_percent', 'volume_today', 'rvol', 'price_vs_vwap', 'vol_5min'],

  // Post-Market: SOLO esta tabla muestra columnas PM por defecto
  post_market: ['price', 'change_percent', 'postmarket_change_percent', 'postmarket_volume', 'volume_today', 'market_cap'],

  // With News: básico para contexto de noticias
  with_news: ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap'],
};

// Columnas base visibles para categorías no definidas
const DEFAULT_BASE_COLUMNS = ['price', 'change_percent', 'volume_today', 'rvol', 'market_cap'];

// Genera el objeto de visibilidad de columnas (todas las columnas excepto las visibles = false)
const ALL_HIDEABLE_COLUMNS = [
  'price', 'change_percent', 'volume_today', 'rvol', 'market_cap', 'free_float',
  'shares_outstanding', 'minute_volume', 'avg_volume_5d', 'avg_volume_10d', 'avg_volume_3m',
  'dollar_volume', 'volume_today_pct', 'volume_yesterday_pct', 'vol_1min', 'vol_5min',
  'vol_10min', 'vol_15min', 'vol_30min', 'chg_1min', 'chg_5min', 'chg_10min', 'chg_15min', 'chg_30min',
  'price_vs_vwap', 'postmarket_change_percent', 'postmarket_volume', 'spread', 'bid_size',
  'ask_size', 'bid_ask_ratio', 'distance_from_nbbo', 'atr_percent', 'atr_used',
  // Trades anomaly detection columns
  'trades_today', 'avg_trades_5d', 'trades_z_score',
];

function getDefaultColumnVisibility(listName: string): Record<string, boolean> {
  const visibleColumns = DEFAULT_VISIBLE_COLUMNS[listName] || DEFAULT_BASE_COLUMNS;
  const visibility: Record<string, boolean> = {};

  // Marcar todas las columnas ocultables como ocultas
  ALL_HIDEABLE_COLUMNS.forEach(col => {
    visibility[col] = false;
  });

  // Mostrar solo las columnas configuradas para esta categoría
  visibleColumns.forEach(col => {
    visibility[col] = true;
  });

  return visibility;
}

// ============================================================================
// PROPS
// ============================================================================

interface CategoryTableV2Props {
  title: string;
  listName: string;
  onClose?: () => void;
}

// ============================================================================
// COMPONENT
// ============================================================================

export default function CategoryTableV2({ title, listName, onClose }: CategoryTableV2Props) {
  const { t } = useTranslation();

  // ======================================================================
  // STATE (Zustand + local UI state)
  // ======================================================================

  // Zustand store selectors
  const initializeList = useTickersStore((state) => state.initializeList);
  const applyDeltas = useTickersStore((state) => state.applyDeltas);
  const updateAggregates = useTickersStore((state) => state.updateAggregates);
  const updateSequence = useTickersStore((state) => state.updateSequence);
  const getList = useTickersStore((state) => state.getList);

  // Get tickers for this list (memoized selector)
  const baseTickers = useTickersStore(selectOrderedTickers(listName));

  // User filters - Zustand store para reactividad en tiempo real
  const activeFilters = useFiltersStore((state) => state.activeFilters);
  const hasActiveFilters = useFiltersStore((state) => state.hasActiveFilters);

  // Serializar filtros para detectar cambios correctamente
  const filtersKey = JSON.stringify(activeFilters);

  // Apply filters with useMemo for performance
  const tickers = useMemo(() => {
    if (!hasActiveFilters) {
      return baseTickers; // No filters = show all
    }

    // Aplicar filtros del store directamente
    return baseTickers.filter(ticker => passesFilter(ticker, activeFilters));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseTickers, filtersKey, hasActiveFilters]);

  // Local UI state (no afecta datos)
  // Ordenamiento inicial según la categoría
  const getInitialSorting = (): SortingState => {
    switch (listName) {
      case 'high_volume':
        return [{ id: 'volume_today', desc: true }];
      case 'gappers_up':
        return [{ id: 'change_percent', desc: true }];
      case 'gappers_down':
        return [{ id: 'change_percent', desc: false }];
      case 'momentum_up':
        // Momentum Up ordena por cambio en 5 minutos (vela de ignición)
        return [{ id: 'chg_5min', desc: true }];
      case 'winners':
        return [{ id: 'change_percent', desc: true }];
      case 'momentum_down':
      case 'losers':
        return [{ id: 'change_percent', desc: false }];
      case 'post_market':
        // Ordenar por cambio % post-market (mayor movimiento primero)
        return [{ id: 'postmarket_change_percent', desc: true }];
      default:
        return [];
    }
  };

  // ========================================================================
  // USER PREFERENCES STORE (sincroniza con BD)
  // ========================================================================

  // Acciones del store global
  const saveColumnVisibilityToStore = useUserPreferencesStore((s) => s.saveColumnVisibility);
  const saveColumnOrderToStore = useUserPreferencesStore((s) => s.saveColumnOrder);

  // Datos del store global para esta lista
  const storedColumnVisibility = useUserPreferencesStore((s) => s.columnVisibility[listName]);
  const storedColumnOrder = useUserPreferencesStore((s) => s.columnOrder[listName]);

  // Helper para localStorage key (solo para sorting que es local)
  const getStorageKey = (suffix: string) => `scanner_table_${listName}_${suffix}`;

  // Cargar preferencias desde localStorage (solo para sorting)
  const loadFromStorage = <T,>(key: string, defaultValue: T): T => {
    if (typeof window === 'undefined') return defaultValue;
    try {
      const stored = localStorage.getItem(getStorageKey(key));
      return stored ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  };

  // Guardar preferencias en localStorage (solo para sorting)
  const saveToStorage = (key: string, value: unknown) => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(getStorageKey(key), JSON.stringify(value));
    } catch {
      // Silent fail for storage errors
    }
  };

  // Sorting: se guarda en localStorage (local)
  const [sorting, setSorting] = useState<SortingState>(() =>
    loadFromStorage('sorting', getInitialSorting())
  );

  // Column Order: usa store global (BD) o vacío
  const [columnOrder, setColumnOrder] = useState<string[]>(() =>
    storedColumnOrder || []
  );

  // Column Visibility: usa store global (BD) o defaults de la categoría
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(() => {
    // Si hay configuración guardada en el store global, usarla
    if (storedColumnVisibility && Object.keys(storedColumnVisibility).length > 0) {
      return storedColumnVisibility;
    }
    // Si no, usar los defaults de la categoría
    return getDefaultColumnVisibility(listName);
  });
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');

  // Persistir sorting en localStorage (local)
  useEffect(() => {
    saveToStorage('sorting', sorting);
  }, [sorting]);

  // Persistir columnOrder en store global (BD)
  useEffect(() => {
    if (columnOrder.length > 0) {
      saveColumnOrderToStore(listName, columnOrder);
    }
  }, [columnOrder, listName, saveColumnOrderToStore]);

  // Persistir columnVisibility en store global (BD)
  useEffect(() => {
    if (Object.keys(columnVisibility).length > 0) {
      saveColumnVisibilityToStore(listName, columnVisibility);
    }
  }, [columnVisibility, listName, saveColumnVisibilityToStore]);

  const [isReady, setIsReady] = useState(false);
  const [noDataAvailable, setNoDataAvailable] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Animaciones (local state) - Solo para ranking changes, no precio
  const [newTickers, setNewTickers] = useState<Set<string>>(new Set());
  const [rowChanges, setRowChanges] = useState<Map<string, 'up' | 'down'>>(new Map());

  // Command executor para abrir Description
  const { executeTickerCommand } = useCommandExecutor();

  // ======================================================================
  // WEBSOCKET (desde AuthWebSocketProvider)
  // ======================================================================

  const debug = false; // Cambiar a true para logs de WebSocket

  // WebSocket ya autenticado (compartido entre todas las tablas)
  const ws = useWebSocket();

  // Auto-subscribe/unsubscribe a la lista
  useListSubscription(listName, debug);

  // ======================================================================
  // WEBSOCKET HANDLERS
  // ======================================================================

  // Handle snapshots
  const handleSnapshot = useCallback(
    (snapshot: any) => {
      if (!snapshot.rows || !Array.isArray(snapshot.rows)) return;

      // Initialize list in Zustand store
      initializeList(listName, snapshot);
      setIsReady(true);
    },
    [listName, initializeList]
  );

  // Handle deltas
  const handleDelta = useCallback(
    (delta: any) => {
      if (!isReady) {
        // Request resync if not ready
        ws.send({ action: 'resync', list: listName });
        return;
      }

      if (!delta.deltas || !Array.isArray(delta.deltas)) return;

      // Apply deltas to Zustand store
      applyDeltas(listName, delta.deltas, delta.sequence);

      // Trigger animations for added/reranked tickers
      // Tiempos optimizados: ligeramente > duración CSS
      delta.deltas.forEach((d: any) => {
        if (d.action === 'add') {
          setNewTickers((prev) => new Set(prev).add(d.symbol));
          setTimeout(() => {
            setNewTickers((prev) => {
              const updated = new Set(prev);
              updated.delete(d.symbol);
              return updated;
            });
          }, 850); // CSS: 800ms
        } else if (d.action === 'rerank') {
          const direction = d.new_rank < d.old_rank ? 'up' : 'down';
          setRowChanges((prev) => new Map(prev).set(d.symbol, direction));
          setTimeout(() => {
            setRowChanges((prev) => {
              const updated = new Map(prev);
              updated.delete(d.symbol);
              return updated;
            });
          }, 450); // CSS: 400ms
        }
      });
    },
    [listName, isReady, applyDeltas, ws]
  );

  // ======================================================================
  // ======================================================================
  // PAGE VISIBILITY (profesional: resync cuando vuelve de tab inactiva)
  // ======================================================================

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden && ws.isConnected) {
        // Tab volvió a ser activa - pedir resync para datos frescos
        // console.log(`🔄 Tab activa - resyncing ${listName}`);
        ws.send({ action: 'resync', list: listName });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [listName, ws.isConnected, ws.send]);

  // ======================================================================
  // STREAM SUBSCRIPTIONS
  // ======================================================================

  useEffect(() => {
    if (!ws.isConnected) {
      setConnectionError('Connecting to server...');
      return;
    }

    setConnectionError(null);

    // Timeout para mostrar "sin datos" si no llegan datos en 10 segundos
    const dataTimeout = setTimeout(() => {
      if (!isReady) {
        setNoDataAvailable(true);
      }
    }, 10000);

    // Subscribe to snapshots
    const snapshotSub = ws.snapshots$.subscribe((snapshot: any) => {
      if (snapshot.list === listName) {
        setNoDataAvailable(false);
        handleSnapshot(snapshot);
      }
    });

    // Subscribe to deltas
    const deltaSub = ws.deltas$.subscribe((delta: any) => {
      if (delta.list === listName) {
        handleDelta(delta);
      }
    });

    // Subscribe to batched aggregates
    // Nota: El tick indicator se maneja en PriceCell de forma aislada
    const aggregateSub = ws.aggregates$.subscribe((batch: any) => {
      if (batch.type === 'aggregates_batch' && batch.data instanceof Map) {
        updateAggregates(batch.data);
      }
    });

    // Subscribe to error messages (for "no data available" errors)
    const errorMsgSub = ws.messages$.subscribe((msg: any) => {
      if (msg.type === 'error' && msg.list === listName) {
        if (msg.message?.includes('No snapshot available')) {
          setNoDataAvailable(true);
          setIsReady(true); // Stop loading state
        }
      }
    });

    return () => {
      clearTimeout(dataTimeout);
      snapshotSub.unsubscribe();
      deltaSub.unsubscribe();
      aggregateSub.unsubscribe();
      errorMsgSub.unsubscribe();
    };
    // NOTA: isReady removido de dependencias para evitar bucle infinito
    // El timeout usa isReady solo para lectura, no necesita re-suscribirse cuando cambia
  }, [ws.isConnected, ws.snapshots$, ws.deltas$, ws.aggregates$, ws.messages$, listName, handleSnapshot, handleDelta, updateAggregates]);

  // ======================================================================
  // TABLE CONFIGURATION
  // ======================================================================

  // Memoized data (viene directo de Zustand)
  const data = useMemo(() => tickers, [tickers]);

  // Get list info from store
  const list = getList(listName);
  const sequence = list?.sequence || 0;
  const lastUpdateTime = list?.lastUpdate || null;

  // Columns definition (same as before)
  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'row_number',
        header: '#',
        size: 40,
        minSize: 35,
        maxSize: 60,
        enableResizing: true,
        enableSorting: false,
        enableHiding: false,
        cell: (info) => (
          <div className="text-center font-semibold text-slate-400">
            {info.row.index + 1}
          </div>
        ),
      }),
      columnHelper.accessor('symbol', {
        header: t('scanner.tableHeaders.symbol'),
        size: 75,
        minSize: 55,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: false,
        cell: (info) => (
          <div
            className="font-bold text-blue-600 cursor-pointer hover:text-blue-800 hover:underline transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              const symbol = info.getValue();
              const tickerData = info.row.original;
              executeTickerCommand(symbol, 'fan', tickerData.exchange);
            }}
            title={t('scanner.clickDescription')}
          >
            {info.getValue()}
          </div>
        ),
      }),
      columnHelper.accessor('price', {
        header: t('scanner.tableHeaders.price'),
        size: 80,
        minSize: 60,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const price = info.getValue();
          const symbol = info.row.original.symbol;
          return (
            <PriceCell price={price} symbol={symbol} />
          );
        },
      }),
      columnHelper.accessor('change_percent', {
        header: t('scanner.tableHeaders.gapPercent'),
        size: 85,
        minSize: 70,
        maxSize: 130,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          const isPositive = (value || 0) > 0;
          return (
            <div
              className={`font-mono font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'
                }`}
            >
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('volume_today', {
        header: t('scanner.tableHeaders.volume'),
        size: 90,
        minSize: 70,
        maxSize: 140,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => (
          <div className="font-mono text-slate-700 font-medium">
            {formatNumber(info.getValue())}
          </div>
        ),
      }),
      columnHelper.accessor((row) => row.rvol_slot ?? row.rvol, {
        id: 'rvol',
        header: t('scanner.tableHeaders.rvol'),
        size: 70,
        minSize: 55,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const ticker = info.row.original;
          const displayValue = ticker.rvol_slot ?? ticker.rvol ?? 0;
          return (
            <div
              className={`
              font-mono font-semibold
              ${displayValue > 3
                  ? 'text-blue-700'
                  : displayValue > 1.5
                    ? 'text-blue-600'
                    : 'text-slate-500'
                }
            `}
            >
              {formatRVOL(displayValue)}
            </div>
          );
        },
      }),
      columnHelper.accessor('market_cap', {
        header: t('scanner.tableHeaders.marketCap'),
        size: 100,
        minSize: 80,
        maxSize: 160,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => (
          <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>
        ),
      }),
      columnHelper.accessor('free_float', {
        id: 'free_float',
        header: 'Free Float',
        size: 90,
        minSize: 70,
        maxSize: 140,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => (
          <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>
        ),
      }),
      columnHelper.accessor('shares_outstanding', {
        id: 'shares_outstanding',
        header: 'Outstanding',
        size: 95,
        minSize: 75,
        maxSize: 140,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => (
          <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>
        ),
      }),
      columnHelper.accessor('minute_volume', {
        header: 'Min Vol',
        size: 80,
        minSize: 60,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('avg_volume_5d', {
        header: 'Vol 5D',
        size: 85,
        minSize: 65,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('avg_volume_10d', {
        header: 'Vol 10D',
        size: 85,
        minSize: 65,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('avg_volume_3m', {
        header: 'Vol 3M',
        size: 85,
        minSize: 65,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('dollar_volume', {
        header: '$ Vol',
        size: 90,
        minSize: 70,
        maxSize: 130,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          // Format as currency with K/M/B suffix
          const formatDollarVolume = (v: number) => {
            if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
            if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
            if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
            return `$${v.toFixed(0)}`;
          };
          return <div className="font-mono text-slate-600">{formatDollarVolume(value)}</div>;
        },
      }),
      columnHelper.accessor('volume_today_pct', {
        header: 'Vol Today %',
        size: 85,
        minSize: 65,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const color = value >= 150 ? 'text-green-600' : value >= 100 ? 'text-slate-600' : 'text-red-500';
          return <div className={`font-mono ${color}`}>{value.toFixed(0)}%</div>;
        },
      }),
      columnHelper.accessor('volume_yesterday_pct', {
        header: 'Vol Yest %',
        size: 85,
        minSize: 65,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const color = value >= 150 ? 'text-green-600' : value >= 100 ? 'text-slate-600' : 'text-red-500';
          return <div className={`font-mono ${color}`}>{value.toFixed(0)}%</div>;
        },
      }),
      columnHelper.accessor('vol_1min', {
        header: '1m vol',
        size: 75,
        minSize: 55,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('vol_5min', {
        header: '5m vol',
        size: 75,
        minSize: 55,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('vol_10min', {
        header: '10m vol',
        size: 80,
        minSize: 60,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('vol_15min', {
        header: '15m vol',
        size: 80,
        minSize: 60,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('vol_30min', {
        header: '30m vol',
        size: 80,
        minSize: 60,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{formatNumber(value)}</div>;
        },
      }),
      // Price change window columns (% change in last N minutes - per-second precision)
      columnHelper.accessor('chg_1min', {
        header: '1m Chg%',
        size: 80,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return <div className={`font-mono font-medium ${colorClass}`}>{prefix}{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('chg_5min', {
        header: '5m Chg%',
        size: 80,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return <div className={`font-mono font-semibold ${colorClass}`}>{prefix}{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('chg_10min', {
        header: '10m Chg%',
        size: 85,
        minSize: 65,
        maxSize: 105,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return <div className={`font-mono font-medium ${colorClass}`}>{prefix}{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('chg_15min', {
        header: '15m Chg%',
        size: 85,
        minSize: 65,
        maxSize: 105,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return <div className={`font-mono font-medium ${colorClass}`}>{prefix}{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('chg_30min', {
        header: '30m Chg%',
        size: 85,
        minSize: 65,
        maxSize: 105,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return <div className={`font-mono font-medium ${colorClass}`}>{prefix}{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('price_vs_vwap', {
        header: 'vs VWAP',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const colorClass = value > 0
            ? 'text-green-600'
            : value < 0
              ? 'text-red-600'
              : 'text-slate-600';
          const prefix = value > 0 ? '+' : '';
          return <div className={`font-mono ${colorClass}`}>{prefix}{value.toFixed(1)}%</div>;
        },
      }),
      // Post-Market columns (populated during POST_MARKET session 16:00-20:00 ET)
      columnHelper.accessor('postmarket_change_percent', {
        header: 'PM Chg%',
        size: 85,
        minSize: 70,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const isPositive = value > 0;
          const colorClass = isPositive ? 'text-emerald-600' : 'text-rose-600';
          const prefix = isPositive ? '+' : '';
          return (
            <div className={`font-mono font-semibold ${colorClass}`}>
              {prefix}{value.toFixed(2)}%
            </div>
          );
        },
      }),
      columnHelper.accessor('postmarket_volume', {
        header: 'PM Vol',
        size: 90,
        minSize: 70,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return (
            <div className="font-mono text-purple-600 font-medium">
              {formatNumber(value)}
            </div>
          );
        },
      }),
      // Trades Anomaly Detection columns (Z-Score based)
      columnHelper.accessor('trades_z_score', {
        header: 'Z-Score',
        size: 80,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          // Color based on anomaly level:
          // < 2: normal (gray), 2-3: elevated (amber), >= 3: anomaly (red/fire)
          const colorClass = value >= 3
            ? 'text-red-600 font-bold'
            : value >= 2
              ? 'text-amber-600 font-semibold'
              : 'text-slate-600';
          const emoji = value >= 5 ? '🔥' : value >= 3 ? '⚠️' : '';
          return (
            <div className={`font-mono ${colorClass}`}>
              {emoji}{value.toFixed(1)}
            </div>
          );
        },
      }),
      columnHelper.accessor('trades_today', {
        header: 'Trades',
        size: 85,
        minSize: 65,
        maxSize: 110,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          // Format large numbers (K/M)
          return (
            <div className="font-mono text-cyan-600">
              {formatNumber(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('avg_trades_5d', {
        header: 'Avg 5d',
        size: 80,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return (
            <div className="font-mono text-slate-500">
              {formatNumber(Math.round(value))}
            </div>
          );
        },
      }),
      columnHelper.accessor('spread', {
        header: 'Spread',
        size: 70,
        minSize: 50,
        maxSize: 90,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          // Spread is in cents: 50.00 = $0.50
          // Color: green if tight (<10¢), yellow if medium (10-25¢), red if wide (>25¢)
          const colorClass = value < 10
            ? 'text-green-600'
            : value < 25
              ? 'text-amber-600'
              : 'text-red-600';
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(1)}¢</div>;
        },
      }),
      columnHelper.accessor('bid_size', {
        header: 'Bid Size',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-blue-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('ask_size', {
        header: 'Ask Size',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-orange-600">{formatNumber(value)}</div>;
        },
      }),
      columnHelper.accessor('bid_ask_ratio', {
        header: 'B/A Ratio',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          // >1 = more demand (green), <1 = more supply (red)
          const colorClass = value > 1.5
            ? 'text-green-600 font-semibold'
            : value < 0.67
              ? 'text-red-600 font-semibold'
              : 'text-slate-600';
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(2)}</div>;
        },
      }),
      columnHelper.accessor('distance_from_nbbo', {
        header: 'NBBO Dist',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          return <div className="font-mono text-slate-600">{value.toFixed(2)}%</div>;
        },
      }),
      columnHelper.accessor('atr_percent', {
        header: t('scanner.tableHeaders.atrPercent'),
        size: 70,
        minSize: 60,
        maxSize: 100,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === null || value === undefined)
            return <div className="text-slate-400">-</div>;
          const colorClass =
            value > 5 ? 'text-orange-600 font-semibold' : 'text-slate-600';
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(1)}%</div>;
        },
      }),
      columnHelper.accessor(
        (row) => {
          const atr_percent = row.atr_percent;
          const prev_close = row.prev_close;
          const change_percent = row.change_percent || 0;

          if (!atr_percent || atr_percent === 0 || !prev_close) return null;

          const high = row.intraday_high ?? row.high;
          const low = row.intraday_low ?? row.low;

          if (!high || !low) {
            return (Math.abs(change_percent) / atr_percent) * 100;
          }

          let range_percent;
          if (change_percent >= 0) {
            range_percent = ((high - prev_close) / prev_close) * 100;
          } else {
            range_percent = ((prev_close - low) / prev_close) * 100;
          }

          return (Math.abs(range_percent) / atr_percent) * 100;
        },
        {
          id: 'atr_used',
          header: t('scanner.tableHeaders.atrUsed'),
          size: 85,
          minSize: 70,
          maxSize: 120,
          enableResizing: true,
          enableSorting: true,
          enableHiding: true,
          cell: (info) => {
            const value = info.getValue();
            if (value === null || value === undefined)
              return <div className="text-slate-400">-</div>;

            let colorClass = 'text-slate-600';
            if (value > 150) {
              colorClass = 'text-red-600 font-bold';
            } else if (value > 100) {
              colorClass = 'text-orange-600 font-semibold';
            } else if (value > 75) {
              colorClass = 'text-yellow-600 font-medium';
            } else if (value > 50) {
              colorClass = 'text-blue-600';
            }

            return (
              <div className={`font-mono ${colorClass}`}>{value.toFixed(0)}%</div>
            );
          },
        }
      ),
    ],
    [] // Sin dependencias - columnas son estáticas, PriceCell maneja su propio estado
  );

  // TanStack Table instance
  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnOrder,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode,
    enableColumnResizing: true,
    columnResizeDirection: 'ltr',
    autoResetPageIndex: false,
    autoResetExpanded: false,
    enableRowSelection: false,
    manualPagination: true,
  });

  // ======================================================================
  // RENDER
  // ======================================================================

  // Mensaje cuando no hay datos disponibles
  if (noDataAvailable && data.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <MarketTableLayout
          title={title}
          isLive={ws.isConnected}
          count={0}
          listName={listName}
          onClose={onClose}
        />
        <div className="flex-1 flex items-center justify-center bg-slate-50">
          <div className="text-center p-6">
            <h3 className="text-lg font-semibold text-slate-700 mb-2">
              {t('common.noData')}
            </h3>
            <p className="text-sm text-slate-500 max-w-xs">
              {connectionError || t('scanner.marketClosed')}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <VirtualizedDataTable
        table={table}
        showResizeHandles={false}
        stickyHeader={true}
        isLoading={!isReady && !noDataAvailable}
        estimateSize={18}
        overscan={10}
        enableVirtualization={true}
        getRowClassName={(row: Row<Ticker>) => {
          const ticker = row.original;
          const classes: string[] = [];

          // Animación para nuevos tickers (azul)
          if (newTickers.has(ticker.symbol)) {
            classes.push('new-ticker-flash');
          }
          // Animaciones de subida/bajada (verde/rojo)
          else {
            const rowChange = rowChanges.get(ticker.symbol);
            if (rowChange === 'up') {
              classes.push('row-flash-up');
            } else if (rowChange === 'down') {
              classes.push('row-flash-down');
            }
          }

          return classes.join(' ');
        }}
      >
        <MarketTableLayout
          title={title}
          isLive={ws.isConnected}
          count={isReady ? data.length : undefined}
          sequence={isReady ? sequence : undefined}
          lastUpdateTime={lastUpdateTime}
          listName={listName}
          onClose={onClose}
          rightActions={
            <TableSettings
              table={table}
              onResetToDefaults={() => {
                // Restaurar defaults de la categoría
                // El useEffect se encargará de guardar en el store global (BD)
                setColumnVisibility(getDefaultColumnVisibility(listName));
                setColumnOrder([]);
              }}
            />
          }
        />
      </VirtualizedDataTable>
    </>
  );
}

