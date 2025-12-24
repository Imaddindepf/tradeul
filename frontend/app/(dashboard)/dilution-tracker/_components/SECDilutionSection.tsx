"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ExternalLink,
  Calendar,
  DollarSign,
  Percent,
  Info,
  BadgeDollarSign,
  CheckCircle2
} from "lucide-react";
import {
  getSECDilutionProfile,
  refreshSECDilutionProfile,
  getRiskRatings,
  type SECDilutionProfileResponse,
  type Warrant,
  type ATMOffering,
  type ShelfRegistration,
  type CompletedOffering,
  type ConvertibleNote,
  type DilutionRiskRatings,
  type RiskLevel
} from "@/lib/dilution-api";

// Fases del análisis SEC
const ANALYSIS_PHASES = [
  { id: 'init', label: 'Initializing analysis engine', icon: '⚡', duration: 500 },
  { id: 'filings', label: 'Scanning SEC EDGAR filings', icon: '📁', duration: 1000 },
  { id: 'download', label: 'Downloading regulatory documents', icon: '📥', duration: 2000 },
  { id: 'parse', label: 'Parsing filing contents', icon: '📄', duration: 1500 },
  { id: 'extract', label: 'Extracting dilution instruments', icon: '🔍', duration: 2000 },
  { id: 'analyze', label: 'Deep analysis of securities', icon: '🔬', duration: 3000 },
  { id: 'warrants', label: 'Processing warrant data', icon: '📊', duration: 1000 },
  { id: 'atm', label: 'Analyzing ATM offerings', icon: '💹', duration: 1000 },
  { id: 'shelf', label: 'Evaluating shelf registrations', icon: '📋', duration: 1000 },
  { id: 'risk', label: 'Computing risk metrics', icon: '⚠️', duration: 500 },
  { id: 'complete', label: 'Analysis complete', icon: '✓', duration: 0 },
];

interface SECDilutionSectionProps {
  ticker: string;
  /** Datos pre-cargados desde caché (si disponibles) */
  cachedData?: SECDilutionProfileResponse | null;
  /** Si hay un job de scraping en progreso */
  jobPending?: boolean;
  /** Status del job */
  jobStatus?: 'queued' | 'processing' | 'none' | 'unknown';
  /** Callback cuando se cargan datos (compatibilidad) */
  onDataLoaded?: () => void;
  /** Callback para solicitar refresh */
  onRefreshRequest?: () => void;
}

