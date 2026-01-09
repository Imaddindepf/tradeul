'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Calendar, Clock, AlertTriangle } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import type { InsightType } from './InsightsPanel';

const FONT_CLASSES: Record<string, string> = {
    'oxygen-mono': 'font-oxygen-mono',
    'ibm-plex-mono': 'font-ibm-plex-mono',
    'jetbrains-mono': 'font-jetbrains-mono',
    'fira-code': 'font-fira-code',
};

// Secciones del reporte - titulos en azul
const SECTION_HEADERS = [
    // Morning News
    'TOP NEWS',
    'BEFORE THE BELL',
    'SMALL CAPS MOVERS',
    'STOCKS TO WATCH',
    'ANALYSIS',
    "ANALYSTS' RECOMMENDATIONS",
    'ECONOMIC EVENTS',
    'COMPANIES REPORTING RESULTS',
    'EX-DIVIDENDS',
    // Mid-Morning Update (English)
    'MARKET SNAPSHOT',
    'TOP SYNTHETIC SECTORS',
    'TOP GAINERS',
    'TOP LOSERS',
    'UNUSUAL VOLUME',
    'MARKET NARRATIVE',
    'ECONOMIC DATA RESULTS',
    'EARNINGS RESULTS',
    'BIG CAPS MOVERS',
    // Mid-Morning Update (Spanish)
    'RESUMEN DEL MERCADO',
    'SECTORES SINTÉTICOS PRINCIPALES',
    'MEJORES SECTORES',
    'MAYORES ALZAS',
    'MAYORES BAJAS',
    'PANORAMA DEL MERCADO',
    'VOLUMEN INUSUAL',
    'NARRATIVA DEL MERCADO',
    'RESULTADOS DE LOS DATOS ECONÓMICOS',
    'RESULTADOS DE DATOS ECONÓMICOS',
    'RESULTADOS DE GANANCIAS',
    'GRANDES CAPITALIZACIONES EN MOVIMIENTO',
    // Evening / Weekly
    'MARKET SUMMARY',
    'WEEKLY HIGHLIGHTS',
    'SECTOR PERFORMANCE',
    'UPCOMING EVENTS',
];

interface InsightData {
    success: boolean;
    date: string;
    date_formatted: string;
    report: string;
    generated_at: string;
    generation_time_seconds?: number;
    lang?: string;
}

interface InsightContentProps {
    insightType?: InsightType;
    insightDate?: string;
    initialData?: InsightData | null;
}

