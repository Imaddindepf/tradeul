"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Legend, ReferenceLine } from "recharts";

interface CashRunwayData {
  ticker?: string;
  historical_cash: number;
  historical_cash_date: string;
  quarterly_operating_cf: number;
  daily_burn_rate: number;
  days_since_report: number;
  prorated_cf: number;
  capital_raises?: {
    total: number;
    count: number;
    details: Array<{
      filing_date: string;
      gross_proceeds: number;
      instrument_type: string;
      description: string;
    }>;
  };
  estimated_current_cash: number;
  runway_days: number | null;
  runway_months: number | null;
  runway_risk_level: string;
  data_source: string;
  cash_history?: Array<{
    date: string;
    cash: number;
    total_assets?: number;
    total_liabilities?: number;
  }>;
  cf_history?: Array<{
    date: string;
    operating_cf: number;
    investing_cf?: number;
    financing_cf?: number;
  }>;
}

interface CashRunwayChartProps {
  data: CashRunwayData | null;
  loading?: boolean;
}

// Colors matching DilutionTracker style
const COLORS = {
  historical: '#3b82f6',      // Blue - historical cash
  reported: '#60a5fa',        // Light blue - reported cash
  burn: '#ef4444',            // Red - cash burn (prorated)
  raise: '#22c55e',           // Green - capital raises
  estimate: '#f59e0b',        // Amber - current estimate
};

