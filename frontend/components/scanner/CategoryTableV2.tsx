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
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, ColumnResizeMode, Row } from '@tanstack/react-table';
import { formatNumber, formatPercent, formatPrice, formatRVOL } from '@/lib/formatters';
import type { Ticker } from '@/lib/types';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import TickerMetadataModal from './TickerMetadataModal';

// Zustand store
import { useTickersStore, selectOrderedTickers } from '@/stores/useTickersStore';

// RxJS WebSocket
import { useRxWebSocket, useListSubscription } from '@/hooks/useRxWebSocket';

const columnHelper = createColumnHelper<Ticker>();

// ============================================================================
// PROPS
// ============================================================================

interface CategoryTableV2Props {
  title: string;
  listName: string;
}

// ============================================================================
// COMPONENT
// ============================================================================

export default function CategoryTableV2({ title, listName }: CategoryTableV2Props) {
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
  const tickers = useTickersStore(selectOrderedTickers(listName));
  
  // Local UI state (no afecta datos)
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [columnVisibility, setColumnVisibility] = useState({});
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');
  const [isReady, setIsReady] = useState(false);
  
  // Animaciones (local state)
  const [newTickers, setNewTickers] = useState<Set<string>>(new Set());
  const [rowChanges, setRowChanges] = useState<Map<string, 'up' | 'down'>>(new Map());
  
  // Modal state
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedTickerData, setSelectedTickerData] = useState<Ticker | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // ======================================================================
  // WEBSOCKET (RxJS Singleton)
  // ======================================================================
  
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const debug = process.env.NODE_ENV === 'development';
  
  // Singleton WebSocket (compartido entre todas las tablas)
  const ws = useRxWebSocket(wsUrl, debug);
  
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

      if (process.env.NODE_ENV === 'development') {
        console.log(`✅ [${listName}] Snapshot initialized:`, snapshot.rows.length, 'tickers');
      }
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
      delta.deltas.forEach((d: any) => {
        if (d.action === 'add') {
          setNewTickers((prev) => new Set(prev).add(d.symbol));
          setTimeout(() => {
            setNewTickers((prev) => {
              const updated = new Set(prev);
              updated.delete(d.symbol);
              return updated;
            });
          }, 3000);
        } else if (d.action === 'rerank') {
          const direction = d.new_rank < d.old_rank ? 'up' : 'down';
          setRowChanges((prev) => new Map(prev).set(d.symbol, direction));
          setTimeout(() => {
            setRowChanges((prev) => {
              const updated = new Map(prev);
              updated.delete(d.symbol);
              return updated;
            });
          }, 1200);
        }
      });

      if (process.env.NODE_ENV === 'development') {
        console.log(`🔄 [${listName}] Delta applied:`, delta.deltas.length, 'changes');
      }
    },
    [listName, isReady, applyDeltas, ws]
  );

  // ======================================================================
  // STREAM SUBSCRIPTIONS
  // ======================================================================
  
  useEffect(() => {
    if (!ws.isConnected) return;

    // Subscribe to snapshots
    const snapshotSub = ws.snapshots$.subscribe((snapshot: any) => {
      if (snapshot.list === listName) {
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
    const aggregateSub = ws.aggregates$.subscribe((batch: any) => {
      if (batch.type === 'aggregates_batch' && batch.data instanceof Map) {
        updateAggregates(batch.data);
        if (debug) {
          console.log(`📊 [${listName}] Aggregates batch:`, batch.count, 'updates');
        }
      }
    });

    return () => {
      snapshotSub.unsubscribe();
      deltaSub.unsubscribe();
      aggregateSub.unsubscribe();
    };
  }, [ws.isConnected, ws.snapshots$, ws.deltas$, ws.aggregates$, listName, handleSnapshot, handleDelta, updateAggregates, debug]);

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
        header: 'Symbol',
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
              setSelectedSymbol(symbol);
              setSelectedTickerData(tickerData);
              setIsModalOpen(true);
            }}
            title="Clic para ver metadatos"
          >
            {info.getValue()}
          </div>
        ),
      }),
      columnHelper.accessor('price', {
        header: 'Price',
        size: 80,
        minSize: 60,
        maxSize: 120,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => {
          const price = info.getValue();
          return (
            <div className="font-mono font-semibold px-1 py-0.5 rounded text-slate-900">
              {formatPrice(price)}
            </div>
          );
        },
      }),
      columnHelper.accessor('change_percent', {
        header: 'Gap %',
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
              className={`font-mono font-semibold ${
                isPositive ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('volume_today', {
        header: 'Volume',
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
        header: 'RVOL',
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
              ${
                displayValue > 3
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
        header: 'Market Cap',
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
        header: 'Float',
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
      columnHelper.accessor('atr_percent', {
        header: 'ATR%',
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
          header: 'ATR Used',
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
    []
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

  return (
    <>
      <VirtualizedDataTable
        table={table}
        showResizeHandles={false}
        stickyHeader={true}
        isLoading={!isReady}
        estimateSize={40}
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
          rightActions={<TableSettings table={table} />}
        />
      </VirtualizedDataTable>

      {/* Modal */}
      {typeof window !== 'undefined' && (
        <TickerMetadataModal
          symbol={selectedSymbol}
          tickerData={selectedTickerData}
          isOpen={isModalOpen}
          onClose={() => {
            setIsModalOpen(false);
            setSelectedSymbol(null);
            setSelectedTickerData(null);
          }}
        />
      )}
    </>
  );
}

