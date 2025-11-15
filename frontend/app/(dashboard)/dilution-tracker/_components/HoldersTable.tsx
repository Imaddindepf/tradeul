"use client";

import { ArrowUp, ArrowDown, Minus, Building2 } from "lucide-react";

interface Holder {
  holder_name: string;
  shares_held: number;
  ownership_percent: number;
  position_change: number;
  position_change_percent: number;
  change_direction: "increase" | "decrease" | "new" | "unchanged";
  report_date: string;
  form_type: string;
}

interface HoldersTableProps {
  holders: Holder[];
  loading?: boolean;
}

export function HoldersTable({ holders, loading = false }: HoldersTableProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="animate-pulse space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (!holders || holders.length === 0) {
    return (
      <div className="text-center py-12">
        <Building2 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No institutional holders data available</p>
      </div>
    );
  }

  const formatShares = (shares: number) => {
    if (shares >= 1_000_000_000) {
      return `${(shares / 1_000_000_000).toFixed(2)}B`;
    }
    if (shares >= 1_000_000) {
      return `${(shares / 1_000_000).toFixed(2)}M`;
    }
    return shares.toLocaleString();
  };

  const getChangeIcon = (direction: string) => {
    switch (direction) {
      case "increase":
        return <ArrowUp className="h-4 w-4 text-green-600 dark:text-green-400" />;
      case "decrease":
        return <ArrowDown className="h-4 w-4 text-red-600 dark:text-red-400" />;
      case "new":
        return <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 rounded font-medium">NEW</span>;
      default:
        return <Minus className="h-4 w-4 text-gray-400" />;
    }
  };

  const getChangeColor = (direction: string) => {
    switch (direction) {
      case "increase":
        return "text-green-600 dark:text-green-400";
      case "decrease":
        return "text-red-600 dark:text-red-400";
      default:
        return "text-gray-500 dark:text-gray-400";
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200/50 dark:border-gray-700/50">
            <th className="text-left py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Institution
            </th>
            <th className="text-right py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Ownership %
            </th>
            <th className="text-right py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Shares
            </th>
            <th className="text-right py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Change
            </th>
            <th className="text-center py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Form
            </th>
            <th className="text-right py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Date
            </th>
          </tr>
        </thead>
        <tbody>
          {holders.map((holder, index) => (
            <tr
              key={`${holder.holder_name}-${index}`}
              className="border-b border-gray-100/50 dark:border-gray-800/50 hover:bg-white/50 dark:hover:bg-white/5 transition-colors"
            >
              {/* Institution Name */}
              <td className="py-4 px-4">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-gray-500/10 flex items-center justify-center">
                    <Building2 className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white text-sm">
                      {holder.holder_name}
                    </p>
                  </div>
                </div>
              </td>

              {/* Ownership % */}
              <td className="py-4 px-4 text-right">
                <span className="text-lg font-semibold text-gray-900 dark:text-white">
                  {holder.ownership_percent.toFixed(2)}%
                </span>
              </td>

              {/* Shares */}
              <td className="py-4 px-4 text-right">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {formatShares(holder.shares_held)}
                </span>
              </td>

              {/* Change */}
              <td className="py-4 px-4 text-right">
                <div className="flex items-center justify-end gap-2">
                  {getChangeIcon(holder.change_direction)}
                  {holder.position_change !== 0 && holder.change_direction !== "new" && (
                    <span className={`text-sm font-medium ${getChangeColor(holder.change_direction)}`}>
                      {holder.position_change > 0 ? '+' : ''}
                      {formatShares(holder.position_change)}
                    </span>
                  )}
                </div>
              </td>

              {/* Form Type */}
              <td className="py-4 px-4 text-center">
                <span className="text-xs px-2 py-1 bg-gray-500/10 text-gray-700 dark:text-gray-300 rounded font-medium">
                  {holder.form_type}
                </span>
              </td>

              {/* Report Date */}
              <td className="py-4 px-4 text-right">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {new Date(holder.report_date).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                  })}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