export function CashRunwayChart({ data, loading = false }: CashRunwayChartProps) {
  // Format functions
  const formatCash = (value: number) => {
    if (!value && value !== 0) return 'N/A';
    const absValue = Math.abs(value);
    if (absValue >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
    if (absValue >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (absValue >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
    return `$${value.toLocaleString()}`;
  };

  const formatCashFull = (value: number) => {
    if (!value && value !== 0) return 'N/A';
    return `$${Math.abs(value).toLocaleString()}`;
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return dateStr;
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
    } catch {
      return dateStr;
    }
  };

  // Loading state
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

  // No data
  if (!data) {
    return null;
  }

  // Build chart data - Historical bars + 4 separate estimate bars
  const buildChartData = () => {
    const chartData: Array<{
      label: string;
      value: number;
      type: 'historical' | 'reported' | 'burn' | 'raise' | 'estimate';
      fullDate?: string;
    }> = [];

    // Historical cash bars - show ALL available history
    if (data.cash_history && data.cash_history.length > 0) {
      const sorted = [...data.cash_history].sort((a, b) => a.date.localeCompare(b.date));
      // Show all historical data (no limit)

      sorted.forEach((item) => {
        chartData.push({
          label: formatDate(item.date),
          value: item.cash,
          type: 'historical',
          fullDate: item.date
        });
      });
    }

    // Add the 4 estimate component bars
    // 1. Reported Cash (last balance sheet)
    chartData.push({
      label: 'Reported',
      value: data.historical_cash,
      type: 'reported'
    });

    // 2. Prorated Operating CF (burn since report - negative if burning)
    const proratedValue = data.quarterly_operating_cf < 0
      ? -Math.abs(data.prorated_cf)  // Negative (burning)
      : data.prorated_cf;             // Positive (generating)

    chartData.push({
      label: 'Prorated CF',
      value: proratedValue,
      type: 'burn'
    });

    // 3. Capital Raises
    chartData.push({
      label: 'Cap. Raise',
      value: data.capital_raises?.total || 0,
      type: 'raise'
    });

    // 4. Current Estimate
    chartData.push({
      label: 'Current Est.',
      value: data.estimated_current_cash,
      type: 'estimate'
    });

    return chartData;
  };

  const chartData = buildChartData();

  // Calculate runway display
  const runwayDisplay = () => {
    if (data.runway_months === null || data.runway_months === undefined) {
      if (data.quarterly_operating_cf >= 0) {
        return { text: 'Cash Positive', color: 'text-green-600' };
      }
      return { text: 'N/A', color: 'text-slate-400' };
    }

    const months = data.runway_months;
    let color = 'text-green-600';

    if (months < 3) color = 'text-red-600';
    else if (months < 6) color = 'text-orange-500';
    else if (months < 12) color = 'text-yellow-600';

    return { text: `${months.toFixed(1)} months`, color };
  };

  const runway = runwayDisplay();

  // Risk badge
  const getRiskBadge = (level: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      critical: { bg: 'bg-red-100', text: 'text-red-700', label: 'Critical' },
      high: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'High Risk' },
      medium: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Moderate' },
      moderate: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Moderate' },
      low: { bg: 'bg-green-100', text: 'text-green-700', label: 'Low Risk' },
      healthy: { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Healthy' },
    };
    return badges[level] || badges.low;
  };

  const riskBadge = getRiskBadge(data.runway_risk_level);

  // Get bar color based on type
  const getBarColor = (type: string) => {
    switch (type) {
      case 'historical': return COLORS.historical;
      case 'reported': return COLORS.reported;
      case 'burn': return COLORS.burn;
      case 'raise': return COLORS.raise;
      case 'estimate': return COLORS.estimate;
      default: return COLORS.historical;
    }
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;

    const item = payload[0]?.payload;
    if (!item) return null;

    const typeLabels: Record<string, string> = {
      historical: 'Historical Cash',
      reported: 'Last Reported Cash',
      burn: 'Prorated Operating CF',
      raise: 'Capital Raised',
      estimate: 'Current Estimate'
    };

    return (
      <div className="bg-slate-800 text-white text-xs rounded-lg p-3 shadow-xl">
        <p className="font-semibold mb-1">{typeLabels[item.type] || label}</p>
        {item.fullDate && <p className="text-slate-400 text-[10px] mb-1">{item.fullDate}</p>}
        <p className={item.value < 0 ? 'text-red-300' : 'text-green-300'}>
          {item.value < 0 ? '-' : ''}{formatCashFull(item.value)}
        </p>
      </div>
    );
  };

  return (
    <div className="border border-slate-200 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="text-sm font-medium text-slate-700">
            Cash Position & Runway
          </h4>
          <p className="text-xs text-slate-400 mt-0.5">
            SEC XBRL data • Last report: {formatDate(data.historical_cash_date)} • {data.days_since_report} days ago
          </p>
        </div>

        {/* Runway & Risk */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-xs text-slate-400">Runway:</span>
            <span className={`ml-1 text-sm font-semibold ${runway.color}`}>
              {runway.text}
            </span>
          </div>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${riskBadge.bg} ${riskBadge.text}`}>
            {riskBadge.label}
          </span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-3 text-[10px]">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS.historical }}></div>
          <span className="text-slate-500">Historical</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS.reported }}></div>
          <span className="text-slate-500">Reported</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS.burn }}></div>
          <span className="text-slate-500">Prorated CF</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS.raise }}></div>
          <span className="text-slate-500">Cap. Raise</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: COLORS.estimate }}></div>
          <span className="text-slate-500">Estimate</span>
        </div>
      </div>

      {/* Chart - taller to show more history */}
      <div className="h-64 overflow-x-auto">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 40 }}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: '#94a3b8' }}
              tickLine={false}
              axisLine={{ stroke: '#e2e8f0' }}
              angle={-45}
              textAnchor="end"
              height={50}
            />
            <YAxis
              tick={{ fontSize: 9, fill: '#94a3b8' }}
              tickFormatter={(val) => formatCash(val)}
              tickLine={false}
              axisLine={false}
              width={55}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />

            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={getBarColor(entry.type)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-2 mt-4 text-xs">
        <div className="bg-blue-50 rounded p-2 text-center">
          <p className="text-slate-500 text-[10px]">Reported</p>
          <p className="font-semibold text-blue-700">{formatCash(data.historical_cash)}</p>
        </div>
        <div className={`rounded p-2 text-center ${data.quarterly_operating_cf < 0 ? 'bg-red-50' : 'bg-green-50'}`}>
          <p className="text-slate-500 text-[10px]">Prorated CF</p>
          <p className={`font-semibold ${data.quarterly_operating_cf < 0 ? 'text-red-700' : 'text-green-700'}`}>
            {data.quarterly_operating_cf < 0 ? '-' : '+'}{formatCash(Math.abs(data.prorated_cf))}
          </p>
        </div>
        <div className="bg-green-50 rounded p-2 text-center">
          <p className="text-slate-500 text-[10px]">Cap. Raise</p>
          <p className="font-semibold text-green-700">
            {data.capital_raises?.total ? `+${formatCash(data.capital_raises.total)}` : '-'}
          </p>
        </div>
        <div className="bg-amber-50 rounded p-2 text-center">
          <p className="text-slate-500 text-[10px]">Current Est.</p>
          <p className="font-semibold text-amber-700">{formatCash(data.estimated_current_cash)}</p>
        </div>
      </div>

      {/* Formula */}
      <div className="mt-3 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
        <p>
          <span className="text-slate-600">Current Est.</span> = Reported Cash + Prorated Operating CF + Capital Raises
        </p>
        <p className="mt-0.5">Cash includes cash equivalents, short-term investments, and restricted cash (DilutionTracker methodology)</p>
      </div>

      {/* Capital Raise Details */}
      {data.capital_raises?.details && data.capital_raises.details.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-100">
          <p className="text-xs font-medium text-slate-600 mb-2">Recent Capital Raises</p>
          <div className="space-y-1">
            {data.capital_raises.details.slice(0, 3).map((raise, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs">
                <span className="text-slate-500">{formatDate(raise.filing_date)}</span>
                <span className="text-slate-600 truncate max-w-[120px]">{raise.instrument_type}</span>
                <span className="font-medium text-green-600">+{formatCash(raise.gross_proceeds)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
