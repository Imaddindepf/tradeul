"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { 
  BarChart3, 
  Building2, 
  FileText, 
  TrendingUp, 
  DollarSign,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
  ChevronRight
} from "lucide-react";
import { HoldersTable } from "./_components/HoldersTable";
import { FilingsTable } from "./_components/FilingsTable";
import { CashRunwayChart } from "./_components/CashRunwayChart";
import { DilutionHistoryChart } from "./_components/DilutionHistoryChart";
import { FinancialsTable } from "./_components/FinancialsTable";

type TabType = "overview" | "dilution" | "holders" | "filings" | "financials";

export default function TickerAnalysisPage() {
  const params = useParams();
  const ticker = (params?.ticker as string)?.toUpperCase() || "";
  
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [loading, setLoading] = useState(false);
  const [tickerData, setTickerData] = useState<any>(null);

  useEffect(() => {
    if (ticker) {
      fetchTickerData();
    }
  }, [ticker]);

  const fetchTickerData = async () => {
    setLoading(true);
    try {
      // TODO: Implementar fetch real desde API
      // const response = await fetch(`/api/dilution-tracker/${ticker}`);
      // const data = await response.json();
      // setTickerData(data);
      
      // Mock data por ahora
      setTickerData({
        ticker,
        company_name: "Loading...",
        status: "pending"
      });
    } catch (error) {
      console.error("Error fetching ticker data:", error);
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "dilution", label: "Dilution", icon: TrendingUp },
    { id: "holders", label: "Institutional Holders", icon: Building2 },
    { id: "filings", label: "SEC Filings", icon: FileText },
    { id: "financials", label: "Financials", icon: DollarSign },
  ];

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                  {ticker}
                </h1>
                <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg">
                  NASDAQ
                </span>
              </div>
              <p className="text-gray-600 dark:text-gray-400">
                {tickerData?.company_name || "Loading company information..."}
              </p>
            </div>
            <button
              onClick={fetchTickerData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300
                       bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600
                       rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Market Cap</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">--</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Float</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">--</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Shares Outstanding</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">--</p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Inst. Ownership</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">--</p>
            </div>
          </div>
        </div>

        {/* Tabs Navigation */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as TabType)}
                  className={`
                    flex items-center gap-2 px-6 py-4 text-sm font-medium whitespace-nowrap
                    border-b-2 transition-all duration-200
                    ${isActive 
                      ? 'border-blue-600 text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-950/20' 
                      : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }
                  `}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {activeTab === "overview" && <OverviewTab ticker={ticker} />}
            {activeTab === "dilution" && <DilutionTab ticker={ticker} />}
            {activeTab === "holders" && <HoldersTab ticker={ticker} />}
            {activeTab === "filings" && <FilingsTab ticker={ticker} />}
            {activeTab === "financials" && <FinancialsTab ticker={ticker} />}
          </div>
        </div>
      </div>
    </PageContainer>
  );
}

// Tab Components
function OverviewTab({ ticker }: { ticker: string }) {
  // TODO: Fetch real data from API
  const mockCashData = null;

  return (
    <div className="space-y-6">
      {/* Risk Scores */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Risk Assessment
        </h3>
        <div className="grid md:grid-cols-3 gap-4">
          <RiskCard title="Overall Risk" score={null} />
          <RiskCard title="Cash Need" score={null} />
          <RiskCard title="Dilution Risk" score={null} />
        </div>
      </div>

      {/* Cash Runway */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Cash Runway Analysis
        </h3>
        <CashRunwayChart data={mockCashData} loading={false} />
      </div>

      {/* Key Metrics Summary */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
            Share Structure
          </h4>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">Shares Outstanding</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">Float</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">1Y Dilution</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
            Financial Health
          </h4>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">Market Cap</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">Debt/Equity</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400">Current Ratio</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">--</span>
            </div>
          </div>
        </div>
      </div>

      {/* Implementation Notice */}
      <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5" />
          <div>
            <h4 className="font-semibold text-blue-900 dark:text-blue-100 mb-1">
              Data Integration in Progress
            </h4>
            <p className="text-sm text-blue-700 dark:text-blue-300">
              Service structure is complete. Real-time data fetching and persistence layer implementation is in progress.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function DilutionTab({ ticker }: { ticker: string }) {
  // TODO: Fetch real data from API
  const mockData = null;

  return (
    <div className="space-y-6">
      <DilutionHistoryChart data={mockData} loading={false} />
      
      {/* Completed Offerings Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Completed Offerings
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Historical offerings data will be displayed here
        </p>
      </div>
    </div>
  );
}

function HoldersTab({ ticker }: { ticker: string }) {
  // TODO: Fetch real data from API
  const mockHolders: any[] = [];

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/20 dark:to-indigo-950/20 rounded-xl p-6 border border-blue-200 dark:border-blue-800">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
              Institutional Ownership
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              13F filings from institutional investors
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Institutional</p>
            <p className="text-3xl font-bold text-blue-600 dark:text-blue-400">
              --
            </p>
          </div>
        </div>
      </div>

      <HoldersTable holders={mockHolders} loading={false} />
    </div>
  );
}

function FilingsTab({ ticker }: { ticker: string }) {
  // TODO: Fetch real data from API
  const mockFilings: any[] = [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            SEC Filings
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Recent SEC documents and regulatory filings
          </p>
        </div>
      </div>

      <FilingsTable filings={mockFilings} loading={false} />
    </div>
  );
}

function FinancialsTab({ ticker }: { ticker: string }) {
  // TODO: Fetch real data from API
  const mockFinancials: any[] = [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            Financial Statements
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Quarterly financial data including balance sheets, income statements, and cash flows
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3 py-1.5 text-sm font-medium bg-blue-100 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 rounded-lg">
            Quarterly
          </button>
          <button className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
            Annual
          </button>
        </div>
      </div>

      <FinancialsTable financials={mockFinancials} loading={false} />
    </div>
  );
}

function RiskCard({ title, score }: { title: string; score: number | null }) {
  const getRiskLevel = (score: number | null) => {
    if (score === null) return { level: "Unknown", color: "gray" };
    if (score >= 80) return { level: "Critical", color: "red" };
    if (score >= 60) return { level: "High", color: "orange" };
    if (score >= 40) return { level: "Medium", color: "yellow" };
    return { level: "Low", color: "green" };
  };

  const risk = getRiskLevel(score);
  
  const colorClasses = {
    gray: "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300",
    red: "bg-red-100 dark:bg-red-950/30 text-red-700 dark:text-red-400",
    orange: "bg-orange-100 dark:bg-orange-950/30 text-orange-700 dark:text-orange-400",
    yellow: "bg-yellow-100 dark:bg-yellow-950/30 text-yellow-700 dark:text-yellow-400",
    green: "bg-green-100 dark:bg-green-950/30 text-green-700 dark:text-green-400",
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">{title}</p>
      <div className="flex items-center justify-between">
        <p className="text-3xl font-bold text-gray-900 dark:text-white">
          {score ?? "--"}
        </p>
        <span className={`px-3 py-1 rounded-lg text-sm font-medium ${colorClasses[risk.color]}`}>
          {risk.level}
        </span>
      </div>
      {score !== null && (
        <div className="mt-4 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full ${
              risk.color === 'red' ? 'bg-red-500' :
              risk.color === 'orange' ? 'bg-orange-500' :
              risk.color === 'yellow' ? 'bg-yellow-500' :
              risk.color === 'green' ? 'bg-green-500' :
              'bg-gray-400'
            }`}
            style={{ width: `${score}%` }}
          />
        </div>
      )}
    </div>
  );
}

