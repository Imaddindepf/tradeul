"use client";

import { TrendingUp, Info } from "lucide-react";

interface DilutionHistoryData {
  history: Array<{
    date: string;
    shares: number;
  }>;
  dilution_1y: number;
  dilution_3y: number;
}

interface DilutionHistoryChartProps {
  data: DilutionHistoryData | null;
  loading?: boolean;
}

export function DilutionHistoryChart({ data, loading = false }: DilutionHistoryChartProps) {
  if (loading) {
    return (
      <div className="animate-pulse">
        <div className="h-80 bg-gray-100 dark:bg-gray-800 rounded-lg" />
      </div>
    );
  }

  if (!data || !data.history || data.history.length === 0) {
    return (
      <div className="text-center py-12">
        <TrendingUp className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No dilution history available</p>
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

  const maxShares = Math.max(...data.history.map(h => h.shares));
  const minShares = Math.min(...data.history.map(h => h.shares));

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid md:grid-cols-3 gap-4">
        <div className="bg-blue-500/10 rounded-xl p-6 border border-blue-500/20">
          <p className="text-sm text-blue-700 dark:text-blue-300 mb-2 font-medium">Current Shares Outstanding</p>
          <p className="text-3xl font-bold text-blue-900 dark:text-blue-100">
            {formatShares(data.history[data.history.length - 1].shares)}
          </p>
        </div>

        <div className={`rounded-xl p-6 border ${
          data.dilution_1y > 10 
            ? 'bg-red-500/10 border-red-500/20' 
            : data.dilution_1y > 5
            ? 'bg-yellow-500/10 border-yellow-500/20'
            : 'bg-green-500/10 border-green-500/20'
        }`}>
          <p className={`text-sm mb-2 font-medium ${
            data.dilution_1y > 10 
              ? 'text-red-700 dark:text-red-300' 
              : data.dilution_1y > 5
              ? 'text-yellow-700 dark:text-yellow-300'
              : 'text-green-700 dark:text-green-300'
          }`}>
            1-Year Dilution
          </p>
          <p className={`text-3xl font-bold ${
            data.dilution_1y > 10 
              ? 'text-red-900 dark:text-red-100' 
              : data.dilution_1y > 5
              ? 'text-yellow-900 dark:text-yellow-100'
              : 'text-green-900 dark:text-green-100'
          }`}>
            {data.dilution_1y > 0 ? '+' : ''}{data.dilution_1y.toFixed(2)}%
          </p>
        </div>

        <div className={`rounded-xl p-6 border ${
          data.dilution_3y > 25 
            ? 'bg-red-500/10 border-red-500/20' 
            : data.dilution_3y > 10
            ? 'bg-yellow-500/10 border-yellow-500/20'
            : 'bg-green-500/10 border-green-500/20'
        }`}>
          <p className={`text-sm mb-2 font-medium ${
            data.dilution_3y > 25 
              ? 'text-red-700 dark:text-red-300' 
              : data.dilution_3y > 10
              ? 'text-yellow-700 dark:text-yellow-300'
              : 'text-green-700 dark:text-green-300'
          }`}>
            3-Year Dilution
          </p>
          <p className={`text-3xl font-bold ${
            data.dilution_3y > 25 
              ? 'text-red-900 dark:text-red-100' 
              : data.dilution_3y > 10
              ? 'text-yellow-900 dark:text-yellow-100'
              : 'text-green-900 dark:text-green-100'
          }`}>
            {data.dilution_3y > 0 ? '+' : ''}{data.dilution_3y.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-white/50 dark:bg-white/5 rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
        <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">
          Historical Shares Outstanding
        </h4>
        
        <div className="relative h-80">
          <div className="flex items-end justify-between h-full gap-3">
            {data.history.map((point, index) => {
              const heightPercent = ((point.shares - minShares) / (maxShares - minShares)) * 100;
              const isLatest = index === data.history.length - 1;
              
              return (
                <div key={index} className="flex-1 flex flex-col items-center gap-2 group">
                  <div className="w-full relative">
                    <div
                      className={`w-full rounded-t-lg transition-all ${
                        isLatest
                          ? 'bg-gradient-to-t from-blue-500 to-blue-400 dark:from-blue-600 dark:to-blue-500'
                          : 'bg-gradient-to-t from-blue-300 to-blue-200 dark:from-blue-800 dark:to-blue-700'
                      }`}
                      style={{ height: `${Math.max(heightPercent, 10)}%` }}
                    />
                    
                    {/* Tooltip */}
                    <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-10 shadow-xl">
                      <div className="font-semibold mb-1">
                        {new Date(point.date).toLocaleDateString('en-US', { 
                          year: 'numeric', 
                          month: 'short' 
                        })}
                      </div>
                      <div>{formatShares(point.shares)} shares</div>
                      <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1 w-2 h-2 bg-gray-900 rotate-45" />
                    </div>
                  </div>
                  
                  <span className="text-xs text-gray-500 dark:text-gray-400 transform -rotate-45 origin-top-left mt-2">
                    {new Date(point.date).toLocaleDateString('en-US', { year: '2-digit' })}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Y-axis labels */}
          <div className="absolute -left-16 top-0 bottom-0 flex flex-col justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>{formatShares(maxShares)}</span>
            <span>{formatShares(minShares)}</span>
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
          <div className="text-sm text-blue-900 dark:text-blue-100">
            <p className="font-medium mb-1">Understanding Dilution</p>
            <p className="text-blue-700 dark:text-blue-300">
              Dilution occurs when a company issues new shares, reducing the ownership percentage of existing shareholders. 
              Positive percentages indicate share count increase, negative indicates buybacks.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

