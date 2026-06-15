import {
    TrendingUp, BarChart3, ListChecks,
    Newspaper, Users, Calendar, ShieldAlert, Info, Gauge, Target, FlaskConical, Table2,
} from 'lucide-react';
import type { WidgetDefinition, CanvasLayout, CanvasTemplate, CanvasConfig, WidgetContext } from '../types';
import {
    ConsensusWidget,
    ShortInterestWidget,
    TechnicalWidget,
    RatingsWidget,
    NewsWidget,
    InsiderWidget,
    CatalystsWidget,
    RiskWidget,
    AboutWidget,
    QuoteStripWidget,
    ChartWidget,
    DilutionRiskWidget,
    KeyMetricsWidget,
} from './widgets';

export const FAN_WIDGETS: WidgetDefinition[] = [
    {
        type: 'quote-strip',
        category: 'overview',
        title: 'Header',
        description: 'Ticker, company, exchange, sector',
        icon: Info,
        component: QuoteStripWidget,
        defaultSize: { w: 12, h: 2 },
        minSize: { w: 6, h: 1 },
        locked: true,
        hiddenFromPalette: true,
    },
    {
        type: 'consensus',
        category: 'intel',
        title: 'Consensus',
        description: 'Analyst consensus + price target',
        icon: Target,
        component: ConsensusWidget,
        defaultSize: { w: 3, h: 4 },
        minSize: { w: 2, h: 3 },
    },
    {
        type: 'short-interest',
        category: 'market',
        title: 'Short Interest',
        description: '% float, DTC, squeeze risk',
        icon: Gauge,
        component: ShortInterestWidget,
        defaultSize: { w: 3, h: 4 },
        minSize: { w: 2, h: 3 },
    },
    {
        type: 'technical',
        category: 'technical',
        title: 'Technical',
        description: 'RSI, MAs, support/resistance',
        icon: TrendingUp,
        component: TechnicalWidget,
        defaultSize: { w: 3, h: 5 },
        minSize: { w: 2, h: 3 },
    },
    {
        type: 'ratings',
        category: 'intel',
        title: 'Analyst Ratings',
        description: 'Firm-by-firm ratings table',
        icon: ListChecks,
        component: RatingsWidget,
        defaultSize: { w: 6, h: 5 },
        minSize: { w: 4, h: 3 },
    },
    {
        type: 'news',
        category: 'intel',
        title: 'News',
        description: 'Sentiment + recent headlines',
        icon: Newspaper,
        component: NewsWidget,
        defaultSize: { w: 4, h: 4 },
        minSize: { w: 3, h: 3 },
    },
    {
        type: 'insider',
        category: 'intel',
        title: 'Insider Activity',
        description: 'Recent insider buys/sells',
        icon: Users,
        component: InsiderWidget,
        defaultSize: { w: 3, h: 5 },
        minSize: { w: 2, h: 3 },
    },
    {
        type: 'catalysts',
        category: 'market',
        title: 'Catalysts',
        description: 'Earnings date + upcoming events',
        icon: Calendar,
        component: CatalystsWidget,
        defaultSize: { w: 3, h: 4 },
        minSize: { w: 2, h: 3 },
    },
    {
        type: 'risk',
        category: 'risk',
        title: 'Risk Factors',
        description: 'Risk score + factor list',
        icon: ShieldAlert,
        component: RiskWidget,
        defaultSize: { w: 4, h: 5 },
        minSize: { w: 3, h: 3 },
    },
    {
        type: 'about',
        category: 'overview',
        title: 'About',
        description: 'Business summary',
        icon: Info,
        component: AboutWidget,
        defaultSize: { w: 6, h: 3 },
        minSize: { w: 3, h: 2 },
    },
    {
        type: 'chart',
        category: 'market',
        title: 'Price Chart',
        description: 'Candlestick chart with indicators',
        icon: BarChart3,
        component: ChartWidget,
        defaultSize: { w: 6, h: 7 },
        minSize: { w: 4, h: 5 },
        customHeader: true,
    },
    {
        type: 'dilution-risk',
        category: 'risk',
        title: 'Dilution Risk',
        description: 'Offering, overhead, cash need ratings',
        icon: FlaskConical,
        component: DilutionRiskWidget,
        defaultSize: { w: 3, h: 5 },
        minSize: { w: 2, h: 4 },
    },
    {
        type: 'key-metrics',
        category: 'fundamentals',
        title: 'Key Metrics',
        description: 'TIKR-style: capital structure, efficiency, growth, valuation',
        icon: Table2,
        component: KeyMetricsWidget,
        defaultSize: { w: 12, h: 11 },
        minSize: { w: 6, h: 7 },
    },
];

