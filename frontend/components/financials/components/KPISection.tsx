'use client';

import type { IndustryProfile, FinancialData } from '../types';
import { formatKPIValue } from '../utils/formatters';

interface KPISectionProps {
    industryProfile: IndustryProfile;
    data: FinancialData;
}

export function KPISection({ industryProfile, data }: KPISectionProps) {
    const calculatedKPIs = industryProfile.kpis.map(kpi => ({
        ...kpi,
        value: kpi.calculate(data),
    }));

    return (
        <div className="p-2 border-b border-slate-100 bg-slate-50">
            <div className="text-[9px] font-medium text-slate-500 mb-1.5">
                Key Metrics — {industryProfile.description}
            </div>
            <div className="grid grid-cols-5 gap-1.5">
                {calculatedKPIs.map((kpi, idx) => {
                    const isGood = kpi.value !== undefined && kpi.benchmark && kpi.value >= kpi.benchmark.good;
                    const isBad = kpi.value !== undefined && kpi.benchmark && kpi.value <= kpi.benchmark.bad;
                    return (
                        <div
                            key={idx}
                            className="bg-white rounded p-1.5 border border-slate-100 hover:border-slate-300 transition-colors cursor-help"
                            title={`${kpi.formula}\n\n${kpi.tooltip}`}
                        >
                            <div className="text-[8px] text-slate-400 truncate">{kpi.name}</div>
                            <div className={`text-xs font-semibold ${
                                isGood ? 'text-green-600' : isBad ? 'text-red-600' : 'text-slate-700'
                            }`}>
                                {formatKPIValue(kpi.value, kpi.format)}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

