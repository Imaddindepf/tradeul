"use client";

import { useState, useMemo, useCallback } from "react";
import { DollarSign, TrendingDown, BarChart3, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";

interface FinancialStatement {
  period_date: string;
  period_type: string;
  fiscal_year: number;

  // Balance Sheet
  total_assets?: number;
  total_current_assets?: number;
  cash_and_equivalents?: number;
  short_term_investments?: number;
  total_cash?: number;
  receivables?: number;
  inventories?: number;
  other_current_assets?: number;
  property_plant_equipment_net?: number;
  goodwill?: number;
  intangible_assets_net?: number;
  other_noncurrent_assets?: number;
  total_liabilities?: number;
  total_current_liabilities?: number;
  accounts_payable?: number;
  debt_current?: number;
  accrued_liabilities?: number;
  deferred_revenue_current?: number;
  long_term_debt?: number;
  other_noncurrent_liabilities?: number;
  total_debt?: number;
  stockholders_equity?: number;
  common_stock?: number;
  additional_paid_in_capital?: number;
  treasury_stock?: number;
  retained_earnings?: number;
  accumulated_other_comprehensive_income?: number;

  // Income Statement
  revenue?: number;
  cost_of_revenue?: number;
  gross_profit?: number;
  research_development?: number;
  selling_general_administrative?: number;
  other_operating_expenses?: number;
  total_operating_expenses?: number;
  operating_income?: number;
  interest_expense?: number;
  interest_income?: number;
  other_income_expense?: number;
  income_before_taxes?: number;
  income_taxes?: number;
  net_income?: number;
  eps_basic?: number;
  eps_diluted?: number;
  ebitda?: number;

  // Cash Flow
  operating_cash_flow?: number;
  depreciation_amortization?: number;
  stock_based_compensation?: number;
  change_in_working_capital?: number;
  other_operating_activities?: number;
  investing_cash_flow?: number;
  capital_expenditures?: number;
  acquisitions?: number;
  other_investing_activities?: number;
  financing_cash_flow?: number;
  debt_issuance_repayment?: number;
  dividends_paid?: number;
  stock_repurchased?: number;
  other_financing_activities?: number;
  change_in_cash?: number;
  free_cash_flow?: number;

  // Shares & Ratios
  shares_outstanding?: number;
  weighted_avg_shares_basic?: number;
  weighted_avg_shares_diluted?: number;
  current_ratio?: number;
  debt_to_equity_ratio?: number;
  working_capital?: number;
}

interface FinancialsTableProps {
  financials: FinancialStatement[];
  loading?: boolean;
}

type TabType = "income" | "balance" | "cashflow";

interface RowConfig {
  label?: string;
  key?: keyof FinancialStatement;
  format?: (value: number | null | undefined) => string;
  showGrowth?: boolean;
  showMargin?: boolean;
  bold?: boolean;
  section?: string;
  subsection?: string;
  isSectionHeader?: boolean;
  isSubsectionHeader?: boolean;
}

// Utility functions
const formatCurrency = (amount: number | null | undefined): string => {
  if (amount === null || amount === undefined || amount === 0) return '-';
  const abs = Math.abs(amount);
  if (abs >= 1_000_000_000) return `$${(amount / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `$${(amount / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(amount / 1_000).toFixed(2)}K`;
  return `$${amount.toLocaleString()}`;
};

const formatShares = (shares: number | null | undefined): string => {
  if (!shares || shares === 0) return '-';
  if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(2)}B`;
  if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(2)}M`;
  return shares.toLocaleString();
};

const formatRatio = (ratio: number | null | undefined): string =>
  ratio ? ratio.toFixed(2) : '-';

// Row configurations by tab
const incomeRows: RowConfig[] = [
  { label: "Revenue", key: "revenue", format: formatCurrency, showGrowth: true, bold: true },
  { label: "Cost of Revenue", key: "cost_of_revenue", format: formatCurrency },
  { label: "Gross Profit", key: "gross_profit", format: formatCurrency, showMargin: true, bold: true },
  { section: "Operating Expenses", isSectionHeader: true },
  { label: "R&D", key: "research_development", format: formatCurrency },
  { label: "SG&A", key: "selling_general_administrative", format: formatCurrency },
  { label: "Other OpEx", key: "other_operating_expenses", format: formatCurrency },
  { label: "Total OpEx", key: "total_operating_expenses", format: formatCurrency, bold: true },
  { label: "Operating Income", key: "operating_income", format: formatCurrency, showMargin: true, bold: true },
  { section: "Other Income/Expense", isSectionHeader: true },
  { label: "Interest Income", key: "interest_income", format: formatCurrency },
  { label: "Interest Expense", key: "interest_expense", format: formatCurrency },
  { label: "Other Income/Expense", key: "other_income_expense", format: formatCurrency },
  { section: "Bottom Line", isSectionHeader: true },
  { label: "Income Before Taxes", key: "income_before_taxes", format: formatCurrency },
  { label: "Income Taxes", key: "income_taxes", format: formatCurrency },
  { label: "Net Income", key: "net_income", format: formatCurrency, showMargin: true, showGrowth: true, bold: true },
  { label: "EBITDA", key: "ebitda", format: formatCurrency, bold: true },
  { section: "Per Share", isSectionHeader: true },
  { label: "EPS (Basic)", key: "eps_basic", format: formatCurrency },
  { label: "EPS (Diluted)", key: "eps_diluted", format: formatCurrency },
];

const balanceRows: RowConfig[] = [
  { section: "Assets", isSectionHeader: true },
  { label: "Total Assets", key: "total_assets", format: formatCurrency, bold: true },
  { subsection: "Current Assets", isSubsectionHeader: true },
  { label: "Cash & Equivalents", key: "cash_and_equivalents", format: formatCurrency },
  { label: "Short-term Investments", key: "short_term_investments", format: formatCurrency },
  { label: "Total Cash", key: "total_cash", format: formatCurrency, bold: true },
  { label: "Receivables", key: "receivables", format: formatCurrency },
  { label: "Inventories", key: "inventories", format: formatCurrency },
  { label: "Other Current", key: "other_current_assets", format: formatCurrency },
  { label: "Total Current Assets", key: "total_current_assets", format: formatCurrency, bold: true },
  { subsection: "Non-Current Assets", isSubsectionHeader: true },
  { label: "PP&E", key: "property_plant_equipment_net", format: formatCurrency },
  { label: "Goodwill", key: "goodwill", format: formatCurrency },
  { label: "Intangibles", key: "intangible_assets_net", format: formatCurrency },
  { label: "Other Non-Current", key: "other_noncurrent_assets", format: formatCurrency },
  { section: "Liabilities", isSectionHeader: true },
  { label: "Total Liabilities", key: "total_liabilities", format: formatCurrency, bold: true },
  { subsection: "Current Liabilities", isSubsectionHeader: true },
  { label: "Accounts Payable", key: "accounts_payable", format: formatCurrency },
  { label: "Current Debt", key: "debt_current", format: formatCurrency },
  { label: "Accrued Liabilities", key: "accrued_liabilities", format: formatCurrency },
  { label: "Deferred Revenue", key: "deferred_revenue_current", format: formatCurrency },
  { label: "Total Current Liabilities", key: "total_current_liabilities", format: formatCurrency, bold: true },
  { subsection: "Non-Current Liabilities", isSubsectionHeader: true },
  { label: "Long-term Debt", key: "long_term_debt", format: formatCurrency },
  { label: "Other Non-Current", key: "other_noncurrent_liabilities", format: formatCurrency },
  { label: "Total Debt", key: "total_debt", format: formatCurrency, bold: true },
  { section: "Equity", isSectionHeader: true },
  { label: "Stockholders' Equity", key: "stockholders_equity", format: formatCurrency, bold: true },
  { label: "Common Stock", key: "common_stock", format: formatCurrency },
  { label: "Additional Paid-in Capital", key: "additional_paid_in_capital", format: formatCurrency },
  { label: "Treasury Stock", key: "treasury_stock", format: formatCurrency },
  { label: "Retained Earnings", key: "retained_earnings", format: formatCurrency },
  { section: "Ratios", isSectionHeader: true },
  { label: "Working Capital", key: "working_capital", format: formatCurrency },
  { label: "Current Ratio", key: "current_ratio", format: formatRatio },
  { label: "Debt/Equity", key: "debt_to_equity_ratio", format: formatRatio },
];

const cashFlowRows: RowConfig[] = [
  { section: "Operating", isSectionHeader: true },
  { label: "Operating Cash Flow", key: "operating_cash_flow", format: formatCurrency, bold: true, showGrowth: true },
  { label: "D&A", key: "depreciation_amortization", format: formatCurrency },
  { label: "Stock Compensation", key: "stock_based_compensation", format: formatCurrency },
  { label: "Working Capital Δ", key: "change_in_working_capital", format: formatCurrency },
  { label: "Other Operating", key: "other_operating_activities", format: formatCurrency },
  { section: "Investing", isSectionHeader: true },
  { label: "Investing Cash Flow", key: "investing_cash_flow", format: formatCurrency, bold: true },
  { label: "CapEx", key: "capital_expenditures", format: formatCurrency },
  { label: "Acquisitions", key: "acquisitions", format: formatCurrency },
  { label: "Other Investing", key: "other_investing_activities", format: formatCurrency },
  { section: "Financing", isSectionHeader: true },
  { label: "Financing Cash Flow", key: "financing_cash_flow", format: formatCurrency, bold: true },
  { label: "Debt Issuance/Repayment", key: "debt_issuance_repayment", format: formatCurrency },
  { label: "Dividends", key: "dividends_paid", format: formatCurrency },
  { label: "Stock Repurchased", key: "stock_repurchased", format: formatCurrency },
  { label: "Other Financing", key: "other_financing_activities", format: formatCurrency },
  { section: "Summary", isSectionHeader: true },
  { label: "Net Change in Cash", key: "change_in_cash", format: formatCurrency, bold: true },
  { label: "Free Cash Flow", key: "free_cash_flow", format: formatCurrency, bold: true, showGrowth: true },
  { section: "Shares", isSectionHeader: true },
  { label: "Shares Outstanding", key: "shares_outstanding", format: formatShares },
  { label: "Wtd Avg (Basic)", key: "weighted_avg_shares_basic", format: formatShares },
  { label: "Wtd Avg (Diluted)", key: "weighted_avg_shares_diluted", format: formatShares },
];

export function FinancialsTable({ financials, loading = false }: FinancialsTableProps) {
  const [activeTab, setActiveTab] = useState<TabType>("income");
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);

  const copyToClipboard = useCallback(() => {
    const jsonData = JSON.stringify(financials, null, 2);
    navigator.clipboard.writeText(jsonData).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [financials]);

  // Filter rows to only show those with data
  const filterRowsWithData = useMemo(() => {
    return (rows: RowConfig[], data: FinancialStatement[]): RowConfig[] => {
      const hasData = (key: keyof FinancialStatement): boolean => {
        return data.some(d => {
          const val = d[key];
          return val !== null && val !== undefined && val !== 0;
        });
      };

      const filtered: RowConfig[] = [];
      let currentSection: string | null = null;
      let sectionHasData = false;
      let sectionStartIndex = -1;

      rows.forEach((row) => {
        if (row.isSectionHeader) {
          // If previous section had data, keep it
          if (currentSection && sectionHasData && sectionStartIndex >= 0) {
            // Section already added, nothing to do
          } else if (currentSection && !sectionHasData && sectionStartIndex >= 0) {
            // Remove section header if no data
            filtered.splice(sectionStartIndex, 1);
          }

          currentSection = row.section || null;
          sectionHasData = false;
          sectionStartIndex = filtered.length;
          filtered.push(row);
        } else if (row.isSubsectionHeader) {
          filtered.push(row);
        } else if (row.key) {
          if (hasData(row.key)) {
            sectionHasData = true;
            filtered.push(row);
          }
        }
      });

      // Handle last section
      if (currentSection && !sectionHasData && sectionStartIndex >= 0) {
        filtered.splice(sectionStartIndex, 1);
      }

      // Remove orphan subsection headers
      return filtered.filter((row, idx) => {
        if (row.isSubsectionHeader) {
          const nextRow = filtered[idx + 1];
          return nextRow && !nextRow.isSectionHeader && !nextRow.isSubsectionHeader;
        }
        return true;
      });
    };
  }, []);

  const recentFinancials = financials.slice(0, 8); // Show 8 quarters (2 years)

  const allRows: Record<TabType, RowConfig[]> = {
    income: incomeRows,
    balance: balanceRows,
    cashflow: cashFlowRows,
  };

  const filteredRows = useMemo(() =>
    filterRowsWithData(allRows[activeTab], recentFinancials),
    [activeTab, recentFinancials, filterRowsWithData]
  );

  const toggleSection = (section: string) => {
    setCollapsedSections(prev => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  const calculateYoYGrowth = (current: number | undefined, yearAgo: number | undefined): number | null => {
    if (!current || !yearAgo || yearAgo === 0) return null;
    return ((current - yearAgo) / Math.abs(yearAgo)) * 100;
  };

  const calculateMargin = (profit: number | undefined, revenue: number | undefined): number | null => {
    if (!profit || !revenue || revenue === 0) return null;
    return (profit / revenue) * 100;
  };

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="animate-pulse space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (!financials || financials.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-12 text-center">
        <DollarSign className="h-12 w-12 text-slate-400 mx-auto mb-4" />
        <p className="text-slate-600">No financial statements available</p>
      </div>
    );
  }

  const tabs = [
    { id: "income" as TabType, label: "Income", icon: DollarSign },
    { id: "balance" as TabType, label: "Balance", icon: BarChart3 },
    { id: "cashflow" as TabType, label: "Cash Flow", icon: TrendingDown },
  ];

  let currentSection: string | null = null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
      {/* Tabs + Copy Button */}
      <div className="flex border-b border-slate-200">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-4 py-3 text-sm font-semibold transition-colors flex items-center justify-center gap-2 ${activeTab === tab.id
              ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600'
              : 'text-slate-600 hover:bg-slate-50'
              }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
        {/* Copy JSON Button */}
        <button
          onClick={copyToClipboard}
          className="px-3 py-2 text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-colors flex items-center gap-1 border-l border-slate-200"
          title="Copy as JSON"
        >
          {copied ? (
            <Check className="h-4 w-4 text-green-500" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="text-left py-2 px-4 text-xs font-bold text-slate-700 uppercase tracking-wider sticky left-0 bg-slate-50 z-10 min-w-[160px]">
                Metric
              </th>
              {recentFinancials.map((f, i) => (
                <th key={i} className="text-right py-2 px-3 text-xs font-semibold text-slate-700 min-w-[90px] whitespace-nowrap">
                  <div className="font-bold">{f.period_type}</div>
                  <div className="text-[10px] text-slate-500 font-normal">
                    {new Date(f.period_date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white">
            {filteredRows.map((row, rowIndex) => {
              // Section Header
              if (row.isSectionHeader && row.section) {
                currentSection = row.section;
                const isCollapsed = collapsedSections.has(row.section);
                return (
                  <tr
                    key={rowIndex}
                    className="bg-slate-100 border-t border-slate-300 cursor-pointer hover:bg-slate-200"
                    onClick={() => toggleSection(row.section!)}
                  >
                    <td colSpan={recentFinancials.length + 1} className="py-2 px-4 text-xs font-bold text-slate-700 uppercase tracking-wider">
                      <div className="flex items-center gap-2">
                        {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        {row.section}
                      </div>
                    </td>
                  </tr>
                );
              }

              // Subsection Header
              if (row.isSubsectionHeader) {
                if (currentSection && collapsedSections.has(currentSection)) return null;
                return (
                  <tr key={rowIndex} className="bg-slate-50/50">
                    <td colSpan={recentFinancials.length + 1} className="py-1.5 px-6 text-[11px] font-semibold text-slate-500 italic">
                      {row.subsection}
                    </td>
                  </tr>
                );
              }

              // Skip if section is collapsed
              if (currentSection && collapsedSections.has(currentSection)) return null;

              // Data Row
              return (
                <tr
                  key={rowIndex}
                  className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${row.bold ? 'bg-blue-50/30' : ''}`}
                >
                  <td className={`py-2 px-4 text-sm sticky left-0 bg-white ${row.bold ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                    {row.label}
                  </td>
                  {recentFinancials.map((f, colIndex) => {
                    if (!row.key) return null;
                    const value = f[row.key] as number | undefined;
                    const isNegative = typeof value === 'number' && value < 0;
                    const formatFn = row.format || formatCurrency;
                    const displayValue = formatFn(value);

                    // YoY Growth
                    let yoyGrowth = null;
                    if (row.showGrowth && colIndex < recentFinancials.length - 4) {
                      const yearAgoValue = recentFinancials[colIndex + 4]?.[row.key] as number;
                      yoyGrowth = calculateYoYGrowth(value, yearAgoValue);
                    }

                    // Margin
                    let margin = null;
                    if (row.showMargin && f.revenue) {
                      margin = calculateMargin(value, f.revenue);
                    }

                    return (
                      <td key={colIndex} className="py-2 px-3 text-right">
                        <div className="flex flex-col items-end">
                          <span className={`text-sm tabular-nums ${isNegative ? 'text-red-600' :
                            displayValue === '-' ? 'text-slate-300' :
                              row.bold ? 'text-slate-900 font-semibold' : 'text-slate-700'
                            }`}>
                            {isNegative && displayValue !== '-' ? `(${displayValue.replace('-', '')})` : displayValue}
                          </span>
                          {yoyGrowth !== null && (
                            <span className={`text-[10px] font-medium ${yoyGrowth > 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {yoyGrowth > 0 ? '+' : ''}{yoyGrowth.toFixed(0)}% YoY
                            </span>
                          )}
                          {margin !== null && (
                            <span className="text-[10px] text-slate-400">
                              {margin.toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
