'use client';

/**
 * Tabla de operaciones.
 *
 * Reutiliza `VirtualizedDataTable`, el componente de la casa que ya mueven el
 * scanner y los eventos: TanStack Table + TanStack Virtual, con orden,
 * cabecera pegada y ~20 filas en el DOM aunque haya 50.000 operaciones.
 *
 * Lo que había era paginación manual de 50 en 50 con un `<table>` completo
 * pintado en cada página, y sin retorno por operación ni duración.
 *
 * Color solo en PnL y retorno, que es lo único direccional. El resto en la
 * escala de grises de la ventana.
 */

import { memo, useMemo, useState } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, type SortingState,
} from '@tanstack/react-table';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import type { TradeRecord } from '@/components/ai-agent/backtest/BacktestTypes';
import { CenterMessage } from './ui';

const nf0 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function shortDate(v: string | Date): string {
  const s = String(v);
  // Llega como ISO (`2026-03-14` o con hora). Cortar es más rápido y estable
  // que construir un Date por celda: son decenas de miles de celdas.
  return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(2, 4)}` : s;
}

const col = createColumnHelper<TradeRecord>();

/** Números direccionales: el signo va delante y el color solo aquí. */
const Signed = memo(function Signed({ v, digits = 0, suffix = '' }: { v: number; digits?: number; suffix?: string }) {
  const f = digits === 0 ? nf0 : nf2;
  return (
    <span className={v >= 0 ? 'text-[var(--color-chart-up,#22c55e)]' : 'text-[var(--color-chart-down,#f87171)]'}>
      {v >= 0 ? '+' : '−'}{f.format(Math.abs(v))}{suffix}
    </span>
  );
});

export const TradesTable = memo(function TradesTable({ trades }: { trades: TradeRecord[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'trade_id', desc: false }]);

  const columns = useMemo(() => [
    col.accessor('trade_id', {
      header: '#', size: 44,
      cell: (c) => <span className="text-foreground/35 tabular-nums">{c.getValue()}</span>,
    }),
    col.accessor('ticker', {
      header: 'Símbolo', size: 72,
      cell: (c) => <span className="font-semibold">{c.getValue()}</span>,
    }),
    col.accessor('direction', {
      header: 'Dir', size: 44,
      cell: (c) => (
        <span className="text-foreground/55 uppercase tracking-wider text-[10px]">
          {c.getValue() === 'long' ? 'L' : 'C'}
        </span>
      ),
    }),
    col.accessor('entry_date', {
      header: 'Entrada', size: 74,
      cell: (c) => <span className="text-foreground/65 tabular-nums">{shortDate(c.getValue() as string)}</span>,
    }),
    col.accessor('entry_fill_price', {
      header: 'P. entrada', size: 82,
      cell: (c) => <span className="tabular-nums text-foreground/65">{nf2.format(c.getValue())}</span>,
    }),
    col.accessor('exit_date', {
      header: 'Salida', size: 74,
      cell: (c) => <span className="text-foreground/65 tabular-nums">{shortDate(c.getValue() as string)}</span>,
    }),
    col.accessor('exit_fill_price', {
      header: 'P. salida', size: 82,
      cell: (c) => <span className="tabular-nums text-foreground/65">{nf2.format(c.getValue())}</span>,
    }),
    col.accessor('shares', {
      header: 'Títulos', size: 70,
      cell: (c) => <span className="tabular-nums text-foreground/65">{nf0.format(c.getValue())}</span>,
    }),
    col.accessor('holding_bars', {
      header: 'Barras', size: 62,
      cell: (c) => <span className="tabular-nums text-foreground/45">{c.getValue() ?? '–'}</span>,
    }),
    col.accessor('return_pct', {
      header: 'Retorno', size: 78,
      cell: (c) => <Signed v={(c.getValue() ?? 0) * 100} digits={2} suffix=" %" />,
    }),
    col.accessor('pnl', {
      header: 'PnL', size: 90,
      cell: (c) => <span className="font-semibold"><Signed v={c.getValue()} suffix=" $" /></span>,
    }),
  ], []);

  const table = useReactTable({
    data: trades,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    // Sin `getPaginationRowModel`: la virtualización sustituye a la paginación.
    enableColumnResizing: false,
  });

  if (!trades.length) {
    return <CenterMessage>Esta corrida no generó operaciones</CenterMessage>;
  }

  return (
    <VirtualizedDataTable
      table={table}
      showResizeHandles={false}
      stickyHeader
      estimateSize={22}
      overscan={12}
      enableVirtualization
    />
  );
});
