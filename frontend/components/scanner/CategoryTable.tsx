'use client';

import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, ColumnResizeMode, Row } from '@tanstack/react-table';
import { formatNumber, formatPercent, formatPrice, formatRVOL } from '@/lib/formatters';
import type { Ticker } from '@/lib/types';
import { useWebSocket } from '@/hooks/useWebSocket';
import { BaseDataTable } from '@/components/table/BaseDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import TickerMetadataModal from './TickerMetadataModal';

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
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnOrder, setColumnOrder] = useState<string[]>([]);
  const [columnVisibility, setColumnVisibility] = useState({});
  const [columnResizeMode] = useState<ColumnResizeMode>('onChange');
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [newTickers, setNewTickers] = useState<Set<string>>(new Set());
  const [rowChanges, setRowChanges] = useState<Map<string, 'up' | 'down'>>(new Map());
  const [dataVersion, setDataVersion] = useState(0); // Contador para forzar re-render
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const deltaBuffer = useRef<DeltaAction[]>([]);
  const aggregateBuffer = useRef<Map<string, any>>(new Map());
  const rafId = useRef<number | null>(null);
  const aggregateRafId = useRef<number | null>(null);
  const hasSubscribed = useRef(false);
  const handleSnapshotRef = useRef<((snapshot: any) => void) | null>(null);
  const handleDeltaRef = useRef<((delta: any) => void) | null>(null);
  const handleAggregateRef = useRef<((aggregate: any) => void) | null>(null);
  const aggregateStats = useRef({ received: 0, applied: 0, lastLog: Date.now() });

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
    handleAggregateRef.current = handleAggregate;
  });

  const applyDeltas = useCallback((deltas: DeltaAction[]) => {
    if (deltas.length === 0) return;

    setTickersMap((prevMap) => {
      const newMap = new Map(prevMap);
      const newRowChanges = new Map<string, 'up' | 'down'>();

      deltas.forEach((delta) => {
        switch (delta.action) {
          case 'add': {
            if (delta.data) {
              delta.data.rank = delta.rank ?? 0;
              newMap.set(delta.symbol, delta.data);
              // Marcar como nuevo ticker (animación azul)
              setNewTickers((prev) => new Set(prev).add(delta.symbol));
              setTimeout(() => {
                setNewTickers((prev) => {
                  const updated = new Set(prev);
                  updated.delete(delta.symbol);
                  return updated;
                });
              }, 3000);
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
              
              if (oldTicker) {
                // Preservar datos en tiempo real de aggregates
                const merged = {
                  ...delta.data,
                  price: oldTicker.price || delta.data.price,
                  volume_today: oldTicker.volume_today || delta.data.volume_today,
                  high: Math.max(oldTicker.high || 0, delta.data.high || 0),
                  low: oldTicker.low && delta.data.low ? Math.min(oldTicker.low, delta.data.low) : (oldTicker.low || delta.data.low),
                };
                newMap.set(delta.symbol, merged);
              } else {
                newMap.set(delta.symbol, delta.data);
              }
            }
            break;
          }
          case 'rerank': {
            const ticker = newMap.get(delta.symbol);
            if (ticker && delta.new_rank !== undefined && delta.old_rank !== undefined) {
              const oldRank = delta.old_rank;
              const newRank = delta.new_rank;
              
              ticker.rank = newRank;
              newMap.set(delta.symbol, ticker);
              
              // Animación: verde si sube (menor rank = mejor posición), rojo si baja
              if (newRank < oldRank) {
                newRowChanges.set(delta.symbol, 'up');
              } else if (newRank > oldRank) {
                newRowChanges.set(delta.symbol, 'down');
              }
            }
            break;
          }
        }
      });

      // Forzar re-render
      setDataVersion((v) => v + 1);

      // Aplicar animaciones de fila SOLO para reranks
      if (newRowChanges.size > 0) {
        // Limpiar animaciones existentes
        setRowChanges((prev) => {
          const cleaned = new Map(prev);
          newRowChanges.forEach((_, key) => cleaned.delete(key));
          return cleaned;
        });
        
        // Aplicar nuevas animaciones
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setRowChanges((prev) => {
              const merged = new Map(prev);
              newRowChanges.forEach((value, key) => merged.set(key, value));
              return merged;
            });

            setTimeout(() => {
              setRowChanges((prev) => {
                const cleaned = new Map(prev);
                newRowChanges.forEach((_, key) => cleaned.delete(key));
                return cleaned;
              });
            }, 1200);
          });
        });
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

  const handleAggregate = useCallback((message: any) => {
    if (!isReady || !message.symbol || !message.data) return;

    // Solo agregar al buffer (no setState directamente)
    aggregateBuffer.current.set(message.symbol, message);
    aggregateStats.current.received++;

    // Log stats cada 10 segundos
    const now = Date.now();
    if (now - aggregateStats.current.lastLog > 10000) {
      const elapsed = (now - aggregateStats.current.lastLog) / 1000;
      const recvRate = (aggregateStats.current.received / elapsed).toFixed(1);
      const applyRate = (aggregateStats.current.applied / elapsed).toFixed(1);
      
      console.log(
        `📊 [${listName}] Aggregate stats: recv=${recvRate}/s, applied=${applyRate}/s, buffer=${aggregateBuffer.current.size}`
      );
      
      aggregateStats.current.received = 0;
      aggregateStats.current.applied = 0;
      aggregateStats.current.lastLog = now;
    }
  }, [isReady, listName]);

  const applyAggregatesBatch = useCallback(() => {
    if (aggregateBuffer.current.size === 0) return;

    const toApply = new Map(aggregateBuffer.current);
    aggregateBuffer.current.clear();

    setTickersMap((prevMap) => {
      const newMap = new Map(prevMap);

      toApply.forEach((message, symbol) => {
        const ticker = newMap.get(symbol);
        if (!ticker) return; // Solo actualizar si está en ranking

        // Actualizar precio
        const newPrice = parseFloat(message.data.c);
        const newVolume = parseInt(message.data.av, 10);

        // Recalcular change_percent si tenemos prev_close
        let newChangePercent = ticker.change_percent;
        if (ticker.prev_close && !isNaN(newPrice)) {
          newChangePercent = ((newPrice - ticker.prev_close) / ticker.prev_close) * 100;
        }

        // Actualizar ticker con nuevos valores (sin animaciones)
        const updated = {
          ...ticker,
          price: newPrice,
          volume_today: newVolume,
          change_percent: newChangePercent,
          high: Math.max(parseFloat(message.data.h) || 0, ticker.high || 0),
          low: ticker.low ? Math.min(parseFloat(message.data.l) || 0, ticker.low) : parseFloat(message.data.l),
        };

        newMap.set(symbol, updated);
        aggregateStats.current.applied++;
      });

      // Forzar re-render incrementando versión
      setDataVersion((v) => v + 1);

      return newMap;
    });
  }, [listName]);

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
    const applyBufferedAggregates = () => {
      applyAggregatesBatch();
      aggregateRafId.current = requestAnimationFrame(applyBufferedAggregates);
    };
    aggregateRafId.current = requestAnimationFrame(applyBufferedAggregates);
    return () => {
      if (aggregateRafId.current) cancelAnimationFrame(aggregateRafId.current);
    };
  }, [applyAggregatesBatch]);

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
        case 'aggregate':
          if (handleAggregateRef.current) {
            handleAggregateRef.current(message);
          }
          break;
      }
    } catch {
      // noop
    }
  }, [ws.lastMessage, listName]);

  // Suscripción a la lista (solo cuando se conecta el WS o cambia el listName)
  useEffect(() => {
    if (!ws.isConnected) {
      // Resetear flag si se desconecta
      if (hasSubscribed.current) {
        hasSubscribed.current = false;
      }
      return;
    }

    // Suscribirse solo si no está suscrito
    if (!hasSubscribed.current) {
      ws.send({ action: 'subscribe_list', list: listName });
      hasSubscribed.current = true;
      console.log(`✅ [${listName}] Subscribed to list`);
    }

    // Cleanup: desuscribir solo al desmontar el componente
    return () => {
      if (hasSubscribed.current) {
        ws.send({ action: 'unsubscribe_list', list: listName });
        hasSubscribed.current = false;
        console.log(`❌ [${listName}] Unsubscribed from list`);
      }
    };
  }, [ws.isConnected, listName, ws.send]);

  // Timeout para resync si no llega snapshot
  useEffect(() => {
    if (!ws.isConnected || isReady) return;

    const snapshotTimeout = setTimeout(() => {
      if (!isReady && ws.isConnected) {
        console.log(`⏱️ [${listName}] Snapshot timeout, requesting resync`);
        ws.send({ action: 'resync', list: listName });
      }
    }, 5000); // 5 segundos para dar tiempo a múltiples conexiones

    return () => clearTimeout(snapshotTimeout);
  }, [ws.isConnected, isReady, listName, ws.send]);

  const data = useMemo(() => {
    return tickerOrder.map((symbol) => tickersMap.get(symbol)!).filter(Boolean);
  }, [tickersMap, tickerOrder, dataVersion]); // dataVersion fuerza recalcular

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
        enableHiding: false, // No se puede ocultar
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
        enableSorting: true,
        enableHiding: false, // No se puede ocultar (columna esencial)
        cell: (info) => (
          <div 
            className="font-bold text-blue-600 cursor-pointer hover:text-blue-800 hover:underline transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedSymbol(info.getValue());
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
          const symbol = info.row.original.symbol;
          const price = info.getValue();
          return (
            <div
              key={`${symbol}-price-${price}-${dataVersion}`}
              className="font-mono font-semibold px-1 py-0.5 rounded text-slate-900"
            >
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
          const symbol = info.row.original.symbol;
          const isPositive = (value || 0) > 0;
          return (
            <div
              key={`${symbol}-pct-${value}-${dataVersion}`}
              className={`font-mono font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}
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
        cell: (info) => {
          const symbol = info.row.original.symbol;
          const volume = info.getValue();
          return (
            <div key={`${symbol}-vol-${volume}-${dataVersion}`} className="font-mono text-slate-700 font-medium">
              {formatNumber(volume)}
            </div>
          );
        },
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
        enableSorting: true,
        enableHiding: true,
        cell: (info) => <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>,
      }),
      columnHelper.accessor('float_shares', {
        header: 'Float',
        size: 90,
        minSize: 70,
        maxSize: 140,
        enableResizing: true,
        enableSorting: true,
        enableHiding: true,
        cell: (info) => <div className="font-mono text-slate-600">{formatNumber(info.getValue())}</div>,
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
          if (value === null || value === undefined) return <div className="text-slate-400">-</div>;
          const colorClass = value > 5 ? 'text-orange-600 font-semibold' : 'text-slate-600';
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(1)}%</div>;
        },
      }),
      columnHelper.accessor((row) => {
        // Calcular % del ATR usado hoy basado en el RANGO intradiario
        const atr_percent = row.atr_percent;
        const prev_close = row.prev_close;
        const change_percent = row.change_percent || 0;
        
        if (!atr_percent || atr_percent === 0 || !prev_close) return null;
        
        // Usar intraday_high/intraday_low (incluye pre/post market)
        // Fallback a high/low si no están disponibles
        const high = row.intraday_high ?? row.high;
        const low = row.intraday_low ?? row.low;
        
        // Si no tenemos high/low (pre-market sin datos), usar gap %
        if (!high || !low) {
          return (Math.abs(change_percent) / atr_percent) * 100;
        }
        
        // Calcular rango usado basado en dirección
        let range_percent;
        if (change_percent >= 0) {
          // Gap up: medir desde cierre previo hasta intraday high
          range_percent = ((high - prev_close) / prev_close) * 100;
        } else {
          // Gap down: medir desde cierre previo hasta intraday low
          range_percent = ((prev_close - low) / prev_close) * 100;
        }
        
        return (Math.abs(range_percent) / atr_percent) * 100;
      }, {
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
          if (value === null || value === undefined) return <div className="text-slate-400">-</div>;
          
          // Colores según el % usado
          let colorClass = 'text-slate-600';
          if (value > 150) {
            colorClass = 'text-red-600 font-bold'; // Movimiento extremo
          } else if (value > 100) {
            colorClass = 'text-orange-600 font-semibold'; // Superó el ATR
          } else if (value > 75) {
            colorClass = 'text-yellow-600 font-medium'; // Alto uso
          } else if (value > 50) {
            colorClass = 'text-blue-600'; // Uso medio-alto
          }
          
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(0)}%</div>;
        },
      }),
    ],
    [dataVersion]
  );

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

  return (
    <>
      <BaseDataTable
        table={table}
        initialHeight={700}
        minHeight={200}
        minWidth={400}
        stickyHeader={true}
        isLoading={!isReady}
        getRowClassName={(row: Row<Ticker>) => {
          const ticker = row.original;
          const classes: string[] = [];
          
          // Animación para nuevos tickers (azul) - tiene prioridad
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
        header={
          <MarketTableLayout
            title={title}
            isLive={ws.isConnected}
            count={isReady ? data.length : undefined}
            sequence={isReady ? sequence : undefined}
            lastUpdateTime={lastUpdateTime}
            rightActions={<TableSettings table={table} />}
          />
        }
      />
      
      <TickerMetadataModal
        symbol={selectedSymbol}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedSymbol(null);
        }}
      />
    </>
  );
}


