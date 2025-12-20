"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Legend, ComposedChart, ReferenceLine } from "recharts";

interface HistoricalSharesData {
  date: string;
  shares: number;
  form?: string;
}

interface PotentialDilution {
  warrants: number;
  atm: number;
  equity_line: number;
  convertibles: number;
  s1_offering: number;
}

interface DilutionHistoryData {
  history?: HistoricalSharesData[];
  all_records?: Array<{ period: string; outstanding_shares: number }>;
  dilution_1y?: number | null;
  dilution_3y?: number | null;
  dilution_5y?: number | null;
  dilution_summary?: {
    "1_year"?: number;
    "3_years"?: number;
    "5_years"?: number;
  };
}

interface SECDilutionData {
  warrants?: Array<{ outstanding?: number; potential_new_shares?: number }>;
  atm_offerings?: Array<{ remaining_capacity?: number; potential_shares_at_current_price?: number }>;
  equity_lines?: Array<{ remaining_capacity?: number; potential_shares?: number }>;
  convertible_notes?: Array<{ potential_shares?: number }>;
  convertible_preferred?: Array<{ potential_shares?: number }>;
  s1_offerings?: Array<{ potential_shares?: number }>;
  shares_outstanding?: number;
  current_price?: number;
}

interface DilutionHistoryChartProps {
  data: DilutionHistoryData | null;
  secData?: SECDilutionData | null;
  loading?: boolean;
}

