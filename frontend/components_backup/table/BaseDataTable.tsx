'use client';

import { ReactNode } from 'react';
import type { Table as TanStackTable } from '@tanstack/react-table';
import { ResizableTable } from '@/components/ui/ResizableTable';

export interface BaseDataTableProps<T> {
  table: TanStackTable<T>;
  className?: string;
  initialHeight?: number;
  minHeight?: number;
  minWidth?: number;
  stickyHeader?: boolean;
  isLoading?: boolean;
  loadingTitle?: string;
  loadingSubtitle?: string;
  emptyTitle?: string;
  emptySubtitle?: string;
  header?: ReactNode; // suele ser MarketTableLayout
  getRowClassName?: (row: any) => string;
}

export function BaseDataTable<T>({
  table,
  className,
  initialHeight = 700,
  minHeight = 200,
  minWidth = 400,
  stickyHeader = true,
  isLoading = false,
  loadingTitle = 'Loading Market Data',
  loadingSubtitle = 'Connecting to server',
  emptyTitle = 'No Tickers Available',
  emptySubtitle = 'Data will appear when market is active',
  header,
  getRowClassName,
}: BaseDataTableProps<T>) {
  return (
    <ResizableTable
      table={table}
      className={`flex flex-col ${className || ''}`}
      initialHeight={initialHeight}
      minHeight={minHeight}
      minWidth={minWidth}
      showResizeHandles={true}
      stickyHeader={stickyHeader}
      isLoading={isLoading}
      getRowClassName={getRowClassName}
      loadingState={
        <div className="flex items-center justify-center h-full bg-slate-50">
          <div className="text-center">
            <div className="animate-spin rounded-full h-14 w-14 border-b-3 border-blue-600 mx-auto mb-4" />
            <p className="text-slate-900 font-semibold text-base">{loadingTitle}</p>
            <p className="text-slate-600 text-sm mt-2">{loadingSubtitle}</p>
          </div>
        </div>
      }
      emptyState={
        <div className="flex items-center justify-center h-full bg-slate-50">
          <div className="text-center">
            <p className="text-slate-900 font-semibold text-base">{emptyTitle}</p>
            <p className="text-slate-600 text-sm mt-2">{emptySubtitle}</p>
          </div>
        </div>
      }
    >
      {header}
    </ResizableTable>
  );
}


