"use client";

import { useState } from "react";
import { FileText, ExternalLink } from "lucide-react";
import { 
  getFilingTags, 
  categorizeFilings,
  type Filing
} from "@/lib/models/filings";

interface FilingsTableProps {
  filings: Filing[];
  loading?: boolean;
}

type ViewType = "chronological" | "categorized";

export function FilingsTable({ filings, loading = false }: FilingsTableProps) {
  const [viewType, setViewType] = useState<ViewType>("categorized");

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="animate-pulse space-y-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-14 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (!filings || filings.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-12 text-center">
        <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
        <p className="text-slate-600">No SEC filings available</p>
      </div>
    );
  }

  const categorizedFilings = categorizeFilings(filings);

  const renderFilingRow = (filing: Filing, showInCategory = false) => {
    const tags = getFilingTags(filing);
    
    return (
      <tr key={filing.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
        <td className="py-2.5 px-4">
          <div className="flex items-start gap-1.5 flex-wrap">
            <span className="px-2 py-0.5 bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold rounded font-mono whitespace-nowrap">
              {filing.filing_type}
            </span>
            {tags.slice(0, showInCategory ? 2 : 3).map((tag, idx) => (
              <span key={idx} className={`px-2 py-0.5 border text-xs font-medium rounded whitespace-nowrap ${tag.color}`}>
                {tag.label}
              </span>
            ))}
          </div>
        </td>
        <td className="py-2.5 px-4 text-sm text-slate-900 leading-snug">
          {filing.title}
        </td>
        <td className="py-2.5 px-4 text-xs text-slate-600 text-right whitespace-nowrap">
          {filing.report_date ? new Date(filing.report_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '-'}
        </td>
        <td className="py-2.5 px-4 text-xs text-slate-600 text-right whitespace-nowrap">
          {new Date(filing.filing_date).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })}
        </td>
        <td className="py-2.5 px-4 text-center">
          {filing.url && (
            <a
              href={filing.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex text-blue-600 hover:text-blue-700 transition-colors"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </td>
      </tr>
    );
  };

  return (
    <div className="space-y-4">
      {/* View Toggle */}
      <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setViewType("chronological")}
          className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
            viewType === "chronological"
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Chronological
        </button>
        <button
          onClick={() => setViewType("categorized")}
          className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors ${
            viewType === "categorized"
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          By Category
        </button>
      </div>

      {/* Chronological View */}
      {viewType === "chronological" && (
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4 text-left text-xs font-bold text-slate-700 uppercase tracking-wider min-w-[280px]">Type & Tags</th>
                  <th className="py-3 px-4 text-left text-xs font-bold text-slate-700 uppercase tracking-wider">Description</th>
                  <th className="py-3 px-4 text-right text-xs font-bold text-slate-700 uppercase tracking-wider whitespace-nowrap">Period Ended</th>
                  <th className="py-3 px-4 text-right text-xs font-bold text-slate-700 uppercase tracking-wider whitespace-nowrap">Filed</th>
                  <th className="py-3 px-4 text-center text-xs font-bold text-slate-700 uppercase tracking-wider w-20">Link</th>
                </tr>
              </thead>
              <tbody>
                {filings.map((filing) => renderFilingRow(filing, false))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Categorized View */}
      {viewType === "categorized" && (
        <div className="grid grid-cols-2 gap-4">
          {categorizedFilings.map((category) => (
            <div
              key={category.key}
              className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden"
            >
              <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                      {category.name}
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">{category.description}</p>
                  </div>
                  <span className="px-2 py-0.5 bg-slate-200 text-slate-700 text-xs font-semibold rounded">
                    {category.filings.length}
                  </span>
                </div>
              </div>
              
              <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                <table className="w-full">
                  <tbody>
                    {category.filings.map((filing) => renderFilingRow(filing, true))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