export function DilutionHistoryChart({ data, secData, loading = false }: DilutionHistoryChartProps) {
  // Format functions
  const formatShares = (shares: number) => {
    if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(2)}B`;
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(2)}M`;
    return shares.toLocaleString();
  };

  const formatSharesCompact = (shares: number) => {
    if (shares >= 1_000_000_000) return `${(shares / 1_000_000_000).toFixed(1)}B`;
    if (shares >= 1_000_000) return `${(shares / 1_000_000).toFixed(1)}M`;
    return `${(shares / 1000).toFixed(0)}K`;
  };

  // Extract historical data
  let historyData: Array<{ date: string; shares: number }> = [];
  
  if (data?.history && data.history.length > 0) {
    historyData = data.history.map(h => ({
      date: h.date,
      shares: h.shares
    }));
  } else if (data?.all_records && data.all_records.length > 0) {
    historyData = data.all_records.map(r => ({
      date: r.period,
      shares: r.outstanding_shares
    }));
  }

  // Calculate potential dilution from SEC data
  const calculatePotentialDilution = (): PotentialDilution => {
    if (!secData) return { warrants: 0, atm: 0, equity_line: 0, convertibles: 0, s1_offering: 0 };

    const currentPrice = Number(secData.current_price) || 1;

    // Warrants - total outstanding
    const warrants = (secData.warrants || []).reduce((sum, w) => {
      return sum + (w.outstanding || w.potential_new_shares || 0);
    }, 0);

    // ATM - remaining capacity / current price
    const atm = (secData.atm_offerings || []).reduce((sum, a) => {
      if (a.potential_shares_at_current_price) return sum + a.potential_shares_at_current_price;
      if (a.remaining_capacity && currentPrice > 0) {
        return sum + Math.floor(a.remaining_capacity / currentPrice);
      }
      return sum;
    }, 0);

    // Equity Lines - remaining capacity / current price
    const equityLine = (secData.equity_lines || []).reduce((sum, e) => {
      if (e.potential_shares) return sum + e.potential_shares;
      if (e.remaining_capacity && currentPrice > 0) {
        return sum + Math.floor(e.remaining_capacity / currentPrice);
      }
      return sum;
    }, 0);

    // Convertibles (notes + preferred)
    const convertibleNotes = (secData.convertible_notes || []).reduce((sum, c) => {
      return sum + (c.potential_shares || 0);
    }, 0);
    const convertiblePref = (secData.convertible_preferred || []).reduce((sum, c) => {
      return sum + (c.potential_shares || 0);
    }, 0);

    // S-1 Offerings
    const s1 = (secData.s1_offerings || []).reduce((sum, s) => {
      return sum + (s.potential_shares || 0);
    }, 0);

    return {
      warrants,
      atm,
      equity_line: equityLine,
      convertibles: convertibleNotes + convertiblePref,
      s1_offering: s1
    };
  };

  const potential = calculatePotentialDilution();
  const hasPotentialDilution = potential.warrants > 0 || potential.atm > 0 || 
    potential.equity_line > 0 || potential.convertibles > 0 || potential.s1_offering > 0;

  // Get dilution percentages
  const dilution1y = data?.dilution_summary?.["1_year"] ?? data?.dilution_1y;
  const dilution3y = data?.dilution_summary?.["3_years"] ?? data?.dilution_3y;
  const dilution5y = data?.dilution_summary?.["5_years"] ?? data?.dilution_5y;

  // Prepare chart data
  const validHistory = historyData.filter(h => h.shares && h.shares > 0);
  const displayHistory = validHistory.slice(-20);
  
  // Current O/S: Use last historical record for consistency in the chart
  // The "Fully Diluted" bar should show the same base O/S as the last historical bar
  const lastHistoricalOS = displayHistory.length > 0 ? displayHistory[displayHistory.length - 1].shares : 0;
  const currentOS = lastHistoricalOS || secData?.shares_outstanding || 0;

  // Build chart data - historical bars show ONLY O/S (no dilution)
  const chartData = displayHistory.map((point, index) => {
    const dateObj = new Date(point.date);
    const isLast = index === displayHistory.length - 1;
    
    return {
      date: dateObj.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }),
      fullDate: point.date,
      shares: point.shares,
      isLatest: isLast,
      // Historical bars: NO dilution - only "Fully Diluted" bar shows potential
      warrants: 0,
      atm: 0,
      equityLine: 0,
      convertibles: 0,
      s1: 0,
    };
  });

  // Add "Fully Diluted" bar if we have potential dilution
  if (hasPotentialDilution && currentOS > 0) {
    chartData.push({
      date: 'Fully Diluted',
      fullDate: 'potential',
      shares: currentOS,
      isLatest: false,
      warrants: potential.warrants,
      atm: potential.atm,
      equityLine: potential.equity_line,
      convertibles: potential.convertibles,
      s1: potential.s1_offering,
    });
  }

  const formatPercent = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'N/A';
    return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
  };

  // Loading or no data
  if (loading) {
    return (
      <div className="border border-slate-200 rounded-lg p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-slate-200 rounded w-1/3"></div>
          <div className="h-48 bg-slate-100 rounded"></div>
        </div>
      </div>
    );
  }

  if (chartData.length === 0) {
    return null;
  }

  // Calculate totals for legend
  const totalPotential = potential.warrants + potential.atm + potential.equity_line + potential.convertibles + potential.s1_offering;
  const fullyDiluted = currentOS + totalPotential;
  const dilutionPct = currentOS > 0 ? (totalPotential / currentOS * 100).toFixed(1) : '0';

  return (
    <div className="border border-slate-200 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="text-sm font-medium text-slate-700">
            Historical O/S & Potential Dilution
          </h4>
          {secData?.current_price && (
            <p className="text-xs text-slate-400 mt-0.5">
              Dilution calculated using market price of ${Number(secData.current_price).toFixed(4)}
            </p>
          )}
        </div>
        
        {/* Dilution Metrics */}
        <div className="flex items-center gap-4 text-xs">
          {dilution1y !== null && dilution1y !== undefined && (
            <div>
              <span className="text-slate-400">1Y:</span>
              <span className={`ml-1 font-medium ${dilution1y > 0 ? 'text-red-600' : dilution1y < 0 ? 'text-green-600' : 'text-slate-600'}`}>
                {formatPercent(dilution1y)}
              </span>
            </div>
          )}
          {dilution3y !== null && dilution3y !== undefined && (
            <div>
              <span className="text-slate-400">3Y:</span>
              <span className={`ml-1 font-medium ${dilution3y > 0 ? 'text-red-600' : dilution3y < 0 ? 'text-green-600' : 'text-slate-600'}`}>
                {formatPercent(dilution3y)}
              </span>
            </div>
          )}
        </div>
      </div>
      
      {/* Chart */}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 30 }}>
            <XAxis 
              dataKey="date" 
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              angle={-45}
              textAnchor="end"
              height={50}
              interval={Math.floor(chartData.length / 8)}
            />
            <YAxis 
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              tickFormatter={formatSharesCompact}
              width={55}
            />
            <Tooltip 
              content={({ active, payload, label }) => {
                if (!active || !payload || payload.length === 0) return null;
                
                const data = payload[0]?.payload;
                const isFullyDiluted = data?.fullDate === 'potential';
                const isLatest = data?.isLatest;
                
                return (
                  <div className="bg-slate-800 border-none rounded-lg p-3 text-xs shadow-xl">
                    <div className="text-slate-100 font-semibold mb-2">{label}</div>
                    {/* Historical O/S or Current O/S */}
                    {data?.shares > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>{isFullyDiluted || isLatest ? 'Current O/S' : 'Historical O/S'}</span>
                        <span className="font-medium text-blue-300">{formatShares(data.shares)}</span>
                      </div>
                    )}
                    {/* Only show dilution components if they have value */}
                    {data?.atm > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>ATM</span>
                        <span className="font-medium text-orange-300">{formatShares(data.atm)}</span>
                      </div>
                    )}
                    {data?.warrants > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>Warrants</span>
                        <span className="font-medium text-yellow-300">{formatShares(data.warrants)}</span>
                      </div>
                    )}
                    {data?.equityLine > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>Equity Line</span>
                        <span className="font-medium text-slate-300">{formatShares(data.equityLine)}</span>
                      </div>
                    )}
                    {data?.s1 > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>S-1 Offering</span>
                        <span className="font-medium text-sky-300">{formatShares(data.s1)}</span>
                      </div>
                    )}
                    {data?.convertibles > 0 && (
                      <div className="flex justify-between gap-4 text-slate-300">
                        <span>Convertibles</span>
                        <span className="font-medium text-slate-400">{formatShares(data.convertibles)}</span>
                      </div>
                    )}
                  </div>
                );
              }}
            />
            
            {/* Stacked Bars */}
            <Bar dataKey="shares" stackId="a" fill="#1e40af" radius={[0, 0, 0, 0]} name="Current O/S" />
            <Bar dataKey="atm" stackId="a" fill="#f97316" radius={[0, 0, 0, 0]} name="ATM" />
            <Bar dataKey="warrants" stackId="a" fill="#eab308" radius={[0, 0, 0, 0]} name="Warrants" />
            <Bar dataKey="equityLine" stackId="a" fill="#a3a3a3" radius={[0, 0, 0, 0]} name="Equity Line" />
            <Bar dataKey="s1" stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]} name="S-1 Offering" />
            <Bar dataKey="convertibles" stackId="a" fill="#6b7280" radius={[4, 4, 0, 0]} name="Convertibles" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend - Potential Dilution Breakdown */}
      {hasPotentialDilution && (
        <div className="mt-4 pt-3 border-t border-slate-100">
          <div className="text-xs text-slate-500 mb-2">Fully Diluted Breakdown:</div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-[#1e40af]"></span>
                Current O/S
              </span>
              <span className="font-medium text-slate-700">{formatShares(currentOS)}</span>
            </div>
            {potential.atm > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#f97316]"></span>
                  ATM
                </span>
                <span className="font-medium text-orange-600">{formatShares(potential.atm)}</span>
              </div>
            )}
            {potential.warrants > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#eab308]"></span>
                  Warrants
                </span>
                <span className="font-medium text-yellow-600">{formatShares(potential.warrants)}</span>
              </div>
            )}
            {potential.equity_line > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#a3a3a3]"></span>
                  Equity Line
                </span>
                <span className="font-medium text-slate-600">{formatShares(potential.equity_line)}</span>
              </div>
            )}
            {potential.s1_offering > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#3b82f6]"></span>
                  S-1 Offering
                </span>
                <span className="font-medium text-blue-600">{formatShares(potential.s1_offering)}</span>
              </div>
            )}
            {potential.convertibles > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#6b7280]"></span>
                  Convertibles
                </span>
                <span className="font-medium text-slate-600">{formatShares(potential.convertibles)}</span>
              </div>
            )}
          </div>
          <div className="mt-2 pt-2 border-t border-slate-100 flex justify-between text-xs">
            <span className="text-slate-500">Fully Diluted Total</span>
            <span className="font-semibold text-slate-800">
              {formatShares(fullyDiluted)} 
              <span className="text-red-500 ml-1">(+{dilutionPct}%)</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