// Terminal Animation Component
function SECAnalysisTerminal({
  ticker,
  isActive,
  onComplete
}: {
  ticker: string;
  isActive: boolean;
  onComplete: () => void;
}) {
  const [currentPhaseIdx, setCurrentPhaseIdx] = useState(0);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [showCursor, setShowCursor] = useState(true);
  const terminalRef = useRef<HTMLDivElement>(null);
  const completedRef = useRef(false);

  // Blinking cursor
  useEffect(() => {
    const interval = setInterval(() => setShowCursor(prev => !prev), 500);
    return () => clearInterval(interval);
  }, []);

  // Progress through phases
  useEffect(() => {
    if (!isActive || completedRef.current) return;

    const phase = ANALYSIS_PHASES[currentPhaseIdx];
    if (!phase) return;

    // Add terminal line
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    setTerminalLines(prev => [
      ...prev.slice(-12),
      `[${timestamp}] ${phase.icon} ${phase.label}...`
    ]);

    if (phase.id === 'complete') {
      completedRef.current = true;
      setTimeout(onComplete, 1000);
      return;
    }

    // Move to next phase
    const timer = setTimeout(() => {
      setCurrentPhaseIdx(prev => Math.min(prev + 1, ANALYSIS_PHASES.length - 1));
    }, phase.duration);

    return () => clearTimeout(timer);
  }, [currentPhaseIdx, isActive, onComplete]);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalLines]);

  // Reset when ticker changes
  useEffect(() => {
    setCurrentPhaseIdx(0);
    setTerminalLines([]);
    completedRef.current = false;
  }, [ticker]);

  if (!isActive) return null;

  const progress = Math.round((currentPhaseIdx / (ANALYSIS_PHASES.length - 1)) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="w-full bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl border border-emerald-500/30 overflow-hidden font-mono text-sm shadow-2xl"
    >
      {/* Terminal Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-black/40 border-b border-emerald-500/20">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div className="w-3 h-3 rounded-full bg-green-500" />
        </div>
        <span className="text-emerald-400 text-xs ml-2 font-semibold">
          SEC DILUTION ANALYSIS — {ticker}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-emerald-500 text-xs font-bold">{progress}%</span>
          <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 p-4">
        {/* Left: Phase Diagram */}
        <div className="space-y-1.5">
          <div className="text-emerald-500/80 text-xs uppercase tracking-wider mb-2 font-bold">
            Pipeline Status
          </div>
          {ANALYSIS_PHASES.slice(0, -1).map((phase, idx) => {
            const status = idx < currentPhaseIdx ? 'completed' : idx === currentPhaseIdx ? 'running' : 'pending';
            return (
              <motion.div
                key={phase.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.03 }}
                className={`flex items-center gap-2 py-1 px-2 rounded text-xs transition-all ${status === 'running'
                  ? 'bg-emerald-500/20 border-l-2 border-emerald-400'
                  : status === 'completed'
                    ? 'opacity-50'
                    : 'opacity-30'
                  }`}
              >
                <div className="w-4 h-4 flex items-center justify-center">
                  {status === 'completed' ? (
                    <span className="text-emerald-400">✓</span>
                  ) : status === 'running' ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                      className="w-3 h-3 border-2 border-emerald-400 border-t-transparent rounded-full"
                    />
                  ) : (
                    <span className="text-slate-600">○</span>
                  )}
                </div>
                <span className="text-sm">{phase.icon}</span>
                <span className={status === 'running' ? 'text-emerald-300' : 'text-slate-400'}>
                  {phase.label}
                </span>
              </motion.div>
            );
          })}
        </div>

        {/* Right: Terminal Output */}
        <div className="flex flex-col">
          <div className="text-emerald-500/80 text-xs uppercase tracking-wider mb-2 font-bold">
            System Log
          </div>
          <div
            ref={terminalRef}
            className="flex-1 bg-black/50 rounded border border-slate-700 p-3 max-h-56 overflow-y-auto"
          >
            <div className="text-cyan-400 text-xs mb-2">
              $ sec-analyze --ticker {ticker} --deep --extract-all
            </div>
            <AnimatePresence mode="popLayout">
              {terminalLines.map((line, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-slate-300 text-xs leading-relaxed"
                >
                  {line}
                </motion.div>
              ))}
            </AnimatePresence>
            <span className={`inline-block w-2 h-4 bg-emerald-500 ml-1 ${showCursor ? 'opacity-100' : 'opacity-0'}`} />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-black/30 border-t border-emerald-500/10 flex items-center justify-between text-xs">
        <div className="flex items-center gap-4 text-slate-400">
          <span><span className="text-emerald-500">◉</span> Connected to SEC EDGAR</span>
          <span>Sources: 10-K, 10-Q, 8-K, S-1, S-3, DEF 14A</span>
        </div>
        <div className="text-slate-500">
          {currentPhaseIdx >= ANALYSIS_PHASES.length - 1 ? (
            <span className="text-emerald-400 font-semibold">✓ Analysis Complete</span>
          ) : (
            <span>Analyzing securities...</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// Risk Rating Tag Component
function RiskRatingTag({ label, level, tooltip }: { label: string; level: RiskLevel; tooltip?: string }) {
  const colorMap: Record<RiskLevel, string> = {
    Low: 'bg-green-100 text-green-700 border-green-200',
    Medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    High: 'bg-red-100 text-red-700 border-red-200',
    Unknown: 'bg-slate-100 text-slate-500 border-slate-200'
  };
  
  return (
    <div className="flex items-center gap-2" title={tooltip}>
      <span className="text-sm text-slate-600">{label}</span>
      <span className={`px-3 py-1 text-xs font-medium rounded-full border ${colorMap[level]}`}>
        {level}
      </span>
    </div>
  );
}

export function SECDilutionSection({
  ticker,
  cachedData,
  jobPending = false,
  jobStatus = 'none',
  onDataLoaded,
  onRefreshRequest
}: SECDilutionSectionProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [riskRatings, setRiskRatings] = useState<DilutionRiskRatings | null>(null);

  // Usar datos pasados como prop
  const data = cachedData;
  
  // Use risk_assessment from profile if available, fallback to separate endpoint
  useEffect(() => {
    // First, try to use risk_assessment from the profile response
    if (data?.risk_assessment) {
      console.log('Using risk_assessment from profile:', data.risk_assessment);
      setRiskRatings(data.risk_assessment as DilutionRiskRatings);
    } else if (ticker) {
      // Fallback: fetch from separate endpoint
      console.log('Fetching risk ratings from separate endpoint for', ticker);
      getRiskRatings(ticker).then(setRiskRatings).catch((err) => {
        console.error('Risk ratings not available for', ticker, err);
      });
    }
  }, [ticker, data?.risk_assessment]);

  // Notificar al padre cuando hay datos (compatibilidad)
  useEffect(() => {
    if (data) {
        onDataLoaded?.();
      }
  }, [data, onDataLoaded]);

  const handleRefresh = () => {
    setRefreshing(true);
    onRefreshRequest?.();
    // El padre controlará el refresh
  };

  // Estado: Job en progreso (analyzing)
  if (jobPending || jobStatus === 'queued' || jobStatus === 'processing') {
    return (
      <div className="border border-slate-200 rounded-lg p-4">
        <h4 className="font-medium text-slate-700 mb-1">SEC Analysis in Progress</h4>
        <p className="text-sm text-slate-500">
          Deep analysis of SEC filings is running in background.
        </p>
        <p className="text-xs text-slate-400 mt-2">
          Status: {jobStatus === 'queued' ? 'Queued' : 'Processing'}
        </p>
      </div>
    );
  }

  // Estado: Sin datos y sin job
  if (!data) {
    return (
      <div className="border border-slate-200 rounded-lg p-4">
        <h4 className="font-medium text-slate-700 mb-1">SEC Data Unavailable</h4>
        <p className="text-sm text-slate-500">
          No cached dilution data available for this ticker.
        </p>
        {onRefreshRequest && (
          <button
            onClick={handleRefresh}
            className="mt-3 px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded hover:bg-slate-50 transition-colors"
          >
            Request Full Analysis
          </button>
        )}
      </div>
    );
  }

  const { profile, dilution_analysis, cached, cache_age_seconds, is_spac } = data;

  // Check if there's any data
  const hasData =
    profile.warrants.length > 0 ||
    profile.atm_offerings.length > 0 ||
    profile.shelf_registrations.length > 0 ||
    profile.completed_offerings.length > 0;

  if (!hasData) {
    return (
      <div className="border border-slate-200 rounded-lg p-4">
        <h4 className="font-medium text-slate-700 mb-1">Clean Dilution Profile</h4>
        <p className="text-sm text-slate-500">
          No active warrants, ATM offerings, or shelf registrations found.
            </p>
        <p className="text-xs text-slate-400 mt-2">
              Last checked: {new Date(profile.metadata.last_scraped_at).toLocaleString()}
            </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Risk Ratings Tags */}
      <div className="border border-slate-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-slate-700">Dilution Risk</h3>
            {is_spac && <span className="text-xs text-slate-400">(SPAC)</span>}
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            {refreshing ? '...' : 'Refresh'}
          </button>
        </div>

        {/* Risk Rating Tags - Similar to DilutionTracker */}
        <div className="flex flex-wrap items-center gap-4">
          <RiskRatingTag 
            label="Overall Risk" 
            level={riskRatings?.overall_risk || 'Unknown'}
            tooltip="Combined assessment of all dilution risk factors"
          />
          <RiskRatingTag 
            label="Offering Ability" 
            level={riskRatings?.offering_ability || 'Unknown'}
            tooltip="Ability to conduct discounted offerings (shelf capacity)"
          />
          <RiskRatingTag 
            label="Overhead Supply" 
            level={riskRatings?.overhead_supply || 'Unknown'}
            tooltip={`Potential dilution: ${riskRatings?.details?.overhead_supply?.dilution_pct?.toFixed(1) || '?'}% of O/S`}
          />
          <RiskRatingTag 
            label="Historical" 
            level={riskRatings?.historical || 'Unknown'}
            tooltip={`O/S change 3yr: ${riskRatings?.details?.historical?.increase_pct?.toFixed(1) || '?'}%`}
          />
          <RiskRatingTag 
            label="Cash Need" 
            level={riskRatings?.cash_need || 'Unknown'}
            tooltip={`Runway: ${riskRatings?.details?.cash_need?.runway_months?.toFixed(1) || '?'} months`}
          />
        </div>

        {/* Quick Stats */}
        <div className="flex items-center gap-6 mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500">
          <span>
            Total Potential: <strong className="text-slate-700">{Number(dilution_analysis.total_potential_dilution_pct).toFixed(1)}%</strong>
            <span className="text-slate-400 ml-1">({(Number(dilution_analysis.total_potential_new_shares) / 1_000_000).toFixed(1)}M shares)</span>
          </span>
          <span>
            Price: <strong className="text-slate-700">${profile.current_price ? Number(profile.current_price).toFixed(2) : 'N/A'}</strong>
          </span>
        </div>
      </div>

      {/* Cards Grid - Máximo 2 columnas */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Warrants */}
        {profile.warrants.length > 0 && (
          <WarrantsCard warrants={profile.warrants} />
        )}

        {/* ATM Offerings */}
        {profile.atm_offerings.length > 0 && (
          <ATMCard offerings={profile.atm_offerings} />
        )}

        {/* Shelf Registrations */}
        {profile.shelf_registrations.length > 0 && (
          <ShelfCard registrations={profile.shelf_registrations} />
        )}

        {/* Convertible Notes */}
        {profile.convertible_notes && profile.convertible_notes.length > 0 && (
          <ConvertibleNotesCard notes={profile.convertible_notes} />
        )}
      </div>

      {/* Completed Offerings Table - Full Width */}
      {profile.completed_offerings.length > 0 && (
        <div className="lg:col-span-2">
          <CompletedOfferingsCard offerings={profile.completed_offerings} />
        </div>
      )}

      {/* Metadata Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500 pt-4 border-t border-slate-200">
        <div className="flex items-center gap-4">
          <span>
            Last scraped: {new Date(profile.metadata.last_scraped_at).toLocaleString()}
          </span>
          {profile.metadata.source_filings.length > 0 && (
            <span>
              {profile.metadata.source_filings.length} filings analyzed
            </span>
          )}
        </div>
        {cached && cache_age_seconds !== undefined && (
          <span className="text-slate-400">
            Cached ({cache_age_seconds < 3600 ? `${Math.floor(cache_age_seconds / 60)}m` : `${Math.floor(cache_age_seconds / 3600)}h`} old)
          </span>
        )}
      </div>
    </div>
  );
}

// =====================================================
// EDUCATIONAL TOOLTIPS
// =====================================================

function EducationalTooltip({ type }: { type: 'warrant' | 'atm' | 'shelf' | 'completed' | 'convertible' }) {
  const tooltips = {
    warrant: {
      title: "Warrants Outstanding",
      description: "Right to purchase shares at a fixed exercise price before expiration",
      impact: "🔴 Immediate dilution when exercised",
      filing: "Found in: 10-K, 10-Q, 424B5, S-1"
    },
    atm: {
      title: "At-The-Market Offering (424B5)",
      description: "Company can issue shares on the open market anytime up to $ amount",
      impact: "🟡 Low immediate impact - Used over time",
      filing: "Filed after shelf receives EFFECT"
    },
    shelf: {
      title: "Shelf Registration (S-3/S-1)",
      description: "Allows company to raise funds over next 3 years up to registered amount",
      impact: "🟢 No immediate impact until used",
      filing: "Requires EFFECT before use"
    },
    completed: {
      title: "Completed Offerings",
      description: "Historical offerings that have been priced and closed",
      impact: "✅ Already executed - Past dilution",
      filing: "Disclosed in 424B5, 8-K, 10-Q"
    },
    convertible: {
      title: "Convertible Notes",
      description: "Debt that can be converted to equity at a fixed conversion price",
      impact: "🔴 Dilution when converted to shares",
      filing: "Found in: 10-K, 10-Q, 8-K, S-1"
    }
  };

  const tooltip = tooltips[type];
  const [show, setShow] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors"
        type="button"
      >
        <Info className="h-3.5 w-3.5" />
      </button>

      {show && (
        <div className="absolute z-50 left-0 top-full mt-1 w-72 bg-slate-900 text-white text-xs rounded-lg shadow-xl p-3 pointer-events-none">
          <div className="font-semibold mb-1">{tooltip.title}</div>
          <div className="text-slate-300 mb-2">{tooltip.description}</div>
          <div className="text-slate-400 mb-1">{tooltip.impact}</div>
          <div className="text-slate-500 text-[10px]">{tooltip.filing}</div>
          {/* Arrow */}
          <div className="absolute -top-1 left-4 w-2 h-2 bg-slate-900 transform rotate-45" />
        </div>
      )}
    </div>
  );
}

