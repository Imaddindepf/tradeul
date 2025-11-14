"use client";

import { AlertCircle, TrendingDown, TrendingUp } from "lucide-react";

interface CashRunwayData {
  current_cash: number;
  quarterly_burn_rate: number;
  estimated_runway_months: number;
  runway_risk_level: "critical" | "high" | "medium" | "low";
  projection: Array<{
    month: number;
    date: string;
    estimated_cash: number;
  }>;
}

interface CashRunwayChartProps {
  data: CashRunwayData | null;
  loading?: boolean;
}

export function CashRunwayChart({ data, loading = false }: CashRunwayChartProps) {
  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-48 bg-gray-100 dark:bg-gray-800 rounded-lg" />
        <div className="grid grid-cols-3 gap-4">
          <div className="h-24 bg-gray-100 dark:bg-gray-800 rounded-lg" />
          <div className="h-24 bg-gray-100 dark:bg-gray-800 rounded-lg" />
          <div className="h-24 bg-gray-100 dark:bg-gray-800 rounded-lg" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No cash runway data available</p>
      </div>
    );
  }

  const formatCash = (amount: number) => {
    if (amount >= 1_000_000_000) {
      return `$${(amount / 1_000_000_000).toFixed(2)}B`;
    }
    if (amount >= 1_000_000) {
      return `$${(amount / 1_000_000).toFixed(2)}M`;
    }
    return `$${amount.toLocaleString()}`;
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case "critical":
        return "bg-red-100 dark:bg-red-950/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800";
      case "high":
        return "bg-orange-100 dark:bg-orange-950/30 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800";
      case "medium":
        return "bg-yellow-100 dark:bg-yellow-950/30 text-yellow-700 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800";
      case "low":
        return "bg-green-100 dark:bg-green-950/30 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800";
      default:
        return "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600";
    }
  };

  const isBurningCash = data.quarterly_burn_rate < 0;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Current Cash */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Current Cash Position</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
            {formatCash(data.current_cash)}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Cash + Short-term Investments
          </p>
        </div>

        {/* Burn Rate */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Quarterly Burn Rate</p>
          <div className="flex items-center gap-2 mb-1">
            <p className={`text-3xl font-bold ${isBurningCash ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
              {formatCash(Math.abs(data.quarterly_burn_rate))}
            </p>
            {isBurningCash ? (
              <TrendingDown className="h-6 w-6 text-red-600 dark:text-red-400" />
            ) : (
              <TrendingUp className="h-6 w-6 text-green-600 dark:text-green-400" />
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {isBurningCash ? 'Negative cash flow' : 'Positive cash flow'}
          </p>
        </div>

        {/* Runway */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Estimated Runway</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            {data.estimated_runway_months.toFixed(1)} <span className="text-lg text-gray-500">months</span>
          </p>
          <span className={`inline-block text-xs px-2 py-1 rounded font-medium border ${getRiskColor(data.runway_risk_level)}`}>
            {data.runway_risk_level.toUpperCase()} RISK
          </span>
        </div>
      </div>

      {/* Cash Projection Chart */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">
          Cash Position Projection (12 Months)
        </h4>
        
        <div className="relative h-64">
          {/* Simple bar chart representation */}
          <div className="flex items-end justify-between h-full gap-2">
            {data.projection.slice(0, 12).map((month, index) => {
              const maxCash = Math.max(...data.projection.map(p => p.estimated_cash));
              const heightPercent = (month.estimated_cash / maxCash) * 100;
              const isZero = month.estimated_cash === 0;
              
              return (
                <div key={index} className="flex-1 flex flex-col items-center gap-2">
                  <div className="w-full relative group">
                    <div
                      className={`w-full rounded-t-lg transition-all ${
                        isZero 
                          ? 'bg-red-200 dark:bg-red-900/50' 
                          : index === 0
                          ? 'bg-blue-500 dark:bg-blue-600'
                          : 'bg-blue-300 dark:bg-blue-700'
                      }`}
                      style={{ height: `${Math.max(heightPercent, 5)}%` }}
                    />
                    {/* Tooltip */}
                    <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-10 shadow-xl">
                      <div className="font-semibold mb-1">{new Date(month.date).toLocaleDateString('en-US', { month: 'short' })}</div>
                      <div>{formatCash(month.estimated_cash)}</div>
                      <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1 w-2 h-2 bg-gray-900 rotate-45" />
                    </div>
                  </div>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    M{month.month}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Zero line */}
          <div className="absolute bottom-0 left-0 right-0 h-px bg-red-300 dark:bg-red-700" />
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-6 mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 bg-blue-500 rounded" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Current</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 bg-blue-300 dark:bg-blue-700 rounded" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Projected</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 bg-red-200 dark:bg-red-900/50 rounded" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Depleted</span>
          </div>
        </div>
      </div>

      {/* Warning if critical */}
      {data.runway_risk_level === "critical" && (
        <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-xl p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
            <div>
              <h4 className="font-semibold text-red-900 dark:text-red-100 mb-1">
                Critical Cash Runway
              </h4>
              <p className="text-sm text-red-700 dark:text-red-300">
                Company has less than 6 months of cash remaining at current burn rate. High probability of offering or capital raise in near term.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