export function InsightContent({ insightType = 'morning', insightDate, initialData }: InsightContentProps) {
    const { t, i18n } = useTranslation();
    const font = useUserPreferencesStore(selectFont);
    const language = i18n.language?.startsWith('es') ? 'es' : 'en';
    const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';

    const [data, setData] = useState<InsightData | null>(initialData || null);
    const [loading, setLoading] = useState(!initialData);
    const [error, setError] = useState<string | null>(null);

    const fetchInsight = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            
            // API unificada de insights
            let url = '';
            if (insightDate) {
                // Fecha específica
                url = `${apiUrl}/insights/date/${insightDate}?type=${insightType}&lang=${language}`;
            } else {
                // Último disponible
                url = `${apiUrl}/insights/latest?type=${insightType}&lang=${language}`;
            }

            const response = await fetch(url);

            if (response.status === 404) {
                const msg = language === 'es'
                    ? 'Este insight no esta disponible'
                    : 'This insight is not available';
                setError(msg);
                setData(null);
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result: InsightData = await response.json();
            setData(result);
        } catch (err) {
            console.error('Error fetching insight:', err);
            setError(err instanceof Error ? err.message : 'Error loading insight');
        } finally {
            setLoading(false);
        }
    }, [insightType, insightDate, language]);

    useEffect(() => {
        if (!initialData) {
            fetchInsight();
        }
    }, [fetchInsight, initialData]);

    const formatGeneratedTime = (isoString: string) => {
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

    // Tipo de insight en texto
    const insightTypeLabel = useMemo(() => {
        const labels: Record<InsightType, { es: string; en: string }> = {
            morning: { es: 'Morning News Call', en: 'Morning News Call' },
            midmorning: { es: 'Mid-Morning Update', en: 'Mid-Morning Update' },
            evening: { es: 'Evening Wrap', en: 'Evening Wrap' },
            weekly: { es: 'Weekly Recap', en: 'Weekly Recap' },
        };
        return labels[insightType]?.[language as 'es' | 'en'] || labels[insightType]?.en || insightType;
    }, [insightType, language]);

    // Función para formatear texto con bold y colores
    const formatText = (text: string, key: string) => {
        // Parsear **bold** y colorear porcentajes
        const parts: JSX.Element[] = [];
        let remaining = text;
        let partIndex = 0;

        // Regex para **bold**, porcentajes positivos y negativos (soporta coma y punto decimal)
        const regex = /(\*\*[^*]+\*\*)|([+-]?\d+[.,]?\d*%)/g;
        let lastIndex = 0;
        let match;

        while ((match = regex.exec(remaining)) !== null) {
            // Texto antes del match
            if (match.index > lastIndex) {
                parts.push(<span key={`${key}-${partIndex++}`}>{remaining.slice(lastIndex, match.index)}</span>);
            }

            const matched = match[0];
            if (matched.startsWith('**') && matched.endsWith('**')) {
                // Bold text
                parts.push(
                    <span key={`${key}-${partIndex++}`} className="font-semibold text-slate-900">
                        {matched.slice(2, -2)}
                    </span>
                );
            } else if (matched.includes('%')) {
                // Porcentaje - verde si positivo, rojo si negativo
                const value = parseFloat(matched);
                const colorClass = value > 0 ? 'text-emerald-600 font-medium' : value < 0 ? 'text-red-600 font-medium' : 'text-slate-700';
                parts.push(
                    <span key={`${key}-${partIndex++}`} className={colorClass}>
                        {matched}
                    </span>
                );
            }

            lastIndex = match.index + matched.length;
        }

        // Texto restante
        if (lastIndex < remaining.length) {
            parts.push(<span key={`${key}-${partIndex++}`}>{remaining.slice(lastIndex)}</span>);
        }

        return parts.length > 0 ? parts : text;
    };

    // Parsear y renderizar el reporte
    const renderedReport = useMemo(() => {
        if (!data?.report) return null;

        const lines = data.report.split('\n');
        const elements: JSX.Element[] = [];

        lines.forEach((line, index) => {
            const trimmedLine = line.trim();

            // Header principal (linea de ====)
            if (trimmedLine.match(/^={10,}$/)) {
                elements.push(
                    <div key={index} className="text-blue-600 text-center select-none text-[11px]">
                        {'═'.repeat(50)}
                    </div>
                );
                return;
            }

            // Titulo TRADEUL.COM
            if (trimmedLine === 'TRADEUL.COM') {
                elements.push(
                    <div key={index} className="text-blue-600 font-bold text-center text-[14px] mt-2">
                        TRADEUL.COM
                    </div>
                );
                return;
            }

            // Subtitulo del tipo de insight
            if (trimmedLine === 'MORNING NEWS CALL' || 
                trimmedLine === 'MID-MORNING UPDATE' ||
                trimmedLine === 'ACTUALIZACIÓN DE MEDIODÍA' ||
                trimmedLine === 'ACTUALIZACIÓN DE MEDIA MAÑANA' ||
                trimmedLine === 'EVENING WRAP' ||
                trimmedLine === 'WEEKLY RECAP') {
                elements.push(
                    <div key={index} className="text-blue-600 font-bold text-center text-[12px] mb-2">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // USA EDITION / EDICIÓN USA
            if (trimmedLine === 'USA EDITION' || trimmedLine === 'EDICIÓN USA') {
                elements.push(
                    <div key={index} className="text-slate-500 text-center text-[10px] mt-3">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Fecha (dias de la semana)
            if (trimmedLine.match(/^(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),/i)) {
                elements.push(
                    <div key={index} className="text-slate-700 text-center text-[12px] font-medium mb-4">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Encabezados de seccion (en azul y bold)
            const isSection = SECTION_HEADERS.some(header =>
                trimmedLine.toUpperCase().startsWith(header) || trimmedLine.toUpperCase() === header
            );

            if (isSection && trimmedLine.length < 60) {
                elements.push(
                    <div key={index} className="text-blue-600 font-bold text-[11px] mt-5 mb-2 border-b border-blue-100 pb-1">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Lineas de ticker (TICKER +XX%) - ticker en negrita, % coloreado
            if (trimmedLine.match(/^[A-Z]{1,5}\s+[+-]?\d/)) {
                // Formato: TICKER +XX.XX% ($price) o TICKER +XX.XX%
                const tickerMatch = trimmedLine.match(/^([A-Z]{1,5})\s+(.*)$/);
                if (tickerMatch) {
                    elements.push(
                        <div key={index} className="text-slate-700 text-[12px] pl-3 py-0.5">
                            <span className="font-bold text-slate-900">{tickerMatch[1]}</span>
                            <span className="text-slate-600"> {formatText(tickerMatch[2], `ticker-${index}`)}</span>
                        </div>
                    );
                    return;
                }
            }

            // Lineas de ticker con paréntesis (TICKER) - ticker en negrita
            if (trimmedLine.match(/^[A-Z]{1,5}\s*\(/)) {
                const ticker = trimmedLine.split('(')[0].trim();
                const rest = trimmedLine.split('(').slice(1).join('(');
                elements.push(
                    <div key={index} className="text-slate-700 text-[12px] pl-3 py-0.5">
                        <span className="font-bold text-slate-900">{ticker}</span>
                        <span className="text-slate-600"> ({formatText(rest, `ticker-p-${index}`)}</span>
                    </div>
                );
                return;
            }

            // Lineas numeradas (1. 2. 3.)
            if (trimmedLine.match(/^\d+\.\s/)) {
                elements.push(
                    <div key={index} className="text-slate-700 text-[12px] pl-3 py-0.5">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Lineas de horario de eventos (hora)
            if (trimmedLine.match(/^\d{2}:\d{2}\s/)) {
                elements.push(
                    <div key={index} className="text-slate-700 text-[12px] pl-3 py-0.5">
                        <span className="font-bold text-slate-900">{trimmedLine.substring(0, 5)}</span>
                        <span className="text-slate-600">{trimmedLine.substring(5)}</span>
                    </div>
                );
                return;
            }

            // Lineas vacias
            if (!trimmedLine) {
                elements.push(<div key={index} className="h-1.5" />);
                return;
            }

            // Texto normal - con bold y colores
            elements.push(
                <div key={index} className="text-slate-700 text-[12px] leading-relaxed">
                    {formatText(line, `line-${index}`)}
                </div>
            );
        });

        return elements;
    }, [data?.report]);

    // Loading state
    if (loading) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <RefreshCw className="w-5 h-5 mx-auto mb-2 text-blue-600 animate-spin" />
                        <p className="text-[11px] text-slate-500">
                            {language === 'es' ? 'Cargando...' : 'Loading...'}
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    // Error state
    if (error) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center max-w-md px-4">
                        <AlertTriangle className="w-5 h-5 mx-auto mb-2 text-amber-500" />
                        <p className="text-[11px] text-slate-600 mb-3">{error}</p>
                        <button
                            onClick={fetchInsight}
                            className="px-3 py-1 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                            {language === 'es' ? 'Reintentar' : 'Retry'}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // No data state
    if (!data) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <Calendar className="w-5 h-5 mx-auto mb-2 text-slate-300" />
                        <p className="text-[11px] text-slate-500">
                            {language === 'es' ? 'No disponible' : 'Not available'}
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className={`h-full flex flex-col bg-white ${fontClass}`}>
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 bg-slate-50">
                <div>
                    <h2 className="text-[11px] font-semibold text-blue-600">
                        {insightTypeLabel}
                    </h2>
                    <p className="text-[9px] text-slate-500">
                        {data.date_formatted}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="text-[9px] text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatGeneratedTime(data.generated_at)}</span>
                    </div>
                    <button
                        onClick={fetchInsight}
                        disabled={loading}
                        className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                    >
                        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
                <div className="px-4 py-3 max-w-2xl mx-auto">
                    {renderedReport}
                </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-center px-3 py-1 border-t border-slate-200 bg-slate-50 text-[9px] text-slate-400">
                <span>Insights</span>
            </div>
        </div>
    );
}