// =====================================================
// WARRANTS CARD (Formato Vertical Detallado)
// =====================================================

function WarrantsCard({ warrants }: { warrants: Warrant[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {warrants.map((warrant, idx) => {
        const seriesName = warrant.series_name || (warrant.issue_date 
          ? `${new Date(warrant.issue_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} Warrants`
          : 'Warrants');
        
        // Helper para formatear fechas completas (YYYY-MM-DD)
        const formatDate = (dateStr?: string) => {
          if (!dateStr) return '—';
          try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' });
          } catch { return dateStr; }
        };

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header */}
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-slate-700">{seriesName}</h3>
                {warrant.is_registered && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded font-medium">
                    {warrant.registration_type || 'EDGAR'}
                  </span>
                )}
                {warrant.is_prefunded && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded font-medium">
                    PRE-FUNDED
                  </span>
                )}
              </div>
              <EducationalTooltip type="warrant" />
            </div>

            {/* Grid Compacto 2 Columnas */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Remaining Warrants Outstanding:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {(warrant.remaining || warrant.outstanding) ? Number(warrant.remaining || warrant.outstanding).toLocaleString() : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Exercise Price:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {warrant.exercise_price ? `$${Number(warrant.exercise_price).toFixed(2)}` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Total Warrants Issued:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {(warrant.total_issued || warrant.potential_new_shares) ? Number(warrant.total_issued || warrant.potential_new_shares).toLocaleString() : '—'}
                  </span>
                </div>
                {warrant.known_owners && (
                  <div>
                    <span className="text-slate-500">Known Owners:</span>
                    <span className="ml-2 text-slate-900">{warrant.known_owners}</span>
                  </div>
                )}
                {warrant.underwriter_agent && (
                  <div>
                    <span className="text-slate-500">Underwriter/Placement Agent:</span>
                    <span className="ml-2 text-slate-900">{warrant.underwriter_agent}</span>
                  </div>
                )}
                {warrant.price_protection && warrant.price_protection !== 'None' && (
                  <div>
                    <span className="text-slate-500">Price Protection:</span>
                    <span className="ml-2 text-slate-900">{warrant.price_protection}</span>
                  </div>
                )}
                {warrant.pp_clause && (
                  <div className="col-span-2">
                    <span className="text-slate-500">PP Clause:</span>
                    <span className="ml-2 text-slate-700 text-[11px]">{warrant.pp_clause}</span>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Issue Date:</span>
                  <span className="ml-2 text-slate-900">{formatDate(warrant.issue_date)}</span>
                </div>
                {warrant.exercisable_date && (
                <div>
                    <span className="text-slate-500">Exercisable Date:</span>
                    <span className="ml-2 text-slate-900">{formatDate(warrant.exercisable_date)}</span>
                </div>
                )}
                <div>
                  <span className="text-slate-500">Expiration Date:</span>
                  <span className="ml-2 text-slate-900">{formatDate(warrant.expiration_date)}</span>
                </div>
                {warrant.last_update_date && (
                  <div>
                    <span className="text-slate-500">Last Update Date:</span>
                    <span className="ml-2 text-slate-900">{formatDate(warrant.last_update_date)}</span>
                  </div>
                )}
                {warrant.has_cashless_exercise && (
                  <div>
                    <span className="text-slate-500">Cashless Exercise:</span>
                    <span className="ml-2 text-green-600 font-medium">Yes</span>
                  </div>
                )}
                {warrant.notes && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Notes:</span>
                    <span className="ml-2 text-slate-700">{warrant.notes}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// ATM OFFERINGS CARD (Formato Vertical Detallado)
// =====================================================

function ATMCard({ offerings }: { offerings: ATMOffering[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {offerings.map((offering, idx) => {
        const filingDate = offering.filing_date ? new Date(offering.filing_date) : null;
        const title = filingDate
          ? `${filingDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} ATM`
          : 'ATM Offering';

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header */}
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-700">{title}</h3>
              <EducationalTooltip type="atm" />
            </div>

            {/* Grid Compacto */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Total Capacity:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.total_capacity ? `$${(Number(offering.total_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Remaining:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.remaining_capacity ? `$${(Number(offering.remaining_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Potential Shares:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {offering.potential_shares_at_current_price ? `${(Number(offering.potential_shares_at_current_price) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Filing Date:</span>
                  <span className="ml-2 text-slate-900">
                    {offering.filing_date ? new Date(offering.filing_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                {offering.placement_agent && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Agent:</span>
                    <span className="ml-2 text-slate-900">{offering.placement_agent}</span>
                  </div>
                )}
                {offering.filing_url && (
                  <div className="col-span-2 mt-2">
                    <a
                      href={offering.filing_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      View Filing <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// SHELF REGISTRATIONS CARD (Formato Vertical Detallado)
// =====================================================

function ShelfCard({ registrations }: { registrations: ShelfRegistration[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {registrations.map((shelf, idx) => {
        const filingDate = shelf.filing_date ? new Date(shelf.filing_date) : null;
        const title = filingDate
          ? `${filingDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} Shelf`
          : 'Shelf Registration';

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header */}
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-700">
                {title}
                {shelf.is_baby_shelf && <span className="ml-2 text-xs text-slate-400">(Baby Shelf)</span>}
              </h3>
              <EducationalTooltip type="shelf" />
            </div>

            {/* Grid Compacto */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Registration:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.registration_statement || '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Total Capacity:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.total_capacity ? `$${(Number(shelf.total_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Remaining:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {shelf.remaining_capacity ? `$${(Number(shelf.remaining_capacity) / 1_000_000).toFixed(1)}M` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Filing Date:</span>
                  <span className="ml-2 text-slate-900">
                    {shelf.filing_date ? new Date(shelf.filing_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Expiration:</span>
                  <span className="ml-2 text-slate-900">
                    {shelf.expiration_date ? new Date(shelf.expiration_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : '~3 years'}
                  </span>
                </div>
                {shelf.filing_url && (
                  <div className="col-span-2 mt-2">
                    <a
                      href={shelf.filing_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700"
                    >
                      View Filing <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =====================================================
// COMPLETED OFFERINGS CARD
// =====================================================

function CompletedOfferingsCard({ offerings }: { offerings: CompletedOffering[] }) {
  // Sort by date (most recent first)
  const sortedOfferings = [...offerings].sort((a, b) => {
    if (!a.offering_date || !b.offering_date) return 0;
    return new Date(b.offering_date).getTime() - new Date(a.offering_date).getTime();
  });

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <h4 className="text-sm font-bold text-slate-900">Completed Offerings</h4>
          <span className="text-xs font-medium px-2 py-0.5 bg-green-100 text-green-700 rounded">
            {offerings.length}
          </span>
        </div>
        <EducationalTooltip type="completed" />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="text-left py-2 px-3 text-slate-600 font-semibold">Date</th>
              <th className="text-left py-2 px-3 text-slate-600 font-semibold">Type</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Shares</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Price</th>
              <th className="text-right py-2 px-3 text-slate-600 font-semibold">Amount Raised</th>
            </tr>
          </thead>
          <tbody>
            {sortedOfferings.map((offering, idx) => (
              <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 px-3 text-slate-700 whitespace-nowrap">
                  {offering.offering_date ? new Date(offering.offering_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) : 'N/A'}
                </td>
                <td className="py-2 px-3 text-slate-700">
                  {offering.offering_type || 'N/A'}
                </td>
                <td className="py-2 px-3 text-right font-medium text-slate-900 tabular-nums">
                  {offering.shares_issued ? `${(Number(offering.shares_issued) / 1_000_000).toFixed(2)}M` : 'N/A'}
                </td>
                <td className="py-2 px-3 text-right text-slate-700 tabular-nums">
                  {offering.price_per_share ? `$${Number(offering.price_per_share).toFixed(2)}` : 'N/A'}
                </td>
                <td className="py-2 px-3 text-right font-semibold text-green-600 tabular-nums">
                  {offering.amount_raised ? `$${(Number(offering.amount_raised) / 1_000_000).toFixed(1)}M` : 'N/A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =====================================================
// CONVERTIBLE NOTES CARD
// =====================================================

function ConvertibleNotesCard({ notes }: { notes: ConvertibleNote[] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      {notes.map((note, idx) => {
        const issueDate = note.issue_date ? new Date(note.issue_date) : null;
        const seriesName = note.series_name || (issueDate 
          ? `${issueDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })} Convertible Note`
          : 'Convertible Note');
        
        const isPaid = (note.remaining_principal_amount || 0) === 0 && (note.total_principal_amount || 0) > 0;

        return (
          <div key={idx} className={idx > 0 ? 'border-t border-slate-200' : ''}>
            {/* Header */}
            <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-slate-700">{seriesName}</h3>
                {isPaid && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-green-100 text-green-700 rounded font-medium">
                    PAID
                  </span>
                )}
                {note.is_toxic && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded font-medium">
                    TOXIC
                  </span>
                )}
              </div>
              <EducationalTooltip type="convertible" />
            </div>

            {/* Grid Compacto 2 Columnas */}
            <div className="p-4">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Total Principal:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {note.total_principal_amount ? `$${Number(note.total_principal_amount).toLocaleString()}` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Remaining:</span>
                  <span className={`ml-2 font-semibold ${isPaid ? 'text-green-600' : 'text-slate-900'}`}>
                    {note.remaining_principal_amount !== undefined 
                      ? (isPaid ? '$0 (Paid)' : `$${Number(note.remaining_principal_amount).toLocaleString()}`)
                      : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Conversion Price:</span>
                  <span className="ml-2 font-semibold text-slate-900">
                    {note.conversion_price ? `$${Number(note.conversion_price).toFixed(2)}` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Interest Rate:</span>
                  <span className="ml-2 text-slate-900">
                    {note.interest_rate ? `${Number(note.interest_rate).toFixed(2)}%` : '—'}
                  </span>
                </div>
                {note.remaining_shares_when_converted && note.remaining_shares_when_converted > 0 && (
                  <div>
                    <span className="text-slate-500">Shares if Converted:</span>
                    <span className="ml-2 font-semibold text-amber-600">
                      {Number(note.remaining_shares_when_converted).toLocaleString()}
                    </span>
                  </div>
                )}
                {note.known_owners && (
                  <div>
                    <span className="text-slate-500">Known Owners:</span>
                    <span className="ml-2 text-slate-900">{note.known_owners}</span>
                  </div>
                )}
                {note.underwriter_agent && (
                  <div>
                    <span className="text-slate-500">Underwriter/Placement Agent:</span>
                    <span className="ml-2 text-slate-900">{note.underwriter_agent}</span>
                  </div>
                )}
                {note.price_protection && note.price_protection !== 'None' && (
                  <div>
                    <span className="text-slate-500">Price Protection:</span>
                    <span className={`ml-2 ${note.price_protection.includes('TOXIC') || note.is_toxic ? 'text-red-600 font-semibold' : 'text-slate-900'}`}>
                      {note.price_protection}
                    </span>
                  </div>
                )}
                {note.pp_clause && (
                  <div className="col-span-2">
                    <span className="text-slate-500">PP Clause:</span>
                    <span className="ml-2 text-slate-700 text-[11px]">{note.pp_clause}</span>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Issue Date:</span>
                  <span className="ml-2 text-slate-900">
                    {note.issue_date ? new Date(note.issue_date).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' }) : '—'}
                  </span>
                </div>
                {note.convertible_date && (
                  <div>
                    <span className="text-slate-500">Convertible Date:</span>
                    <span className="ml-2 text-slate-900">
                      {new Date(note.convertible_date).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' })}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Maturity Date:</span>
                  <span className="ml-2 text-slate-900">
                    {note.maturity_date ? new Date(note.maturity_date).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' }) : '—'}
                  </span>
                </div>
                {note.last_update_date && (
                  <div>
                    <span className="text-slate-500">Last Update Date:</span>
                    <span className="ml-2 text-slate-900">
                      {new Date(note.last_update_date).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' })}
                    </span>
                  </div>
                )}
                {note.notes && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Notes:</span>
                    <span className="ml-2 text-slate-700">{note.notes}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

