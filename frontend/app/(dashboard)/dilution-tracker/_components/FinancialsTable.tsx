"use client";

import { useState } from "react";
import { DollarSign, TrendingUp, TrendingDown, BarChart3 } from "lucide-react";

interface FinancialStatement {
  period_date: string;
  period_type: string;
  fiscal_year: number;
  
  // Balance Sheet - Assets
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
  
  // Balance Sheet - Liabilities
  total_liabilities?: number;
  total_current_liabilities?: number;
  accounts_payable?: number;
  debt_current?: number;
  accrued_liabilities?: number;
  deferred_revenue_current?: number;
  long_term_debt?: number;
  other_noncurrent_liabilities?: number;
  total_debt?: number;
  
  // Balance Sheet - Equity
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
  
  // Shares
  shares_outstanding?: number;
  weighted_avg_shares_basic?: number;
  weighted_avg_shares_diluted?: number;
  
  // Ratios
  current_ratio?: number;
  debt_to_equity_ratio?: number;
  working_capital?: number;
}

interface FinancialsTableProps {
  financials: FinancialStatement[];
  loading?: boolean;
}

type TabType = "income" | "balance" | "cashflow";

export function FinancialsTable({ financials, loading = false }: FinancialsTableProps) {
  const [activeTab, setActiveTab] = useState<TabType>("income");

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
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-12 text-center">
        <DollarSign className="h-12 w-12 text-slate-400 mx-auto mb-4" />
        <p className="text-slate-600">No financial statements available</p>
      </div>
    );
  }

  const formatCurrency = (amount: number | null | undefined) => {
    if (amount === null || amount === undefined) return '-';
    if (amount === 0) return '-';  // Tratar 0 como dato faltante
    const abs = Math.abs(amount);
    if (abs >= 1_000_000_000) return `$${(abs / 1_000_000_000).toFixed(2)}B`;
    if (abs >= 1_000_000) return `$${(abs / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `$${(abs / 1_000).toFixed(2)}K`;
    return `$${abs.toLocaleString()}`;
  };

  const formatShares = (shares: number | null | undefined) => {
    if (!shares || shares === 0) return '-';
    if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(2)}B`;
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(2)}M`;
    return shares.toLocaleString();
  };

  const formatRatio = (ratio: number | null | undefined) => ratio ? ratio.toFixed(2) : '-';
  const formatPercent = (value: number | null | undefined) => value ? `${value.toFixed(1)}%` : '-';

  const calculateMargin = (profit: number | undefined, revenue: number | undefined) => {
    if (!profit || !revenue || revenue === 0) return null;
    return (profit / revenue) * 100;
  };

  const calculateYoYGrowth = (current: number | undefined, yearAgo: number | undefined) => {
    if (!current || !yearAgo || yearAgo === 0) return null;
    return ((current - yearAgo) / Math.abs(yearAgo)) * 100;
  };

  const recentFinancials = financials.slice(0, 12);

  const tabs = [
    { id: "income" as TabType, label: "Income Statement", icon: DollarSign },
    { id: "balance" as TabType, label: "Balance Sheet", icon: BarChart3 },
    { id: "cashflow" as TabType, label: "Cash Flow", icon: TrendingDown },
  ];

  const incomeStatementRows = [
    { label: "Revenue", key: "revenue" as keyof FinancialStatement, format: formatCurrency, showGrowth: true, bold: true },
    { label: "Cost of Revenue", key: "cost_of_revenue" as keyof FinancialStatement, format: formatCurrency },
    { label: "Gross Profit", key: "gross_profit" as keyof FinancialStatement, format: formatCurrency, showMargin: true, bold: true },
    
    { section: "Operating Expenses", isSectionHeader: true },
    { label: "Research & Development", key: "research_development" as keyof FinancialStatement, format: formatCurrency },
    { label: "Selling, General & Admin", key: "selling_general_administrative" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Operating Expenses", key: "other_operating_expenses" as keyof FinancialStatement, format: formatCurrency },
    { label: "Total Operating Expenses", key: "total_operating_expenses" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Operating Income (EBIT)", key: "operating_income" as keyof FinancialStatement, format: formatCurrency, showMargin: true, bold: true },
    
    { section: "Other Income & Expenses", isSectionHeader: true },
    { label: "Interest Income", key: "interest_income" as keyof FinancialStatement, format: formatCurrency },
    { label: "Interest Expense", key: "interest_expense" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Income/Expense", key: "other_income_expense" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Profitability", isSectionHeader: true },
    { label: "Income Before Taxes", key: "income_before_taxes" as keyof FinancialStatement, format: formatCurrency },
    { label: "Income Taxes", key: "income_taxes" as keyof FinancialStatement, format: formatCurrency },
    { label: "Net Income", key: "net_income" as keyof FinancialStatement, format: formatCurrency, showMargin: true, showGrowth: true, bold: true },
    { label: "EBITDA", key: "ebitda" as keyof FinancialStatement, format: formatCurrency, showMargin: true, bold: true },
    
    { section: "Per Share Data", isSectionHeader: true },
    { label: "EPS (Basic)", key: "eps_basic" as keyof FinancialStatement, format: formatCurrency },
    { label: "EPS (Diluted)", key: "eps_diluted" as keyof FinancialStatement, format: formatCurrency },
  ];

  const balanceSheetRows = [
    { section: "Assets", isSectionHeader: true },
    { label: "Total Assets", key: "total_assets" as keyof FinancialStatement, format: formatCurrency, bold: true },
    
    { subsection: "Current Assets", isSubsectionHeader: true },
    { label: "Total Current Assets", key: "total_current_assets" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Cash & Equivalents", key: "cash_and_equivalents" as keyof FinancialStatement, format: formatCurrency },
    { label: "Short-term Investments", key: "short_term_investments" as keyof FinancialStatement, format: formatCurrency },
    { label: "Total Cash", key: "total_cash" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Receivables", key: "receivables" as keyof FinancialStatement, format: formatCurrency },
    { label: "Inventories", key: "inventories" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Current Assets", key: "other_current_assets" as keyof FinancialStatement, format: formatCurrency },
    
    { subsection: "Non-Current Assets", isSubsectionHeader: true },
    { label: "Property, Plant & Equipment", key: "property_plant_equipment_net" as keyof FinancialStatement, format: formatCurrency },
    { label: "Goodwill", key: "goodwill" as keyof FinancialStatement, format: formatCurrency },
    { label: "Intangible Assets", key: "intangible_assets_net" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Non-current Assets", key: "other_noncurrent_assets" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Liabilities", isSectionHeader: true },
    { label: "Total Liabilities", key: "total_liabilities" as keyof FinancialStatement, format: formatCurrency, bold: true },
    
    { subsection: "Current Liabilities", isSubsectionHeader: true },
    { label: "Total Current Liabilities", key: "total_current_liabilities" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Accounts Payable", key: "accounts_payable" as keyof FinancialStatement, format: formatCurrency },
    { label: "Current Debt", key: "debt_current" as keyof FinancialStatement, format: formatCurrency },
    { label: "Accrued Liabilities", key: "accrued_liabilities" as keyof FinancialStatement, format: formatCurrency },
    { label: "Deferred Revenue", key: "deferred_revenue_current" as keyof FinancialStatement, format: formatCurrency },
    
    { subsection: "Non-Current Liabilities", isSubsectionHeader: true },
    { label: "Long-term Debt", key: "long_term_debt" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Non-current Liabilities", key: "other_noncurrent_liabilities" as keyof FinancialStatement, format: formatCurrency },
    { label: "Total Debt", key: "total_debt" as keyof FinancialStatement, format: formatCurrency, bold: true },
    
    { section: "Shareholders' Equity", isSectionHeader: true },
    { label: "Total Equity", key: "stockholders_equity" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Common Stock", key: "common_stock" as keyof FinancialStatement, format: formatCurrency },
    { label: "Additional Paid-in Capital", key: "additional_paid_in_capital" as keyof FinancialStatement, format: formatCurrency },
    { label: "Treasury Stock", key: "treasury_stock" as keyof FinancialStatement, format: formatCurrency },
    { label: "Retained Earnings", key: "retained_earnings" as keyof FinancialStatement, format: formatCurrency },
    { label: "Accumulated OCI", key: "accumulated_other_comprehensive_income" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Key Metrics", isSectionHeader: true },
    { label: "Working Capital", key: "working_capital" as keyof FinancialStatement, format: formatCurrency },
        { label: "Current Ratio", key: "current_ratio" as keyof FinancialStatement, format: formatRatio },
        { label: "Debt/Equity Ratio", key: "debt_to_equity_ratio" as keyof FinancialStatement, format: formatRatio },
  ];

  const cashFlowRows = [
    { section: "Operating Activities", isSectionHeader: true },
    { label: "Net Cash from Operations", key: "operating_cash_flow" as keyof FinancialStatement, format: formatCurrency, bold: true, showGrowth: true },
    { label: "Depreciation & Amortization", key: "depreciation_amortization" as keyof FinancialStatement, format: formatCurrency },
    { label: "Stock-based Compensation", key: "stock_based_compensation" as keyof FinancialStatement, format: formatCurrency },
    { label: "Change in Working Capital", key: "change_in_working_capital" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Operating Activities", key: "other_operating_activities" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Investing Activities", isSectionHeader: true },
    { label: "Net Cash from Investing", key: "investing_cash_flow" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Capital Expenditures (CapEx)", key: "capital_expenditures" as keyof FinancialStatement, format: formatCurrency },
    { label: "Acquisitions", key: "acquisitions" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Investing Activities", key: "other_investing_activities" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Financing Activities", isSectionHeader: true },
    { label: "Net Cash from Financing", key: "financing_cash_flow" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Debt Issuance/Repayment", key: "debt_issuance_repayment" as keyof FinancialStatement, format: formatCurrency },
    { label: "Dividends Paid", key: "dividends_paid" as keyof FinancialStatement, format: formatCurrency },
    { label: "Stock Repurchased", key: "stock_repurchased" as keyof FinancialStatement, format: formatCurrency },
    { label: "Other Financing Activities", key: "other_financing_activities" as keyof FinancialStatement, format: formatCurrency },
    
    { section: "Summary", isSectionHeader: true },
    { label: "Net Change in Cash", key: "change_in_cash" as keyof FinancialStatement, format: formatCurrency, bold: true },
    { label: "Free Cash Flow", key: "free_cash_flow" as keyof FinancialStatement, format: formatCurrency, bold: true, showGrowth: true },
    
    { section: "Share Information", isSectionHeader: true },
    { label: "Shares Outstanding", key: "shares_outstanding" as keyof FinancialStatement, format: formatShares },
    { label: "Weighted Avg Shares (Basic)", key: "weighted_avg_shares_basic" as keyof FinancialStatement, format: formatShares },
    { label: "Weighted Avg Shares (Diluted)", key: "weighted_avg_shares_diluted" as keyof FinancialStatement, format: formatShares },
  ];

  const getCurrentRows = () => {
    switch (activeTab) {
      case "income": return incomeStatementRows;
      case "balance": return balanceSheetRows;
      case "cashflow": return cashFlowRows;
      default: return incomeStatementRows;
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
        <div className="flex border-b border-slate-200">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 px-6 py-4 text-sm font-semibold transition-colors flex items-center justify-center gap-2 ${
                activeTab === tab.id
                  ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left py-3 px-6 text-xs font-bold text-slate-700 uppercase tracking-wider sticky left-0 bg-slate-50 z-10 min-w-[220px]">
                  Period
                  </th>
                {recentFinancials.map((financial, index) => {
                  const date = new Date(financial.period_date);
                  const quarter = financial.period_type;
                  const month = date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                  
                  return (
                    <th key={index} className="text-right py-3 px-4 text-xs font-semibold text-slate-700 min-w-[110px] whitespace-nowrap">
                      <div className="font-bold">{quarter}</div>
                      <div className="text-xs text-slate-500 font-normal mt-0.5">{month}</div>
                    </th>
                  );
                })}
                </tr>
              </thead>
            <tbody className="bg-white">
              {getCurrentRows().map((row, rowIndex) => {
                if (row.isSectionHeader) {
                  return (
                    <tr key={rowIndex} className="bg-slate-100 border-t-2 border-slate-300">
                      <td colSpan={recentFinancials.length + 1} className="py-2 px-6 text-xs font-bold text-slate-700 uppercase tracking-wider">
                        {row.section}
                      </td>
                    </tr>
                  );
                }

                if ('isSubsectionHeader' in row && (row as any).isSubsectionHeader) {
                  return (
                    <tr key={rowIndex} className="bg-slate-50 border-t border-slate-200">
                      <td colSpan={recentFinancials.length + 1} className="py-2 px-8 text-xs font-semibold text-slate-600 italic">
                        {(row as any).subsection}
                      </td>
                    </tr>
                  );
                }

                return (
                  <tr key={rowIndex} className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${row.bold ? 'bg-slate-50/50' : ''}`}>
                    <td className={`py-3 px-6 text-sm sticky left-0 bg-white group-hover:bg-slate-50 ${row.bold ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                      {row.label}
                    </td>
                    {recentFinancials.map((financial, colIndex) => {
                      if (!('key' in row) || !row.key) return null;
                      const value = financial[row.key];
                      const isNegative = typeof value === 'number' && value < 0;
                      const formatFn = 'format' in row && row.format ? row.format : formatCurrency;
                      const displayValue = formatFn(Math.abs(value as number) as any);
                      
                      let yoyGrowth = null;
                      if ('showGrowth' in row && (row as any).showGrowth && colIndex < recentFinancials.length - 4) {
                        const yearAgoValue = recentFinancials[colIndex + 4]?.[row.key] as number;
                        if (yearAgoValue && value) {
                          yoyGrowth = calculateYoYGrowth(value as number, yearAgoValue);
                        }
                      }

                      let margin = null;
                      if ('showMargin' in row && (row as any).showMargin && financial.revenue) {
                        margin = calculateMargin(value as number, financial.revenue);
                      }
                      
                      return (
                        <td key={colIndex} className="py-3 px-4 text-right">
                          <div className="flex flex-col items-end gap-1">
                            <span className={`text-sm tabular-nums ${
                            isNegative 
                                ? 'text-red-600' 
                                : value === 0 || value == null
                                ? 'text-slate-400'
                                : row.bold
                                ? 'text-slate-900 font-semibold'
                                : 'text-slate-700'
                          }`}>
                              {isNegative && value !== 0 && value !== null ? `(${displayValue})` : displayValue}
                            </span>
                            {yoyGrowth !== null && (
                              <span className={`text-xs font-medium ${yoyGrowth > 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {yoyGrowth > 0 ? '+' : ''}{yoyGrowth.toFixed(1)}%
                              </span>
                            )}
                            {margin !== null && (
                              <span className="text-xs text-slate-500">
                                {margin.toFixed(1)}% margin
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
    </div>
  );
}