// ── Overview (default) ───────────────────────────────────────────────────
// Vista compacta de alto valor: cotización, chart con consenso/técnico al
// lado, panel Key Metrics (3 columnas, adaptativo) y descripción. Sin scroll
// largo: prioriza señal sobre cantidad.
export const FAN_DEFAULT_LAYOUT: CanvasLayout = {
    version: 1,
    items: [
        { i: 'quote-strip-0', type: 'quote-strip', x: 0, y: 0, w: 12, h: 2 },
        { i: 'chart-0', type: 'chart', x: 0, y: 2, w: 7, h: 7 },
        { i: 'consensus-0', type: 'consensus', x: 7, y: 2, w: 5, h: 3 },
        { i: 'technical-0', type: 'technical', x: 7, y: 5, w: 5, h: 4 },
        { i: 'key-metrics-0', type: 'key-metrics', x: 0, y: 9, w: 12, h: 14 },
        { i: 'about-0', type: 'about', x: 0, y: 23, w: 12, h: 3 },
    ],
};

// ── Trading (day trader) ─────────────────────────────────────────────────
// Acción de precio + técnico + flujo: chart grande, técnico, short interest,
// noticias, catalizadores e insiders. Todo en una sola pantalla.
const DAYTRADER_LAYOUT: CanvasLayout = {
    version: 1,
    items: [
        { i: 'quote-strip-dt', type: 'quote-strip', x: 0, y: 0, w: 12, h: 2 },
        { i: 'chart-dt', type: 'chart', x: 0, y: 2, w: 8, h: 8 },
        { i: 'technical-dt', type: 'technical', x: 8, y: 2, w: 4, h: 5 },
        { i: 'short-interest-dt', type: 'short-interest', x: 8, y: 7, w: 4, h: 3 },
        { i: 'news-dt', type: 'news', x: 0, y: 10, w: 4, h: 5 },
        { i: 'catalysts-dt', type: 'catalysts', x: 4, y: 10, w: 4, h: 5 },
        { i: 'insider-dt', type: 'insider', x: 8, y: 10, w: 4, h: 5 },
    ],
};

// ── Fundamentals (value) ─────────────────────────────────────────────────
// Key Metrics como protagonista (full width, alto), seguido de contexto:
// negocio, consenso, dilución, ratings y riesgo.
const VALUE_LAYOUT: CanvasLayout = {
    version: 1,
    items: [
        { i: 'quote-strip-v', type: 'quote-strip', x: 0, y: 0, w: 12, h: 2 },
        { i: 'key-metrics-v', type: 'key-metrics', x: 0, y: 2, w: 12, h: 16 },
        { i: 'about-v', type: 'about', x: 0, y: 18, w: 6, h: 4 },
        { i: 'consensus-v', type: 'consensus', x: 6, y: 18, w: 3, h: 4 },
        { i: 'dilution-risk-v', type: 'dilution-risk', x: 9, y: 18, w: 3, h: 5 },
        { i: 'ratings-v', type: 'ratings', x: 0, y: 22, w: 6, h: 5 },
        { i: 'risk-v', type: 'risk', x: 6, y: 23, w: 6, h: 5 },
    ],
};

