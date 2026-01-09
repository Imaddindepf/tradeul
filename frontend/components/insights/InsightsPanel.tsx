'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, FileText, Clock, ChevronRight } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { InsightContent } from './InsightContent';

const FONT_CLASSES: Record<string, string> = {
    'oxygen-mono': 'font-oxygen-mono',
    'ibm-plex-mono': 'font-ibm-plex-mono',
    'jetbrains-mono': 'font-jetbrains-mono',
    'fira-code': 'font-fira-code',
};

// Tipos de insights
export const INSIGHT_TYPES = {
    morning: {
        id: 'morning',
        labelKey: 'insights.types.morning',
        schedule: '07:30 ET',
    },
    midmorning: {
        id: 'midmorning',
        labelKey: 'insights.types.midmorning',
        schedule: '10:30 ET',
    },
    evening: {
        id: 'evening',
        labelKey: 'insights.types.evening',
        schedule: '20:00 ET',
    },
    weekly: {
        id: 'weekly',
        labelKey: 'insights.types.weekly',
        schedule: 'Fri 18:00 ET',
    },
} as const;

export type InsightType = keyof typeof INSIGHT_TYPES;

interface InsightItem {
    id: string;
    type: InsightType;
    date: string;
    date_formatted: string;
    generated_at: string;
    preview?: string;
    title?: string;
    lang?: string;
}

interface InsightsPanelProps {
    initialType?: InsightType;
}

