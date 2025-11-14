"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { Search, TrendingUp, ArrowRight, BarChart3, Clock } from "lucide-react";

export default function DilutionTrackerPage() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [trendingTickers, setTrendingTickers] = useState<any[]>([]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/dilution-tracker/${searchQuery.toUpperCase()}`);
    }
  };

  return (
    <main className="min-h-screen bg-white">
      <div className="w-full px-6 py-8">
        {/* Hero Section */}
        <div className="max-w-5xl mx-auto">
          <div className="text-center space-y-6">
            {/* Icon */}
            <div className="flex justify-center">
              <div className="p-4 bg-blue-50 rounded-2xl">
                <BarChart3 className="h-12 w-12 text-blue-600" />
              </div>
            </div>

            {/* Title */}
            <div className="space-y-3">
              <h1 className="text-5xl font-bold text-slate-900 tracking-tight">
                Dilution Tracker
              </h1>
              <p className="text-xl text-slate-600 max-w-2xl mx-auto">
                Advanced dilution analysis, cash runway tracking, and institutional ownership monitoring
              </p>
            </div>

            {/* Search Bar */}
            <form onSubmit={handleSearch} className="max-w-2xl mx-auto mt-8">
              <div className="relative group">
                <Search className="absolute left-5 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400 group-focus-within:text-blue-600 transition-colors" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Enter ticker symbol (e.g., AAPL, TSLA, NVDA)"
                  className="w-full pl-14 pr-32 py-5 text-lg border border-slate-200 rounded-xl 
                           focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none
                           bg-white text-slate-900
                           placeholder:text-slate-400
                           transition-all duration-200"
                />
                <button
                  type="submit"
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 
                           px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg
                           transition-all duration-200
                           flex items-center gap-2"
                >
                  Analyze
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
              <p className="text-sm text-slate-500 mt-3">
                Press Enter or click Analyze to view detailed dilution metrics
              </p>
            </form>
          </div>
        </div>

        {/* Features Grid */}
        <div className="max-w-6xl mx-auto py-12">
          <div className="grid md:grid-cols-3 gap-6">
            {/* Feature 1 */}
            <div className="bg-white rounded-xl p-8 border border-slate-200 hover:border-blue-500 transition-all duration-200 hover:shadow-sm">
              <div className="h-12 w-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                <BarChart3 className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                Dilution Analysis
              </h3>
              <p className="text-slate-600 text-sm leading-relaxed">
                Track historical share dilution, outstanding shares progression, and identify potential dilution events
              </p>
            </div>

            {/* Feature 2 */}
            <div className="bg-white rounded-xl p-8 border border-slate-200 hover:border-green-500 transition-all duration-200 hover:shadow-sm">
              <div className="h-12 w-12 bg-green-50 rounded-xl flex items-center justify-center mb-4">
                <Clock className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                Cash Runway
              </h3>
              <p className="text-slate-600 text-sm leading-relaxed">
                Calculate burn rate, estimate cash runway, and project future cash position with detailed metrics
              </p>
            </div>

            {/* Feature 3 */}
            <div className="bg-white rounded-xl p-8 border border-slate-200 hover:border-purple-500 transition-all duration-200 hover:shadow-sm">
              <div className="h-12 w-12 bg-purple-50 rounded-xl flex items-center justify-center mb-4">
                <TrendingUp className="h-6 w-6 text-purple-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">
                Institutional Holdings
              </h3>
              <p className="text-slate-600 text-sm leading-relaxed">
                Monitor 13F filings, track position changes, and analyze institutional ownership patterns
              </p>
            </div>
          </div>
        </div>

        {/* Additional Info */}
        <div className="max-w-5xl mx-auto py-12">
          <div className="bg-blue-50 rounded-xl p-8 border border-slate-200">
            <h3 className="text-xl font-semibold text-slate-900 mb-4">
              Comprehensive Analysis Tools
            </h3>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="flex items-start gap-3">
                <div className="h-2 w-2 bg-blue-600 rounded-full mt-1.5"></div>
                <div>
                  <span className="font-medium text-slate-900">Financial Statements</span>
                  <p className="text-slate-600">Balance sheets, income statements, and cash flow analysis</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="h-2 w-2 bg-blue-600 rounded-full mt-1.5"></div>
                <div>
                  <span className="font-medium text-slate-900">SEC Filings</span>
                  <p className="text-slate-600">10-K, 10-Q, 8-K, S-3, and other relevant filings</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="h-2 w-2 bg-blue-600 rounded-full mt-1.5"></div>
                <div>
                  <span className="font-medium text-slate-900">Risk Scoring</span>
                  <p className="text-slate-600">Automated risk assessment from 0-100 scale</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="h-2 w-2 bg-blue-600 rounded-full mt-1.5"></div>
                <div>
                  <span className="font-medium text-slate-900">Historical Tracking</span>
                  <p className="text-slate-600">Multi-year dilution trends and pattern analysis</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Searches / Trending */}
        {trendingTickers.length > 0 && (
          <div className="max-w-5xl mx-auto py-8">
            <div className="bg-white rounded-xl p-6 border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Trending Analysis
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {trendingTickers.map((ticker) => (
                  <button
                    key={ticker.symbol}
                    onClick={() => router.push(`/dilution-tracker/${ticker.symbol}`)}
                    className="px-4 py-2 text-sm font-medium text-slate-700 
                             bg-slate-50 hover:bg-slate-100
                             rounded-lg transition-colors border border-slate-200"
                  >
                    {ticker.symbol}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