// ── Earnings ──────────────────────────────────────────────────────────────
// Foco en el evento: consenso/catalizadores/SI arriba, chart + ratings,
// crecimiento/valoración (key metrics) y noticias.
const EARNINGS_LAYOUT: CanvasLayout = {
    version: 1,
    items: [
        { i: 'quote-strip-e', type: 'quote-strip', x: 0, y: 0, w: 12, h: 2 },
        { i: 'consensus-e', type: 'consensus', x: 0, y: 2, w: 4, h: 4 },
        { i: 'catalysts-e', type: 'catalysts', x: 4, y: 2, w: 4, h: 4 },
        { i: 'short-interest-e', type: 'short-interest', x: 8, y: 2, w: 4, h: 4 },
        { i: 'chart-e', type: 'chart', x: 0, y: 6, w: 7, h: 7 },
        { i: 'ratings-e', type: 'ratings', x: 7, y: 6, w: 5, h: 7 },
        { i: 'key-metrics-e', type: 'key-metrics', x: 0, y: 13, w: 12, h: 12 },
        { i: 'news-e', type: 'news', x: 0, y: 25, w: 12, h: 5 },
    ],
};

// ── Research (deep dive) ────────────────────────────────────────────────
// La vista completa: todos los paneles, bien empaquetados en filas de ancho
// completo. Para análisis exhaustivo en una ventana grande.
const RESEARCH_LAYOUT: CanvasLayout = {
    version: 1,
    items: [
        { i: 'quote-strip-r', type: 'quote-strip', x: 0, y: 0, w: 12, h: 2 },
        { i: 'about-r', type: 'about', x: 0, y: 2, w: 12, h: 3 },
        { i: 'chart-r', type: 'chart', x: 0, y: 5, w: 7, h: 7 },
        { i: 'technical-r', type: 'technical', x: 7, y: 5, w: 5, h: 4 },
        { i: 'consensus-r', type: 'consensus', x: 7, y: 9, w: 5, h: 3 },
        { i: 'key-metrics-r', type: 'key-metrics', x: 0, y: 12, w: 12, h: 14 },
        { i: 'ratings-r', type: 'ratings', x: 0, y: 26, w: 6, h: 6 },
        { i: 'news-r', type: 'news', x: 6, y: 26, w: 6, h: 6 },
        { i: 'insider-r', type: 'insider', x: 0, y: 32, w: 4, h: 5 },
        { i: 'short-interest-r', type: 'short-interest', x: 4, y: 32, w: 4, h: 4 },
        { i: 'catalysts-r', type: 'catalysts', x: 8, y: 32, w: 4, h: 4 },
        { i: 'risk-r', type: 'risk', x: 0, y: 37, w: 6, h: 5 },
        { i: 'dilution-risk-r', type: 'dilution-risk', x: 6, y: 37, w: 6, h: 5 },
    ],
};

export const FAN_TEMPLATES: CanvasTemplate[] = [
    { id: 'default', name: 'Overview', description: 'Snapshot: chart, key metrics, consensus & technicals', layout: FAN_DEFAULT_LAYOUT },
    { id: 'daytrader', name: 'Trading', description: 'Price action, technicals, short interest & flow', layout: DAYTRADER_LAYOUT },
    { id: 'value', name: 'Fundamentals', description: 'Key metrics deep-dive, ratings & risk', layout: VALUE_LAYOUT },
    { id: 'earnings', name: 'Earnings', description: 'Consensus, catalysts, estimates & reaction', layout: EARNINGS_LAYOUT },
    { id: 'research', name: 'Research', description: 'Everything — full analyst workspace', layout: RESEARCH_LAYOUT },
];

export const FAN_CONFIG: CanvasConfig = {
    manifest: { id: 'fan', widgets: FAN_WIDGETS },
    defaultLayout: FAN_DEFAULT_LAYOUT,
    templates: FAN_TEMPLATES,
    cols: 12,
    rowHeight: 28,
};