export function InsightsPanel({ initialType }: InsightsPanelProps = {}) {
    const { t, i18n } = useTranslation();
    const font = useUserPreferencesStore(selectFont);
    const language = i18n.language?.startsWith('es') ? 'es' : 'en';
    const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';

    const [insights, setInsights] = useState<InsightItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeFilter, setActiveFilter] = useState<InsightType | 'all'>('all');
    const [selectedInsight, setSelectedInsight] = useState<InsightItem | null>(null);

    // Fetch insights list
    const fetchInsights = useCallback(async () => {
        setLoading(true);
        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            // Por ahora solo tenemos morning news, pero la estructura soporta más
            const response = await fetch(`${apiUrl}/insights/list?lang=${language}`);
            
            if (response.ok) {
                const data = await response.json();
                // API returns array directly, not { insights: [...] }
                setInsights(Array.isArray(data) ? data : data.insights || []);
            } else if (response.status === 404) {
                // Fallback: intentar obtener el morning news actual
                const latestResponse = await fetch(`${apiUrl}/morning-news/latest?lang=${language}`);
                if (latestResponse.ok) {
                    const latest = await latestResponse.json();
                    setInsights([{
                        id: `morning-${latest.date}`,
                        type: 'morning',
                        date: latest.date,
                        date_formatted: latest.date_formatted,
                        generated_at: latest.generated_at,
                        preview: latest.report?.substring(0, 200),
                        lang: latest.lang || language,
                    }]);
                }
            }
        } catch (err) {
            console.error('Error fetching insights:', err);
            // Intentar fallback
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                const latestResponse = await fetch(`${apiUrl}/morning-news/latest?lang=${language}`);
                if (latestResponse.ok) {
                    const latest = await latestResponse.json();
                    setInsights([{
                        id: `morning-${latest.date}`,
                        type: 'morning',
                        date: latest.date,
                        date_formatted: latest.date_formatted,
                        generated_at: latest.generated_at,
                        preview: latest.report?.substring(0, 200),
                        lang: latest.lang || language,
                    }]);
                }
            } catch {
                setInsights([]);
            }
        } finally {
            setLoading(false);
        }
    }, [language]);

    useEffect(() => {
        fetchInsights();
    }, [fetchInsights]);

    // Filter insights
    const filteredInsights = useMemo(() => {
        if (activeFilter === 'all') return insights;
        return insights.filter(i => i.type === activeFilter);
    }, [insights, activeFilter]);

    // Format time
    const formatTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            return d.toLocaleTimeString(language === 'es' ? 'es-ES' : 'en-US', {
                hour: '2-digit',
                minute: '2-digit',
                timeZoneName: 'short'
            });
        } catch {
            return '';
        }
    };

    // Get type label
    const getTypeLabel = (type: InsightType) => {
        const labels: Record<InsightType, { es: string; en: string }> = {
            morning: { es: 'Matutino', en: 'Morning' },
            midmorning: { es: 'Media Manana', en: 'Mid-Morning' },
            evening: { es: 'Nocturno', en: 'Evening' },
            weekly: { es: 'Semanal', en: 'Weekly' },
        };
        return labels[type][language as 'es' | 'en'] || labels[type].en;
    };

    // If viewing an insight
    if (selectedInsight) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                {/* Back header */}
                <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                    <button
                        onClick={() => setSelectedInsight(null)}
                        className="px-2 py-0.5 text-[10px] font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded"
                    >
                        {t('common.back')}
                    </button>
                    <span className="text-slate-300">|</span>
                    <span className="text-[11px] text-slate-600">
                        {getTypeLabel(selectedInsight.type)} - {selectedInsight.date_formatted}
                    </span>
                </div>
                
                {/* Content */}
                <div className="flex-1 overflow-hidden">
                    <InsightContent 
                        insightType={selectedInsight.type}
                        insightDate={selectedInsight.date}
                    />
                </div>
            </div>
        );
    }

    return (
        <div className={`h-full flex flex-col bg-white ${fontClass}`}>
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50">
                <div>
                    <h2 className="text-[13px] font-semibold text-slate-900">
                        INSIGHTS
                    </h2>
                    <p className="text-[10px] text-slate-500">
                        {language === 'es' ? 'Reportes y analisis del mercado' : 'Market reports and analysis'}
                    </p>
                </div>
                <button
                    onClick={fetchInsights}
                    disabled={loading}
                    className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded"
                    title={t('common.refresh')}
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {/* Filter tabs */}
            <div className="flex items-center gap-1 px-3 py-1.5 border-b border-slate-200">
                <button
                    onClick={() => setActiveFilter('all')}
                    className={`px-2 py-0.5 text-[10px] rounded ${
                        activeFilter === 'all'
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-600 hover:bg-slate-100'
                    }`}
                >
                    {language === 'es' ? 'Todos' : 'All'}
                </button>
                {Object.keys(INSIGHT_TYPES).map((type) => (
                    <button
                        key={type}
                        onClick={() => setActiveFilter(type as InsightType)}
                        className={`px-2 py-0.5 text-[10px] rounded ${
                            activeFilter === type
                                ? 'bg-blue-600 text-white'
                                : 'text-slate-600 hover:bg-slate-100'
                        }`}
                    >
                        {getTypeLabel(type as InsightType)}
                    </button>
                ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
                {loading ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                            <RefreshCw className="w-5 h-5 mx-auto mb-2 text-blue-600 animate-spin" />
                            <p className="text-[11px] text-slate-500">
                                {language === 'es' ? 'Cargando...' : 'Loading...'}
                            </p>
                        </div>
                    </div>
                ) : filteredInsights.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                            <FileText className="w-6 h-6 mx-auto mb-2 text-slate-300" />
                            <p className="text-[11px] text-slate-500">
                                {language === 'es' 
                                    ? 'No hay insights disponibles' 
                                    : 'No insights available'}
                            </p>
                            <p className="text-[10px] text-slate-400 mt-1">
                                {language === 'es'
                                    ? 'El Morning News se genera a las 07:30 ET'
                                    : 'Morning News is generated at 07:30 ET'}
                            </p>
                        </div>
                    </div>
                ) : (
                    <table className="w-full text-[11px]">
                        <thead className="sticky top-0 bg-slate-100 border-b border-slate-200">
                            <tr>
                                <th className="px-3 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">
                                    {language === 'es' ? 'Tipo' : 'Type'}
                                </th>
                                <th className="px-3 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">
                                    {language === 'es' ? 'Fecha' : 'Date'}
                                </th>
                                <th className="px-3 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider">
                                    {language === 'es' ? 'Generado' : 'Generated'}
                                </th>
                                <th className="px-3 py-1.5 w-8"></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {filteredInsights.map((insight) => (
                                <tr
                                    key={insight.id}
                                    onClick={() => setSelectedInsight(insight)}
                                    className="hover:bg-blue-50 cursor-pointer"
                                >
                                    <td className="px-3 py-2">
                                        <span className="inline-block px-1.5 py-0.5 text-[10px] bg-blue-50 text-blue-700 border border-blue-200 rounded">
                                            {getTypeLabel(insight.type)}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2 text-slate-700">
                                        {insight.date_formatted}
                                    </td>
                                    <td className="px-3 py-2 text-right text-slate-500">
                                        <div className="flex items-center justify-end gap-1">
                                            <Clock className="w-3 h-3" />
                                            {formatTime(insight.generated_at)}
                                        </div>
                                    </td>
                                    <td className="px-3 py-2">
                                        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-3 py-1 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-400">
                <span>{filteredInsights.length} {language === 'es' ? 'reportes' : 'reports'}</span>
                <span>Insights</span>
            </div>
        </div>
    );
}

