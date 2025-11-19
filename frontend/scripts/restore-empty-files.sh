#!/bin/bash
# Script para restaurar archivos vacíos con stubs mínimos válidos

set -e

FRONTEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FRONTEND_DIR"

echo "🔧 Restaurando archivos vacíos..."

# Función para crear archivo si está vacío
restore_if_empty() {
    local file="$1"
    local content="$2"
    
    if [ ! -f "$file" ] || [ $(wc -l < "$file" 2>/dev/null || echo 0) -le 1 ]; then
        echo "  ✓ Restaurando: $file"
        mkdir -p "$(dirname "$file")"
        echo "$content" > "$file"
    fi
}

# ============================================================================
# CRITICAL NEXT.JS FILES
# ============================================================================

restore_if_empty "app/layout.tsx" 'import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tradeul Scanner",
  description: "Real-time market scanner",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}'

restore_if_empty "app/loading.tsx" 'export default function Loading() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-slate-500">Cargando...</div>
    </div>
  );
}'

restore_if_empty "app/error.tsx" '\'use client\';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <h2 className="text-xl font-bold text-red-600 mb-4">Algo salió mal</h2>
      <button
        onClick={reset}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Intentar de nuevo
      </button>
    </div>
  );
}'

restore_if_empty "app/global-error.tsx" '\'use client\';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body>
        <div className="flex flex-col items-center justify-center min-h-screen">
          <h2 className="text-xl font-bold text-red-600 mb-4">Error Global</h2>
          <button onClick={reset} className="px-4 py-2 bg-blue-600 text-white rounded">
            Reiniciar
          </button>
        </div>
      </body>
    </html>
  );
}'

restore_if_empty "app/not-found.tsx" 'export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h2 className="text-2xl font-bold mb-4">404 - Página no encontrada</h2>
        <p className="text-slate-600">La página que buscas no existe.</p>
      </div>
    </div>
  );
}'

restore_if_empty "app/page.tsx" 'export default function HomePage() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-4">Tradeul Scanner</h1>
        <p className="text-slate-600">Redirigiendo...</p>
      </div>
    </div>
  );
}'

# ============================================================================
# DASHBOARD LAYOUT
# ============================================================================

restore_if_empty "app/(dashboard)/layout.tsx" 'export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}'

restore_if_empty "app/(dashboard)/scanner/layout.tsx" 'export default function ScannerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}'

# ============================================================================
# PAGES
# ============================================================================

restore_if_empty "app/(dashboard)/settings/page.tsx" '\'use client\';

export default function SettingsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Configuración</h1>
      <p className="text-slate-600">Página de configuración en desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/alerts/page.tsx" '\'use client\';

export default function AlertsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Alertas</h1>
      <p className="text-slate-600">Página de alertas en desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/analytics/page.tsx" '\'use client\';

export default function AnalyticsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Analíticas</h1>
      <p className="text-slate-600">Página de analíticas en desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/dilution-tracker/page.tsx" '\'use client\';

export default function DilutionTrackerPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Dilution Tracker</h1>
      <p className="text-slate-600">Página en desarrollo...</p>
    </div>
  );
}'

# ============================================================================
# COMPONENTS
# ============================================================================

restore_if_empty "components/layout/AppShell.tsx" '\'use client\';

export default function AppShell({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-white">{children}</div>;
}'

restore_if_empty "components/layout/PageContainer.tsx" '\'use client\';

export default function PageContainer({ children }: { children: React.ReactNode }) {
  return <div className="container mx-auto px-4 py-6">{children}</div>;
}'

restore_if_empty "components/layout/Sidebar.tsx" '\'use client\';

export default function Sidebar() {
  return (
    <aside className="w-64 bg-slate-100 p-4">
      <nav>
        <ul className="space-y-2">
          <li><a href="/scanner" className="text-blue-600">Scanner</a></li>
        </ul>
      </nav>
    </aside>
  );
}'

restore_if_empty "components/scanner/TickerMetadataModal.tsx" '\'use client\';

interface TickerMetadataModalProps {
  symbol: string | null;
  tickerData: any;
  isOpen: boolean;
  onClose: () => void;
}

export default function TickerMetadataModal({
  symbol,
  tickerData,
  isOpen,
  onClose,
}: TickerMetadataModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full">
        <h2 className="text-xl font-bold mb-4">{symbol}</h2>
        <pre className="text-sm overflow-auto">{JSON.stringify(tickerData, null, 2)}</pre>
        <button onClick={onClose} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded">
          Cerrar
        </button>
      </div>
    </div>
  );
}'

restore_if_empty "components/table/BaseDataTable.tsx" '\'use client\';

export default function BaseDataTable() {
  return <div>BaseDataTable - En desarrollo</div>;
}'

restore_if_empty "components/table/MarketTableLayout.tsx" '\'use client\';

interface MarketTableLayoutProps {
  title: string;
  isLive?: boolean;
  count?: number;
  sequence?: number;
  lastUpdateTime?: Date | null;
  rightActions?: React.ReactNode;
  children?: React.ReactNode;
}

