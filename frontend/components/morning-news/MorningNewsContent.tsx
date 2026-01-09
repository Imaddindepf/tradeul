'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Calendar, Clock, AlertTriangle } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

const FONT_CLASSES: Record<string, string> = {
    'oxygen-mono': 'font-oxygen-mono',
    'ibm-plex-mono': 'font-ibm-plex-mono',
    'jetbrains-mono': 'font-jetbrains-mono',
    'fira-code': 'font-fira-code',
};

// Secciones del reporte (en orden) - SOLO estos títulos van en azul
const SECTION_HEADERS = [
    'TOP NEWS',
    'BEFORE THE BELL',
    'SMALL CAPS MOVERS',
    'STOCKS TO WATCH',
    'ANALYSIS',
    "ANALYSTS' RECOMMENDATIONS",
    'ECONOMIC EVENTS',
    'COMPANIES REPORTING RESULTS',
    'EX-DIVIDENDS',
];

interface MorningNewsData {
    success: boolean;
    date: string;
    date_formatted: string;
    report: string;
    generated_at: string;
    generation_time_seconds?: number;
}

interface MorningNewsContentProps {
    initialData?: MorningNewsData | null;
}

export function MorningNewsContent({ initialData }: MorningNewsContentProps = {}) {
    const { t } = useTranslation();
    const font = useUserPreferencesStore(selectFont);
    const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';

    const [newsData, setNewsData] = useState<MorningNewsData | null>(initialData || null);
    const [loading, setLoading] = useState(!initialData);
    const [error, setError] = useState<string | null>(null);

    // Detectar idioma del usuario
    const { i18n } = useTranslation();
    const userLang = i18n.language?.startsWith('es') ? 'es' : 'en';

    const fetchMorningNews = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(`${apiUrl}/morning-news/latest?lang=${userLang}`);

            if (response.status === 404) {
                const msg = userLang === 'es'
                    ? 'No hay Morning News disponible. Se genera a las 7:30 AM ET.'
                    : 'No Morning News available. Generated at 7:30 AM ET.';
                setError(msg);
                setNewsData(null);
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data: MorningNewsData = await response.json();
            setNewsData(data);
        } catch (err) {
            console.error('Error fetching morning news:', err);
            setError(err instanceof Error ? err.message : 'Error loading morning news');
        } finally {
            setLoading(false);
        }
    }, [userLang]);

    useEffect(() => {
        if (!initialData) {
            fetchMorningNews();
        }
    }, [fetchMorningNews, initialData]);

    const formatGeneratedTime = (isoString: string) => {
        try {
            const d = new Date(isoString);
            return {
                date: d.toLocaleDateString('es-ES', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                }),
                time: d.toLocaleTimeString('es-ES', {
                    hour: '2-digit',
                    minute: '2-digit',
                    timeZoneName: 'short'
                })
            };
        } catch {
            return { date: '', time: '' };
        }
    };

    // Función para resaltar tickers inline en el texto
    const highlightTickers = (text: string, keyPrefix: string): JSX.Element[] => {
        // Regex para detectar tickers: (AAPL), (NVDA), etc. o TICKER al inicio seguido de espacio
        const tickerRegex = /\(([A-Z]{1,5})\)|(?:^|\s)([A-Z]{2,5})(?=\s+\()|(?<=\()([A-Z]{1,5})(?:\/[A-Z]{1,5})?(?=\))/g;

        const parts: JSX.Element[] = [];
        let lastIndex = 0;
        let match;
        let partIndex = 0;

        while ((match = tickerRegex.exec(text)) !== null) {
            // Texto antes del ticker
            if (match.index > lastIndex) {
                parts.push(
                    <span key={`${keyPrefix}-${partIndex++}`}>
                        {text.slice(lastIndex, match.index)}
                    </span>
                );
            }

            // El ticker con estilo
            const ticker = match[1] || match[2] || match[3];
            if (match[1]) {
                // Ticker entre paréntesis: (AAPL)
                parts.push(
                    <span key={`${keyPrefix}-${partIndex++}`} className="font-semibold text-blue-700">
                        ({ticker})
                    </span>
                );
            } else if (match[2]) {
                // Ticker al inicio: "AAPL ("
                parts.push(
                    <span key={`${keyPrefix}-${partIndex++}`}>
                        {text.slice(lastIndex, match.index)}
                    </span>
                );
                parts.push(
                    <span key={`${keyPrefix}-${partIndex++}`} className="font-bold text-slate-900">
                        {ticker}
                    </span>
                );
            }

            lastIndex = match.index + match[0].length;
        }

        // Resto del texto
        if (lastIndex < text.length) {
            parts.push(
                <span key={`${keyPrefix}-${partIndex++}`}>
                    {text.slice(lastIndex)}
                </span>
            );
        }

        return parts.length > 0 ? parts : [<span key={`${keyPrefix}-0`}>{text}</span>];
    };

    // Función simplificada para resaltar tickers entre paréntesis
    const renderWithTickers = (text: string, keyPrefix: string): JSX.Element => {
        // Resaltar (TICKER) patterns
        const parts = text.split(/(\([A-Z]{1,5}(?:\/[A-Z]{1,5})?\))/g);

        return (
            <>
                {parts.map((part, i) => {
                    if (part.match(/^\([A-Z]{1,5}(?:\/[A-Z]{1,5})?\)$/)) {
                        return (
                            <span key={`${keyPrefix}-${i}`} className="font-semibold text-blue-700">
                                {part}
                            </span>
                        );
                    }
                    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
                })}
            </>
        );
    };

    // Parsear y renderizar el reporte con estilos
    const renderedReport = useMemo(() => {
        if (!newsData?.report) return null;

        const lines = newsData.report.split('\n');
        const elements: JSX.Element[] = [];

        lines.forEach((line, index) => {
            const trimmedLine = line.trim();

            // Header principal (linea de ====)
            if (trimmedLine.match(/^={10,}$/)) {
                elements.push(
                    <div key={index} className="text-blue-600 text-center select-none">
                        {'═'.repeat(60)}
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

            // Subtitulo MORNING NEWS CALL
            if (trimmedLine === 'MORNING NEWS CALL') {
                elements.push(
                    <div key={index} className="text-blue-600 font-bold text-center text-[12px] mb-2">
                        MORNING NEWS CALL
                    </div>
                );
                return;
            }

            // USA EDITION
            if (trimmedLine === 'USA EDITION') {
                elements.push(
                    <div key={index} className="text-slate-500 text-center text-[10px] mt-3">
                        USA EDITION
                    </div>
                );
                return;
            }

            // Fecha (dias de la semana en español o inglés)
            if (trimmedLine.match(/^(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),/i)) {
                elements.push(
                    <div key={index} className="text-slate-700 text-center text-[13px] font-medium mb-4">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Encabezados de seccion (en azul y bold)
            const isSection = SECTION_HEADERS.some(header =>
                trimmedLine.startsWith(header) || trimmedLine === header
            );

            if (isSection && trimmedLine.length < 60) {
                elements.push(
                    <div key={index} className="text-blue-600 font-bold text-[12px] mt-6 mb-2 border-b border-blue-100 pb-1">
                        {trimmedLine}
                    </div>
                );
                return;
            }

            // Lineas que empiezan con "Company Name (TICKER):" - formato STOCKS TO WATCH
            const stockMatch = trimmedLine.match(/^([A-Za-z][A-Za-z0-9\s&.,'-]+)\s+\(([A-Z]{1,5}(?:\/[A-Z]{1,5})?)\):/);
            if (stockMatch) {
                const [, companyName, ticker] = stockMatch;
                const restOfLine = trimmedLine.slice(stockMatch[0].length);
                elements.push(
                    <div key={index} className="text-slate-700 text-[13px] mb-3 leading-relaxed">
                        <span className="font-bold text-slate-900">{companyName}</span>
                        <span className="font-semibold text-blue-700"> ({ticker})</span>
                        <span className="text-slate-600">:{renderWithTickers(restOfLine, `line-${index}`)}</span>
                    </div>
                );
                return;
            }

            // Lineas de ticker simple al inicio (TICKER:) - para small caps y analysts
            // Este es un fallback por si el stockMatch anterior no captura (nombres muy cortos como "RTX")
            if (trimmedLine.match(/^[A-Z][A-Za-z0-9\s&.,'-]+\s+\([A-Z]{1,5}\):/)) {
                const parts = trimmedLine.split(/(\([A-Z]{1,5}\))/);
                elements.push(
                    <div key={index} className="text-slate-700 text-[13px] mb-3 leading-relaxed">
                        <span className="font-bold text-slate-900">{parts[0].trim()}</span>
                        <span className="font-semibold text-blue-700"> {parts[1]}</span>
                        <span className="text-slate-600">{renderWithTickers(parts.slice(2).join(''), `fallback-${index}`)}</span>
                    </div>
                );
                return;
            }

            // Lineas de horario de eventos (empiezan con hora) - hora en negrita
            if (trimmedLine.match(/^\d{1,2}:\d{2}\s*(AM|PM)?/i)) {
                const timeMatch = trimmedLine.match(/^(\d{1,2}:\d{2}\s*(?:AM|PM)?)/i);
                const time = timeMatch ? timeMatch[1] : trimmedLine.substring(0, 5);
                const rest = trimmedLine.slice(time.length);
                elements.push(
                    <div key={index} className="text-slate-700 text-[13px] pl-4 py-0.5">
                        <span className="font-bold text-slate-900">{time}</span>
                        <span className="text-slate-600">{renderWithTickers(rest, `time-${index}`)}</span>
                    </div>
                );
                return;
            }

            // Lineas vacias
            if (!trimmedLine) {
                elements.push(<div key={index} className="h-2" />);
                return;
            }

            // Texto normal con tickers resaltados
            elements.push(
                <div key={index} className="text-slate-700 text-[13px] leading-relaxed">
                    {renderWithTickers(line, `text-${index}`)}
                </div>
            );
        });

        return elements;
    }, [newsData?.report]);

    // Loading state
    if (loading) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <RefreshCw className="w-6 h-6 mx-auto mb-3 text-blue-600 animate-spin" />
                        <p className="text-[13px] text-slate-500">Cargando Morning News...</p>
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
                        <AlertTriangle className="w-6 h-6 mx-auto mb-3 text-amber-500" />
                        <p className="text-[13px] text-slate-600 mb-3">{error}</p>
                        <button
                            onClick={fetchMorningNews}
                            className="px-3 py-1.5 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                            Reintentar
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // No data state
    if (!newsData) {
        return (
            <div className={`h-full flex flex-col bg-white ${fontClass}`}>
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                        <Calendar className="w-6 h-6 mx-auto mb-3 text-slate-300" />
                        <p className="text-[13px] text-slate-500">No hay Morning News disponible</p>
                        <p className="text-[10px] text-slate-400 mt-1">Se genera a las 7:30 AM ET</p>
                    </div>
                </div>
            </div>
        );
    }

    const { time: generatedTime } = formatGeneratedTime(newsData.generated_at);

    return (
        <div className={`h-full flex flex-col bg-white ${fontClass}`}>
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200 bg-gradient-to-r from-blue-50 to-white">
                <div className="flex items-center gap-3">
                    <div>
                        <h2 className="text-[12px] font-semibold text-blue-600">
                            Morning News Call
                        </h2>
                        <p className="text-[10px] text-slate-500">
                            {newsData.date_formatted}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="text-[9px] text-slate-400 text-right">
                        <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span>{generatedTime}</span>
                        </div>
                    </div>
                    <button
                        onClick={fetchMorningNews}
                        disabled={loading}
                        className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                        title="Actualizar"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto bg-white">
                <div className="px-6 py-4 max-w-3xl mx-auto">
                    {renderedReport}
                </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-center px-4 py-1.5 border-t border-slate-200 bg-gradient-to-r from-white to-blue-50 text-[9px] text-slate-400">
                <span>USA Edition</span>
            </div>
        </div>
    );
}
