"use client";

import { DollarSign } from "lucide-react";

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
      <div className="animate-pulse space-y-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-32 bg-gray-100 dark:bg-gray-800 rounded-lg" />
        ))}
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

  const sections = [
    {
      title: "Balance Sheet",
      rows: [
        { label: "Cash & Equivalents", key: "cash" as keyof FinancialStatement, format: formatCurrency },
        { label: "Total Cash", key: "total_cash" as keyof FinancialStatement, format: formatCurrency },
        { label: "Total Debt", key: "debt" as keyof FinancialStatement, format: formatCurrency },
        { label: "Stockholders Equity", key: "equity" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Income Statement",
      rows: [
        { label: "Revenue", key: "revenue" as keyof FinancialStatement, format: formatCurrency },
        { label: "Net Income", key: "net_income" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Cash Flow",
      rows: [
        { label: "Operating Cash Flow", key: "operating_cash_flow" as keyof FinancialStatement, format: formatCurrency },
        { label: "Free Cash Flow", key: "free_cash_flow" as keyof FinancialStatement, format: formatCurrency },
      ]
    },
    {
      title: "Key Metrics",
      rows: [
        { label: "Shares Outstanding", key: "shares_outstanding" as keyof FinancialStatement, format: formatShares },
        { label: "Current Ratio", key: "current_ratio" as keyof FinancialStatement, format: formatRatio },
        { label: "Debt/Equity Ratio", key: "debt_to_equity_ratio" as keyof FinancialStatement, format: formatRatio },
      ]
    },
  ];

  // Show last 4 periods
  const recentFinancials = financials.slice(0, 4);

  return (
    <div className="space-y-8">
      {sections.map((section) => (
        <div key={section.title} className="bg-white/50 dark:bg-white/5 rounded-xl border border-gray-200/50 dark:border-gray-700/50 overflow-hidden">
          <div className="bg-gray-500/5 px-6 py-4 border-b border-gray-200/50 dark:border-gray-700/50">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {section.title}
            </h3>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200/50 dark:border-gray-700/50">
                  <th className="text-left py-4 px-6 text-sm font-semibold text-gray-700 dark:text-gray-300 min-w-[200px]">
                    Metric
                  </th>
                  {recentFinancials.map((financial, index) => (
                    <th
                      key={index}
                      className="text-right py-4 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300 min-w-[120px]"
                    >
                      <div className="space-y-1">
                        <div>{financial.period_type}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 font-normal">
                          {new Date(financial.period_date).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short'
                          })}
                        </div>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {section.rows.map((row, rowIndex) => (
                  <tr
                    key={rowIndex}
                    className="border-b border-gray-100/50 dark:border-gray-800/50 hover:bg-white/50 dark:hover:bg-white/5 transition-colors"
                  >
                    <td className="py-4 px-6 text-sm font-medium text-gray-900 dark:text-white">
                      {row.label}
                    </td>
                    {recentFinancials.map((financial, colIndex) => {
                      const value = financial[row.key];
                      const isNegative = typeof value === 'number' && value < 0;
                      
                      return (
                        <td
                          key={colIndex}
                          className="py-4 px-4 text-right"
                        >
                          <span className={`text-sm font-mono ${
                            isNegative 
                              ? 'text-red-600 dark:text-red-400' 
                              : 'text-gray-900 dark:text-white'
                          }`}>
                            {value != null ? row.format(value as number) : '--'}
                          </span>
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

