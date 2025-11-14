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
    <main className="min-h-screen bg-white">
      <div className="w-full px-6 py-6 space-y-6">
        {/* Header */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-slate-900">
                  {ticker}
                </h1>
                <span className="px-3 py-1 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg">
                  NASDAQ
                </span>
              </div>
              <p className="text-slate-600">
                {tickerData?.company_name || "Loading company information..."}
              </p>
            </div>
            <button
              onClick={fetchTickerData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-700
                       bg-slate-50 hover:bg-slate-100 border border-slate-200
                       rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-200">
            <div>
              <p className="text-sm text-slate-500 mb-1">Market Cap</p>
              <p className="text-lg font-semibold text-slate-900">--</p>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Float</p>
              <p className="text-lg font-semibold text-slate-900">--</p>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Shares Outstanding</p>
              <p className="text-lg font-semibold text-slate-900">--</p>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Inst. Ownership</p>
              <p className="text-lg font-semibold text-slate-900">--</p>
            </div>
          </div>
        </div>

        {/* Tabs Navigation */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="flex border-b border-slate-200 overflow-x-auto">
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
                      ? 'border-blue-600 text-blue-600 bg-blue-50' 
                      : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
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
    </main>
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
        <h3 className="text-lg font-semibold text-slate-900 mb-4">
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
        <h3 className="text-lg font-semibold text-slate-900 mb-4">
          Cash Runway Analysis
        </h3>
        <CashRunwayChart data={mockCashData} loading={false} />
      </div>

      {/* Key Metrics Summary */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
          <h4 className="text-sm font-semibold text-slate-700 mb-4">
            Share Structure
          </h4>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">Shares Outstanding</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">Float</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">1Y Dilution</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
          <h4 className="text-sm font-semibold text-slate-700 mb-4">
            Financial Health
          </h4>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">Market Cap</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">Debt/Equity</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-slate-600">Current Ratio</span>
              <span className="text-sm font-semibold text-slate-900">--</span>
            </div>
          </div>
        </div>
      </div>

      {/* Implementation Notice */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-blue-600 mt-0.5" />
          <div>
            <h4 className="font-semibold text-slate-900 mb-1">
              Data Integration in Progress
            </h4>
            <p className="text-sm text-slate-600">
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
      <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900 mb-4">
          Completed Offerings
        </h3>
        <p className="text-sm text-slate-600">
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
      <div className="bg-blue-50 rounded-xl p-6 border border-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 mb-1">
              Institutional Ownership
            </h3>
            <p className="text-sm text-slate-600">
              13F filings from institutional investors
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-slate-500 mb-1">Total Institutional</p>
            <p className="text-3xl font-bold text-blue-600">
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
          <h3 className="text-lg font-semibold text-slate-900 mb-1">
            SEC Filings
          </h3>
          <p className="text-sm text-slate-600">
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
          <h3 className="text-lg font-semibold text-slate-900 mb-1">
            Financial Statements
          </h3>
          <p className="text-sm text-slate-600">
            Quarterly financial data including balance sheets, income statements, and cash flows
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3 py-1.5 text-sm font-medium bg-blue-100 text-blue-700 rounded-lg">
            Quarterly
          </button>
          <button className="px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
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
    gray: "bg-slate-100 text-slate-700",
    red: "bg-red-100 text-red-700",
    orange: "bg-orange-100 text-orange-700",
    yellow: "bg-yellow-100 text-yellow-700",
    green: "bg-green-100 text-green-700",
  };

  return (
    <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
      <p className="text-sm text-slate-500 mb-3">{title}</p>
      <div className="flex items-center justify-between">
        <p className="text-3xl font-bold text-slate-900">
          {score ?? "--"}
        </p>
        <span className={`px-3 py-1 rounded-lg text-sm font-medium ${colorClasses[risk.color]}`}>
          {risk.level}
        </span>
      </div>
      {score !== null && (
        <div className="mt-4 h-2 bg-slate-100 rounded-full overflow-hidden">
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

