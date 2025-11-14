"use client";

import { FileText, ExternalLink } from "lucide-react";

interface Filing {
  id: number;
  filing_type: string;
  filing_date: string;
  report_date?: string;
  title: string;
  category: string;
  is_offering_related: boolean;
  is_dilutive: boolean;
  url?: string;
}

interface FilingsTableProps {
  filings: Filing[];
  loading?: boolean;
}

export function FilingsTable({ filings, loading = false }: FilingsTableProps) {
  if (loading) {
    return (
      <div className="animate-pulse space-y-3">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-14 bg-gray-100 dark:bg-gray-800 rounded-lg" />
        ))}
      </div>
    );
  }

  if (!filings || filings.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No SEC filings available</p>
      </div>
    );
  }

  const getCategoryBadge = (category: string) => {
    const colors = {
      financial: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
      offering: "bg-purple-500/10 text-purple-700 dark:text-purple-300",
      ownership: "bg-green-500/10 text-green-700 dark:text-green-300",
      proxy: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-300",
      disclosure: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
      other: "bg-gray-500/10 text-gray-700 dark:text-gray-300",
    };

    const color = colors[category as keyof typeof colors] || colors.other;

    return (
      <span className={`text-xs px-2 py-1 rounded font-medium ${color}`}>
        {category}
      </span>
    );
  };

  return (
    <div className="space-y-3">
      {/* Filter pills */}
      <div className="flex items-center gap-2 flex-wrap pb-4 border-b border-gray-200/50 dark:border-gray-700/50">
        <button className="px-3 py-1.5 text-sm font-medium bg-blue-500/10 text-blue-700 dark:text-blue-300 rounded-lg">
          All
        </button>
        <button className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-white/5 rounded-lg transition-colors">
          Financial
        </button>
        <button className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-white/5 rounded-lg transition-colors">
          Offering
        </button>
        <button className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-white/5 rounded-lg transition-colors">
          Ownership
        </button>
      </div>

      {/* Filings List */}
      <div className="space-y-2">
        {filings.map((filing) => (
          <div
            key={filing.id}
            className="flex items-center justify-between p-4 bg-white/50 dark:bg-white/5 rounded-lg border border-gray-200/50 dark:border-gray-700/50 hover:border-blue-500/50 transition-all"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2">
                <span className="px-3 py-1 bg-white/80 dark:bg-white/10 border border-gray-200/50 dark:border-gray-700/50 text-gray-900 dark:text-white text-sm font-mono font-semibold rounded">
                  {filing.filing_type}
                </span>
                {getCategoryBadge(filing.category)}
                {filing.is_dilutive && (
                  <span className="text-xs px-2 py-1 bg-red-500/10 text-red-700 dark:text-red-300 rounded font-medium">
                    Dilutive
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-900 dark:text-white font-medium mb-1">
                {filing.title}
              </p>
              <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                <span>Filed: {new Date(filing.filing_date).toLocaleDateString()}</span>
                {filing.report_date && (
                  <span>Period: {new Date(filing.report_date).toLocaleDateString()}</span>
                )}
              </div>
            </div>
            
            {filing.url && (
              <a
                href={filing.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 rounded-lg transition-colors"
              >
                View
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