export function MarketTableLayout({
  title,
  isLive = false,
  count,
  sequence,
  lastUpdateTime,
  rightActions,
  children,
}: MarketTableLayoutProps) {
  return (
    <div className="border border-slate-200 rounded-lg">
      <div className="p-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h3 className="font-bold text-lg">{title}</h3>
          {count !== undefined && <span className="text-sm text-slate-600">{count} tickers</span>}
        </div>
        {rightActions}
      </div>
      {children}
    </div>
  );
}'

restore_if_empty "components/table/TableSettings.tsx" '\'use client\';

export function TableSettings({ table }: { table: any }) {
  return <div className="text-sm text-slate-600">⚙️</div>;
}'

restore_if_empty "components/ui/ResizableTable.tsx" '\'use client\';

export default function ResizableTable() {
  return <div>ResizableTable - En desarrollo</div>;
}'

# ============================================================================
# HOOKS & UTILS
# ============================================================================

restore_if_empty "hooks/useWebSocket.ts" '// Legacy hook - usar useRxWebSocket en su lugar
export function useWebSocket(url: string) {
  return {
    isConnected: false,
    send: () => {},
    messages: [],
  };
}'

restore_if_empty "lib/formatters.ts" 'export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("es-ES").format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `$${value.toFixed(2)}`;
}

export function formatRVOL(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toFixed(2);
}'

restore_if_empty "lib/types.ts" 'export interface Ticker {
  symbol: string;
  rank?: number;
  price?: number;
  change?: number;
  changePercent?: number;
  volume?: number;
  rvol?: number;
  [key: string]: any;
}

export interface WebSocketMessage {
  type: "snapshot" | "delta" | "aggregate" | "connected";
  list?: string;
  sequence?: number;
  rows?: Ticker[];
  deltas?: any[];
  symbol?: string;
  data?: any;
  connection_id?: string;
}'

restore_if_empty "lib/models/index.ts" 'export * from "./types";'

restore_if_empty "lib/dilution-api.ts" 'export async function getDilutionData(symbol: string) {
  return null;
}'

restore_if_empty "lib/filings-utils.ts" 'export function parseFiling(data: any) {
  return null;
}'

restore_if_empty "shared/table/dataAdapter.ts" 'export function adaptData(data: any[]) {
  return data;
}'

restore_if_empty "contexts/FloatingWindowContext.tsx" '\'use client\';

import { createContext, useContext } from "react";

const FloatingWindowContext = createContext<any>(null);

export function FloatingWindowProvider({ children }: { children: React.ReactNode }) {
  return (
    <FloatingWindowContext.Provider value={{}}>
      {children}
    </FloatingWindowContext.Provider>
  );
}

export function useFloatingWindow() {
  return useContext(FloatingWindowContext);
}'

restore_if_empty "components/floating-window/index.ts" 'export * from "./FloatingWindow";'

restore_if_empty "components/floating-window/FloatingWindow.tsx" '\'use client\';

export default function FloatingWindow() {
  return null;
}'

restore_if_empty "components/floating-window/FloatingWindowManager.tsx" '\'use client\';

export default function FloatingWindowManager() {
  return null;
}'

restore_if_empty "components/floating-window/DilutionTrackerContent.tsx" '\'use client\';

export default function DilutionTrackerContent() {
  return null;
}'

# ============================================================================
# DILUTION TRACKER COMPONENTS
# ============================================================================

restore_if_empty "app/(dashboard)/dilution-tracker/_components/FilingsTable.tsx" '\'use client\';

export default function FilingsTable() {
  return (
    <div className="p-4">
      <h3 className="font-bold mb-2">Filings Table</h3>
      <p className="text-sm text-slate-600">En desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/dilution-tracker/_components/FinancialsTable.tsx" '\'use client\';

export default function FinancialsTable() {
  return (
    <div className="p-4">
      <h3 className="font-bold mb-2">Financials Table</h3>
      <p className="text-sm text-slate-600">En desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/dilution-tracker/_components/SECDilutionSection.tsx" '\'use client\';

export default function SECDilutionSection() {
  return (
    <div className="p-4">
      <h3 className="font-bold mb-2">SEC Dilution Section</h3>
      <p className="text-sm text-slate-600">En desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/dilution-tracker/_components/CashRunwayChart.tsx" '\'use client\';

export default function CashRunwayChart() {
  return (
    <div className="p-4">
      <h3 className="font-bold mb-2">Cash Runway Chart</h3>
      <p className="text-sm text-slate-600">En desarrollo...</p>
    </div>
  );
}'

restore_if_empty "app/(dashboard)/dilution-tracker/_components/DilutionHistoryChart.tsx" '\'use client\';

export default function DilutionHistoryChart() {
  return (
    <div className="p-4">
      <h3 className="font-bold mb-2">Dilution History Chart</h3>
      <p className="text-sm text-slate-600">En desarrollo...</p>
    </div>
  );
}'

restore_if_empty "tailwind.config.ts" 'import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;'

echo ""
echo "✅ Archivos restaurados correctamente!"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Revisa los archivos restaurados"
echo "   2. Si tienes un repo en GitHub, inicializa git:"
echo "      git init"
echo "      git remote add origin <tu-repo-url>"
echo "      git add ."
echo "      git commit -m 'Restore empty files and add V2 tables'"
echo "   3. Para sincronizar con GitHub sin perder cambios locales:"
echo "      git fetch origin"
echo "      git merge origin/main --allow-unrelated-histories"
echo ""

