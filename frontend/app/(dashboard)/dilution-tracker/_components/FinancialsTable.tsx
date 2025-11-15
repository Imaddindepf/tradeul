"use client";

import { DollarSign, TrendingUp, TrendingDown } from "lucide-react";

interface FinancialStatement {
  period_date: string;
  period_type: string;
  fiscal_year: number;
  cash: number;
  total_cash: number;
  debt: number;
  equity: number;
  revenue: number;
  net_income: number;
  operating_cash_flow: number;
  free_cash_flow: number;
  shares_outstanding: number;
  current_ratio: number;
  debt_to_equity_ratio: number;
}

interface FinancialsTableProps {
  financials: FinancialStatement[];
  loading?: boolean;
}

export function FinancialsTable({ financials, loading = false }: FinancialsTableProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="animate-pulse space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (!financials || financials.length === 0) {
    return (
      <div className="text-center py-12">
        <DollarSign className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No financial statements available</p>
      </div>
    );
  }

  const formatCurrency = (amount: number) => {
    if (amount >= 1_000_000_000) {
      return `$${(amount / 1_000_000_000).toFixed(2)}B`;
    }
    if (amount >= 1_000_000) {
      return `$${(amount / 1_000_000).toFixed(2)}M`;
    }
    return `$${amount.toLocaleString()}`;
  };

  const formatShares = (shares: number) => {
    if (shares >= 1_000_000_000) {
      return `${(shares / 1_000_000_000).toFixed(2)}B`;
    }
    if (shares >= 1_000_000) {
      return `${(shares / 1_000_000).toFixed(2)}M`;
    }
    return shares.toLocaleString();
  };

  const formatRatio = (ratio: number) => {
    return ratio.toFixed(2);
  };

  const formatPercent = (value: number) => {
    return `${value.toFixed(1)}%`;
  };

  // Calcular YoY growth para revenue
  const calculateYoYGrowth = (current: number, yearAgo: number) => {
    if (!yearAgo || yearAgo === 0) return null;
    return ((current - yearAgo) / Math.abs(yearAgo)) * 100;
  };

  const sections = [
    {
      title: "Income Statement",
      icon: DollarSign,
      rows: [
        { label: "Revenue", key: "revenue" as keyof FinancialStatement, format: formatCurrency, showGrowth: true },
        { label: "Net Income", key: "net_income" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Balance Sheet",
      icon: TrendingUp,
      rows: [
        { label: "Cash & Equivalents", key: "cash" as keyof FinancialStatement, format: formatCurrency },
        { label: "Total Cash", key: "total_cash" as keyof FinancialStatement, format: formatCurrency },
        { label: "Total Debt", key: "debt" as keyof FinancialStatement, format: formatCurrency },
        { label: "Stockholders Equity", key: "equity" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Cash Flow Statement",
      icon: TrendingDown,
      rows: [
        { label: "Operating Cash Flow", key: "operating_cash_flow" as keyof FinancialStatement, format: formatCurrency },
        { label: "Free Cash Flow", key: "free_cash_flow" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Supplementary Data",
      icon: DollarSign,
      rows: [
        { label: "Shares Outstanding", key: "shares_outstanding" as keyof FinancialStatement, format: formatShares },
        { label: "Current Ratio", key: "current_ratio" as keyof FinancialStatement, format: formatRatio },
        { label: "Debt/Equity Ratio", key: "debt_to_equity_ratio" as keyof FinancialStatement, format: formatRatio },
      ]
    },
  ];

  // Show last 12 periods (~3 years of quarterly data)
  const recentFinancials = financials.slice(0, 12);

  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <div key={section.title} className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
          <div className="bg-slate-50 px-6 py-3 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <section.icon className="h-4 w-4 text-slate-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                {section.title}
              </h3>
            </div>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left py-3 px-6 text-xs font-bold text-slate-700 uppercase tracking-wider sticky left-0 bg-slate-50 z-10 min-w-[180px]">
                    Period
                  </th>
                  {recentFinancials.map((financial, index) => {
                    const date = new Date(financial.period_date);
                    const quarter = financial.period_type;
                    const month = date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                    
                    return (
                      <th
                        key={index}
                        className="text-right py-3 px-4 text-xs font-semibold text-slate-700 min-w-[100px] whitespace-nowrap"
                      >
                        <div className="font-bold">{quarter}</div>
                        <div className="text-xs text-slate-500 font-normal mt-0.5">{month}</div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="bg-white">
                {section.rows.map((row, rowIndex) => (
                  <tr
                    key={rowIndex}
                    className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${rowIndex === 0 ? 'font-semibold' : ''}`}
                  >
                    <td className="py-3 px-6 text-sm text-slate-900 sticky left-0 bg-white group-hover:bg-slate-50">
                      {row.label}
                    </td>
                    {recentFinancials.map((financial, colIndex) => {
                      const value = financial[row.key];
                      const isNegative = typeof value === 'number' && value < 0;
                      const displayValue = value != null ? row.format(Math.abs(value as number)) : '-';
                      
                      // Calcular YoY growth si es revenue y tenemos datos de hace 4 quarters
                      let yoyGrowth = null;
                      if (row.label === "Revenue" && colIndex < recentFinancials.length - 4) {
                        const yearAgoValue = recentFinancials[colIndex + 4]?.[row.key] as number;
                        if (yearAgoValue && value) {
                          yoyGrowth = calculateYoYGrowth(value as number, yearAgoValue);
                        }
                      }
                      
                      return (
                        <td
                          key={colIndex}
                          className="py-3 px-4 text-right"
                        >
                          <div className="flex flex-col items-end gap-1">
                            <span className={`text-sm tabular-nums ${
                              isNegative 
                                ? 'text-red-600' 
                                : value === 0 || value == null
                                ? 'text-slate-400'
                                : 'text-slate-900'
                            }`}>
                              {isNegative && value !== 0 ? `(${displayValue})` : displayValue}
                            </span>
                            {yoyGrowth !== null && (
                              <span className={`text-xs font-medium ${
                                yoyGrowth > 0 ? 'text-green-600' : 'text-red-600'
                              }`}>
                                {yoyGrowth > 0 ? '+' : ''}{yoyGrowth.toFixed(1)}%
                              </span>
                            )}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

