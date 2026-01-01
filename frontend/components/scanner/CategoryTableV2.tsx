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

const columnHelper = createColumnHelper<Ticker>();

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
      case 'winners':
        return [{ id: 'change_percent', desc: true }];
      case 'momentum_down':
      case 'losers':
        return [{ id: 'change_percent', desc: false }];
      default:
        return [];
    }
  };

  // Helper para localStorage key
  const getStorageKey = (suffix: string) => `scanner_table_${listName}_${suffix}`;

  // Cargar preferencias desde localStorage
  const loadFromStorage = <T,>(key: string, defaultValue: T): T => {
    if (typeof window === 'undefined') return defaultValue;
    try {
      const stored = localStorage.getItem(getStorageKey(key));
      return stored ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  };

  // Guardar preferencias en localStorage
  const saveToStorage = (key: string, value: unknown) => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(getStorageKey(key), JSON.stringify(value));
    } catch {
      // Silent fail for storage errors
    }
  };

  const [sorting, setSorting] = useState<SortingState>(() => 
    loadFromStorage('sorting', getInitialSorting())
  );
  const [columnOrder, setColumnOrder] = useState<string[]>(() => 
    loadFromStorage('columnOrder', [])
  );
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(() => 
    loadFromStorage('columnVisibility', {})
  );
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');

  // Persistir cambios en localStorage
  useEffect(() => {
    saveToStorage('sorting', sorting);
  }, [sorting]);

  useEffect(() => {
    saveToStorage('columnOrder', columnOrder);
  }, [columnOrder]);

  useEffect(() => {
    saveToStorage('columnVisibility', columnVisibility);
  }, [columnVisibility]);
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
              executeTickerCommand(symbol, 'description', tickerData.exchange);
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
      columnHelper.accessor('float_shares', {
        header: t('scanner.tableHeaders.float'),
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
          rightActions={<TableSettings table={table} />}
        />
      </VirtualizedDataTable>
    </>
  );
}

