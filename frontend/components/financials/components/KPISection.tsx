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
        <div className="p-2 border-b border-border-subtle bg-surface-hover">
            <div className="text-[9px] font-medium text-muted-fg mb-1.5">
                Key Metrics — {industryProfile.description}
            </div>
            <div className="grid grid-cols-5 gap-1.5">
                {calculatedKPIs.map((kpi, idx) => {
                    const isGood = kpi.value !== undefined && kpi.benchmark && kpi.value >= kpi.benchmark.good;
                    const isBad = kpi.value !== undefined && kpi.benchmark && kpi.value <= kpi.benchmark.bad;
                    return (
                        <div
                            key={idx}
                            className="bg-surface rounded p-1.5 border border-border-subtle hover:border-border transition-colors cursor-help"
                            title={`${kpi.formula}\n\n${kpi.tooltip}`}
                        >
                            <div className="text-[8px] text-muted-fg truncate">{kpi.name}</div>
                            <div className={`text-xs font-semibold ${
                                isGood ? 'text-green-600' : isBad ? 'text-red-600' : 'text-foreground'
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

