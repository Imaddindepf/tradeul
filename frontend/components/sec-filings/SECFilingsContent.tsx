'use client';

import { useState, useEffect } from "react";
import { 
  Search, 
  Filter,
  Calendar,
  FileText,
  RefreshCw,
  AlertTriangle,
  ExternalLink
} from "lucide-react";

type SECFiling = {
  id: string;
  ticker: string | null;
  form_type: string;
  filed_at: string;
  company_name: string | null;
  description: string | null;
  link_to_filing_details: string | null;
  accession_no: string;
  cik: string;
};

type FilingsResponse = {
  total: number;
  filings: SECFiling[];
};

export function SECFilingsContent() {
  const [filings, setFilings] = useState<SECFiling[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [formTypeFilter, setFormTypeFilter] = useState("");
  const [startDate, setStartDate] = useState(() => {
    const today = new Date();
    today.setDate(today.getDate() - 1); // Ayer
    return today.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split('T')[0];
  });

  const fetchFilings = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.append('ticker', searchQuery.trim().toUpperCase());
      if (formTypeFilter.trim()) params.append('form_type', formTypeFilter.trim());
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);
      params.append('limit', '100');

      const response = await fetch(`http://localhost:8012/api/v1/filings?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: FilingsResponse = await response.json();
      setFilings(data.filings);
    } catch (err) {
      console.error('Error fetching filings:', err);
      setError(err instanceof Error ? err.message : "Error al cargar filings");
      setFilings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFilings();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchFilings();
  };

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return {
      date: date.toLocaleDateString('en-CA'), // YYYY-MM-DD
      time: date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    };
  };

  const truncateDescription = (desc: string | null, maxLength: number = 60) => {
    if (!desc) return '—';
    if (desc.length <= maxLength) return desc;
    return desc.substring(0, maxLength) + '...';
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Search Bar */}
      <div className="p-4 border-b border-slate-200 bg-slate-50">
        <form onSubmit={handleSearch} className="flex flex-col gap-3">
          {/* Row 1: Search and Button */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
                placeholder="Buscar por ticker (ej: TSLA, AAPL)"
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
            >
              {loading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              Buscar
            </button>
          </div>

          {/* Row 2: Filters */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <FileText className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={formTypeFilter}
                onChange={(e) => setFormTypeFilter(e.target.value.toUpperCase())}
                placeholder="Tipo de formulario (8-K, 10-K, 4, etc.)"
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
              />
            </div>
          </div>
        </form>

        {/* Results count */}
        {!loading && !error && (
          <div className="mt-2 text-xs text-slate-500">
            Mostrando {filings.length} resultados
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
          <AlertTriangle className="w-5 h-5" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-100 border-b border-slate-200">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Ticker
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Form
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Description
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Date
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Time
              </th>
              <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Link
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center">
                  <RefreshCw className="w-8 h-8 mx-auto mb-2 text-blue-500 animate-spin" />
                  <p className="text-slate-500">Cargando filings...</p>
                </td>
              </tr>
            ) : filings.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center">
                  <FileText className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                  <p className="text-slate-500 font-medium">No se encontraron filings</p>
                  <p className="text-xs text-slate-400 mt-1">
                    Intenta ajustar los filtros o el rango de fechas
                  </p>
                </td>
              </tr>
            ) : (
              filings.map((filing) => {
                const { date, time } = formatDateTime(filing.filed_at);
                return (
                  <tr 
                    key={filing.id} 
                    className="hover:bg-blue-50 transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`font-mono font-semibold ${
                        filing.ticker 
                          ? 'text-blue-600' 
                          : 'text-slate-400'
                      }`}>
                        {filing.ticker || '--'}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-slate-100 text-slate-700 group-hover:bg-blue-100 group-hover:text-blue-700">
                        {filing.form_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-600 text-xs">
                        {truncateDescription(filing.description)}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right font-mono text-xs text-slate-700">
                      {date}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right font-mono text-xs text-slate-600">
                      {time}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {filing.link_to_filing_details && (
                        <a
                          href={filing.link_to_filing_details}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center text-blue-600 hover:text-blue-800 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-slate-200 bg-slate-50 text-xs text-slate-500 flex items-center justify-between">
        <div>
          Mostrando {filings.length} de {filings.length} resultados
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
          <span>Live</span>
        </div>
      </div>
    </div>
  );
}

