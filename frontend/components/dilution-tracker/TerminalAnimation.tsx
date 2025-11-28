'use client';

import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface AnalysisPhase {
  id: string;
  label: string;
  icon: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  detail?: string;
}

interface TerminalAnimationProps {
  ticker: string;
  isActive: boolean;
  progress: number;
  currentPhase: string;
  phases?: AnalysisPhase[];
  onComplete?: () => void;
}

const DEFAULT_PHASES: AnalysisPhase[] = [
  { id: 'init', label: 'Initializing analysis engine', icon: '⚡', status: 'pending' },
  { id: 'validating', label: 'Validating ticker in market universe', icon: '🔍', status: 'pending' },
  { id: 'fetching_metadata', label: 'Retrieving company metadata', icon: '📊', status: 'pending' },
  { id: 'fetching_financials', label: 'Downloading financial statements', icon: '📈', status: 'pending' },
  { id: 'fetching_holders', label: 'Scanning institutional holders', icon: '🏦', status: 'pending' },
  { id: 'fetching_filings', label: 'Indexing SEC EDGAR filings', icon: '📁', status: 'pending' },
  { id: 'analyzing_sec', label: 'Deep regulatory analysis', icon: '🔬', status: 'pending' },
  { id: 'calculating_risk', label: 'Computing risk metrics', icon: '⚠️', status: 'pending' },
];

const PHASE_ORDER = [
  'init', 'validating', 'fetching_metadata', 'fetching_financials',
  'fetching_holders', 'fetching_filings', 'analyzing_sec', 'calculating_risk', 'completed'
];

export default function TerminalAnimation({
  ticker,
  isActive,
  progress,
  currentPhase,
  phases: externalPhases,
  onComplete
}: TerminalAnimationProps) {
  const [phases, setPhases] = useState<AnalysisPhase[]>(DEFAULT_PHASES);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement>(null);
  const [showCursor, setShowCursor] = useState(true);

  // Blinking cursor effect
  useEffect(() => {
    const interval = setInterval(() => setShowCursor(prev => !prev), 500);
    return () => clearInterval(interval);
  }, []);

  // Update phases based on currentPhase
  useEffect(() => {
    if (!currentPhase) return;

    const currentIndex = PHASE_ORDER.indexOf(currentPhase);
    
    setPhases(prev => prev.map((phase, idx) => {
      const phaseIndex = PHASE_ORDER.indexOf(phase.id);
      
      if (phaseIndex < currentIndex) {
        return { ...phase, status: 'completed' };
      } else if (phaseIndex === currentIndex) {
        return { ...phase, status: 'running' };
      }
      return { ...phase, status: 'pending' };
    }));

    // Add terminal line
    const phaseData = DEFAULT_PHASES.find(p => p.id === currentPhase);
    if (phaseData) {
      const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
      setTerminalLines(prev => [
        ...prev.slice(-15), // Keep last 15 lines
        `[${timestamp}] ${phaseData.icon} ${phaseData.label}...`
      ]);
    }

    if (currentPhase === 'completed') {
      setTerminalLines(prev => [
        ...prev,
        `[${new Date().toLocaleTimeString('en-US', { hour12: false })}] ✅ Analysis complete for ${ticker}`
      ]);
      onComplete?.();
    }
  }, [currentPhase, ticker, onComplete]);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalLines]);

  if (!isActive) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="w-full bg-black/95 rounded-lg border border-emerald-500/30 overflow-hidden font-mono text-sm"
    >
      {/* Terminal Header */}
      <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-900/50 to-black border-b border-emerald-500/20">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <span className="text-emerald-400/80 text-xs ml-2">
          tradeul@analysis ~ {ticker}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-emerald-500/60 text-xs">{progress}%</span>
          <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-2 gap-4 p-4">
        {/* Left: Phase Diagram */}
        <div className="space-y-2">
          <div className="text-emerald-500/80 text-xs uppercase tracking-wider mb-3">
            Analysis Pipeline
          </div>
          {phases.map((phase, idx) => (
            <motion.div
              key={phase.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05 }}
              className={`flex items-center gap-3 py-1.5 px-2 rounded transition-all ${
                phase.status === 'running' 
                  ? 'bg-emerald-500/10 border-l-2 border-emerald-500' 
                  : phase.status === 'completed'
                  ? 'opacity-60'
                  : 'opacity-40'
              }`}
            >
              {/* Status indicator */}
              <div className="w-5 h-5 flex items-center justify-center">
                {phase.status === 'completed' ? (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="text-emerald-400"
                  >
                    ✓
                  </motion.span>
                ) : phase.status === 'running' ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full"
                  />
                ) : (
                  <span className="text-gray-600">○</span>
                )}
              </div>
              
              {/* Phase icon and label */}
              <span className="text-lg">{phase.icon}</span>
              <span className={`text-xs ${
                phase.status === 'running' ? 'text-emerald-400' :
                phase.status === 'completed' ? 'text-gray-400' : 'text-gray-600'
              }`}>
                {phase.label}
              </span>
            </motion.div>
          ))}
        </div>

        {/* Right: Terminal Output */}
        <div className="flex flex-col">
          <div className="text-emerald-500/80 text-xs uppercase tracking-wider mb-3">
            System Output
          </div>
          <div
            ref={terminalRef}
            className="flex-1 bg-black/50 rounded border border-gray-800 p-3 max-h-64 overflow-y-auto scrollbar-thin scrollbar-thumb-emerald-500/20"
          >
            <div className="text-emerald-400/80 text-xs mb-2">
              $ analyze --ticker {ticker} --deep
            </div>
            <AnimatePresence mode="popLayout">
              {terminalLines.map((line, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-gray-400 text-xs leading-relaxed"
                >
                  {line}
                </motion.div>
              ))}
            </AnimatePresence>
            {/* Blinking cursor */}
            <span className={`inline-block w-2 h-4 bg-emerald-500 ${showCursor ? 'opacity-100' : 'opacity-0'}`} />
          </div>
        </div>
      </div>

      {/* Footer Stats */}
      <div className="px-4 py-2 bg-black/50 border-t border-emerald-500/10 flex items-center justify-between text-xs">
        <div className="flex items-center gap-4">
          <span className="text-gray-500">
            <span className="text-emerald-500">◉</span> Connected
          </span>
          <span className="text-gray-500">
            Sources: FMP, SEC EDGAR, Polygon
          </span>
        </div>
        <div className="text-gray-500">
          {currentPhase === 'completed' ? (
            <span className="text-emerald-400">Analysis Complete</span>
          ) : (
            <span>Processing...</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

