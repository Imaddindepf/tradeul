'use client';

import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, ColumnResizeMode } from '@tanstack/react-table';
import { formatNumber, formatPercent, formatPrice, formatRVOL } from '@/lib/formatters';
import type { Ticker } from '@/lib/types';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { BaseDataTable } from '@/components/table/BaseDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';

type CellChange = {
  symbol: string;
  field: string;
  direction: 'up' | 'down';
};

type DeltaAction = {
  action: 'add' | 'remove' | 'update' | 'rerank';
  rank?: number;
  symbol: string;
  data?: Ticker;
  old_rank?: number;
  new_rank?: number;
};

const columnHelper = createColumnHelper<Ticker>();

interface CategoryTableProps {
  title: string;
  listName: string;
}

export default function CategoryTable({ title, listName }: CategoryTableProps) {
  const [tickersMap, setTickersMap] = useState<Map<string, Ticker>>(new Map());
  const [tickerOrder, setTickerOrder] = useState<string[]>([]);
  const [sequence, setSequence] = useState(0);
  const [cellChanges, setCellChanges] = useState<Map<string, CellChange>>(new Map());
  const [sorting, setSorting] = useState<SortingState>([{ id: 'rank', desc: false }]);
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);
  const [isReady, setIsReady] = useState(false);

  const deltaBuffer = useRef<DeltaAction[]>([]);
  const rafId = useRef<number | null>(null);
  const hasSubscribed = useRef(false);
  const handleSnapshotRef = useRef<((snapshot: any) => void) | null>(null);
  const handleDeltaRef = useRef<((delta: any) => void) | null>(null);

  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useWebSocket(wsUrl);

  const handleSnapshot = useCallback((snapshot: any) => {
    if (!snapshot.rows || !Array.isArray(snapshot.rows)) return;

    if (snapshot.rows.length === 0) {
      setIsReady(true);
      return;
    }

    const newMap = new Map<string, Ticker>();
    const newOrder: string[] = [];

    snapshot.rows.forEach((ticker: Ticker, index: number) => {
      ticker.rank = ticker.rank ?? index;
      newMap.set(ticker.symbol, ticker);
      newOrder.push(ticker.symbol);
    });

    newOrder.sort((a, b) => {
      const tickerA = newMap.get(a);
      const tickerB = newMap.get(b);
      return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
    });

    setTickersMap(newMap);
    setTickerOrder(newOrder);
    setSequence(snapshot.sequence);
    setLastUpdateTime(new Date());
    setIsReady(true);
  }, []);

  useEffect(() => {
    handleSnapshotRef.current = handleSnapshot;
    handleDeltaRef.current = handleDelta;
  });

  const applyDeltas = useCallback((deltas: DeltaAction[]) => {
    if (deltas.length === 0) return;

    setTickersMap((prevMap) => {
      const newMap = new Map(prevMap);
      const newChanges = new Map<string, CellChange>();

      deltas.forEach((delta) => {
        switch (delta.action) {
          case 'add': {
            if (delta.data) {
              delta.data.rank = delta.rank ?? 0;
              newMap.set(delta.symbol, delta.data);
            }
            break;
          }
          case 'remove': {
            newMap.delete(delta.symbol);
            break;
          }
          case 'update': {
            if (delta.data) {
              const oldTicker = newMap.get(delta.symbol);
              delta.data.rank = delta.rank ?? 0;
              newMap.set(delta.symbol, delta.data);

              if (oldTicker) {
                if (delta.data.price !== oldTicker.price) {
                  const direction = delta.data.price > oldTicker.price ? 'up' : 'down';
                  newChanges.set(`${delta.symbol}-price`, { symbol: delta.symbol, field: 'price', direction });
                }
                if (delta.data.change_percent !== oldTicker.change_percent) {
                  const direction = (delta.data.change_percent || 0) > (oldTicker.change_percent || 0) ? 'up' : 'down';
                  newChanges.set(`${delta.symbol}-change_percent`, { symbol: delta.symbol, field: 'change_percent', direction });
                }
              }
            }
            break;
          }
          case 'rerank': {
            const ticker = newMap.get(delta.symbol);
            if (ticker && delta.new_rank !== undefined) {
              ticker.rank = delta.new_rank;
              newMap.set(delta.symbol, ticker);
            }
            break;
          }
        }
      });

      if (newChanges.size > 0) {
        setCellChanges((prev) => {
          const merged = new Map(prev);
          newChanges.forEach((value, key) => merged.set(key, value));
          return merged;
        });

        setTimeout(() => {
          setCellChanges((prev) => {
            const cleaned = new Map(prev);
            newChanges.forEach((_, key) => cleaned.delete(key));
            return cleaned;
          });
        }, 2000);
      }

      return newMap;
    });

    setTickerOrder((prevOrder) => {
      const newOrder = [...prevOrder];

      deltas.forEach((delta) => {
        if (delta.action === 'add' && !newOrder.includes(delta.symbol)) {
          newOrder.push(delta.symbol);
        }
      });

      deltas.forEach((delta) => {
        if (delta.action === 'remove') {
          const index = newOrder.indexOf(delta.symbol);
          if (index !== -1) newOrder.splice(index, 1);
        }
      });

      setTickersMap((currentMap) => {
        newOrder.sort((a, b) => {
          const tickerA = currentMap.get(a);
          const tickerB = currentMap.get(b);
          return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
        });
        return currentMap;
      });

      return newOrder;
    });

    setLastUpdateTime(new Date());
  }, []);

  const handleDelta = useCallback((delta: any) => {
    if (!isReady || tickersMap.size === 0) {
      if (ws.isConnected) {
        ws.send({ action: 'resync', list: listName });
      }
      return;
    }

    if (!delta.deltas || !Array.isArray(delta.deltas)) return;
    deltaBuffer.current.push(...delta.deltas);
    setSequence(delta.sequence);
  }, [isReady, tickersMap, ws, listName]);

  useEffect(() => {
    const applyBufferedDeltas = () => {
      if (deltaBuffer.current.length > 0) {
        const toApply = [...deltaBuffer.current];
        deltaBuffer.current = [];
        applyDeltas(toApply);
      }
      rafId.current = requestAnimationFrame(applyBufferedDeltas);
    };
    rafId.current = requestAnimationFrame(applyBufferedDeltas);
    return () => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
    };
  }, [applyDeltas]);

  useEffect(() => {
    if (!ws.lastMessage) return;
    const message = ws.lastMessage;
    try {
      switch (message.type) {
        case 'connected':
          break;
        case 'snapshot':
          if (message.list === listName && handleSnapshotRef.current) {
            handleSnapshotRef.current(message);
          }
          break;
        case 'delta':
          if (message.list === listName && handleDeltaRef.current) {
            handleDeltaRef.current(message);
          }
          break;
      }
    } catch {
      // noop
    }
  }, [ws.lastMessage, listName]);

  useEffect(() => {
    if (ws.isConnected && !hasSubscribed.current) {
      try {
        ws.send({ action: 'subscribe_list', list: listName });
        hasSubscribed.current = true;
        const snapshotTimeout = setTimeout(() => {
          if (!isReady && ws.isConnected) {
            ws.send({ action: 'resync', list: listName });
          }
        }, 3000);
        return () => clearTimeout(snapshotTimeout);
      } catch {
        // noop
      }
    }
    if (!ws.isConnected && hasSubscribed.current) {
      hasSubscribed.current = false;
    }
    return () => {
      if (ws.isConnected && hasSubscribed.current) {
        ws.send({ action: 'unsubscribe_list', list: listName });
        hasSubscribed.current = false;
      }
    };
  }, [ws.isConnected, isReady, listName, ws]);

  const data = useMemo(() => {
    return tickerOrder.map((symbol) => tickersMap.get(symbol)!).filter(Boolean);
  }, [tickersMap, tickerOrder]);

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'row_number',
        header: '#',
        size: 40,
        minSize: 35,
        maxSize: 60,
        enableResizing: true,
        cell: (info) => (
          <div className="text-center font-semibold text-slate-400">{info.row.index + 1}</div>
        ),
      }),
      columnHelper.accessor('symbol', {
        header: 'Symbol',
        size: 75,
        minSize: 55,
        maxSize: 120,
        enableResizing: true,
        cell: (info) => <div className="font-bold text-blue-600">{info.getValue()}</div>,
      }),
      columnHelper.accessor('price', {
        header: 'Price',
        size: 80,
        minSize: 60,
        maxSize: 120,
        enableResizing: true,
        cell: (info) => {
          const symbol = info.row.original.symbol;
          const change = cellChanges.get(`${symbol}-price`);
          const isUp = change?.direction === 'up';
          const isDown = change?.direction === 'down';
          return (
            <div
              className={`
                inline-flex items-center gap-1 font-mono font-semibold px-1 py-0.5 rounded
                ${isUp ? 'text-emerald-600 flash-up' : ''}
                ${isDown ? 'text-rose-600 flash-down' : ''}
                ${!change ? 'text-slate-900' : ''}
                transition-colors duration-200
              `}
            >
              {isUp ? <ChevronUp className="w-3 h-3" /> : null}
              {isDown ? <ChevronDown className="w-3 h-3" /> : null}
              {formatPrice(info.getValue())}
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
        cell: (info) => {
          const value = info.getValue();
          const symbol = info.row.original.symbol;
          const change = cellChanges.get(`${symbol}-change_percent`);
          const isPositive = (value || 0) > 0;
          return (
            <div
              className={`
                inline-flex items-center gap-0.5 font-mono font-semibold
                ${isPositive ? 'text-emerald-600' : 'text-rose-600'}
                ${change?.direction === 'up' ? 'flash-up' : ''}
                ${change?.direction === 'down' ? 'flash-down' : ''}
                transition-all duration-200
              `}
            >
              {isPositive ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
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
        cell: (info) => <div className="font-mono text-slate-700 font-medium">{formatNumber(info.getValue())}</div>,
      }),
      columnHelper.accessor((row) => row.rvol_slot ?? row.rvol, {
        id: 'rvol',
        header: 'RVOL',
        size: 70,
        minSize: 55,
        maxSize: 100,
        enableResizing: true,
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
                : 'text-slate-500'}
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
        cell: (info) => <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>,
      }),
      columnHelper.accessor('float_shares', {
        header: 'Float',
        size: 90,
        minSize: 70,
        maxSize: 140,
        enableResizing: true,
        cell: (info) => <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>,
      }),
    ],
    [cellChanges]
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
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

  return (
    <BaseDataTable
      table={table}
      initialHeight={700}
      minHeight={200}
      minWidth={400}
      stickyHeader={true}
      isLoading={!isReady}
      header={
        <MarketTableLayout
          title={title}
          isLive={ws.isConnected}
          count={isReady ? data.length : undefined}
          sequence={isReady ? sequence : undefined}
          lastUpdateTime={lastUpdateTime}
        />
      }
    />
  );
}


